"""Fixture G: dynamic tool collection that must degrade to partial, never guessed."""
from langchain.agents import create_agent


def load_plugins():
    return [open, subprocess.run]  # pragma: no cover - must never execute


tools = load_plugins()

agent = create_agent("local-model", tools=tools, system_prompt="Operate loaded plugins.")
