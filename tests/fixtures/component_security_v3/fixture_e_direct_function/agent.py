"""Fixture E: direct function Tool via tools= without an explicit Tool wrapper."""
from langchain.agents import create_agent


def read_document(path: str) -> str:
    return open(path, encoding="utf-8").read()


agent = create_agent("local-model", tools=[read_document], system_prompt="Read a document.")
