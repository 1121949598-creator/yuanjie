"""A's frozen 1.0 contract: evidence integrity and truthful local model use."""
import copy
import json
import math
from pathlib import Path

import pytest

from yuanjian_agent.component_security import (
    ContractError, EvidenceConstrainedScorer, IntentCapabilityInput, IntentCapabilityResult,
)

FIXTURES = Path(__file__).parent / "fixtures" / "v1_contract"


def fixture(name="install_skill"):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class Encoder:
    """A controlled cosine, not a substitute for the separate real-model smoke run."""
    def __init__(self, cosine):
        self.cosine = cosine
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        return [[1., 0.]] + [[self.cosine, math.sqrt(1 - self.cosine ** 2)] for _ in texts[1:]]


def run(payload, similarity=0.8):
    return EvidenceConstrainedScorer(encoder=Encoder(similarity)).score(payload).to_dict()


@pytest.mark.parametrize("name,cosine,relation,count", [
    ("install_skill", .8, "justified", 1),
    ("release_agent", .1, "inconsistent", 2),
])
def test_a_examples_have_valid_per_capability_outputs(name, cosine, relation, count):
    payload = fixture(name)
    original = copy.deepcopy(payload)
    result = EvidenceConstrainedScorer(encoder=Encoder(cosine)).score(IntentCapabilityInput.from_mapping(payload))
    assert isinstance(result, IntentCapabilityResult)
    out = result.to_dict()
    assert payload == original
    assert out["status"] == "success"
    assert out["component_id"] == payload["component"]["component_id"]
    assert out["scene"] == payload["scene"]
    assert out["schema_version"] == "1.0"
    assert out["summary"]["total"] == count
    assert out["summary"]["by_relation"][relation] == count
    assert len({a["assessment_id"] for a in out["assessments"]}) == count
    evidence_ids = {e["evidence_id"] for e in payload["evidence"]}
    for assessment in out["assessments"]:
        assert assessment["relation"] == relation
        assert assessment["evidence_refs"]
        assert set(assessment["evidence_refs"]) <= evidence_ids
        assert 0 <= assessment["score"] <= 1
        assert assessment["model"]["used"] is True
        assert assessment["model"]["provider"] == "local"
        assert assessment["uncertainty"]["level"] in {"low", "medium", "high"}
        for reason in assessment["reasons"]:
            assert set(reason) == {"code", "message", "evidence_refs"}
            assert set(reason["evidence_refs"]) <= set(assessment["evidence_refs"])
    assert out["summary"]["max_score"] == max(a["score"] for a in out["assessments"])
    json.dumps(out, allow_nan=False)


def test_risk_score_increases_with_disagreement():
    payload = fixture("release_agent")
    high = run(payload, .1)["summary"]["max_score"]
    low = run(payload, .8)["summary"]["max_score"]
    assert high > low
    assert all(a["relation"] != "inconsistent" for a in run(payload, .8)["assessments"])


@pytest.mark.parametrize("omit_field", [False, True])
def test_missing_purpose_does_not_call_model(omit_field):
    payload = fixture()
    payload["component"]["declared_purpose"] = ""
    if omit_field:
        del payload["component"]["declared_purpose"]
    encoder = Encoder(.8)
    out = EvidenceConstrainedScorer(encoder=encoder).score(payload).to_dict()
    assert out["status"] == "partial"
    assert out["assessments"][0]["relation"] == "insufficient_evidence"
    assert out["assessments"][0]["model"]["used"] is False
    assert encoder.calls == 0


@pytest.mark.parametrize("field,status", [("component", "partial"), ("component", "unresolved"),
                                          ("parser", "partial"), ("parser", "unavailable"), ("parser", "failed")])
def test_partial_coverage_never_gives_justified(field, status):
    payload = fixture()
    payload[field]["extraction_status" if field == "component" else "status"] = status
    out = run(payload)
    assert out["status"] != "success"
    assert all(a["relation"] != "justified" for a in out["assessments"])


def test_dangling_capability_is_isolated_and_boundary_refs_are_checked():
    payload = fixture("release_agent")
    payload["capabilities"][0]["evidence_refs"] = ["missing"]
    payload["boundaries"][0]["evidence_refs"].append("missing")
    out = run(payload, .1)
    assert out["status"] == "partial"
    assert [a["capability_id"] for a in out["assessments"]] == ["cap_credential_001"]
    assert "missing" not in json.dumps(out)
    assert out["warnings"]


@pytest.mark.parametrize("field", ["evidence", "capabilities"])
def test_empty_inputs_are_not_success(field):
    payload = fixture()
    payload[field] = []
    out = run(payload)
    assert out["status"] != "success"
    assert out["assessments"] == []
    assert out["warnings"]


