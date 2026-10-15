"""Fixture I: malicious code that must NEVER run during static analysis."""
from langchain.agents import create_agent
from langchain.tools import tool


def evil():
    raise RuntimeError("THIS MUST NEVER EXECUTE")


@tool
def dangerous(command: str) -> str:
    """Runs an arbitrary shell command."""
    os.system("THIS MUST NEVER RUN")
    return "done"


agent = create_agent(
    "local-model", tools=[dangerous], system_prompt="A dangerous admin agent."
)
