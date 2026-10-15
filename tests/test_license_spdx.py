from dataclasses import asdict
import json

import pytest

from yuanjian_agent.license import spdx
from yuanjian_agent.license.models import EXPRESSION_LIMIT, EXPRESSION_WITHHELD


@pytest.mark.parametrize("expression,canonical", [
    ("MIT", "MIT"), ("Apache-2.0", "Apache-2.0"), ("mit", "MIT"),
    ("aPaChe-2.0", "Apache-2.0"), ("MIT and GPL-3.0-only", "MIT AND GPL-3.0-only"),
    ("MIT or Apache-2.0", "MIT OR Apache-2.0"),
    ("mit and (apache-2.0 or bsd-2-clause)", "MIT AND (Apache-2.0 OR BSD-2-Clause)"),
    ("GPL-2.0-only with classpath-exception-2.0", "GPL-2.0-only WITH Classpath-exception-2.0"),
    ("  MIT  ", "MIT"), ("MIT\nOR\tApache-2.0", "MIT OR Apache-2.0"),
])
def test_canonicalization(expression, canonical):
    result = spdx.normalize_spdx(expression)
    assert result.status == "canonical" and result.canonical_expression == canonical
    assert result.original_expression == expression
    assert not result.manual_review_required
    assert json.loads(json.dumps(asdict(result)))["canonical_expression"] == canonical


def test_exception_is_separate_from_license_ids():
    result = spdx.normalize_spdx("GPL-2.0-only WITH Classpath-exception-2.0 AND MIT")
    assert result.license_ids == ["GPL-2.0-only", "MIT"]
    assert result.exception_ids == ["Classpath-exception-2.0"]


@pytest.mark.parametrize("expression", ["LicenseRef-Custom", "licenseref-Custom", "MIT AND LicenseRef-Example"])
def test_license_refs_require_review(expression):
    result = spdx.normalize_spdx(expression)
    assert result.status == "license_ref" and result.manual_review_required
    assert "LicenseRef-" in result.canonical_expression


@pytest.mark.parametrize("expression", [None, "", "  ", "\n\t"])
def test_missing(expression):
    result = spdx.normalize_spdx(expression)
    assert result.status == "missing" and result.manual_review_required
    assert result.canonical_expression is None


@pytest.mark.parametrize("expression", [
    "MIT OR", "(MIT", "MIT)", "MIT Apache-2.0", "Unknown-License-Example", "unknown",
    "MIT WITH Unknown-exception", "(GPL-2.0-only) WITH Classpath-exception-2.0",
    "MIT AND ()", "MIT & Apache-2.0", "LicenseRef-", "MIT WITH MIT",
])
def test_invalid_facts_are_retained_as_review(expression):
    result = spdx.normalize_spdx(expression)
    assert result.status == "invalid" and result.manual_review_required
    assert result.canonical_expression is None
    assert result.reason in {"invalid_expression_or_identifier", "unsafe_expression_withheld"}


@pytest.mark.parametrize("expression,reason", [
    ("x" * 4097, "expression_length_limit"),
    (" " * 100_000, "expression_length_limit"),
    (" OR ".join(["MIT"] * 130), "token_limit"),
    ("(" * 17 + "MIT" + ")" * 17, "parenthesis_depth_limit"),
    (" AND ".join(["MIT"] * 65), "license_id_limit"),
    (EXPRESSION_LIMIT, "expression_length_limit"),
], ids=["length", "whitespace-length", "tokens", "depth", "ids", "provider-limit-marker"])
def test_limits_run_before_packaging(expression, reason, monkeypatch):
    def forbidden(*args):
        pytest.fail("Over-budget input reached packaging")
    monkeypatch.setattr(spdx, "canonicalize_license_expression", forbidden)
    result = spdx.normalize_spdx(expression)
    assert result.status == "unsupported" and result.reason == reason and result.manual_review_required
    assert result.original_expression is None
    assert len(json.dumps(asdict(result))) < 400


@pytest.mark.parametrize("expression", ["C:/target/license", "/etc/license", "https://u:password@example.org",
                                         "MIT\x00secret", EXPRESSION_WITHHELD])
def test_unsafe_expression_not_echoed(expression):
    result = spdx.normalize_spdx(expression)
    assert result.manual_review_required and result.original_expression is None
    assert expression not in json.dumps(asdict(result))


def test_document_ref_is_explicitly_unsupported():
    result = spdx.normalize_spdx("DocumentRef-Example:LicenseRef-Custom")
    assert result.status == "unsupported" and result.reason == "document_reference_unsupported"


@pytest.mark.parametrize("expression", [3, [], {}])
def test_nonstring_input_is_bounded_unsupported(expression):
    assert spdx.normalize_spdx(expression).status == "unsupported"


def test_exact_supported_bounds():
    assert spdx.normalize_spdx("(" * 16 + "MIT" + ")" * 16).status == "canonical"
    assert spdx.normalize_spdx(" AND ".join(["MIT"] * 64)).status == "canonical"


def test_canonicalization_growth_is_also_bounded():
    expression = "(LicenseRef-" + "a" * 4073 + ")AND(MIT)"
    assert len(expression) <= 4096
    result = spdx.normalize_spdx(expression)
    assert result.status == "license_ref"
    expression = "(LicenseRef-" + "a" * 4075 + ")AND(MIT)"
    assert len(expression) == 4096
    result = spdx.normalize_spdx(expression)
    assert result.status == "unsupported" and result.reason == "canonical_expression_length_limit"


def test_long_invalid_original_is_not_a_context_container():
    expression = "Unrecognized-" + "a" * 300
    result = spdx.normalize_spdx(expression)
    assert result.status == "invalid" and result.original_expression is None
