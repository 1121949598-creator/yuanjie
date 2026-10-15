"""Fixture A: agent that consumes a Tool defined in another module."""
from langchain.agents import create_agent
from tools import read_tool

agent = create_agent("local-model", tools=[read_tool], system_prompt="Read a selected file.")
