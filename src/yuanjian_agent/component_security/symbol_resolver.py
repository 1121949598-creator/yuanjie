"""B11-B15: cross-module static symbol resolution for tools (member B).

Resolves a Tool reference (name, alias, attribute, re-export, relative import,
tool collection, concatenation, starred list) to the concrete implementation
symbols, across Python modules, using only the scan-local ``PythonModuleIndex``
(filesystem + AST + text). No target module is imported or executed; missing /
external / dynamic symbols degrade to ``partial`` / ``unresolved`` with an
explicit reason.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from ..parsers import dotted_name
from .module_index import PythonModuleIndex

MAX_IMPORT_DEPTH = 12
MAX_SYMBOL_RESOLUTION_DEPTH = 24
MAX_COLLECTION_EXPANSION = 250

_W_DYNAMIC = "dynamic_tool_collection"
_W_UNRESOLVED = "unresolved_symbol"
_W_CYCLE = "circular_import"
_W_DEPTH = "resolution_depth_exceeded"
_W_STAR = "unsupported_import_star"
_W_LIMIT = "collection_limit_exceeded"


@dataclass(slots=True)
class ResolvedTool:
    """A concrete, statically located Tool implementation."""

    module: str
    impl_name: str
    impl_kind: str  # function | classtool | wrapper
    chain: list[str] = field(default_factory=list)  # evidence chain, "module:name"


@dataclass(slots=True)
class ToolExpansion:
    """Result of expanding one Tool reference (may be a collection)."""

    tools: list[ResolvedTool] = field(default_factory=list)
    status: str = "unresolved"  # resolved | partial | unresolved | cycle | ambiguous
    reason: str = ""


def _expansion(tools: list[ResolvedTool], status: str, reason: str = "") -> ToolExpansion:
    return ToolExpansion(tools=tools, status=status, reason=reason)


def _is_tool_constructor(fn: ast.AST | None) -> bool:
    if isinstance(fn, ast.Name):
        return fn.id in {"Tool", "StructuredTool"}
    if isinstance(fn, ast.Attribute):
        return fn.attr in {"Tool", "StructuredTool", "from_function", "from_func"}
    return False


def _wrapped_symbol(call: ast.Call) -> str:
    for kw in (call.keywords or []):
        if kw.arg in {"func", "coroutine"} and isinstance(kw.value, (ast.Name, ast.Attribute)):
            return dotted_name(kw.value)
    if isinstance(call.func, ast.Attribute) and call.func.attr in {"from_function", "from_func"} and call.args:
        return dotted_name(call.args[0])
    return ""


class CrossModuleSymbolResolver:
    """Resolves cross-file Tool references to implementations via the index."""

    def __init__(self, index: PythonModuleIndex) -> None:
        self.index = index

    # ------------------------------------------------------------------ public
    def expand(self, context_module: str, symbol: str) -> ToolExpansion:
        budget = _Budget()
        visited: set[tuple[str, str]] = set()
        return self._expand_ref(context_module, symbol, 0, visited, budget, [])

    # ------------------------------------------------------------------ names
    def _expand_ref(
        self,
        context: str,
        symbol: str,
        depth: int,
        visited: set[tuple[str, str]],
        budget: "_Budget",
        path: list[str],
    ) -> ToolExpansion:
        if depth > MAX_SYMBOL_RESOLUTION_DEPTH:
            return _expansion([], "partial", _W_DEPTH)
        key = (context, symbol)
        if key in visited:
            return _expansion([], "cycle", _W_CYCLE)
        visited = visited | {key}
        info = self.index.get(context)
        if info is None or info.tree is None:
            return _expansion([], "partial", _W_UNRESOLVED)
        if "." in symbol:
            head, _, rest = symbol.partition(".")
            module = None
            if head in info.module_aliases:
                module = info.module_aliases[head]
            elif self.index.get(head) is not None:
                module = head
            if module is None:
                return _expansion([], "unresolved", f"{_W_UNRESOLVED}:{symbol}")
            return self._expand_into(module, rest, depth, visited, budget, path, source=context)
        return self._expand_name(context, symbol, depth, visited, budget, path)

    def _expand_into(
        self,
        module: str,
        symbol: str,
        depth: int,
        visited: set[tuple[str, str]],
        budget: "_Budget",
        path: list[str],
        *,
        source: str,
    ) -> ToolExpansion:
        if "." in symbol:
            head, _, rest = symbol.partition(".")
            candidate = f"{module}.{head}"
            if self.index.module_exists(candidate):
                return self._expand_into(candidate, rest, depth, visited, budget, path, source=source)
            return _expansion([], "unresolved", f"{_W_UNRESOLVED}:{symbol}")
        return self._expand_name(module, symbol, depth, visited, budget, path)

    def _expand_name(self, context: str, name: str, depth: int, visited, budget, path) -> ToolExpansion:
        info = self.index.get(context)
        if info is None or info.tree is None:
            return _expansion([], "partial", _W_UNRESOLVED)
        step = f"{context}:{name}"
        new_path = path + [step]
        budget.count += 1
        if budget.count > MAX_COLLECTION_EXPANSION:
            return _expansion([], "partial", _W_LIMIT)

        if name in info.functions:
            return _expansion([ResolvedTool(context, name, "function", new_path)], "resolved")
        if name in info.class_tools:
            return _expansion([ResolvedTool(context, name, "classtool", new_path)], "resolved")
        if name in info.wrapper_tools:
            wrapped = _wrapped_symbol(info.wrapper_tools[name])
            if not wrapped:
                return _expansion([], "partial", "wrapper_unresolved_target")
            result = self._expand_ref(context, wrapped, depth + 1, visited, budget, new_path)
            for tool in result.tools:
                tool.impl_kind = "function"
            return result
        if name in info.assignments:
            return self._expand_assignment(context, info.assignments[name], name, depth, visited, budget, new_path)

        # from-import (re-export or direct cross-module).
        for mref, iname, asname in info.from_imports:
            if asname != name:
                continue
            target = self.index.resolve_module_ref(context, mref)
            if target is None:
                return _expansion([], "partial", "unresolved_relative_import")
            if not self.index.module_exists(target):
                return _expansion([], "unresolved", f"{_W_UNRESOLVED}:{name}")
            return self._expand_name(target, iname, depth + 1, visited, budget, new_path)

        # star-import limited to a static __all__.
        for cref in info.star_imports:
            target = self.index.resolve_module_ref(context, cref)
            if target is None or not self.index.module_exists(target):
                return _expansion([], "partial", _W_STAR)
            tinfo = self.index.get(target)
            if tinfo.all_names is None or name not in tinfo.all_names:
                continue
            return self._expand_name(target, name, depth + 1, visited, budget, new_path)

        return _expansion([], "unresolved", f"{_W_UNRESOLVED}:{name}")

    # ------------------------------------------------------------ assignments
    def _expand_assignment(self, context: str, value: ast.AST, name: str, depth, visited, budget, path) -> ToolExpansion:
        step = f"{context}:{name}"
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            tools: list[ResolvedTool] = []
            statuses: list[str] = []
            for elt in value.elts:
                if isinstance(elt, ast.Starred):
                    if isinstance(elt.value, ast.Call):
                        statuses.append("dynamic")
                        continue
                    sub = self._expand_ref(context, dotted_name(elt.value), depth + 1, visited, budget, path)
                    if sub.status != "resolved":
                        statuses.append(sub.status)
                    tools.extend(sub.tools)
                    continue
                sym = dotted_name(elt)
                if not sym:
                    statuses.append("unresolved")
                    continue
                sub = self._expand_ref(context, sym, depth + 1, visited, budget, path)
                tools.extend(sub.tools)
                statuses.append(sub.status)
            return self._aggregate(tools, statuses, _W_DYNAMIC)
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            left = self._expand_assignment(context, value.left, "", depth, visited, budget, path)
            right = self._expand_assignment(context, value.right, "", depth, visited, budget, path)
            return self._merge_two(left, right)
        if isinstance(value, ast.Name):
            return self._expand_name(context, value.id, depth + 1, visited, budget, path)
        if isinstance(value, ast.Attribute):
            return self._expand_ref(context, dotted_name(value), depth + 1, visited, budget, path)
        if isinstance(value, ast.Call):
            if _is_tool_constructor(value.func):
                wrapped = _wrapped_symbol(value)
                if wrapped:
                    result = self._expand_ref(context, wrapped, depth + 1, visited, budget, path)
                    for tool in result.tools:
                        tool.impl_kind = "function"
                    return result
            return _expansion([], "partial", _W_DYNAMIC)
        if isinstance(value, ast.IfExp):
            return _expansion([], "partial", _W_DYNAMIC)
        return _expansion([], "partial", _W_DYNAMIC)

    @staticmethod
    def _aggregate(tools: list[ResolvedTool], statuses: list[str], dyn_reason: str) -> ToolExpansion:
        if not tools:
            if statuses and all(s == "unresolved" for s in statuses):
                return _expansion([], "unresolved", "unresolved_tool_collection")
            return _expansion([], "partial", dyn_reason)
        if any(s != "resolved" for s in statuses):
            return _expansion(tools, "partial", dyn_reason)
        return _expansion(tools, "resolved")

    @staticmethod
    def _merge_two(left: ToolExpansion, right: ToolExpansion) -> ToolExpansion:
        tools = left.tools + right.tools
        statuses = [left.status, right.status]
        return CrossModuleSymbolResolver._aggregate(tools, statuses, _W_DYNAMIC)


class _Budget:
    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0
