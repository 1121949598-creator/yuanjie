"""Fixture L: dynamic tool collection must degrade to partial."""
from pathlib import Path


def build_tools():
    return [read_tool, search_web]


def read_tool(path: str) -> str:
    return Path(path).read_text()


def search_web(query: str) -> str:
    return requests.get("https://search.example.com").text


ALL_TOOLS = build_tools()
