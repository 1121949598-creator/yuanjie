"""Bound untrusted input before using packaging's public SPDX validator.

No upstream exception text is exposed. Unsafe/oversized originals are withheld,
but their observations and fixed review reasons remain available.
"""
import re

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression

from .models import EXPRESSION_LIMIT, EXPRESSION_WITHHELD, SpdxNormalizationResult


MAX_EXPRESSION_LENGTH = 4096
MAX_TOKENS = 256
MAX_DEPTH = 16
MAX_LICENSE_IDS = 64
MAX_INVALID_ORIGINAL_LENGTH = 256
NORMALIZER_VERSION = "1"


def normalize_spdx(expression: str | None) -> SpdxNormalizationResult:
    def review(status, reason, original=None):
        return SpdxNormalizationResult(original, None, status, True, reason)

    if expression is None:
        return review("missing", "missing_expression")
    if not isinstance(expression, str):
        return review("unsupported", "unsupported_input_type")
    if len(expression) > MAX_EXPRESSION_LENGTH or expression == EXPRESSION_LIMIT:
        return review("unsupported", "expression_length_limit")
    if not expression.strip():
        return review("missing", "missing_expression")
    if expression == EXPRESSION_WITHHELD or not re.fullmatch(r"[A-Za-z0-9().+ :_\-\t\r\n]+", expression):
        return review("invalid", "unsafe_expression_withheld")
    if ":" in expression:
        # DocumentRef references are outside packaging's License-Expression subset.
        if re.fullmatch(r"DocumentRef-[A-Za-z0-9.-]+:LicenseRef-[A-Za-z0-9.-]+", expression):
            return review("unsupported", "document_reference_unsupported", expression)
        return review("invalid", "unsafe_expression_withheld")
    tokens = re.findall(r"\(|\)|[^\s()]+", expression)
    if len(tokens) > MAX_TOKENS:
        return review("unsupported", "token_limit")
    depth = 0
    for token in tokens:
        depth += (token == "(") - (token == ")")
        if depth > MAX_DEPTH:
            return review("unsupported", "parenthesis_depth_limit")
    ids = [t for i, t in enumerate(tokens) if t.upper() not in {"AND", "OR", "WITH", "(", ")"}
           and (i == 0 or tokens[i - 1].upper() != "WITH")]
    if len(ids) > MAX_LICENSE_IDS:
        return review("unsupported", "license_id_limit")
    try:
        canonical = str(canonicalize_license_expression(expression))
    except InvalidLicenseExpression:
        # Includes unknown SPDX identifiers; do not guess from exception text.
        original = expression if len(expression) <= MAX_INVALID_ORIGINAL_LENGTH else None
        return review("invalid", "invalid_expression_or_identifier", original)
    except (RecursionError, ValueError):
        return review("unsupported", "normalizer_limit")
    if len(canonical) > MAX_EXPRESSION_LENGTH:
        return review("unsupported", "canonical_expression_length_limit")
    canonical_tokens = re.findall(r"\(|\)|[^\s()]+", canonical)
    licenses, exceptions = [], []
    for i, token in enumerate(canonical_tokens):
        if token in {"AND", "OR", "WITH", "(", ")"}:
            continue
        destination = exceptions if i and canonical_tokens[i - 1] == "WITH" else licenses
        if token not in destination:
            destination.append(token)
    referenced = any(t.startswith("LicenseRef-") for t in licenses)
    return SpdxNormalizationResult(expression, canonical, "license_ref" if referenced else "canonical",
                                   referenced, "license_reference_review" if referenced else "canonicalized",
                                   licenses, exceptions)
