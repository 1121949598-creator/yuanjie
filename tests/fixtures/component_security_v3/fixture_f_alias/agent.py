"""Fixture F: simple same-file alias propagation."""
from langchain.agents import create_agent


def read_document(path: str) -> str:
    return open(path, encoding="utf-8").read()


reader = read_document

agent = create_agent("local-model", tools=[reader], system_prompt="Read a document.")
