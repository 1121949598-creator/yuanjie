"""Fixture E: module alias attr access ft.read_tool."""
import tools.file as ft

from langchain.agents import create_agent

agent = create_agent("local-model", tools=[ft.read_tool], system_prompt="Read a document.")
