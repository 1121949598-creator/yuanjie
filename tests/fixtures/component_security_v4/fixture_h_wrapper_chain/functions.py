"""Fixture H: plain function in functions.py."""
from pathlib import Path


def read_document(path: str) -> str:
    return Path(path).read_text()
