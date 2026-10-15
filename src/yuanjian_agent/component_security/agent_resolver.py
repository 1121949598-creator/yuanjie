"""Static Agent / Tool / Binding resolution for the component-security pipeline.

This module turns Python source into per-Agent ``ComponentFacts`` without
executing, importing, or running the audited code. It reuses the existing
pure-AST helpers from ``yuanjian_agent.parsers`` and the shared capability
rules / evidence model from ``component_security.facts``, so it needs no second
Tool taxonomy and never spawns processes or starts MCP servers.

Every emitted Agent carries only the capabilities of the Tools it statically
binds, so multiple Agents in one file stay isolated and never inherit the
file-level capability bag. Dynamic tool collections degrade to ``partial`` and
are never guessed or executed.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from ..analysis import load_tool_rules
from ..files import TextFile
from ..models import SourceSpan
from ..parsers import (
    assignment_name,
    base_tool_class,
    dotted_name,
    source_span,
    static_string,
)
from .facts import (
    BoundaryFact,
    CapabilityFact,
    ComponentFacts,
    EvidenceFact,
    _action_for,
    _capability_from_symbol,
    _controls_for,
    _masked_line,
    _resource_for,
    _rule_for,
    mask_excerpt,
)
from .module_index import PythonModuleIndex
from .symbol_resolver import CrossModuleSymbolResolver

# Framework-aware constructor names recognised as Agent declarations.
_KNOWN_AGENT_NAMES = {
    "create_agent",
    "create_react_agent",
    "initialize_agent",
    "create_agent_executor",
    "create_react_agent_executor",
    "AgentExecutor",
}
_AGENT_FRAMEWORK_BASES = {
    "crewai",
    "autogen",
    "langchain",
    "langchain_core",
    "langgraph",
}

_WARNING_DYNAMIC = "dynamic_tool_binding"
_WARNING_UNRESOLVED_COLLECTION = "unresolved_tool_collection"
_WARNING_UNSUPPORTED_EXPR = "unsupported_binding_expression"


@dataclass(slots=True)
class ToolBindingFact:
    """Internal static binding fact; projected, never added to the frozen contract."""

    agent_symbol: str
    tool_symbol: str
    binding_kind: str  # constructor_argument | registration_call | wrapper | direct_function
    source_span: SourceSpan
    resolution_status: str  # resolved | partial | unresolved
    evidence: EvidenceFact | None = None
    detail: str = ""
    cross_file: bool = False


@dataclass(slots=True)
class AgentDeclaration:
    symbol: str
    name: str
    frame_path: str
    source_span: SourceSpan
    task_text: str
    bindings: list[ToolBindingFact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "resolved"
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _FileScope:
    imports: set[str]
    alias_map: dict[str, str]
    local_defs: set[str]
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    class_tools: dict[str, ast.ClassDef]
    wrapper_tools: dict[str, ast.Call]
    assignments: dict[str, ast.AST]
    wrapper_to_func: dict[str, str]
    # Batch 4 cross-file import details.
    from_import_names: set[str] = field(default_factory=set)
    module_aliases: dict[str, str] = field(default_factory=dict)
    has_star_import: bool = False
    star_modules: list[str] = field(default_factory=list)


_NORMALIZE_RE = re.compile(r"[^0-9A-Za-z_]+")


def _safe_name(value: str) -> str:
    value = _NORMALIZE_RE.sub("_", value).strip("_")
    return value[:80] or "agent"


def _is_imported_ref(name: str, scope: _FileScope) -> bool:
    """True when ``name`` is a symbol bound by an import (could be cross-file)."""
    return name in scope.from_import_names or name in scope.module_aliases


def _alias_reaches_import(name: str, scope: _FileScope, seen: set[str] | None = None) -> bool:
    """True when a same-file alias chain for ``name`` reaches an imported symbol."""
    if _is_imported_ref(name, scope):
        return True
    seen = set(seen or ())
    if name in seen:
        return False
    seen.add(name)
    if name not in scope.assignments:
        return False
    value = scope.assignments[name]
    if isinstance(value, ast.Name):
        return _alias_reaches_import(value.id, scope, seen)
    if isinstance(value, ast.Attribute):
        head = dotted_name(value).split(".", 1)[0]
        return head in scope.module_aliases
    return False


def _call_parts(call: ast.Call) -> tuple[str, str, str]:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id, fn.id, fn.id
    if isinstance(fn, ast.Attribute):
        parts: list[str] = []
        cur = fn
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        base = ""
        if isinstance(cur, ast.Name):
            base = cur.id
        elif isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name):
            base = cur.func.id
        if base:
            parts.append(base)
        return base, fn.attr, ".".join(reversed(parts))
    return "", "", ""


def _is_framework_import(scope: _FileScope) -> bool:
    return any(
        imp.split(".")[0] in _AGENT_FRAMEWORK_BASES or imp in _AGENT_FRAMEWORK_BASES
        for imp in scope.imports
    )


def _is_agent_constructor(call: ast.Call, scope: _FileScope) -> bool:
    base, short, _dotted = _call_parts(call)
    canonical = scope.alias_map.get(short, short)
    kw_names = {k.arg for k in (call.keywords or []) if k.arg}
    has_tools = "tools" in kw_names
    framework = _is_framework_import(scope)
    agent_kw = bool(kw_names & {"role", "goal", "backstory", "description", "system_prompt", "prompt", "name"})

    if canonical in _KNOWN_AGENT_NAMES or short in _KNOWN_AGENT_NAMES:
        return True
    if short == "Agent" or canonical == "Agent":
        if framework or has_tools or agent_kw:
            return short not in scope.local_defs or framework
        return False
    # Generic Agent-family constructor carrying an explicit tools= argument.
    if has_tools and framework:
        return True
    return False


def _resolve_tool_elements(
    node: ast.AST | None,
    scope: _FileScope,
    seen: set[str] | None = None,
) -> tuple[list[ast.AST], str]:
    if node is None:
        return [], "tools argument missing"
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        items: list[ast.AST] = []
        for elt in node.elts:
            sub, reason = _resolve_tool_elements(elt, scope, seen)
            if reason:
                return [], reason
            items.extend(sub)
        return items, ""
    if isinstance(node, ast.Name):
        visited = set(seen or ())
        if node.id in visited:
            return [], f"cyclic tool alias: {node.id}"
        visited.add(node.id)
        final = _follow_alias(node.id, scope, visited)
        if final is not None:
            return [ast.Name(id=final)], ""
        if node.id in scope.local_defs or node.id in scope.wrapper_tools:
            return [node], ""
        if _is_imported_ref(node.id, scope) or scope.has_star_import:
            return [node], ""
        return [], f"{_WARNING_UNRESOLVED_COLLECTION}:{node.id}"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, left_reason = _resolve_tool_elements(node.left, scope, seen)
        right, right_reason = _resolve_tool_elements(node.right, scope, seen)
        if left_reason or right_reason:
            return [], f"{_WARNING_UNSUPPORTED_EXPR}:{ast.unparse(node)[:60]}"
        return left + right, ""
    if isinstance(node, ast.Call):
        return [node], ""
    if isinstance(node, ast.Attribute):
        return [node], ""
    return [], f"{_WARNING_DYNAMIC}:{ast.unparse(node)[:60]}"


def _follow_alias(name: str, scope: _FileScope, seen: set[str]) -> str | None:
    """Resolve shallow same-file alias chains to a function/class/wrapper symbol."""
    if name in scope.functions or name in scope.class_tools or name in scope.wrapper_tools:
        return name
    if name not in scope.assignments:
        return None
    value = scope.assignments[name]
    if isinstance(value, ast.Name):
        if value.id in seen:
            return None
        seen.add(value.id)
        return _follow_alias(value.id, scope, seen)
    if isinstance(value, ast.Attribute):
        return _follow_alias(value.attr, scope, seen)
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        elts: list[ast.AST] = []
        for elt in value.elts:
            sub = _follow_alias(elt.id if isinstance(elt, ast.Name) else "", scope, seen)
            if sub is None:
                return None
            elts.append(sub)
        return None  # collection aliases are handled by _resolve_tool_elements
    return None


def _tool_symbol(tool_node: ast.AST) -> str:
    if isinstance(tool_node, (ast.Name, ast.Attribute)):
        return dotted_name(tool_node)
    if isinstance(tool_node, ast.Call):
        base, short, dotted = _call_parts(tool_node)
        if base and short in {"from_function", "from_func"} and tool_node.args:
            return _tool_symbol(tool_node.args[0])
        for kw in (tool_node.keywords or []):
            if kw.arg in {"func", "coroutine"}:
                return _tool_symbol(kw.value)
        return dotted or short or base or _safe_name(ast.unparse(tool_node))
    return _safe_name(ast.unparse(tool_node))


def _tool_impl_for(
    symbol: str,
    scope: _FileScope,
    file: TextFile,
) -> tuple[ast.AST | None, str]:
    """Return (impl_node, kind) for a resolved tool symbol."""
    if symbol in scope.functions:
        return scope.functions[symbol], "function"
    if symbol in scope.class_tools:
        return scope.class_tools[symbol], "classtool"
    if symbol in scope.wrapper_tools:
        wrapper = scope.wrapper_tools[symbol]
        func_symbol = None
        for kw in (wrapper.keywords or []):
            if kw.arg in {"func", "coroutine"} and isinstance(kw.value, ast.Name):
                func_symbol = kw.value.id
        if func_symbol is None and isinstance(wrapper.func, ast.Attribute) and wrapper.func.attr in {"from_function", "from_func"} and wrapper.args:
            if isinstance(wrapper.args[0], ast.Name):
                func_symbol = wrapper.args[0].id
        if func_symbol and func_symbol in scope.functions:
            return scope.functions[func_symbol], "wrapper"
        return wrapper, "wrapper_unresolved"
    return None, "unknown"


def _impl_calls_ast(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, ast.AST]]:
    out: list[tuple[str, ast.AST]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        base, short, dotted = _call_parts(node)
        symbol = dotted or short or base
        if symbol:
            out.append((symbol, node))
    distinct: dict[str, ast.AST] = {}
    for symbol, node in out:
        distinct.setdefault(symbol, node)
    return list(distinct.items())


class _BaseToolWorker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[tuple[str, ast.AST]] = []

    def visit_Call(self, node: ast.Call) -> None:
        base, short, dotted = _call_parts(node)
        symbol = dotted or short or base
        if symbol:
            self.calls.append((symbol, node))
        self.generic_visit(node)


def _class_tool_calls(cls: ast.ClassDef) -> list[tuple[str, ast.AST]]:
    worker = _BaseToolWorker()
    for child in cls.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name in {"_run", "_arun", "run"}:
            worker.visit(child)
    return list(worker.calls)


def _open_write(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if any(isinstance(k.value, ast.Constant) and "w" in str(k.value.value) for k in (node.keywords or []) if k.arg == "mode"):
        return True
    return len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and "w" in str(node.args[1].value)


def _task_text_from_call(call: ast.Call) -> str:
    keys = {"prompt", "system_prompt", "description", "role", "goal", "backstory", "name"}
    values: list[str] = []
    for kw in (call.keywords or []):
        if kw.arg in keys:
            value = static_string(kw.value, {})
            if value:
                values.append(value)
    return " ".join(values)


class AgentResolver:
    """Resolve per-Agent static facts from a list of ``TextFile`` sources."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules = rules or load_tool_rules()

    def resolve(self, files: list[TextFile]) -> list[AgentDeclaration]:
        declarations: list[AgentDeclaration] = []
        for file in files:
            if file.path.suffix.lower() != ".py":
                continue
            try:
                tree = ast.parse(file.text, filename=file.relative_path)
            except SyntaxError:
                continue
            self._resolve_file(file, tree, declarations)
        return declarations

    def _resolve_file(
        self,
        file: TextFile,
        tree: ast.Module,
        declarations: list[AgentDeclaration],
    ) -> None:
        scope = _build_asserted_scope(file, tree)
        file_decls: dict[str, AgentDeclaration] = {}

        # Pass 1: direct constructor declarations.
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Call):
                continue
            symbol = assignment_name(node)
            if not symbol or not _is_agent_constructor(node.value, scope):
                continue
            name = _safe_name(symbol)
            decl = AgentDeclaration(
                symbol=symbol,
                name=name,
                frame_path=file.relative_path,
                source_span=source_span(file.relative_path, node),
                task_text=_task_text_from_call(node.value),
            )
            file_decls[symbol] = decl
            declarations.append(decl)
            tools_node = self._tools_argument(node.value)
            if tools_node is None:
                decl.status = "partial"
                decl.reasons.append("No static tools= argument was found")
                decl.warnings.append(_WARNING_UNRESOLVED_COLLECTION)
                continue
            tool_nodes, reason = _resolve_tool_elements(tools_node, scope)
            if reason:
                decl.status = "partial"
                decl.reasons.append(reason)
                decl.warnings.append(reason.split(":", 1)[0])
                continue
            for tool_node in tool_nodes:
                binding = self._resolve_binding(decl, tool_node, node, scope, file)
                decl.bindings.append(binding)
            if not decl.bindings:
                decl.status = "partial"
                decl.reasons.append("No statically resolvable Tool bindings")
                decl.warnings.append(_WARNING_UNRESOLVED_COLLECTION)

        # Pass 2: registration calls (agent.add_tool / agent.register_tool / .tools.append).
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            base, short, dotted = _call_parts(node)
            if short in {"add_tool", "register_tool", "append_tool"}:
                owner = _attr_owner(node.func)
                decl = file_decls.get(owner)
                if decl is None:
                    continue
                if not node.args:
                    decl.status = "partial"
                    decl.reasons.append("registration call has no tool argument")
                    continue
                tool_arg = node.args[0]
                tool_nodes, reason = _resolve_tool_elements(tool_arg, scope)
                if reason or not tool_nodes:
                    decl.status = "partial"
                    decl.reasons.append(f"dynamic registration: {reason or 'no tool argument'}")
                    decl.warnings.append(_WARNING_DYNAMIC)
                    continue
                for tool_node in tool_nodes:
                    binding = self._resolve_registration_binding(decl, tool_node, node, scope, file)
                    decl.bindings.append(binding)
            elif short in {"append", "extend"} and base:
                owner = _attr_owner(node.func.value) if isinstance(node.func, ast.Attribute) else ""
                if not owner.endswith(".tools"):
                    continue
                agent_sym = owner.rsplit(".tools", 1)[0].rsplit(".", 1)[-1]
                decl = file_decls.get(agent_sym)
                if decl is None:
                    continue
                if not node.args:
                    decl.status = "partial"
                    decl.reasons.append("dynamic tools mutation: no argument")
                    decl.warnings.append(_WARNING_DYNAMIC)
                    continue
                tool_nodes, reason = _resolve_tool_elements(node.args[0], scope)
                if reason or not tool_nodes:
                    decl.status = "partial"
                    decl.reasons.append(f"dynamic tools mutation: {reason or 'no argument'}")
                    decl.warnings.append(_WARNING_DYNAMIC)
                    continue
                for tool_node in tool_nodes:
                    binding = self._resolve_registration_binding(decl, tool_node, node, scope, file)
                    decl.bindings.append(binding)

    @staticmethod
    def _tools_argument(call: ast.Call) -> ast.AST | None:
        for kw in (call.keywords or []):
            if kw.arg == "tools":
                return kw.value
        base, short, _dotted = _call_parts(call)
        if short in {"create_agent", "create_react_agent"} and len(call.args) >= 2:
            return call.args[1]
        return None

    def _resolve_binding(
        self,
        decl: AgentDeclaration,
        tool_node: ast.AST,
        agent_node: ast.Assign | ast.AnnAssign,
        scope: _FileScope,
        file: TextFile,
    ) -> ToolBindingFact:
        return self._build_binding(decl, tool_node, agent_node, scope, file, kind="constructor_argument")

    def _resolve_registration_binding(
        self,
        decl: AgentDeclaration,
        tool_node: ast.AST,
        call_node: ast.Call,
        scope: _FileScope,
        file: TextFile,
    ) -> ToolBindingFact:
        return self._build_binding(decl, tool_node, call_node, scope, file, kind="registration_call")

    def _build_binding(
        self,
        decl: AgentDeclaration,
        tool_node: ast.AST,
        anchor: ast.AST,
        scope: _FileScope,
        file: TextFile,
        *,
        kind: str,
    ) -> ToolBindingFact:
        symbol = _tool_symbol(tool_node)
        span = source_span(file.relative_path, anchor)
        excerpt = mask_excerpt((ast.get_source_segment(file.text, anchor) or "Agent(tools=[...])").strip()[:160])
        evidence = EvidenceFact(
            symbol=f"agent.tool_binding:{symbol}",
            span=span,
            excerpt=excerpt,
            parser="python-agent-static",
            details={
                "agent": decl.symbol,
                "tool": symbol,
                "binding_kind": kind,
                "parser": "python-agent-static",
                "rule_version": str(self.rules.get("version", "1.0")),
            },
        )
        if isinstance(tool_node, ast.Call):
            return ToolBindingFact(
                agent_symbol=decl.symbol,
                tool_symbol=symbol,
                binding_kind="wrapper",
                source_span=span,
                resolution_status="resolved",
                evidence=evidence,
                detail="inline tool constructor",
            )
        if isinstance(tool_node, (ast.Name, ast.Attribute)):
            base_sym = symbol.rsplit(".", 1)[-1]
            if base_sym in scope.functions or base_sym in scope.class_tools or base_sym in scope.wrapper_tools:
                return ToolBindingFact(
                    agent_symbol=decl.symbol,
                    tool_symbol=symbol,
                    binding_kind=kind,
                    source_span=span,
                    resolution_status="resolved",
                    evidence=evidence,
                    detail="static tool symbol",
                )
            head = symbol.split(".", 1)[0]
            if (
                _is_imported_ref(head, scope)
                or _alias_reaches_import(base_sym, scope)
                or scope.has_star_import
            ):
                return ToolBindingFact(
                    agent_symbol=decl.symbol,
                    tool_symbol=symbol,
                    binding_kind=kind,
                    source_span=span,
                    resolution_status="resolved",
                    evidence=evidence,
                    detail="cross-file tool reference",
                    cross_file=True,
                )
        return ToolBindingFact(
            agent_symbol=decl.symbol,
            tool_symbol=symbol,
            binding_kind="direct_function",
            source_span=span,
            resolution_status="unresolved",
            evidence=evidence,
            detail="tool symbol not statically resolvable",
        )


