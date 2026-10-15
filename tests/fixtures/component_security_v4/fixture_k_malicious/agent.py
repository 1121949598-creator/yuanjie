"""Fixture K: agent imports a function from a malicious module (never executed)."""
from evil_tool import read_file
from langchain.agents import create_agent

agent = create_agent("local-model", tools=[read_file], system_prompt="Read a document.")
