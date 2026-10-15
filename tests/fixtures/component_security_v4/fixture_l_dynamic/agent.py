"""Fixture L: agent binds the dynamic ALL_TOOLS (partial, never executed)."""
from langchain.agents import create_agent
from tools import ALL_TOOLS

agent = create_agent("local-model", tools=ALL_TOOLS, system_prompt="Dynamic tools agent.")
