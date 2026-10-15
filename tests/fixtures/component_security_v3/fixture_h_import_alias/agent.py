"""Fixture H: import alias on the Agent constructor."""
from langchain.agents import create_agent as create_agent_alias
from langchain.tools import tool as tool_alias


@tool_alias
def read_document(path: str) -> str:
    """Read a text document from the local filesystem."""
    return open(path, encoding="utf-8").read()


agent = create_agent_alias(
    "local-model", tools=[read_document], system_prompt="Read one document."
)
