"""neg: an imported plain function used as data must never be treated as a Tool."""
from pathlib import Path
from langchain.agents import create_agent
from utils import format_text


def read_document(path: str) -> str:
    return Path(path).read_text()


formatted = format_text("  hi  ")

agent = create_agent("local-model", tools=[read_document], system_prompt="Read a document.")
