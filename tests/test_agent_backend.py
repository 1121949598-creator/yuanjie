import json
from pathlib import Path

from fastapi.testclient import TestClient

from yuanjian_agent.config import Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.models import FindingCategory, ResolutionStatus, ReviewStatus
from yuanjian_agent.repair import RepairService
from yuanjian_agent.web import create_app


def _engine(tmp_path: Path) -> ScanEngine:
    return ScanEngine(Settings(data_dir=tmp_path / "state"))


def test_langchain_constructor_alias_and_static_prompt_are_recovered(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text(
        '''
from langchain.agents import create_react_agent
from langchain.tools import Tool

PROMPT = "Search public papers and summarize abstracts."

def dangerous_shell(command: str):
    """Run an arbitrary local shell command."""
    return subprocess.run(command, shell=True)

shell_tool = Tool("shell_exec", dangerous_shell, "Execute shell commands")
base_tools = []
extra_tools = [shell_tool]
agent = create_react_agent("model", base_tools + extra_tools, prompt=PROMPT)
''',
        encoding="utf-8",
    )
    result = _engine(tmp_path).scan(project)
    assert result.agents[0].task_text == "Search public papers and summarize abstracts."
    assert result.tools[0].name == "shell_exec"
    assert result.tools[0].metadata["kind"] == "tool_constructor"
    assert result.bindings[0].resolution_status == ResolutionStatus.RESOLVED_BY_NAME
    assert result.bindings[0].resolution_reason
    assert {item.capability for item in result.tools[0].capabilities} >= {"shell_execute"}


def test_dynamic_binding_records_reason_and_is_never_auto_repaired(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text(
        'agent = create_agent("model", tools=discover_tools(), system_prompt="Research papers")\n',
        encoding="utf-8",
    )
    engine = _engine(tmp_path)
    result = engine.scan(project)
    assert result.bindings[0].resolution_status == ResolutionStatus.UNRESOLVED
    assert "dynamic tool expression" in result.bindings[0].resolution_reason
    finding = next(item for item in result.findings if item.category == FindingCategory.UNRESOLVED)
    action = next(
        item for item in RepairService(engine.settings, engine.secret_scanner).preview(result)["actions"]
        if item["finding_id"] == finding.id
    )
    assert action["automatic"] is False
    assert action["change_kind"] == "manual-review"


def test_static_mcp_catalog_is_recovered_without_starting_server(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "mcp.json").write_text(
        json.dumps(
            {
                "description": "Read approved project notes",
                "mcpServers": {
                    "notes": {
                        "command": "malicious-server",
                        "tools": [
                            {
                                "name": "read_note",
                                "description": "Read a note file",
                                "parameters": {"properties": {"path": {"type": "string"}}},
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = _engine(tmp_path).scan(project)
    tool = next(item for item in result.tools if item.name == "read_note")
    binding = next(item for item in result.bindings if item.tool_id == tool.id)
    assert tool.parameters == ["path"]
    assert binding.resolution_status == ResolutionStatus.RESOLVED
    assert result.summary.unresolved == 0


def test_high_confidence_literal_tool_removal_happens_only_in_safe_copy(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    original = '''
@tool
def search_web(query: str):
    """Search public web pages."""
    return requests.get(query)

@tool
def shell_exec(command: str):
    """Execute any local shell command."""
    return subprocess.run(command, shell=True)

agent = create_agent("model", tools=[search_web, shell_exec], system_prompt="Search public papers")
'''
    (project / "agent.py").write_text(original, encoding="utf-8")
    engine = _engine(tmp_path)
    result = engine.scan(project)
    finding = next(item for item in result.findings if item.category == FindingCategory.TOOL_EXPOSURE)
    assert finding.review_status == ReviewStatus.OPEN
    service = RepairService(engine.settings, engine.secret_scanner)
    action = next(item for item in service.preview(result)["actions"] if item["finding_id"] == finding.id)
    assert action["automatic"] is True
    assert "shell_exec" in action["patch"]
    safe_copy = service.create_safe_copy(result)
    assert "tools=[search_web]" in (safe_copy / "agent.py").read_text(encoding="utf-8")
    assert (project / "agent.py").read_text(encoding="utf-8") == original
    compared = engine.scan(safe_copy, parent_scan_id=result.id)
    assert finding.signature in compared.comparison["resolved"]


def test_agent_security_api_returns_backend_contract(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "state")
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text(
        '@tool\ndef shell_exec(command):\n    """Execute shell commands."""\n    return subprocess.run(command)\n'
        'agent=create_agent("m", tools=[shell_exec], system_prompt="Summarize papers")\n',
        encoding="utf-8",
    )
    result = ScanEngine(settings).scan(project)
    response = TestClient(create_app(settings)).get(f"/api/scans/{result.id}/agent-security")
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_policy"] == "static-only-never-execute-target"
    assert payload["rules_version"] == "2026.09.13"
    assert payload["agents"] and payload["tools"] and payload["bindings"]
    assert all(item["category"] in {"agent_security", "tool_exposure", "unresolved"} for item in payload["findings"])
