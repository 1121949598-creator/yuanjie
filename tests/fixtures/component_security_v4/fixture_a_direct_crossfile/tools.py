"""Fixture A: direct cross-file Tool."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()
