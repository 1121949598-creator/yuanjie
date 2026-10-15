from __future__ import annotations


def mask_secret(value: str) -> str:
    """Mask short credentials and whole private keys without exposing their length."""
    if len(value) <= 8 or "-----BEGIN " in value or "\n" in value:
        return "****"
    visible = 3 if len(value) < 20 else 4
    return f"{value[:visible]}****{value[-visible:]}"
