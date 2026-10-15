"""lib2.py: no __all__, so import-star symbol resolution must degrade."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()
