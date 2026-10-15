"""Fixture C: agent consuming the cross-file ALL_TOOLS collection."""
from langchain.agents import create_agent
from tools import ALL_TOOLS

researcher = create_agent("local-model", tools=ALL_TOOLS, system_prompt="Research files and the web.")
