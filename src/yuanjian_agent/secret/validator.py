from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from urllib.parse import unquote, urlsplit

from .entropy import shannon_entropy
from .rules import (
    ENV_REFERENCE, HASH_VALUE, PLACEHOLDER_WORDS, REPEATED_VALUE, TEMPLATE,
    UUID_VALUE, SecretRule,
)


PLACEHOLDERS = frozenset({
    "password", "passwd", "pwd", "secret", "token", "apikey", "changeme",
    "example", "dummy", "test", "fake", "sample", "replaceme", "redacted",
    "yourapikey", "yourtoken", "yoursecret", "yoursecrethere", "testtoken",
})


def is_placeholder(value: str, extra: set[str] | frozenset[str] = frozenset()) -> bool:
    normalized = PLACEHOLDER_WORDS.sub("", value.strip().lower())
    markers = PLACEHOLDERS | {PLACEHOLDER_WORDS.sub("", item.lower()) for item in extra}
    return (
        not normalized or normalized in markers
        or normalized.startswith(("your", "insert", "replacewith"))
        or bool(REPEATED_VALUE.fullmatch(normalized))
        or bool(TEMPLATE.search(value))
        or bool(ENV_REFERENCE.match(value.strip()))
    )


def _literal(rule: SecretRule, value: str) -> bool:
    if "://" in value:
        return _database(rule, value)
    return len(value) >= rule.min_length


def _token(rule: SecretRule, value: str) -> bool:
    classes = sum((any(c.islower() for c in value), any(c.isupper() for c in value),
                   any(c.isdigit() for c in value), any(not c.isalnum() for c in value)))
    return (
        len(value) >= rule.min_length and classes >= 2
        and shannon_entropy(value) >= rule.min_entropy
        and not UUID_VALUE.fullmatch(value) and not HASH_VALUE.fullmatch(value)
        and not any(c.isspace() for c in value)
        and not any(c in value for c in "()[]")
        and "://" not in value
    )


def _jwt(rule: SecretRule, value: str) -> bool:
    try:
        header, payload, signature = value.split(".")
        decoded = []
        for part in (header, payload):
            decoded.append(json.loads(base64.b64decode(
                part + "=" * (-len(part) % 4), altchars=b"-_", validate=True
            )))
        return (all(isinstance(item, dict) for item in decoded)
                and isinstance(decoded[0].get("alg"), str) and bool(signature))
    except (ValueError, UnicodeError, binascii.Error, RecursionError):
        return False


def _database(rule: SecretRule, value: str) -> bool:
    try:
        uri = urlsplit(value)
        return bool(uri.hostname and uri.username and uri.password
                    and not is_placeholder(unquote(uri.password)))
    except ValueError:
        return False


VALIDATORS: dict[str, Callable[[SecretRule, str], bool]] = {
    "literal": _literal, "token": _token, "jwt": _jwt, "database": _database,
}


def validate_candidate(rule: SecretRule, value: str, placeholders: set[str]) -> bool:
    """Offline syntax/context checks only; never contact a credential provider."""
    if is_placeholder(value, placeholders):
        return False
    return VALIDATORS[rule.validator](rule, value)
