"""Fixture I: module a imports module b (b imports a back)."""
from b import y_tool
from langchain.agents import create_agent

x_tool = [y_tool]

agent = create_agent("local-model", tools=x_tool, system_prompt="Cycle agent.")
