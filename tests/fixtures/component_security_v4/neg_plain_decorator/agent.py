"""neg: an ordinary decorator must not be treated as @tool (no Agent declared)."""
def cache(func):
    return func


@cache
def read_file(path: str) -> str:
    return Path(path).read_text()
