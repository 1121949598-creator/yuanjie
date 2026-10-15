"""tools.file: implementation for import-alias fixture."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()
