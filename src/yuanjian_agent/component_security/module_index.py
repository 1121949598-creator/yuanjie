"""B10: finite, deterministic cross-file Python module index (member B).

Builds a scan-local index of a repository's Python files from ``TextFile``
objects only (filesystem + AST + text). It never executes, imports, or runs the
audited code and never reaches into site-packages. The index exposes each
module's structured imports, symbol table, assignments and AST so the
cross-module resolver can trace ``from x import y``, aliases, re-exports and
tool collections purely statically.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..files import TextFile
from ..parsers import assignment_name, base_tool_class


@dataclass(slots=True)
class ModuleInfo:
    """Static, scan-local description of one Python module."""

    module: str
    relative_path: str
    is_package: bool
    tree: ast.Module | None
    parse_status: str  # ok | syntax_error
    # Structured imports for cross-module resolution.
    from_imports: list[tuple[str, str, str]] = field(default_factory=list)  # (module_ref, name, asname)
    module_aliases: dict[str, str] = field(default_factory=dict)  # asname -> absolute module
    top_module_names: set[str] = field(default_factory=set)  # 'import a.b' -> 'a'
    star_imports: list[str] = field(default_factory=list)  # absolute module refs
    import_names: set[str] = field(default_factory=set)  # every locally-bound import name
    # Symbol tables (same shapes the agent resolver uses).
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=dict)
    class_tools: dict[str, ast.ClassDef] = field(default_factory=dict)
    wrapper_tools: dict[str, ast.Call] = field(default_factory=dict)
    assignments: dict[str, ast.AST] = field(default_factory=dict)
    local_defs: set[str] = field(default_factory=set)
    all_names: list[str] | None = None


def _package_of_module(module: str, is_package: bool) -> str:
    """Return the ``__package__``-like base used for relative imports."""
    if not module:
        return ""
    if is_package:
        return module
    head = module.rsplit(".", 1)
    return head[0] if len(head) == 2 else ""


def _detect_src_package(py_relative_paths: list[str]) -> str | None:
    """Detect a single 'src/<pkg>' layout package, if present."""
    candidates: set[str] = set()
    for rel in py_relative_paths:
        parts = rel.split("/")
        if len(parts) >= 3 and parts[0] == "src" and parts[-1] == "__init__.py":
            candidates.add(parts[1])
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _join_parts(parts: list[str], src_pkg: str | None) -> str:
    """Join path parts into a module name, dropping an __init__ marker."""
    inner = parts[:]
    if inner and inner[-1] == "__init__.py":
        inner = inner[:-1]
    if not inner:
        return ""
    if src_pkg and inner[0] == src_pkg:
        segs = inner[1:]
        if segs and segs[-1].endswith(".py"):
            segs[-1] = segs[-1][:-3]
        return ".".join(segs) if segs else src_pkg
    if inner[-1].endswith(".py"):
        inner[-1] = inner[-1][:-3]
    return ".".join(inner)


def _relative_module_name(relative: str, src_pkg: str | None) -> str:
    parts = relative.split("/")
    if src_pkg and len(parts) >= 3 and parts[0] == "src" and parts[1] == src_pkg:
        return _join_parts(parts[2:], src_pkg)
    return _join_parts(parts, None)


def _static_all(tree: ast.Module, scope: "ModuleInfo") -> list[str] | None:
    """Read a fully-static ``__all__`` list. Never evaluate dynamic expressions."""
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if assignment_name(node) not in {"__all__"}:
            continue
        value = node.value
        names: list[str] = []
        if isinstance(value, (ast.List, ast.Tuple)):
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.append(elt.value)
        if names or isinstance(value, (ast.List, ast.Tuple)):
            return names
    return None


class PythonModuleIndex:
    """Scan-local index mapping module names to static module facts."""

    def __init__(self, files: list[TextFile]) -> None:
        self.modules: dict[str, ModuleInfo] = {}
        self.module_to_file: dict[str, str] = {}
        self._by_path: dict[str, ModuleInfo] = {}
        src_pkg = _detect_src_package([f.relative_path for f in files if f.relative_path.lower().endswith(".py")])
        self._src_pkg = src_pkg
        for file in files:
            if not file.relative_path.lower().endswith(".py"):
                continue
            module = _relative_module_name(file.relative_path, src_pkg)
            if not module:
                continue
            info = self._build(file, module)
            self.modules[module] = info
            self.module_to_file[module] = file.relative_path
            self._by_path[file.relative_path] = info

    @staticmethod
    def _build(file: TextFile, module: str) -> ModuleInfo:
        is_package = Path(file.relative_path).name == "__init__.py"
        try:
            tree = ast.parse(file.text, filename=file.relative_path)
            parse_status = "ok"
        except SyntaxError:
            tree = None
            parse_status = "syntax_error"
        info = ModuleInfo(
            module=module,
            relative_path=file.relative_path,
            is_package=is_package,
            tree=tree,
            parse_status=parse_status,
        )
        if tree is None:
            return info
        _populate_imports(tree, info)
        _populate_symbols(tree, info)
        info.all_names = _static_all(tree, info)
        return info

    def get(self, module: str) -> ModuleInfo | None:
        return self.modules.get(module)

    def module_for_path(self, relative_path: str) -> str | None:
        info = self._by_path.get(relative_path)
        return info.module if info is not None else None

    def path_for_module(self, module: str) -> str | None:
        return self.module_to_file.get(module)

    def resolve_module_ref(self, context_module: str, ref: str) -> str | None:
        """Resolve an import module reference (possibly relative) to an absolute name."""
        if not ref:
            return None
        if ref.startswith("."):
            info = self.modules.get(context_module)
            base = _package_of_module(context_module, info.is_package if info else False) if info else context_module.rsplit(".", 1)[0]
            dots = len(ref) - len(ref.lstrip("."))
            tail = ref[dots:].lstrip(".")
            current = base
            for _ in range(dots - 1):
                head, _, rest = current.rpartition(".")
                current = head if rest else ""
            target = f"{current}.{tail}" if current and tail else (current or tail)
            return target or None
        return ref

    def module_exists(self, module: str) -> bool:
        return module in self.modules


def _populate_imports(tree: ast.Module, info: ModuleInfo) -> None:
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                info.top_module_names.add(name.split(".")[0])
                if alias.asname:
                    info.module_aliases[alias.asname] = name
                    info.import_names.add(alias.asname)
                else:
                    info.import_names.add(name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            ref = node.module or ("." * (node.level or 1))
            if node.level:
                ref = ("." * node.level) + (node.module or "")
            for alias in node.names:
                asname = alias.asname or alias.name
                if alias.name == "*":
                    info.star_imports.append(ref)
                    continue
                info.from_imports.append((ref, alias.name, asname))
                info.import_names.add(asname)


def _populate_symbols(tree: ast.Module, info: ModuleInfo) -> None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.functions[node.name] = node
            info.local_defs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            info.local_defs.add(node.name)
            if base_tool_class(node):
                info.class_tools[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            name = assignment_name(node)
            if not name or "." in name:
                continue
            info.local_defs.add(name)
            info.assignments[name] = node.value
            if isinstance(node.value, ast.Call):
                fn = node.value.func
                short = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
                if short in {"Tool", "StructuredTool"} or (
                    isinstance(fn, ast.Attribute) and fn.attr in {"from_function", "from_func"}
                ):
                    info.wrapper_tools[name] = node.value
