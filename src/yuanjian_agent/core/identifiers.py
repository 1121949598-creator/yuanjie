import hashlib


def stable_id(prefix: str, *parts: str) -> str:
    """Existing stable identifier algorithm, shared without importing parsers."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{prefix}_{digest}"
