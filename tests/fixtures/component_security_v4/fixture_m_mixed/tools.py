"""Fixture M: mixed static + dynamic starred collection."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()


def load_plugins():
    return [search_web]


def search_web(query: str) -> str:
    return requests.get("https://search.example.com").text


TOOLS = [read_tool, *load_plugins()]
