"""Fixture C: decorator Tool bound to an Agent."""
from langchain.agents import create_agent
from langchain.tools import tool


@tool
def read_document(path: str) -> str:
    """Read a text document from the local filesystem."""
    return open(path, encoding="utf-8").read()


agent = create_agent("local-model", tools=[read_document], system_prompt="Read one document.")
