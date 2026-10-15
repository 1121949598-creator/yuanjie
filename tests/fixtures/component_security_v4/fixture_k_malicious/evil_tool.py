"""Fixture K: malicious module that must NEVER execute."""
raise RuntimeError("THIS MODULE MUST NEVER EXECUTE")


def read_file(path: str) -> str:
    return Path(path).read_text()
