"""Fixture B: two cross-file Agents bound to different Tools, must stay isolated."""
from langchain.agents import create_agent
from tools import read_tool, shell_tool

reader = create_agent("local-model", tools=[read_tool], system_prompt="Read a selected file.")

admin = create_agent("local-model", tools=[shell_tool], system_prompt="Run admin shell commands.")
