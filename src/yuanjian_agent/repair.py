from __future__ import annotations

import ast
import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .agent_security.demo import require_feature
from .files import IGNORED_DIRS, iter_text_files
from .models import Finding, FindingCategory, ReviewStatus, ScanResult, SourceSpan
from .secrets import SecretScanner
from .storage import ScanStore


def _ignore_links_and_builds(directory: str, names: list[str]) -> set[str]:
    root = Path(directory)
    ignored = {name for name in names if name in IGNORED_DIRS}
    for name in names:
        try:
            if (root / name).is_symlink():
                ignored.add(name)
        except OSError:
            ignored.add(name)
    return ignored


@dataclass(slots=True)
class ToolEdit:
    relative_path: str
    start: int
    end: int
    replacement: bytes
    patch: str


class AgentRepairPlanner:
    """Build narrow edits for literal Agent Tool lists without executing code."""

    def plan(self, result: ScanResult, finding: Finding) -> ToolEdit | None:
        if (
            finding.category != FindingCategory.TOOL_EXPOSURE
            or finding.confidence < 0.65
            or finding.review_status == ReviewStatus.NEEDS_REVIEW
        ):
            return None
        registration = next(
            (item for item in finding.evidence if item.details.get("evidence_kind") == "registration"),
            None,
        )
        if registration is None:
            return None
        symbol = str(registration.details.get("tool_symbol") or "")
        if not symbol:
            return None
        root = Path(result.source_path).resolve()
        path = (root / registration.source_span.path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return None
        if not path.is_file() or path.suffix.lower() != ".py":
            return None
        try:
            # Decode bytes directly so CRLF offsets remain identical between
            # the original tree and the copied tree on Windows.
            source = path.read_bytes().decode("utf-8")
            tree = ast.parse(source, filename=registration.source_span.path)
        except (OSError, UnicodeError, SyntaxError):
            return None
        candidate = self._literal_element(tree, registration.source_span, symbol)
        if candidate is None:
            return None
        start, end = self._removal_range(source, candidate[0], candidate[1])
        encoded = source.encode("utf-8")
        updated = encoded[:start] + encoded[end:]
        try:
            after = updated.decode("utf-8")
        except UnicodeDecodeError:
            return None
        patch = "".join(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{registration.source_span.path}",
                tofile=f"b/{registration.source_span.path}",
            )
        )
        if not patch:
            return None
        return ToolEdit(registration.source_span.path, start, end, b"", patch)

    @classmethod
    def _literal_element(
        cls,
        tree: ast.Module,
        span: SourceSpan,
        symbol: str,
    ) -> tuple[ast.AST, ast.AST] | None:
        matches: list[tuple[ast.AST, ast.AST]] = []
        wanted = {symbol, symbol.split(".")[-1]}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Call):
                continue
            if not (span.start_line <= getattr(node, "lineno", 0) <= span.end_line):
                continue
            tools_node = next((item.value for item in node.value.keywords if item.arg == "tools"), None)
            if tools_node is None and len(node.value.args) >= 2:
                tools_node = node.value.args[1]
            if not isinstance(tools_node, (ast.List, ast.Tuple, ast.Set)):
                continue
            for element in tools_node.elts:
                name = cls._node_name(element)
                if name in wanted or name.split(".")[-1] in wanted:
                    matches.append((tools_node, element))
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _node_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = AgentRepairPlanner._node_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Call):
            return AgentRepairPlanner._node_name(node.func)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return ""

    @staticmethod
    def _byte_offset(lines: list[str], line: int, column: int) -> int:
        return sum(len(item.encode("utf-8")) for item in lines[: line - 1]) + column

    @classmethod
    def _removal_range(cls, source: str, container: ast.AST, element: ast.AST) -> tuple[int, int]:
        lines = source.splitlines(keepends=True)
        data = source.encode("utf-8")
        start = cls._byte_offset(lines, element.lineno, element.col_offset)
        end = cls._byte_offset(lines, element.end_lineno, element.end_col_offset)
        container_start = cls._byte_offset(lines, container.lineno, container.col_offset)
        container_end = cls._byte_offset(lines, container.end_lineno, container.end_col_offset)
        cursor = end
        while cursor < container_end and data[cursor:cursor + 1] in {b" ", b"\t"}:
            cursor += 1
        if data[cursor:cursor + 1] == b",":
            cursor += 1
            if data[cursor:cursor + 1] == b" ":
                cursor += 1
            return start, cursor
        cursor = start
        while cursor > container_start and data[cursor - 1:cursor] in {b" ", b"\t"}:
            cursor -= 1
        if data[cursor - 1:cursor] == b",":
            cursor -= 1
        return cursor, end