def test_model_failure_falls_back_without_exception_or_secret_leak():
    class Broken:
        def encode(self, texts):
            raise RuntimeError(r"C:\private\model sk-real-secret-value")

    out = EvidenceConstrainedScorer(encoder=Broken()).score(fixture()).to_dict()
    assert out["status"] == "partial"
    assert out["assessments"][0]["relation"] == "needs_review"
    model = out["assessments"][0]["model"]
    assert model["used"] is False and model["provider"] == "builtin"
    serialized = json.dumps(out)
    assert "private" not in serialized and "sk-real" not in serialized


def test_one_encoder_failure_keeps_other_capability_result():
    class Flaky(Encoder):
        def encode(self, texts):
            if self.calls == 0:
                self.calls += 1
                raise RuntimeError("private failure")
            return super().encode(texts)

    out = EvidenceConstrainedScorer(encoder=Flaky(.1)).score(fixture("release_agent")).to_dict()
    assert out["status"] == "partial"
    assert len(out["assessments"]) == 2
    assert [a["model"]["used"] for a in out["assessments"]] == [False, True]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version="2.0"),
    lambda p: p.update(scene="invalid"),
    lambda p: p["capabilities"][0].update(impact=True),
    lambda p: p["capabilities"][0].update(confidence=float("nan")),
    lambda p: p["evidence"][0]["source_span"].update(path=r"C:\private\source.py"),
    lambda p: p["evidence"][0]["source_span"].update(path="../source.py"),
    lambda p: p["evidence"].append(copy.deepcopy(p["evidence"][0])),
    lambda p: p["capabilities"].append(copy.deepcopy(p["capabilities"][0])),
    lambda p: p["boundaries"][0].update(credential_use="false"),
    lambda p: p.pop("parser"),
])
def test_invalid_contract_raises_fixed_error(mutation):
    payload = fixture()
    mutation(payload)
    with pytest.raises(ContractError) as caught:
        run(payload)
    assert str(caught.value) == "invalid_intent_capability_input"


def test_controls_and_boundaries_of_other_capability_do_not_justify_unknown_scope():
    payload = fixture()
    second = copy.deepcopy(payload["capabilities"][0])
    second.update(capability_id="cap_other", controls=[], resource="unknown", evidence_refs=["ev_other"])
    payload["capabilities"].append(second)
    extra = copy.deepcopy(payload["evidence"][0])
    extra["evidence_id"] = "ev_other"
    payload["evidence"].append(extra)
    out = run(payload)
    assert [a["relation"] for a in out["assessments"]] == ["justified", "needs_review"]
    assert out["assessments"][1]["evidence_refs"] == ["ev_other"]


@pytest.mark.parametrize("cosine,expected", [(.29, "inconsistent"), (.30, "needs_review"), (.8, "needs_review")])
def test_low_similarity_is_required_even_for_sensitive_capabilities(cosine, expected):
    assert all(a["relation"] == expected for a in run(fixture("release_agent"), cosine)["assessments"])


def test_long_valid_capability_id_still_has_valid_stable_assessment_id():
    data = fixture()
    data["capabilities"][0]["capability_id"] = "a" * 128
    out = run(data)
    assert out["assessments"][0]["assessment_id"] == run(data)["assessments"][0]["assessment_id"]


def test_local_model_with_wrong_hash_is_reported_as_unused(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"not the pinned model")
    from yuanjian_agent.component_security.semantic import LocalSentenceTransformerEncoder
    with pytest.raises(ValueError, match="model_hash_mismatch"):
        LocalSentenceTransformerEncoder(tmp_path, expected_sha256="0" * 64).encode(["test"])
    out = EvidenceConstrainedScorer.from_local_model(tmp_path).score(fixture()).to_dict()
    assert out["status"] == "partial"
    assert out["assessments"][0]["model"]["used"] is False


def test_public_output_does_not_echo_parser_details_or_excerpts():
    data = fixture()
    data["parser"]["warnings"] = [r"C:\private\secret sk-live-SENSITIVE"]
    data["evidence"][0]["masked_excerpt"] = "sk-live-SENSITIVE"
    data["evidence"][0]["details"]["private"] = "sk-live-SENSITIVE"
    out = run(data)
    assert out["status"] == "partial"
    assert out["assessments"][0]["relation"] != "justified"
    assert "SENSITIVE" not in json.dumps(out)
    assert "private" not in json.dumps(out)


def test_result_validator_rejects_invented_evidence_id():
    payload = fixture()
    result = run(payload)
    result["assessments"][0]["evidence_refs"].append("ev_invented")
    with pytest.raises(ContractError, match="invalid_intent_capability_result"):
        IntentCapabilityResult(result).validate(IntentCapabilityInput.from_mapping(payload))
