from yuanjian_agent.analysis import CapabilityAnalyzer, ContextRiskScorer
from yuanjian_agent.models import Framework, SourceSpan, ToolSpec


def tool(name: str, calls: list[str]) -> ToolSpec:
    return ToolSpec(
        id=name,
        framework=Framework.GENERIC,
        name=name,
        description="",
        parameters=[],
        source_spans=[SourceSpan("tool.py", 1, 1)],
        body_calls=calls,
    )


def test_method_suffix_does_not_confuse_requests_get_with_environment_get():
    analyzed = CapabilityAnalyzer().analyze(tool("search", ["requests.get"]))
    capabilities = {item.capability for item in analyzed.capabilities}
    assert "network_access" in capabilities
    assert "credential_access" not in capabilities


def test_receiver_elided_ast_call_still_recognizes_unlink():
    analyzed = CapabilityAnalyzer().analyze(tool("cleanup", ["unlink"]))
    assert "file_delete" in {item.capability for item in analyzed.capabilities}


def test_task_necessary_high_privilege_tool_is_not_treated_as_overexposed_by_default():
    analyzed = CapabilityAnalyzer().analyze(
        ToolSpec(
            id="shell",
            framework=Framework.LANGCHAIN,
            name="shell_exec",
            description="Execute a shell command to run tests and debug code",
            parameters=["command"],
            source_spans=[SourceSpan("tool.py", 1, 3)],
            body_calls=["subprocess.run"],
        )
    )
    score = ContextRiskScorer().score(
        "Coding agent that executes tests, debugs failures, and builds the project",
        analyzed,
    )
    assert score.impact == 5
    assert score.probability < 0.35
