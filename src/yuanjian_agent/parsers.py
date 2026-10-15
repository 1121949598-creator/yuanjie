from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from .files import TextFile
from .core.identifiers import stable_id
from .models import (
    AgentSpec,
    AgentToolBinding,
    Framework,
    ResolutionStatus,
    SourceSpan,
    ToolSpec,
)


def dotted_name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def literal_string(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        values = [literal_string(item) for item in node.elts]
        return " ".join(value for value in values if value)
    return ""


def static_string(
    node: ast.AST | None,
    assignments: dict[str, ast.AST],
    seen: set[str] | None = None,
) -> str:
    """Resolve only statically provable strings; never evaluate project code."""
    direct = literal_string(node)
    if direct:
        return direct
    if isinstance(node, ast.Name):
        visited = set(seen or ())
        if node.id in visited:
            return ""
        visited.add(node.id)
        return static_string(assignments.get(node.id), assignments, visited)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = static_string(node.left, assignments, seen)
        right = static_string(node.right, assignments, seen)
        return left + right if left and right else ""
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                return ""
            parts.append(value.value)
        return "".join(parts)
    return ""


def assignment_name(node: ast.AST) -> str:
    if isinstance(node, ast.Assign) and node.targets:
        return dotted_name(node.targets[0])
    if isinstance(node, ast.AnnAssign):
        return dotted_name(node.target)
    return ""


def source_span(relative_path: str, node: ast.AST) -> SourceSpan:
    return SourceSpan(
        path=relative_path,
        start_line=getattr(node, "lineno", 1),
        end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
        start_column=getattr(node, "col_offset", 0),
        end_column=getattr(node, "end_col_offset", 0),
    )


def function_description(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    doc = ast.get_docstring(node) or ""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            for keyword in decorator.keywords:
                if keyword.arg == "description":
                    return literal_string(keyword.value) or doc
    return doc


def decorated_tool_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, Framework] | None:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = dotted_name(target).lower()
        if name.endswith(".tool") or name == "tool":
            custom = ""
            if isinstance(decorator, ast.Call) and decorator.args:
                custom = literal_string(decorator.args[0])
            if name.startswith("mcp.") or "fastmcp" in name:
                framework = Framework.MCP
            else:
                framework = Framework.GENERIC
            return custom or node.name, framework
    return None


def base_tool_class(node: ast.ClassDef) -> bool:
    return any(dotted_name(base).split(".")[-1] == "BaseTool" for base in node.bases)


def class_text_attribute(node: ast.ClassDef, attribute: str) -> str:
    for child in node.body:
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            name = assignment_name(child)
            value = child.value
            if name == attribute:
                return literal_string(value)
    return ""


class CallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = dotted_name(node.func)
        if name:
            suffix = ""
            if name in {"open", "Path.open"} and len(node.args) > 1:
                suffix = f":{literal_string(node.args[1])}"
            for keyword in node.keywords:
                if name.endswith("open") and keyword.arg == "mode":
                    suffix = f":{literal_string(keyword.value)}"
            self.calls.append(f"{name}{suffix}")
        self.generic_visit(node)


@dataclass(slots=True)
class ParseResult:
    agents: list[AgentSpec] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    bindings: list[AgentToolBinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ProjectParser(Protocol):
    """Static framework provider: parse agents/tools and resolve bindings without execution."""

    def parse(self, files: list[TextFile]) -> ParseResult: ...


class PythonAgentParser:
    def __init__(self, readme_text: str = "") -> None:
        self.readme_text = readme_text[:3000]

    def parse(self, files: list[TextFile]) -> ParseResult:
        result = ParseResult()
        definitions: dict[str, list[ToolSpec]] = {}
        function_nodes: dict[str, tuple[TextFile, ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        parsed: list[tuple[TextFile, ast.Module, str]] = []

        for file in files:
            if file.path.suffix.lower() != ".py":
                continue
            try:
                tree = ast.parse(file.text, filename=file.relative_path)
            except SyntaxError as error:
                result.warnings.append(f"Python syntax error in {file.relative_path}:{error.lineno}: {error.msg}")
                continue
            parsed.append((file, tree, file.text))
            mcp_instances = {
                assignment_name(node)
                for node in tree.body
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                and isinstance(node.value, ast.Call)
                and dotted_name(node.value.func).split(".")[-1] == "FastMCP"
            }
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_nodes[node.name] = (file, node)
                    decorated = decorated_tool_name(node)
                    if decorated:
                        tool_name, framework = decorated
                        decorator_roots = {
                            dotted_name(item.func if isinstance(item, ast.Call) else item).split(".")[0]
                            for item in node.decorator_list
                        }
                        if decorator_roots & mcp_instances:
                            framework = Framework.MCP
                        tool = self._function_tool(file, node, tool_name, framework)
                        result.tools.append(tool)
                        definitions.setdefault(node.name, []).append(tool)
                        if tool_name != node.name:
                            definitions.setdefault(tool_name, []).append(tool)
                elif isinstance(node, ast.ClassDef) and base_tool_class(node):
                    tool_name = class_text_attribute(node, "name") or node.name
                    description = class_text_attribute(node, "description") or ast.get_docstring(node) or ""
                    run_method = next(
                        (
                            child
                            for child in node.body
                            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and child.name in {"_run", "_arun", "run"}
                        ),
                        None,
                    )
                    collector = CallCollector()
                    if run_method:
                        collector.visit(run_method)
                    body_source = ast.get_source_segment(file.text, node) or ""
                    tool = ToolSpec(
                        id=stable_id("tool", file.relative_path, node.name),
                        framework=Framework.CREWAI,
                        name=tool_name,
                        description=description,
                        parameters=self._parameters(run_method) if run_method else [],
                        source_spans=[source_span(file.relative_path, node)],
                        body_calls=collector.calls,
                        metadata={"symbol": node.name, "body_source": body_source, "kind": "BaseTool"},
                    )
                    result.tools.append(tool)
                    definitions.setdefault(node.name, []).append(tool)
                    if tool_name != node.name:
                        definitions.setdefault(tool_name, []).append(tool)

        # Tool constructors are inspected as syntax only. Their referenced
        # functions are never imported or called.
        for file, tree, _ in parsed:
            assignments = self._list_assignments(tree)
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Call):
                    continue
                call_name = dotted_name(node.value.func)
                if call_name.split(".")[-1] not in {"Tool", "StructuredTool", "from_function"}:
                    continue
                symbol = assignment_name(node)
                if not symbol:
                    continue
                tool = self._constructor_tool(file, node, symbol, assignments, function_nodes)
                result.tools.append(tool)
                definitions.setdefault(symbol, []).append(tool)
                if tool.name != symbol:
                    definitions.setdefault(tool.name, []).append(tool)

        for file, tree, text in parsed:
            list_assignments = self._list_assignments(tree)
            mcp_tools = [tool for tool in result.tools if tool.framework == Framework.MCP and tool.source_spans[0].path == file.relative_path]
            if mcp_tools:
                agent = AgentSpec(
                    id=stable_id("agent", file.relative_path, "mcp_server"),
                    framework=Framework.MCP,
                    name=f"mcp_server:{Path(file.relative_path).stem}",
                    task_text=self.readme_text,
                    source_spans=[source_span(file.relative_path, tree)],
                    metadata={"synthetic_from_server": True},
                )
                result.agents.append(agent)
                for tool in mcp_tools:
                    result.bindings.append(
                        AgentToolBinding(
                            agent_id=agent.id,
                            tool_id=tool.id,
                            tool_name=tool.name,
                            registration_span=tool.source_spans[0],
                            resolution_status=ResolutionStatus.RESOLVED,
                        )
                    )

            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Call):
                    continue
                call_name = dotted_name(node.value.func)
                short_name = call_name.split(".")[-1]
                if short_name not in {"create_agent", "create_react_agent", "initialize_agent", "Agent"}:
                    continue
                framework = Framework.CREWAI if short_name == "Agent" else Framework.LANGCHAIN
                name = assignment_name(node) or f"agent_at_{getattr(node, 'lineno', 1)}"
                task_text = self._task_text(node.value, framework, list_assignments) or self.readme_text
                agent = AgentSpec(
                    id=stable_id("agent", file.relative_path, name, str(getattr(node, "lineno", 1))),
                    framework=framework,
                    name=name,
                    task_text=task_text,
                    source_spans=[source_span(file.relative_path, node)],
                )
                result.agents.append(agent)
                tools_node = self._tools_argument(node.value, framework)
                tool_nodes, unresolved_name = self._expand_tools(tools_node, list_assignments)
                if unresolved_name:
                    agent.extraction_status = "unresolved"
                    agent.extraction_reasons.append(unresolved_name)
                    result.bindings.append(
                        AgentToolBinding(
                            agent_id=agent.id,
                            tool_id=None,
                            tool_name=unresolved_name,
                            registration_span=source_span(file.relative_path, node),
                            resolution_status=ResolutionStatus.UNRESOLVED,
                            resolution_reason=unresolved_name,
                        )
                    )
                for tool_node in tool_nodes:
                    symbol = (
                        dotted_name(tool_node)
                        or (dotted_name(tool_node.func) if isinstance(tool_node, ast.Call) else "")
                        or literal_string(tool_node)
                        or ast.unparse(tool_node)
                    )
                    candidates = definitions.get(symbol, []) or definitions.get(symbol.split(".")[-1], [])
                    if not candidates and symbol in function_nodes:
                        tool_file, function = function_nodes[symbol]
                        tool = self._function_tool(tool_file, function, function.name, framework)
                        result.tools.append(tool)
                        definitions.setdefault(symbol, []).append(tool)
                        candidates = [tool]
                    if len(candidates) == 1:
                        status = ResolutionStatus.RESOLVED_BY_NAME
                        tool_id = candidates[0].id
                        tool_name = candidates[0].name
                        reason = f"Resolved static symbol {symbol!r}"
                        if candidates[0].framework == Framework.GENERIC:
                            candidates[0].framework = framework
                    elif len(candidates) > 1:
                        status = ResolutionStatus.AMBIGUOUS
                        tool_id = None
                        tool_name = symbol
                        reason = f"Multiple static Tool definitions match {symbol!r}"
                    else:
                        status = ResolutionStatus.UNRESOLVED
                        tool_id = None
                        tool_name = symbol
                        reason = f"No static Tool definition matches {symbol!r}"
                    result.bindings.append(
                        AgentToolBinding(
                            agent_id=agent.id,
                            tool_id=tool_id,
                            tool_name=tool_name,
                            registration_span=source_span(file.relative_path, node),
                            resolution_status=status,
                            resolution_reason=reason,
                        )
                    )
        return result

    def _constructor_tool(
        self,
        file: TextFile,
        node: ast.Assign | ast.AnnAssign,
        symbol: str,
        assignments: dict[str, ast.AST],
        function_nodes: dict[str, tuple[TextFile, ast.FunctionDef | ast.AsyncFunctionDef]],
    ) -> ToolSpec:
        call = node.value
        assert isinstance(call, ast.Call)
        keywords = {item.arg: item.value for item in call.keywords if item.arg}
        function_node = keywords.get("func") or keywords.get("coroutine")
        constructor_name = dotted_name(call.func).split(".")[-1]
        positional_name: ast.AST | None = None
        positional_description: ast.AST | None = None
        if constructor_name == "Tool":
            positional_name = call.args[0] if call.args else None
            if function_node is None and len(call.args) >= 2:
                function_node = call.args[1]
            positional_description = call.args[2] if len(call.args) >= 3 else None
        elif function_node is None and call.args:
            function_node = call.args[0]
        function_symbol = dotted_name(function_node).split(".")[-1]
        implementation = function_nodes.get(function_symbol)
        name = static_string(keywords.get("name") or positional_name, assignments) or symbol
        description = static_string(keywords.get("description") or positional_description, assignments)
        calls: list[str] = []
        parameters: list[str] = []
        extraction_status = "resolved"
        extraction_reasons: list[str] = []
        implementation_span = source_span(file.relative_path, node)
        body_source = ast.get_source_segment(file.text, node) or ""
        if implementation:
            implementation_file, function = implementation
            collector = CallCollector()
            collector.visit(function)
            calls = collector.calls
            parameters = self._parameters(function)
            description = description or function_description(function)
            implementation_span = source_span(implementation_file.relative_path, function)
            body_source = ast.get_source_segment(implementation_file.text, function) or body_source
        else:
            extraction_status = "partial"
            extraction_reasons.append(f"Implementation function {function_symbol or 'unknown'!r} was not resolved")
        return ToolSpec(
            id=stable_id("tool", file.relative_path, symbol),
            framework=Framework.LANGCHAIN,
            name=name,
            description=description,
            parameters=parameters,
            source_spans=[implementation_span],
            body_calls=calls,
            extraction_status=extraction_status,
            extraction_reasons=extraction_reasons,
            metadata={
                "symbol": symbol,
                "implementation_symbol": function_symbol,
                "body_source": body_source,
                "kind": "tool_constructor",
            },
        )

    def _function_tool(
        self,
        file: TextFile,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        tool_name: str,
        framework: Framework,
    ) -> ToolSpec:
        collector = CallCollector()
        collector.visit(node)
        return ToolSpec(
            id=stable_id("tool", file.relative_path, node.name),
            framework=framework,
            name=tool_name,
            description=function_description(node),
            parameters=self._parameters(node),
            source_spans=[source_span(file.relative_path, node)],
            body_calls=collector.calls,
            metadata={
                "symbol": node.name,
                "body_source": ast.get_source_segment(file.text, node) or "",
                "kind": "function",
            },
        )

    @staticmethod
    def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef | None) -> list[str]:
        if node is None:
            return []
        args = [arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        return [arg for arg in args if arg not in {"self", "cls"}]

    @staticmethod
    def _list_assignments(tree: ast.Module) -> dict[str, ast.AST]:
        values: dict[str, ast.AST] = {}
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                name = assignment_name(node)
                if name:
                    values[name] = node.value
        return values

    @staticmethod
    def _tools_argument(call: ast.Call, framework: Framework) -> ast.AST | None:
        for keyword in call.keywords:
            if keyword.arg == "tools":
                return keyword.value
        if framework == Framework.LANGCHAIN and len(call.args) >= 2:
            return call.args[1]
        return None

    @staticmethod
    def _expand_tools(
        node: ast.AST | None,
        assignments: dict[str, ast.AST],
        seen: set[str] | None = None,
    ) -> tuple[list[ast.AST], str]:
        if node is None:
            return [], "tools argument missing"
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return list(node.elts), ""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, left_reason = PythonAgentParser._expand_tools(node.left, assignments, seen)
            right, right_reason = PythonAgentParser._expand_tools(node.right, assignments, seen)
            if left_reason or right_reason:
                return [], f"dynamic tool expression: {ast.unparse(node)}"
            return left + right, ""
        if isinstance(node, ast.Name):
            visited = set(seen or ())
            if node.id in visited:
                return [], f"cyclic tool alias: {node.id}"
            visited.add(node.id)
            assigned = assignments.get(node.id)
            if assigned is not None:
                return PythonAgentParser._expand_tools(assigned, assignments, visited)
        return [], f"dynamic tool expression: {ast.unparse(node)}"

    @staticmethod
    def _task_text(call: ast.Call, framework: Framework, assignments: dict[str, ast.AST]) -> str:
        keys = {"system_prompt", "prompt", "description", "name"}
        if framework == Framework.CREWAI:
            keys |= {"role", "goal", "backstory"}
        values = [static_string(keyword.value, assignments) for keyword in call.keywords if keyword.arg in keys]
        return "\n".join(value for value in values if value)


class MCPConfigParser:
    CONFIG_NAMES = {"mcp.json", "mcp.yaml", "mcp.yml", "mcp.toml", "claude_desktop_config.json"}

    def parse(self, files: list[TextFile]) -> ParseResult:
        result = ParseResult()
        for file in files:
            if file.path.name.lower() not in self.CONFIG_NAMES and "mcp" not in file.path.name.lower():
                continue
            try:
                data = self._load(file)
            except (ValueError, yaml.YAMLError, tomllib.TOMLDecodeError) as error:
                result.warnings.append(f"Could not parse MCP config {file.relative_path}: {error}")
                continue
            servers = self._find_servers(data)
            if not servers:
                continue
            agent = AgentSpec(
                id=stable_id("agent", file.relative_path, "mcp_client"),
                framework=Framework.MCP,
                name=f"mcp_client:{Path(file.relative_path).stem}",
                task_text=self._task_text(data) or "MCP client configuration",
                source_spans=[SourceSpan(file.relative_path, 1, max(file.text.count("\n") + 1, 1))],
                extraction_status="partial",
                extraction_reasons=["MCP configuration cannot prove the runtime server Tool catalog"],
            )
            result.agents.append(agent)
            for server_name, server in servers.items():
                static_tools = self._static_tools(server)
                if static_tools:
                    for index, item in enumerate(static_tools):
                        tool_name = str(item.get("name") or f"tool_{index + 1}")
                        tool = ToolSpec(
                            id=stable_id("tool", file.relative_path, str(server_name), tool_name),
                            framework=Framework.MCP,
                            name=tool_name,
                            description=str(item.get("description") or ""),
                            parameters=self._parameter_names(item.get("parameters")),
                            source_spans=[SourceSpan(file.relative_path, 1, max(file.text.count("\n") + 1, 1))],
                            metadata={"kind": "mcp_static_catalog", "server": str(server_name)},
                        )
                        result.tools.append(tool)
                        result.bindings.append(
                            AgentToolBinding(
                                agent_id=agent.id,
                                tool_id=tool.id,
                                tool_name=tool.name,
                                registration_span=tool.source_spans[0],
                                resolution_status=ResolutionStatus.RESOLVED,
                                resolution_reason="Tool declared in a static MCP configuration catalog",
                            )
                        )
                    continue
                command = str(server.get("command", "")) if isinstance(server, dict) else ""
                args = server.get("args", []) if isinstance(server, dict) else []
                arg_count = len(args) if isinstance(args, list) else 0
                command_name = Path(command).name if command else "unspecified"
                description = f"Configured MCP server; command={command_name!r}; argument_count={arg_count}"
                tool = ToolSpec(
                    id=stable_id("tool", file.relative_path, str(server_name)),
                    framework=Framework.MCP,
                    name=f"mcp_server:{server_name}",
                    description=description,
                    parameters=[],
                    source_spans=[SourceSpan(file.relative_path, 1, max(file.text.count("\n") + 1, 1))],
                    body_calls=[command] if command else [],
                    extraction_status="unresolved_tool_catalog",
                    extraction_reasons=["Server Tool catalog is available only after runtime discovery"],
                    metadata={"body_source": file.text, "kind": "mcp_config", "command": command_name},
                )
                result.tools.append(tool)
                result.bindings.append(
                    AgentToolBinding(
                        agent_id=agent.id,
                        tool_id=tool.id,
                        tool_name=tool.name,
                        registration_span=tool.source_spans[0],
                        resolution_status=ResolutionStatus.UNRESOLVED,
                        resolution_reason="MCP server was not started; runtime Tool catalog remains unknown",
                    )
                )
        return result

    @staticmethod
    def _task_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        values = [data.get(key) for key in ("task", "description", "prompt", "system_prompt")]
        return "\n".join(str(value) for value in values if isinstance(value, str) and value.strip())

    @staticmethod
    def _static_tools(server: Any) -> list[dict[str, Any]]:
        if not isinstance(server, dict):
            return []
        value = server.get("tools")
        if isinstance(value, dict):
            return [
                {"name": name, **(details if isinstance(details, dict) else {})}
                for name, details in value.items()
            ]
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"name": item} for item in value if isinstance(item, (str, dict))]
        return []

    @staticmethod
    def _parameter_names(value: Any) -> list[str]:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                return sorted(str(key) for key in properties)
            return sorted(str(key) for key in value)
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @staticmethod
    def _load(file: TextFile) -> Any:
        suffix = file.path.suffix.lower()
        if suffix == ".json":
            return json.loads(file.text)
        if suffix == ".toml":
            return tomllib.loads(file.text)
        return yaml.safe_load(file.text)

    def _find_servers(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            for key in ("mcpServers", "mcp_servers", "servers"):
                candidate = value.get(key)
                if isinstance(candidate, dict) and (key != "servers" or "mcp" in json.dumps(value).lower()):
                    return candidate
            for child in value.values():
                found = self._find_servers(child)
                if found:
                    return found
        return {}


def parse_project(files: list[TextFile], *, providers: Sequence[ProjectParser] = ()) -> ParseResult:
    readme = next((file.text for file in files if Path(file.relative_path).name.lower().startswith("readme")), "")
    result = ParseResult()
    adapters: list[ProjectParser] = [PythonAgentParser(readme), MCPConfigParser(), *providers]
    for adapter in adapters:
        partial = adapter.parse(files)
        result.agents.extend(partial.agents)
        result.tools.extend(partial.tools)
        result.bindings.extend(partial.bindings)
        result.warnings.extend(partial.warnings)
    return result
