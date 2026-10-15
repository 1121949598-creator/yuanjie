"""lib.py: static __all__ export for the import-star fixture."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()


def helper_unused(text: str) -> str:
    return text.upper()


__all__ = ["read_tool"]
