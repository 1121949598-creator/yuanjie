"""Fixture F: agent consumes the aliased collection DEFAULT_TOOLS."""
from langchain.agents import create_agent
from tools import DEFAULT_TOOLS

agent = create_agent("local-model", tools=DEFAULT_TOOLS, system_prompt="Read a document.")
