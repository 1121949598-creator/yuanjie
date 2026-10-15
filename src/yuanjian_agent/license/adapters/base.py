"""Bounded upstream JSON and safe, explicitly projected provider facts."""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Protocol
from urllib.parse import unquote

from ...config import LicenseProviderSettings
from ...core.context import ScanContext
from ...core.scanner import ScanStatus
from ...models import Evidence, SourceSpan
from ..models import (EXPRESSION_LIMIT, EXPRESSION_WITHHELD, LicenseEvidence,
                      LicenseProviderResult, PackageEvidence, ProviderProvenance)


class InvalidProviderOutput(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid provider output; diagnostic details suppressed")


class ProviderLimitExceeded(InvalidProviderOutput):
    pass


class LicenseProvider(Protocol):
    name: str

    def collect(self, context: ScanContext) -> LicenseProviderResult: ...


def reject() -> None:
    raise InvalidProviderOutput()


def object_value(value) -> dict:
    if not isinstance(value, dict):
        reject()
    return value


def array(value, maximum: int) -> list:
    if not isinstance(value, list):
        reject()
    if len(value) > maximum:
        raise ProviderLimitExceeded()
    return value


def validate_tree(value, limits: LicenseProviderSettings) -> None:
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > limits.max_nodes or depth > limits.max_depth:
            raise ProviderLimitExceeded()
        if isinstance(item, dict):
            stack.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif isinstance(item, list):
            stack.extend((part, depth + 1) for part in item)
        elif isinstance(item, str):
            if len(item) > limits.max_string_length:
                raise ProviderLimitExceeded()
        elif isinstance(item, float):
            if not math.isfinite(item):
                reject()
        elif item is not None and type(item) not in (int, bool):
            reject()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject()
        result[key] = value
    return result


def read_json(path: Path, limits: LicenseProviderSettings) -> dict:
    # Reject links before reading and bound the read even if the file grows.
    if has_link(path) or not path.is_file():
        reject()
    with path.open("rb") as stream:
        raw = stream.read(limits.max_json_bytes + 1)
    if len(raw) > limits.max_json_bytes:
        reject()
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
        validate_tree(value, limits)
        return object_value(value)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise InvalidProviderOutput() from None


def has_link(path: Path) -> bool:
    return any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
               for p in (path, *path.parents))


def within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def version(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][A-Za-z0-9.]+)?", value):
        reject()
    return value


def atom(value, *, optional=False) -> str | None:
    if value is None or value == "":
        if optional:
            return None
        reject()
    if not isinstance(value, str) or len(value) > 256 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+~-]*", value):
        reject()
    return value


def relative_path(value) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        reject()
    # Decode only to inspect; never turn encoded separators into an accepted path.
    decoded = unquote(value)
    if (any(ord(c) < 32 for c in decoded) or any(c in decoded for c in ":@?#\\")
            or decoded.startswith("/") or any(p in {"", ".", ".."} for p in decoded.split("/"))):
        reject()
    return PurePosixPath(value).as_posix()


def expression(value) -> str | None:
    if value is None or value == "":
        return None
    # Shape validation only. Never classify, simplify, or claim SPDX validity here.
    if not isinstance(value, str):
        reject()
    if len(value) > 4096:
        return EXPRESSION_LIMIT
    if value in {EXPRESSION_LIMIT, EXPRESSION_WITHHELD}:
        return value
    if not re.fullmatch(r"[A-Za-z0-9().+ :_-]+", value):
        return EXPRESSION_WITHHELD
    if ":" in value and "DocumentRef-" not in value:
        return EXPRESSION_WITHHELD
    return value


