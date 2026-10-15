"""Fixture A: single Agent bound to a file reader and a network search Tool."""
from langchain.agents import create_agent


def read_file(path: str) -> str:
    return open(path, encoding="utf-8").read()


def search_web(query: str) -> str:
    return requests.get("https://search.example.com", params={"q": query}).text


agent = create_agent(
    "local-model",
    tools=[read_file, search_web],
    system_prompt="Read local files and search the web.",
)
