"""Fixture B: cross-file multi-Agent isolation."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()


def shell_tool(command: str) -> str:
    return subprocess.run(command, shell=True, check=True)