def _attr_owner(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attr_owner(node.value)
    return ""


def _build_asserted_scope(file: TextFile, tree: ast.Module) -> _FileScope:
    scope = _FileScope(
        imports=set(),
        alias_map={},
        local_defs=set(),
        functions={},
        class_tools={},
        wrapper_tools={},
        assignments={},
        wrapper_to_func={},
    )
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                scope.imports.add(alias.name)
                if alias.asname:
                    scope.alias_map[alias.asname] = alias.name
                    scope.module_aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            scope.imports.add(module)
            scope.imports.add(module.split(".")[0])
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                scope.imports.add(full)
                if alias.name == "*":
                    scope.has_star_import = True
                    scope.star_modules.append(module)
                    continue
                bound = alias.asname or alias.name
                scope.alias_map[bound] = alias.name
                scope.from_import_names.add(bound)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope.functions[node.name] = node
            scope.local_defs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            scope.local_defs.add(node.name)
            if base_tool_class(node):
                scope.class_tools[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            name = assignment_name(node)
            if not name:
                continue
            scope.local_defs.add(name)
            scope.assignments[name] = node.value
            if isinstance(node.value, ast.Call):
                base, short, _dotted = _call_parts(node.value)
                if short in {"Tool", "StructuredTool"} or (
                    isinstance(node.value.func, ast.Attribute) and node.value.func.attr in {"from_function", "from_func"}
                ):
                    scope.wrapper_tools[name] = node.value
    return scope


def resolve_agent_declarations(files: list[TextFile], rules: dict[str, Any] | None = None) -> list[AgentDeclaration]:
    """Convenience wrapper that resolves Agent/Tool/Binding declarations only."""
    return AgentResolver(rules).resolve(files)


_IMPORT_LINE_RE = re.compile(r"^\s*(from\s+\S+|import\s+\S+)")


def _import_evidence(
    file_text: str,
    name: str,
    relative_path: str,
    rule_version: str,
) -> EvidenceFact | None:
    """Locate the import statement that bound ``name``; emit python-import-static evidence."""
    token = re.escape(name)
    for idx, line in enumerate(file_text.splitlines(), 1):
        if not _IMPORT_LINE_RE.match(line):
            continue
        if re.search(rf"(^|[.\s]){token}\b", line):
            excerpt = mask_excerpt(line.strip()[:160])
            return EvidenceFact(
                symbol=f"import:{name}",
                span=SourceSpan(relative_path, idx, idx, 0, 0),
                excerpt=excerpt,
                parser="python-import-static",
                details={
                    "parser": "python-import-static",
                    "name": name,
                    "rule_version": rule_version,
                },
            )
    return None


def effective_agent_facts(
    declarations: list[AgentDeclaration],
    files: list[TextFile],
    rules: dict[str, Any] | None = None,
) -> list[ComponentFacts]:
    rules = rules or load_tool_rules()
    by_path: dict[str, TextFile] = {f.relative_path: f for f in files}
    cached_scope: dict[str, _FileScope] = {}
    results: list[ComponentFacts] = []
    for decl in declarations:
        file = by_path.get(decl.frame_path)
        if file is None:
            continue
        if decl.frame_path not in cached_scope:
            try:
                cached_scope[decl.frame_path] = _build_asserted_scope(file, ast.parse(file.text, filename=file.relative_path))
            except SyntaxError:
                cached_scope[decl.frame_path] = _FileScope(set(), {}, set(), {}, {}, {}, {}, {})
        scope = cached_scope[decl.frame_path]

        caps: dict[str, CapabilityFact] = {}
        warnings = list(decl.warnings)
        status = decl.status
        reasons = list(decl.reasons)

        cross_index: PythonModuleIndex | None = None
        cross_resolver: CrossModuleSymbolResolver | None = None
        agent_module = ""
        produced: list[str] = []

        for binding in decl.bindings:
            produced.clear()
            if binding.resolution_status == "unresolved":
                if status == "resolved":
                    status = "partial"
                    reasons.append(f"Tool binding {binding.tool_symbol} could not be resolved statically")
                continue
            base = binding.tool_symbol.rsplit(".", 1)[-1]
            impl, kind = _tool_impl_for(base, scope, file)
            impls: list[tuple[str, str, str]] = []
            local_impl = impl
            if impl is not None:
                impls.append(("", base, kind))
            elif binding.cross_file:
                if cross_index is None:
                    cross_index = PythonModuleIndex(files)
                    cross_resolver = CrossModuleSymbolResolver(cross_index)
                    agent_module = cross_index.module_for_path(decl.frame_path) or ""
                if agent_module:
                    expansion = cross_resolver.expand(agent_module, binding.tool_symbol)
                    if expansion.status != "resolved":
                        if status == "resolved":
                            status = "partial"
                        reason = expansion.reason or f"cross-file:{expansion.status}"
                        reasons.append(f"cross-file {expansion.status}: {reason}")
                        code = reason.split(":", 1)[0]
                        warnings.append(code if code else _WARNING_DYNAMIC)
                    for rt in expansion.tools:
                        impls.append((rt.module, rt.impl_name, rt.impl_kind))
            else:
                continue

            for impl_module, impl_name, kind2 in impls:
                if local_impl is not None:
                    impl2 = local_impl
                    kind3 = kind
                    impl_text = file.text
                    impl_path = file.relative_path
                else:
                    minfo = cross_index.get(impl_module) if cross_index else None
                    if minfo is None or minfo.tree is None:
                        if status == "resolved":
                            status = "partial"
                            reasons.append(f"Tool implementation for {binding.tool_symbol} could not be located")
                        continue
                    impl2 = minfo.functions.get(impl_name) or minfo.class_tools.get(impl_name)
                    if impl2 is None:
                        continue
                    impl_file = by_path.get(minfo.relative_path)
                    impl_text = impl_file.text if impl_file is not None else file.text
                    impl_path = minfo.relative_path
                    kind3 = kind2
                calls: list[tuple[str, ast.AST]] = []
                if isinstance(impl2, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls = _impl_calls_ast(impl2)
                elif isinstance(impl2, ast.ClassDef):
                    calls = _class_tool_calls(impl2)
                for symbol, node in calls:
                    capability_id = _capability_from_symbol(symbol, rules)
                    if not capability_id:
                        if symbol == "open" and _open_write(node):
                            capability_id = "file_write"
                        else:
                            continue
                    if capability_id not in produced:
                        produced.append(capability_id)
                    span = source_span(impl_path, node)
                    evidence = EvidenceFact(
                        symbol=symbol,
                        span=span,
                        excerpt=_masked_line(impl_text, node, fallback=symbol),
                        parser="python-tool-static",
                        details={
                            "symbol": symbol,
                            "parser": "python-tool-static",
                            "tool": binding.tool_symbol,
                            "tool_kind": kind3,
                            "impl_module": impl_module if impl_module else "",
                            "rule_version": str(rules.get("version", "1.0")),
                        },
                    )
                    cap = caps.get(capability_id)
                    if cap is None:
                        rule = _rule_for(capability_id, rules) or {}
                        cap = CapabilityFact(
                            capability=capability_id,
                            action=_action_for(capability_id, symbol),
                            resource=_resource_for(symbol),
                            impact=int(rule.get("impact", 1)),
                            confidence=0.0,
                            rule_id=f"component.capability.{capability_id}",
                            controls=_controls_for(file.text, symbol),
                        )
                        caps[capability_id] = cap
                    cap.evidence.append(evidence)
            # Attach Agent->Tool binding evidence plus the import provenance.
            if binding.evidence is not None and produced:
                ref_cap = caps[produced[0]]
                ref_cap.evidence.append(binding.evidence)
                imp = _import_evidence(
                    file.text,
                    binding.tool_symbol.split(".", 1)[0],
                    file.relative_path,
                    str(rules.get("version", "1.0")),
                )
                if imp is not None:
                    ref_cap.evidence.append(imp)

        for cap in caps.values():
            distinct = {ev.symbol for ev in cap.evidence}
            cap.confidence = round(min(0.99, 0.55 + 0.10 * len(distinct)) if distinct else 0.40, 2)
        if not caps and status == "resolved":
            status = "partial"
        boundaries = _boundaries_from_caps(caps.values(), decl.source_span)
        results.append(
            ComponentFacts(
                component_type="agent",
                name=decl.name,
                declared_purpose=decl.task_text[:200],
                purpose_spans=[decl.source_span],
                extraction_status="resolved" if status == "resolved" else ("partial" if status == "partial" else "unresolved"),
                extraction_reasons=sorted(set(reasons)),
                capabilities=[caps[key] for key in sorted(caps)],
                boundaries=boundaries,
                warnings=sorted(set(warnings)),
            )
        )
    return results


def _boundaries_from_caps(caps: Any, agent_span: SourceSpan) -> list[BoundaryFact]:
    caps = list(caps)
    if not caps:
        return []
    data_scope = sorted({cap.resource for cap in caps if cap.resource != "unknown"})
    credential_use = any(cap.capability == "credential_access" for cap in caps)
    names = {cap.capability for cap in caps}
    if "shell_execute" in names:
        execution_mode = "shell"
    elif "process_execute" in names or any("subprocess" in ev.symbol for cap in caps for ev in cap.evidence):
        execution_mode = "local_process"
    else:
        execution_mode = "network" if "network_access" in names else ("filesystem" if data_scope else "none")
    evidence: list[EvidenceFact] = []
    seen: set[tuple] = set()
    for cap in caps:
        for ev in cap.evidence:
            key = (ev.symbol, ev.span.path, ev.span.start_line, ev.span.start_column, ev.parser)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(ev)
    return [
        BoundaryFact(
            data_scope=data_scope,
            network_target=[],
            credential_use=credential_use,
            execution_mode=execution_mode,
            evidence=evidence,
        )
    ]
