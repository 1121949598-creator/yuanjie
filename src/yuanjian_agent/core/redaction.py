from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Protocol


class TextRedactor(Protocol):
    def redact_text(self, text: str) -> str: ...


def sanitize_value(value, redactor: TextRedactor):
    """Last in-memory boundary, covering evidence, names, dictionary keys and warnings."""
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        return redactor.redact_text(value)
    if isinstance(value, list):
        return [sanitize_value(item, redactor) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item, redactor) for item in value)
    if isinstance(value, dict):
        return {sanitize_value(key, redactor): sanitize_value(item, redactor) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            setattr(value, item.name, sanitize_value(getattr(value, item.name), redactor))
    return value