class RepairService:
    def __init__(self, settings: Settings, secret_scanner: SecretScanner) -> None:
        self.settings = settings
        self.store = ScanStore(settings)
        self.secret_scanner = secret_scanner
        self.agent_planner = AgentRepairPlanner()

    def preview(self, result: ScanResult) -> dict:
        require_feature(self.settings, "repair_preview")
        actions = []
        for finding in result.findings:
            tool_edit = self.agent_planner.plan(result, finding)
            is_secret_edit = finding.category == FindingCategory.SECRET and finding.confidence >= 0.7
            actions.append(
                {
                    "finding_id": finding.id,
                    "category": finding.category.value,
                    "location": finding.evidence[0].source_span.path if finding.evidence else "unknown",
                    "remediation": finding.remediation,
                    "automatic": is_secret_edit or tool_edit is not None,
                    "change_kind": (
                        "secret-placeholder"
                        if is_secret_edit
                        else "remove-literal-tool-binding"
                        if tool_edit is not None
                        else "manual-review"
                    ),
                    "patch": tool_edit.patch if tool_edit is not None else "",
                }
            )
        return {
            "scan_id": result.id,
            "actions": actions,
            "safety": "The original project is never modified. Automatic edits are limited to a copied tree.",
        }

    def create_safe_copy(self, result: ScanResult) -> Path:
        require_feature(self.settings, "repair")
        source = Path(result.source_path).resolve()
        target = (self.settings.scans_dir / result.id / "safe_copy").resolve()
        expected_parent = (self.settings.scans_dir / result.id).resolve()
        if target.parent != expected_parent:
            raise ValueError("Safe-copy target is outside the scan workspace")
        if target.exists():
            raise FileExistsError(f"Safe copy already exists: {target}")
        shutil.copytree(source, target, ignore=_ignore_links_and_builds)
        tool_edits: dict[str, list[tuple[ToolEdit, str]]] = {}
        for finding in result.findings:
            edit = self.agent_planner.plan(result, finding)
            if edit is not None:
                tool_edits.setdefault(edit.relative_path, []).append((edit, finding.id))
        applied_tool_findings: set[str] = set()
        for relative_path, edits in tool_edits.items():
            destination = (target / relative_path).resolve()
            try:
                destination.relative_to(target)
            except ValueError:
                continue
            if not destination.is_file():
                continue
            data = destination.read_bytes()
            ranges: set[tuple[int, int]] = set()
            for edit, finding_id in sorted(edits, key=lambda item: item[0].start, reverse=True):
                if (edit.start, edit.end) in ranges or edit.end > len(data):
                    continue
                ranges.add((edit.start, edit.end))
                data = data[:edit.start] + edit.replacement + data[edit.end:]
                applied_tool_findings.add(finding_id)
            destination.write_bytes(data)
        files, _ = iter_text_files(target, self.settings.limits)
        repaired: list[tuple[str, int, str]] = []
        eligible = {
            (evidence.source_span.path, evidence.source_span.start_line, finding.rule_id)
            for finding in result.findings
            if finding.category == FindingCategory.SECRET
            and finding.confidence >= 0.7
            and finding.evidence
            for evidence in finding.evidence
        }
        for file in files:
            original_lines = file.text.splitlines(keepends=True)
            updated_lines = list(original_lines)
            changed = False
            for index, line in enumerate(original_lines):
                replacements_by_span: dict[tuple[int, int], tuple[int, int, str, str]] = {}
                for match in self.secret_scanner.matches(line):
                    if (file.relative_path, index + 1, match.rule_id) not in eligible:
                        continue
                    value_lower = match.value.lower()
                    if any(marker in value_lower for marker in self.secret_scanner.placeholders):
                        continue
                    if match.rule_id == "secret.private-key":
                        continue
                    replacement = "YOUR_SECRET_HERE"
                    value_start = line.find(match.value, match.start, match.end)
                    if value_start < 0:
                        value_start = line.find(match.value)
                    if value_start >= 0:
                        span = (value_start, value_start + len(match.value))
                        replacements_by_span.setdefault(span, (span[0], span[1], replacement, match.rule_id))
                for start, end, replacement, rule_id in sorted(replacements_by_span.values(), reverse=True):
                    updated_lines[index] = updated_lines[index][:start] + replacement + updated_lines[index][end:]
                    repaired.append((file.relative_path, index + 1, rule_id))
                    changed = True
            if changed:
                file.path.write_text("".join(updated_lines), encoding="utf-8")
        manifest_lines = [
            "# 源界 remediation manifest",
            "",
            "This safe copy was generated without modifying the original project.",
            "Secret-like values with high-confidence syntax were replaced by placeholders.",
            "Only high-confidence literal Tool bindings were removed automatically; dynamic bindings require review.",
            "",
            "## Automatic replacements",
            "",
        ]
        manifest_lines.extend(f"- `{path}:{line}` - {rule_id}" for path, line, rule_id in repaired)
        manifest_lines.extend(
            f"- Tool binding removed for Finding `{finding_id}`"
            for finding_id in sorted(applied_tool_findings)
        )
        manifest_lines.extend(["", "## Manual actions", ""])
        for finding in result.findings:
            if finding.category == FindingCategory.TOOL_EXPOSURE and finding.id not in applied_tool_findings:
                manifest_lines.append(f"- {finding.title}: {'; '.join(finding.remediation)}")
        (target / "OPENGUARD_REMEDIATION.md").write_text("\n".join(manifest_lines), encoding="utf-8")
        env_example = target / ".env.example"
        if not env_example.exists():
            names = []
            pattern = re.compile(r"(?i)\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\b")
            for file in files:
                names.extend(pattern.findall(file.text))
            if names:
                env_example.write_text("\n".join(f"{name}=" for name in sorted(set(names))) + "\n", encoding="utf-8")
        result.safe_copy_path = str(target)
        self.store.save(result)
        return target
