"""Fixture F: cross-file Tool collection alias."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()


ALL_TOOLS = [read_tool]

DEFAULT_TOOLS = ALL_TOOLS
