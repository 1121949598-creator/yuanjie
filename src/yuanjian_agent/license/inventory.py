"""Explicit safe inventory projection; Store never needs provider-specific JSON."""
from dataclasses import asdict, replace
import json
import re

from packaging import __version__ as packaging_version

from ..core.identifiers import stable_id
from ..core.scanner import ScanStatus
from ..models import Evidence, Severity, SourceSpan
from .adapters.base import atom, package_from_purl, relative_path, requirement
from .catalog import CATALOG_VERSION
from .models import LicenseAssessment, PackageEvidence
from .policy import POLICY_VERSION
from .spdx import NORMALIZER_VERSION, normalize_spdx


MAX_INVENTORY_RECORDS = 2000  # Per collection; truncation is explicit and partial.
MAX_INVENTORY_BYTES = 8 * 1024 * 1024


def safe_provenance(items):
    output = []
    for item in items[:8]:
        projected = {key: atom(value, optional=True) for key, value in asdict(item).items()}
        if projected not in output:
            output.append(projected)
    return output


def safe_package(package):
    if package is None:
        return None
    purl = package_from_purl(package.purl, None).purl if package.purl else None
    identity = package.identifier
    if identity is not None and (len(identity) > 1024 or not re.fullmatch(
            r"[A-Za-z0-9._+-]+:[A-Za-z0-9._/-]*:[A-Za-z0-9._+~-]+:[A-Za-z0-9._+~-]*", identity)):
        identity = None
    return PackageEvidence(atom(package.name), atom(package.version, optional=True), purl,
                           package.provenance[:8], identity)


def package_id(package):
    return stable_id("package", package.purl or package.identifier or package.name, package.version or "")


def prepare_fact(fact):
    """Do not copy upstream excerpts or arbitrary Evidence.details into L2 output."""
    normalized = normalize_spdx(fact.license_expression)
    span = fact.evidence.source_span
    path = relative_path(span.path)
    if type(span.start_line) is not int or type(span.end_line) is not int or not 1 <= span.start_line <= span.end_line:
        raise ValueError("Invalid license location")
    details = {"provenance": safe_provenance(fact.provenance),
               "source_kind": atom(fact.evidence.details.get("source_kind"), optional=True),
               "source_scope": atom(fact.evidence.details.get("source_scope"), optional=True),
               "location_precision": atom(fact.evidence.details.get("location_precision"), optional=True)}
    return replace(fact, source=atom(fact.source), package=safe_package(fact.package),
                   license_expression=normalized.original_expression, normalization=normalized,
                   evidence=Evidence(SourceSpan(path, span.start_line, span.end_line),
                                     "[upstream text withheld]", details))


def fact_id(fact):
    span = fact.evidence.source_span
    normalized = fact.normalization
    return stable_id("license", package_id(fact.package) if fact.package else "", span.path,
                     str(span.start_line), str(span.end_line),
                     fact.evidence.details.get("source_kind") or "",
                     fact.evidence.details.get("source_scope") or "",
                     fact.evidence.details.get("location_precision") or "",
                     normalized.original_expression or "", normalized.status, normalized.reason)


