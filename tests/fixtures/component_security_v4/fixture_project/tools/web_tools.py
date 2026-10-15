"""Network tool implementations."""


def search_web(query: str) -> str:
    return requests.get("https://search.example.com", params={"q": query}).text
