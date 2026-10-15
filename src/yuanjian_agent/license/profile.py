"""Bounded, trusted JSON configuration for License policy overrides."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from ..models import Severity
from .catalog import CATEGORY_RANK
from .spdx import normalize_spdx


PROFILE_SCHEMA_VERSION = 1
MAX_PROFILE_BYTES = 64 * 1024
MAX_PROFILE_ENTRIES = 256
MAX_PROFILE_STRING = 128
_ROOT_FIELDS = frozenset({"schema_version", "license_overrides", "classification_overrides"})
_CLASSIFICATION_FIELDS = frozenset({"severity", "manual_review_required"})
_CLASSIFICATIONS = frozenset(CATEGORY_RANK)


class InvalidLicensePolicyProfile(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid License policy profile; diagnostic details suppressed")


@dataclass(frozen=True, slots=True)
class ClassificationOverride:
    severity: Severity | None = None
    manual_review_required: bool | None = None


@dataclass(frozen=True, slots=True)
class LicensePolicyProfile:
    license_overrides: dict[str, str] = field(default_factory=dict)
    classification_overrides: dict[str, ClassificationOverride] = field(default_factory=dict)
    schema_version: int = PROFILE_SCHEMA_VERSION


def _reject() -> None:
    raise InvalidLicensePolicyProfile()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _object(value) -> dict:
    if not isinstance(value, dict):
        _reject()
    return value


def _bounded_string(value) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_PROFILE_STRING:
        _reject()
    return value


def _classification(value) -> str:
    value = _bounded_string(value)
    if value not in _CLASSIFICATIONS:
        _reject()
    return value


def parse_license_policy_profile(raw: bytes) -> LicensePolicyProfile:
    if not isinstance(raw, bytes) or len(raw) > MAX_PROFILE_BYTES:
        _reject()
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _reject()
    data = _object(data)
    if set(data) - _ROOT_FIELDS or data.get("schema_version") != PROFILE_SCHEMA_VERSION:
        _reject()

    license_values = _object(data.get("license_overrides", {}))
    classification_values = _object(data.get("classification_overrides", {}))
    if len(license_values) + len(classification_values) > MAX_PROFILE_ENTRIES:
        _reject()

    license_overrides = {}
    for raw_id, raw_classification in license_values.items():
        license_id = _bounded_string(raw_id)
        normalized = normalize_spdx(license_id)
        if (normalized.status != "canonical" or normalized.canonical_expression != license_id
                or normalized.license_ids != [license_id] or normalized.exception_ids):
            _reject()
        license_overrides[license_id] = _classification(raw_classification)

    classification_overrides = {}
    for raw_name, raw_override in classification_values.items():
        name = _classification(raw_name)
        item = _object(raw_override)
        if set(item) - _CLASSIFICATION_FIELDS or not item:
            _reject()
        severity = item.get("severity")
        if severity is not None:
            try:
                severity = Severity(_bounded_string(severity))
            except (TypeError, ValueError):
                _reject()
        manual = item.get("manual_review_required")
        if manual is not None and type(manual) is not bool:
            _reject()
        classification_overrides[name] = ClassificationOverride(severity, manual)
    return LicensePolicyProfile(license_overrides, classification_overrides)


def load_license_policy_profile(configured, project_root: Path) -> LicensePolicyProfile:
    try:
        path = Path(configured)
        root = project_root.resolve()
        if not path.is_absolute():
            _reject()
        resolved = path.resolve()
        if resolved == root or root in resolved.parents:
            _reject()
        if any(part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
               for part in (path, *path.parents)):
            _reject()
        if not path.is_file() or path.stat().st_size > MAX_PROFILE_BYTES:
            _reject()
        with path.open("rb") as stream:
            raw = stream.read(MAX_PROFILE_BYTES + 1)
        return parse_license_policy_profile(raw)
    except InvalidLicensePolicyProfile:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise InvalidLicensePolicyProfile() from None
