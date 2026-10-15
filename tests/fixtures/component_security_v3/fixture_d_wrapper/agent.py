"""Fixture D: Tool wrapper (structured Tool) bound to an Agent."""
from langchain.agents import create_agent
from langchain.tools import StructuredTool


def read_document(path: str) -> str:
    return open(path, encoding="utf-8").read()


read_tool = StructuredTool.from_function(read_document)

agent = create_agent("local-model", tools=[read_tool], system_prompt="Read a document.")
