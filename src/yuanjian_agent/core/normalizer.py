from __future__ import annotations

from ..models import Finding


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """One finding per old signature; preserve every distinct evidence occurrence."""
    unique: dict[tuple, Finding] = {}
    for finding in findings:
        key = (finding.category, finding.signature)
        if key not in unique:
            unique[key] = finding
        else:
            existing = unique[key]
            for evidence in finding.evidence:
                if evidence not in existing.evidence:
                    existing.evidence.append(evidence)
    return list(unique.values())
