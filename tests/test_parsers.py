from pathlib import Path

from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import Framework, ResolutionStatus, ScanLimits
from yuanjian_agent.parsers import parse_project


EXAMPLES = Path(__file__).parents[1] / "examples"


def parse(name: str):
    files, _ = iter_text_files(EXAMPLES / name, ScanLimits())
    return parse_project(files)


def test_langchain_tools_and_binding():
    result = parse("01_langchain_research")
    assert any(agent.framework == Framework.LANGCHAIN for agent in result.agents)
    assert {tool.name for tool in result.tools} >= {"search_papers", "shell_exec"}
    assert sum(binding.resolution_status == ResolutionStatus.RESOLVED_BY_NAME for binding in result.bindings) == 2


def test_crewai_basetool_and_agent():
    result = parse("04_crewai_cleanup")
    assert any(tool.framework == Framework.CREWAI for tool in result.tools)
    assert any(agent.framework == Framework.CREWAI for agent in result.agents)


def test_mcp_config_is_partial_and_unresolved():
    result = parse("05_mcp_static")
    assert any(agent.framework == Framework.MCP for agent in result.agents)
    assert any(tool.framework == Framework.MCP and tool.name == "read_note" for tool in result.tools)
    assert any(binding.resolution_status == ResolutionStatus.UNRESOLVED for binding in result.bindings)


def test_dynamic_tool_list_is_not_guessed():
    result = parse("06_dynamic_unresolved")
    assert result.bindings[0].resolution_status == ResolutionStatus.UNRESOLVED
