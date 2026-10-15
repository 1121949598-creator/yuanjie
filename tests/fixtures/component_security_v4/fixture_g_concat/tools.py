"""Fixture G: static collection concatenation."""
from pathlib import Path


def read_tool(path: str) -> str:
    return Path(path).read_text()


def search_web(query: str) -> str:
    return requests.get("https://search.example.com", params={"q": query}).text


FILE_TOOLS = [read_tool]
WEB_TOOLS = [search_web]

ALL_TOOLS = FILE_TOOLS + WEB_TOOLS
