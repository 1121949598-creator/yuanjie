"""Strict, Web-independent validation for A's frozen 1.0 contract.

Validation errors are fixed codes. Never include a submitted value or a raw
exception in messages returned across the backend boundary.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

RELATIONS = ("justified", "needs_review", "inconsistent", "insufficient_evidence")
STATUSES = {"success", "partial", "unavailable", "failed"}
SCENES = {"install_precheck", "release_precheck"}
_ABSOLUTE_ID = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/])")


class ContractError(ValueError):
    def __init__(self, code="invalid_intent_capability_input"):
        super().__init__(code)


def _require(condition):
    if not condition:
        raise ContractError()


def _text(value):
    _require(isinstance(value, str))


def _identifier(value):
    # The frozen contract specifies strings, not an ASCII/length restriction.
    _require(isinstance(value, str) and bool(value.strip())
             and not _ABSOLUTE_ID.match(value) and not any(ord(c) < 32 for c in value))


def _array(value):
    _require(isinstance(value, list))


def _strings(value, *, identifiers=False):
    _array(value)
    for entry in value:
        (_identifier if identifiers else _text)(entry)


def _number(value, low, high):
    _require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high)


def _span(value):
    _require(isinstance(value, Mapping))
    path = value["path"]
    _text(path)
    normalized = path.replace("\\", "/")
    _require(bool(normalized) and normalized not in {".", ".."}
             and not normalized.startswith("/") and ":" not in normalized
             and ".." not in PurePosixPath(normalized).parts and "\x00" not in normalized)
    for field in ("start_line", "end_line", "start_column", "end_column"):
        _require(type(value[field]) is int)
    _require(value["start_line"] >= 1 and value["end_line"] >= value["start_line"])
    _require(value["start_column"] >= 0 and value["end_column"] >= 0)
    if value["start_line"] == value["end_line"]:
        _require(value["end_column"] >= value["start_column"])


def _unique(rows, key):
    _array(rows)
    seen = set()
    for row in rows:
        _require(isinstance(row, Mapping))
        _identifier(row[key])
        _require(row[key] not in seen)
        seen.add(row[key])


@dataclass(frozen=True)
class IntentCapabilityInput:
    payload: dict[str, Any]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "IntentCapabilityInput":
        try:
            _require(isinstance(payload, Mapping))
            payload = copy.deepcopy(dict(payload))
            _require(payload["schema_version"] == "1.0")
            _identifier(payload["scan_id"])
            _require(payload["scene"] in SCENES)
            component = payload["component"]
            _require(isinstance(component, Mapping))
            component = dict(component)
            # A explicitly requires an absent purpose to fail closed, not crash.
            component.setdefault("declared_purpose", "")
            payload["component"] = component
            _identifier(component["component_id"])
            _require(component["component_type"] in {"skill", "mcp_server", "agent", "project"})
            _text(component["name"])
            _text(component["declared_purpose"])
            _require(component["extraction_status"] in {"resolved", "partial", "unresolved"})
            _strings(component["extraction_reasons"])
            _array(component["source_spans"])
            for span in component["source_spans"]:
                _span(span)
            _unique(payload["capabilities"], "capability_id")
            for cap in payload["capabilities"]:
                for key in ("capability", "action", "resource", "rule_id"):
                    _text(cap[key])
                _require(type(cap["impact"]) is int and 1 <= cap["impact"] <= 5)
                _number(cap["confidence"], 0, 1)
                _strings(cap["controls"])
                _strings(cap["evidence_refs"], identifiers=True)
            _unique(payload["boundaries"], "boundary_id")
            for boundary in payload["boundaries"]:
                _strings(boundary["data_scope"])
                _strings(boundary["network_target"])
                _require(type(boundary["credential_use"]) is bool)
                _text(boundary["execution_mode"])
                _strings(boundary["evidence_refs"], identifiers=True)
            _unique(payload["evidence"], "evidence_id")
            for evidence in payload["evidence"]:
                _span(evidence["source_span"])
                _text(evidence["masked_excerpt"])
                _require(isinstance(evidence["details"], Mapping))
            parser = payload["parser"]
            _require(isinstance(parser, Mapping) and parser["status"] in STATUSES)
            _text(parser["version"])
            _strings(parser["warnings"])
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            raise ContractError() from None
        return cls(copy.deepcopy(dict(payload)))


@dataclass(frozen=True)
class IntentCapabilityResult:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)

    def validate(self, source: IntentCapabilityInput) -> None:
        """Validate result structure and referential integrity before returning."""
        try:
            out, data = self.payload, source.payload
            _require(out["schema_version"] == "1.0")
            _require(out["component_id"] == data["component"]["component_id"])
            _require(out["scene"] == data["scene"] and out["status"] in STATUSES)
            _strings(out["warnings"])
            known_refs = {e["evidence_id"] for e in data["evidence"]}
            known_caps = {c["capability_id"] for c in data["capabilities"]}
            _unique(out["assessments"], "assessment_id")
            counted = dict.fromkeys(RELATIONS, 0)
            cap_ids = set()
            for a in out["assessments"]:
                _require(a["capability_id"] in known_caps and a["capability_id"] not in cap_ids)
                cap_ids.add(a["capability_id"])
                _require(a["relation"] in RELATIONS)
                counted[a["relation"]] += 1
                _number(a["score"], 0, 1)
                _strings(a["evidence_refs"], identifiers=True)
                _require(bool(a["evidence_refs"]) and set(a["evidence_refs"]) <= known_refs)
                _array(a["reasons"])
                _require(bool(a["reasons"]))
                for reason in a["reasons"]:
                    _text(reason["code"])
                    _text(reason["message"])
                    _strings(reason["evidence_refs"], identifiers=True)
                    _require(bool(reason["evidence_refs"]) and set(reason["evidence_refs"]) <= set(a["evidence_refs"]))
                _require(a["uncertainty"]["level"] in {"low", "medium", "high"})
                _strings(a["uncertainty"]["reasons"])
                model = a["model"]
                for field in ("name", "version", "provider", "rules_version", "feature_version"):
                    _text(model[field])
                _require(type(model["used"]) is bool)
            summary = out["summary"]
            _require(summary["total"] == len(out["assessments"]) and summary["by_relation"] == counted)
            _require(summary["max_score"] == max((a["score"] for a in out["assessments"]), default=0.0))
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            raise ContractError("invalid_intent_capability_result") from None
