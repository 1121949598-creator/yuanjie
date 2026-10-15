"""neg: a plain string list must not be treated as a Tool collection."""
from langchain.agents import create_agent

COLORS = ["red", "blue"]

agent = create_agent("local-model", tools=COLORS, system_prompt="Color agent.")
