import ast
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest

from yuanjian_agent.config import ScannerSettings, Settings
from yuanjian_agent.core.registry import ScannerRegistry
from yuanjian_agent.core.scanner import ScannerResult, ScanStatus, SecurityModule
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.models import Evidence, Finding, FindingCategory, Severity, SourceSpan
from yuanjian_agent.parsers import ParseResult
from yuanjian_agent.repair import RepairService
from yuanjian_agent.reporting import render_html_report


PACKAGE = Path(__file__).parents[1] / "src" / "yuanjian_agent"
EXAMPLES = Path(__file__).parents[1] / "examples"


def test_default_coverage_does_not_claim_license_success(tmp_path):
    result = ScanEngine(Settings(data_dir=tmp_path / "state")).scan(EXAMPLES / "01_langchain_research")
    assert result.status == "completed"
    statuses = result.metadata["scanners"]
    assert statuses["secret"]["status"] == "success"
    assert statuses["license"]["status"] == "unavailable"
    assert statuses["agent_security"]["status"] == "success"
    assert result.summary.agent_security == result.summary.tool_exposures + result.summary.unresolved


def test_license_only_scan_is_unavailable_instead_of_clean(tmp_path):
    config = ScannerSettings(enable_secret=False, enable_agent=False)
    result = ScanEngine(Settings(data_dir=tmp_path / "state", scanners=config)).scan(EXAMPLES / "03_crewai_mail")
    assert result.status == "unavailable"
    assert result.summary.licenses == 0


def test_new_categories_are_visible_in_existing_web_api(tmp_path):
    from fastapi.testclient import TestClient
    from yuanjian_agent.storage import ScanStore
    from yuanjian_agent.web import create_app
    from yuanjian_agent.engine import _summary

    settings = Settings(data_dir=tmp_path / "state")
    result = ScanEngine(settings).scan(EXAMPLES / "03_crewai_mail")
    for category in (FindingCategory.LICENSE, FindingCategory.AGENT_SECURITY):
        result.findings.append(Finding(
            category.value, category.value, category, "test.contract", Severity.INFO, 1,
            "Contract fixture", [Evidence(SourceSpan("manifest.txt", 1, 1), "safe")], [], [],
        ))
    result.summary = _summary(result.findings)
    ScanStore(settings).save(result)
    client = TestClient(create_app(settings))
    response = client.get(f"/api/scans/{result.id}/findings")
    assert response.status_code == 200
    assert {f["category"] for f in response.json()["findings"]} >= {"license", "agent_security"}
    assert client.get(f"/scans/{result.id}").status_code == 200
    assert client.get(f"/findings/license?scan_id={result.id}").status_code == 200


@pytest.mark.parametrize("failed_module", list(SecurityModule))
def test_one_module_failure_does_not_prevent_other_modules(failed_module, tmp_path, capsys, caplog):
    visited = []
    diagnostic = "synthetic-sensitive-error-must-not-persist"

    class TestScanner:
        def __init__(self, name):
            self.name = name

        def scan(self, context):
            visited.append(self.name)
            if self.name == failed_module:
                raise RuntimeError(diagnostic)
            return ScannerResult()

    registry = ScannerRegistry()
    for name in SecurityModule:
        registry.register(TestScanner(name))
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"), registry=registry)
    result = engine.scan(EXAMPLES / "01_langchain_research")
    assert visited == list(SecurityModule)
    assert result.status == "partial"
    assert result.metadata["scanners"][failed_module]["status"] == "failed"
    assert all(result.metadata["scanners"][m]["status"] == "success" for m in SecurityModule if m != failed_module)
    assert diagnostic not in engine.store.result_path(result.id).read_text(encoding="utf-8")
    assert diagnostic not in render_html_report(result)
    assert diagnostic not in capsys.readouterr().out + caplog.text


def test_enabled_stub_preserves_builtin_findings(tmp_path):
    config = ScannerSettings(enable_gitleaks=True, enable_detect_secrets=True, enable_trufflehog=True,
                             enable_scancode=True, enable_ort=True)
    result = ScanEngine(Settings(data_dir=tmp_path / "state", scanners=config)).scan(EXAMPLES / "02_secret_project")
    assert result.summary.secrets == 2
    assert result.status == "partial"
    statuses = result.metadata["scanners"]
    assert statuses["secret"]["providers"]["builtin-secret"] == "success"
    assert statuses["secret"]["providers"]["gitleaks"] == "unavailable"
    assert set(statuses["license"]["providers"].values()) == {"unavailable"}


@pytest.mark.parametrize("failure", [False, True])
def test_redaction_survives_disabled_or_failed_secret_module(failure, tmp_path, monkeypatch):
    raw = "synthetic_Credential_2849AqmZ"
    project = tmp_path / "input"
    project.mkdir()
    (project / "agent.py").write_text(
        f'password="{raw}"\nagent=create_agent("local", tools=discover("{raw}"), system_prompt="{raw}")\n',
        encoding="utf-8",
    )
    engine = ScanEngine(Settings(data_dir=tmp_path / "state", scanners=ScannerSettings(enable_secret=failure)))
    if failure:
        def fail(files):
            raise RuntimeError(raw)
        monkeypatch.setattr(engine.secret_scanner, "scan", fail)
    result = engine.scan(project)
    assert result.summary.secrets == 0
    assert result.summary.unresolved == 1
    serialized = engine.store.result_path(result.id).read_text(encoding="utf-8")
    assert raw not in serialized + json.dumps(result.to_dict()) + render_html_report(result)
    with engine.store._connect() as connection:
        assert raw not in connection.execute("SELECT result_json FROM scans").fetchone()[0]


