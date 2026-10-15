"""Local semantic relation scorer constrained by B's static evidence.

The encoder supplies sentence vectors only. Rules retain ownership of the
capability facts, sensitive boundaries and fail-closed decisions.
"""

from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .scoring import Assessment, ComponentContext, assess


class SentenceEncoder(Protocol):
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


@dataclass(slots=True)
class LocalSentenceTransformerEncoder:
    """Load model weights from a local directory; never invoke a model API."""

    model_dir: Path
    expected_sha256: str | None = None
    _model: object | None = None

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not self.model_dir.is_dir():
            raise FileNotFoundError(f"local model directory missing: {self.model_dir}")
        if self._model is None:
            if self.expected_sha256 is not None:
                with (self.model_dir / "model.safetensors").open("rb") as weights:
                    actual_hash = hashlib.file_digest(weights, "sha256").hexdigest()
                if actual_hash.lower() != self.expected_sha256.lower():
                    raise ValueError("model_hash_mismatch")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(str(self.model_dir), device="cpu", local_files_only=True)
        return self._model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) == 0:
        return None
    if not all(math.isfinite(float(x)) for x in (*left, *right)):
        return None
    left_norm = math.sqrt(sum(float(x) ** 2 for x in left))
    right_norm = math.sqrt(sum(float(x) ** 2 for x in right))
    if not left_norm or not right_norm:
        return None
    return sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)


def assess_semantic(
    context: ComponentContext, *, encoder: SentenceEncoder,
    model_name: str, model_version: str,
) -> Assessment:
    """Relate declared purpose to evidenced capability and boundary facts.

    Thresholds are engineering defaults, not calibrated probabilities. The
    small synthetic evaluation is insufficient for deployment claims.
    """
    preflight = assess(context, method="rule")
    if preflight.relation == "insufficient_evidence":
        return Assessment(preflight.relation, 0.0, preflight.reasons,
                          preflight.uncertainty, preflight.evidence_refs,
                          model_name, model_version)

    texts = [context.declared_purpose] + [
        " ".join((fact.capability, fact.action, fact.resource)).strip()
        for fact in context.capabilities
    ]
    try:
        vectors = encoder.encode(texts)
        if len(vectors) != len(texts):
            raise ValueError("encoder returned wrong number of vectors")
        similarities = [_cosine(vectors[0], vector) for vector in vectors[1:]]
        if any(value is None for value in similarities):
            raise ValueError("encoder returned invalid vectors")
    except (OSError, ImportError, ValueError, TypeError, OverflowError, RuntimeError):
        return Assessment("insufficient_evidence", 0.0,
                          ("Local semantic encoding was unavailable or invalid",),
                          ("local_semantic_model_unavailable",), preflight.evidence_refs, model_name, model_version)

    weakest = min(similarities)
    maximum_impact = max(fact.impact for fact in context.capabilities)
    broad_boundary = bool(context.boundary.get("credential_use")) or any(
        str(context.boundary.get(key, "")).lower() in {"any", "all", "*", "environment", "unrestricted"}
        for key in ("data_scope", "network_target")
    )
    low_fact_confidence = min(fact.confidence for fact in context.capabilities) < 0.6
    sensitive = maximum_impact >= 4 or broad_boundary
    if weakest < 0.20 and sensitive:
        relation = "inconsistent"
    elif weakest >= 0.45 and not sensitive and not low_fact_confidence and context.controls:
        relation = "justified"
    else:
        relation = "needs_review"
    reasons = (
        f"Lowest declared-purpose/capability cosine similarity is {weakest:.3f}",
        f"Highest evidenced impact is {maximum_impact}/5",
        "Sensitive or broad boundary is present" if sensitive else "Boundary is limited by supplied facts",
    )
    uncertainty = ["Cosine similarity is not a probability or a safety verdict"]
    if low_fact_confidence:
        uncertainty.append("At least one static fact has low extraction confidence")
    if context.scene == "release_precheck":
        uncertainty.append("Release decision requires source-owner review")
    return Assessment(relation, round(max(0.0, min(1.0, weakest)), 4), reasons,
                      tuple(uncertainty), preflight.evidence_refs, model_name, model_version)
