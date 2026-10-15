"""Fixture D: agent imports read_tool re-exported by the tools package."""
from langchain.agents import create_agent
from tools import read_tool

agent = create_agent("local-model", tools=[read_tool], system_prompt="Read a document.")
