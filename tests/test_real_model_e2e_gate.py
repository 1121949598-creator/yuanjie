"""Acceptance gate tests; these do NOT load or evaluate an actual AI model."""
import copy
import importlib.util
from pathlib import Path

import pytest

from yuanjian_agent.component_security.v1 import MODEL_NAME, MODEL_REVISION


SPEC = importlib.util.spec_from_file_location(
    "real_model_e2e", Path(__file__).parents[1] / "experiments" / "run_real_model_e2e.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def payload(real=True):
    status = "success" if real else "partial"
    return {"status": status, "components": [{"result": {
        "status": status, "assessments": [{
            "model": {"used": real, "name": MODEL_NAME, "version": MODEL_REVISION},
            "evidence_refs": ["synthetic_evidence"], "relation": "needs_review",
        }],
    }}], "warnings": [] if real else ["semantic_model_unavailable"]}


def test_gate_accepts_explicit_model_use_and_visible_fallback():
    assert MODULE.validate_model_payload(payload(), real_model=True) == 1
    assert MODULE.validate_model_payload(payload(False), real_model=False) == 1


@pytest.mark.parametrize("mutation", [
    "empty_components", "empty_assessments", "false_model", "truthy_not_boolean",
    "wrong_version", "missing_evidence", "partial_component", "partial_module",
])
def test_real_model_gate_rejects_false_success(mutation):
    value = copy.deepcopy(payload())
    component = value["components"][0]["result"]
    assessment = component["assessments"][0]
    if mutation == "empty_components":
        value["components"] = []
    elif mutation == "empty_assessments":
        component["assessments"] = []
    elif mutation == "false_model":
        assessment["model"]["used"] = False
    elif mutation == "truthy_not_boolean":
        assessment["model"]["used"] = "true"
    elif mutation == "wrong_version":
        assessment["model"]["version"] = "unverified"
    elif mutation == "missing_evidence":
        assessment["evidence_refs"] = []
    elif mutation == "partial_component":
        component["status"] = "partial"
    elif mutation == "partial_module":
        value["status"] = "partial"
    with pytest.raises(RuntimeError):
        MODULE.validate_model_payload(value, real_model=True)


def test_fallback_must_be_visible_not_a_successful_safety_claim():
    value = payload(False)
    value["warnings"] = []
    with pytest.raises(RuntimeError, match="fallback_warning_missing"):
        MODULE.validate_model_payload(value, real_model=False)
    value = payload(False)
    value["components"][0]["result"]["assessments"][0]["relation"] = "justified"
    with pytest.raises(RuntimeError, match="fallback_not_marked_for_review"):
        MODULE.validate_model_payload(value, real_model=False)
