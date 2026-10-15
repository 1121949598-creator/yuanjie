"""Fixture C: cross-file Tool collection."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()


def search_web(query: str) -> str:
    return requests.get("https://search.example.com", params={"q": query}).text


ALL_TOOLS = [read_tool, search_web]
