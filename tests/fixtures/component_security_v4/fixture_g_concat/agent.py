"""Fixture G: agent uses the concatenated collection."""
from langchain.agents import create_agent
from tools import ALL_TOOLS

agent = create_agent("local-model", tools=ALL_TOOLS, system_prompt="Read and search.")
