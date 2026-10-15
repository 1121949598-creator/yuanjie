"""Fixture J: external package Tool must degrade, never import."""
from langchain.agents import create_agent
from unknown_sdk import dangerous_tool

agent = create_agent("local-model", tools=[dangerous_tool], system_prompt="External tool agent.")