def test_multiple_secrets_on_one_line_are_masked_at_builtin_boundary(tmp_path):
    from yuanjian_agent.files import TextFile
    from yuanjian_agent.secrets import SecretScanner

    values = ["sk-syntheticDemo_0123456789abcdefgh", "sk-syntheticDemo_abcdefgh0123456789"]
    scanner = SecretScanner(b"x" * 32)
    text_file = TextFile(tmp_path / ".env", ".env", f'API_KEY="{values[0]}"; AUTH_TOKEN="{values[1]}"')
    findings = scanner.scan([text_file])
    assert len(findings) == 2
    assert all(value not in str(findings) for value in values)
    assert all(value not in repr(scanner.redactor_for([text_file])) + repr(text_file) for value in values)
    assert all(value not in repr(scanner.matches(text_file.text)) for value in values)


def test_dedup_preserves_locations_and_repair_handles_each_occurrence(tmp_path):
    project = tmp_path / "input"
    project.mkdir()
    raw = "sk-syntheticRepeated_0123456789abcdefgh"
    (project / ".env").write_text(f'API_KEY="{raw}"\nAPI_KEY="{raw}"\n', encoding="utf-8")
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    result = engine.scan(project)
    assert result.summary.secrets == 1
    assert {e.source_span.start_line for e in result.findings[0].evidence} == {1, 2}
    copy = RepairService(engine.settings, engine.secret_scanner).create_safe_copy(result)
    assert (copy / ".env").read_text(encoding="utf-8").count("YOUR_SECRET_HERE") == 2
    assert engine.scan(copy, parent_scan_id=result.id).comparison["counts"]["resolved"] == 1


@pytest.mark.parametrize("disabled", [True, False])
def test_incomplete_rescan_does_not_claim_missing_findings_resolved(disabled, tmp_path, monkeypatch):
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    previous = engine.scan(EXAMPLES / "02_secret_project")
    if disabled:
        engine.settings.scanners.enable_secret = False
    else:
        def fail(files):
            raise RuntimeError("failure")
        monkeypatch.setattr(engine.secret_scanner, "scan", fail)
    current = engine.scan(EXAMPLES / "02_secret_project", parent_scan_id=previous.id)
    assert current.comparison["counts"]["resolved"] == 0
    assert len(current.comparison["not_evaluated"]) == previous.summary.secrets
    assert current.comparison["incomplete"] is True


def test_framework_provider_can_be_added_without_engine_changes(tmp_path):
    class AdditionalStaticProvider:
        def parse(self, files):
            return ParseResult(warnings=["additional static provider visited"])

    result = ScanEngine(
        Settings(data_dir=tmp_path / "state"), agent_providers=[AdditionalStaticProvider()]
    ).scan(EXAMPLES / "01_langchain_research")
    assert "additional static provider visited" in result.warnings
    assert result.summary.tool_exposures == 1


def test_agent_receives_prior_normalized_outputs_in_order(tmp_path):
    fixture = Finding("f", "sig", FindingCategory.SECRET, "test", Severity.INFO, 1, "Fixture",
                      [Evidence(SourceSpan("a.txt", 1, 1), "safe")], [], [])
    registry = ScannerRegistry()

    class First:
        name = SecurityModule.SECRET
        def scan(self, context):
            return ScannerResult(findings=[deepcopy(fixture)])

    class Last:
        name = SecurityModule.AGENT_SECURITY
        def scan(self, context):
            assert context.upstream_findings[0].signature == "sig"
            assert context.upstream_statuses["secret"] == ScanStatus.SUCCESS
            return ScannerResult()

    registry.register(Last())
    registry.register(First())
    result = ScanEngine(Settings(data_dir=tmp_path / "state"), registry=registry).scan(EXAMPLES / "03_crewai_mail")
    assert result.metadata["scanners"]["agent_security"]["status"] == ScanStatus.SUCCESS


def test_recursive_static_boundary_and_no_external_scanner_imports():
    forbidden = {"exec", "eval", "compile", "runpy.run_path", "subprocess.run", "subprocess.Popen", "os.system"}
    third_party = {"gitleaks", "detect_secrets", "trufflehog", "scancode", "ort"}
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if ast.unparse(node.func) == "subprocess.Popen" and path == PACKAGE / "license" / "adapters" / "process.py":
                    # L1 authorizes only this audited static ScanCode boundary.
                    # Every call (including Windows process-tree cleanup) must avoid a shell.
                    keywords = {item.arg: item.value for item in node.keywords}
                    assert isinstance(keywords.get("shell"), ast.Constant)
                    assert keywords["shell"].value is False
                    continue
                assert ast.unparse(node.func) not in forbidden, (path, node.lineno)
            if isinstance(node, ast.Import):
                assert not any(alias.name.split(".")[0] in third_party for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or "").split(".")[0] not in third_party


def test_package_import_graph_is_acyclic():
    graph = {}
    for path in PACKAGE.rglob("*.py"):
        parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
        dependencies = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                base = importlib.util.resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
                if base:
                    dependencies.add(base)
                    dependencies.update(f"{base}.{item.name}" for item in node.names)
            elif isinstance(node, ast.Import):
                dependencies.update(item.name for item in node.names)
        graph[module] = dependencies
    visiting, visited = set(), set()

    def visit(module):
        assert module not in visiting, f"Circular import at {module}"
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module] & graph.keys():
            if dependency != module:
                visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)
