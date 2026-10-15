"""Fixture M: agent binds the mixed collection (static preserved, dynamic partial)."""
from langchain.agents import create_agent
from tools import TOOLS

agent = create_agent("local-model", tools=TOOLS, system_prompt="Mixed tools agent.")