def requirement(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and len(value) <= 256 and re.fullmatch(r"[A-Za-z0-9.*+~^<>=!, \-]+", value):
        return value
    return "[withheld]"


def package_from_purl(value, provenance: ProviderProvenance) -> PackageEvidence:
    if not isinstance(value, str) or not value.startswith("pkg:") or len(value) > 1024:
        reject()
    # Qualifiers/subpaths can contain repository URLs or credentials: never export them.
    base = value.split("?", 1)[0].split("#", 1)[0]
    coordinate = base[4:]
    if "/" not in coordinate:
        reject()
    ecosystem, coordinate = coordinate.split("/", 1)
    atom(ecosystem)
    path, separator, release = coordinate.rpartition("@")
    if not separator:
        path, release = coordinate, None
    parts = path.split("/")
    for part in parts:
        atom(unquote(part).removeprefix("@"))
    name = atom(unquote(parts[-1]))
    release = atom(unquote(release), optional=True) if release else None
    return PackageEvidence(name, release, base, [provenance])


def provenance(provider, provider_version, kind, mode, origin=None, origin_version=None):
    return ProviderProvenance(provider, provider_version, origin or provider, kind, mode, origin_version)


def license_fact(path, license_expression, prov, package=None, *, start=None, end=None,
                 score=None, source_scope="project") -> LicenseEvidence:
    precise = start is not None and type(start) is int and start >= 1
    if start is not None and not precise:
        reject()
    if end is not None and (type(end) is not int or end < (start or 1)):
        reject()
    confidence = None
    if score is not None:
        if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 100:
            reject()
        confidence = score / 100
    details = {"provenance": [asdict(prov)], "source_kind": prov.source_kind,
               "source_scope": source_scope, "location_precision": "line" if precise else "file",
               "license_expression": expression(license_expression), "provider_score": score}
    return LicenseEvidence(
        Evidence(SourceSpan(relative_path(path), start or 1, end or start or 1),
                 "[upstream text withheld]", details),
        source=prov.provider, license_expression=details["license_expression"], package=package,
        provenance=[prov], confidence=confidence,
    )


def note_partial(result: LicenseProviderResult, reason="invalid_record") -> None:
    result.status = ScanStatus.PARTIAL
    result.reason_code = "incomplete_output"
    if reason not in result.warnings:
        result.warnings.append(reason)


def record_error(result, error, reason="invalid_record"):
    if isinstance(error, ProviderLimitExceeded):
        raise error
    note_partial(result, reason)


def append_license(result, fact, limits):
    # Bound the expanded output as it is built, including package/path products.
    if len(result.licenses) >= limits.max_detections:
        raise ProviderLimitExceeded()
    result.licenses.append(fact)


def deduplicate_facts(results: list[LicenseProviderResult]) -> list[LicenseEvidence]:
    """Merge observations only when the identity, scope, kind and location agree."""
    unique = {}
    for result in results:
        if result.status not in {ScanStatus.SUCCESS, ScanStatus.PARTIAL}:
            continue
        for fact in result.licenses:
            span = fact.evidence.source_span
            package = fact.package
            key = (package.name if package else None, package.version if package else None,
                   package.purl if package else None, fact.license_expression,
                   span.path, span.start_line, span.end_line,
                   fact.evidence.details.get("source_scope"), fact.evidence.details.get("location_precision"),
                   fact.evidence.details.get("source_kind"))
            if key not in unique:
                from copy import deepcopy
                unique[key] = deepcopy(fact)
                continue
            old = unique[key]
            for prov in fact.provenance:
                if prov not in old.provenance:
                    old.provenance.append(prov)
            for dependency in fact.dependencies:
                if dependency not in old.dependencies:
                    old.dependencies.append(dependency)
            old.evidence.details["provenance"] = [asdict(p) for p in old.provenance]
    return list(unique.values())


def sanitize_result(result: LicenseProviderResult, context: ScanContext | None = None) -> LicenseProviderResult:
    from ...core.redaction import sanitize_value
    from ...secrets import SecretScanner

    redactor = SecretScanner(b"license-projection-no-fingerprints")
    sanitize_value(result, redactor.redactor_for(context.files) if context else redactor)
    return result