class LicenseInventory:
    def __init__(self):
        self.packages, self.dependencies, self.licenses, self.assessments = {}, {}, {}, {}
        self.bytes = 0
        self.dropped = 0
        self.issues = set()

    def _fits(self, rows):
        size = len(json.dumps(rows, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if self.bytes + size > MAX_INVENTORY_BYTES:
            self.dropped += 1
            self.issues.add("inventory_limit")
            return False
        self.bytes += size
        return True

    def _room(self, collection):
        if len(collection) >= MAX_INVENTORY_RECORDS:
            self.dropped += 1
            self.issues.add("inventory_limit")
            return False
        return True

    def add_package(self, package):
        package = safe_package(package)
        if package is None:
            return None
        key = package_id(package)
        row = {"id": key, "name": package.name, "version": package.version, "purl": package.purl,
               "identifier": package.identifier, "provenance": safe_provenance(package.provenance)}
        if key in self.packages:
            old = self.packages[key]
            for prov in row["provenance"]:
                if prov not in old["provenance"] and len(old["provenance"]) < 8 and self._fits(prov):
                    old["provenance"].append(prov)
            if not old["identifier"] and row["identifier"] and self._fits(row["identifier"]):
                old["identifier"] = row["identifier"]
            return key
        if self._room(self.packages) and self._fits(row):
            self.packages[key] = row
            return key
        return None

    def add_dependency(self, dependency):
        owner = self.add_package(dependency.package)
        if owner is None:
            return None
        row = {"package_id": owner, "manifest_path": relative_path(dependency.manifest_path),
               "relationship": atom(dependency.relationship), "scope": atom(dependency.scope, optional=True),
               "requirement": requirement(dependency.requirement),
               "from_package": None, "provenance": safe_provenance(dependency.provenance)}
        # Parent coordinates are already projected by L1. Revalidate their shape.
        if dependency.from_package:
            parent = dependency.from_package
            if parent.startswith("pkg:"):
                row["from_package"] = package_from_purl(parent, None).purl
            elif len(parent) <= 1024 and re.fullmatch(r"[A-Za-z0-9._+~:/-]+", parent) and len(parent.split(":")) == 4:
                row["from_package"] = parent
        key = stable_id("dependency", *(str(row[k] or "") for k in
                        ("package_id", "manifest_path", "relationship", "scope", "requirement", "from_package")))
        row["id"] = key
        if key in self.dependencies:
            old = self.dependencies[key]
            for prov in row["provenance"]:
                if prov not in old["provenance"] and len(old["provenance"]) < 8 and self._fits(prov):
                    old["provenance"].append(prov)
            return key
        if self._room(self.dependencies) and self._fits(row):
            self.dependencies[key] = row
            return key
        return None

    def add_fact(self, fact, assessment, findings):
        package = self.add_package(fact.package)
        if fact.package is not None and package is None:
            return False
        key = fact_id(fact)
        row = {"id": key, "package_id": package, "location": asdict(fact.evidence.source_span),
               "source": fact.source, **fact.evidence.details, "normalization": asdict(fact.normalization)}
        review = {"id": stable_id("assessment", key), "license_id": key, "package_id": package,
                  **asdict(assessment), "finding_ids": [finding.id for finding in findings]}
        if review["severity"] is not None:
            review["severity"] = review["severity"].value
        if self._room(self.licenses) and self._room(self.assessments) and self._fits([row, review]):
            self.licenses[key] = row
            self.assessments[review["id"]] = review
            return True
        return False

    def finish(self, outputs, status):
        # Packages without a source location remain inventory-only, never receive
        # a fabricated manifest. Their missing assessment is explicit and linked.
        observed = {a["package_id"] for a in self.assessments.values()}
        for key in sorted(self.packages.keys() - observed):
            self.issues.add("unlocated_package_review")
            assessment = LicenseAssessment("unknown", Severity.MEDIUM, True, "no_located_license_fact", policy_status="unavailable")
            row = {"id": stable_id("assessment", key), "license_id": None, "package_id": key,
                   **asdict(assessment), "finding_ids": []}
            row["severity"] = row["severity"].value
            if self._room(self.assessments) and self._fits(row):
                self.assessments[row["id"]] = row
        categories = {}
        for item in self.assessments.values():
            category = item["classification"]
            categories[category] = categories.get(category, 0) + 1
        return {"schema_version": 1, "policy_version": POLICY_VERSION, "catalog_version": CATALOG_VERSION,
                "normalizer_version": NORMALIZER_VERSION, "packaging_version": packaging_version,
                "summary": {"packages": len(self.packages), "dependencies": len(self.dependencies),
                            "licenses": len(self.licenses), "assessments": len(self.assessments),
                            "manual_review_required": sum(a["manual_review_required"] for a in self.assessments.values()),
                            "by_classification": categories},
                "coverage": {"status": str(status), "inventory_complete": not self.issues,
                             "providers_complete": any(o.status == ScanStatus.SUCCESS for o in outputs)
                             and all(o.status in {ScanStatus.SUCCESS, ScanStatus.DISABLED} for o in outputs),
                             "assessment_complete": all(a["policy_status"] == "success" for a in self.assessments.values())
                             and any(o.status == ScanStatus.SUCCESS for o in outputs) and not self.issues,
                             "dropped_records": self.dropped, "issues": sorted(self.issues)},
                "providers": [{"name": o.name, "status": str(o.status), "reason": o.reason_code,
                               "version": o.version, "execution_mode": o.execution_mode,
                               "scan_error_count": o.scan_error_count} for o in outputs],
                "packages": list(self.packages.values()), "dependencies": list(self.dependencies.values()),
                "licenses": list(self.licenses.values()), "assessments": list(self.assessments.values())}
