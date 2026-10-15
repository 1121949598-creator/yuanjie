import json

import pytest

from yuanjian_agent.config import LicenseProviderSettings
from yuanjian_agent.license.adapters.base import InvalidProviderOutput, deduplicate_facts
from yuanjian_agent.license.adapters.ort import OrtAdapter, OrtResultProvider, OrtResultParser
from yuanjian_agent.license.adapters.scancode import ScanCodeResultParser
from license_provider_support import ORT, SCANCODE, context_for, safe_payload


def test_ort_import_maps_metadata_graph_and_scanner_provenance(tmp_path):
    result = OrtResultProvider().collect(context_for(tmp_path))
    assert result.status == "success"
    assert result.version == "50.0.0" and result.execution_mode == "result-import"
    assert len(result.dependencies) == 1
    dependency = result.dependencies[0]
    assert dependency.package.name == "foo" and dependency.package.purl == "pkg:pypi/foo@1.0"
    assert dependency.manifest_path == "requirements.txt" and dependency.scope == "runtime"
    assert dependency.from_package == "PIP::synthetic-project:1.0"
    assert dependency.package.identifier == "PyPI::foo:1.0"
    kinds = {f.provenance[0].source_kind for f in result.licenses}
    assert kinds >= {"declared_package_metadata", "processed_declared_license", "concluded_license", "detected_license"}
    detected = next(f for f in result.licenses if f.provenance[0].source_kind == "detected_license")
    assert detected.package.name == "foo"
    assert detected.provenance[0].origin_provider == "scancode"
    assert detected.provenance[0].origin_version == "32.4.1"
    assert detected.evidence.source_span.start_line == 2
    safe_payload(result)


def test_ort_never_runs_analyzer_even_if_binary_exists(tmp_path, monkeypatch):
    context = context_for(tmp_path)
    (context.project_root / "ort-result.json").write_text(ORT.read_text())
    (context.project_root / ".ort.yml").write_text("analyzeSetupPyInsecurely: true")
    context.config.license_providers.ort_result_path = None
    def forbidden(*args, **kwargs):
        pytest.fail("ORT import attempted executable detection or execution")
    monkeypatch.setattr("shutil.which", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    assert OrtResultProvider().collect(context).reason_code == "result_not_configured"
    context.config.scanners.enable_ort = False
    assert OrtResultProvider().collect(context).status == "disabled"
    assert not (tmp_path / "target-executed").exists()


@pytest.mark.parametrize("where", ["project", "relative", "missing", "corrupt", "oversize"])
def test_ort_input_trust_and_read_limits(where, tmp_path):
    context = context_for(tmp_path)
    if where == "project":
        path = context.project_root / "analyzer-result.json"
        path.write_text(ORT.read_text())
        context.config.license_providers.ort_result_path = path
    if where == "relative": context.config.license_providers.ort_result_path = "ort.json"
    if where == "missing": context.config.license_providers.ort_result_path = tmp_path / "missing.json"
    if where == "corrupt": context.config.license_providers.ort_result_path.write_text("invalid SyntheticToken9")
    if where == "oversize": context.config.license_providers.max_json_bytes = 10
    result = OrtResultProvider().collect(context)
    assert result.status in {"unavailable", "failed"}
    assert not result.licenses
    safe_payload(result)


def test_ort_classical_scopes_and_curated_wrapper():
    data = json.loads(ORT.read_text())
    analyzer = data["analyzer"]["result"]
    analyzer.pop("dependency_graphs")
    project = analyzer["projects"][0]
    project.pop("scope_names")
    project["scopes"] = [{"name": "runtime", "dependencies": [{"id": "PyPI::foo:1.0", "dependencies": []}]}]
    analyzer["packages"] = [{"package": p, "curations": []} for p in analyzer["packages"]]
    result = OrtResultParser().parse(data, LicenseProviderSettings())
    assert result.status == "success" and result.dependencies[0].package.name == "foo"


def test_ort_graph_uses_pkg_fragment_not_node_index_and_handles_cycles():
    data = json.loads(ORT.read_text())
    graph = data["analyzer"]["result"]["dependency_graphs"]["PIP"]
    graph["packages"] += ["PyPI::bar:2.0"]
    graph["nodes"] = [{"pkg": 1, "fragment": 2}, {"pkg": 0}]
    graph["edges"] = [{"from": 1, "to": 0}, {"from": 0, "to": 1}]
    result = OrtResultParser().parse(data, LicenseProviderSettings())
    assert result.status == "partial"  # bar metadata was not supplied.
    assert any(d.relationship == "direct" and d.package.name == "foo" for d in result.dependencies)
    assert any(d.relationship == "transitive" and d.package.name == "bar" for d in result.dependencies)
    assert any(d.from_package == "PyPI::foo:1.0" and d.package.identifier == "PyPI::bar:2.0"
               for d in result.dependencies)
    assert len(result.dependencies) <= 4


@pytest.mark.parametrize("bad", ["edge-index", "package-index", "scope", "provenance", "path", "score", "legacy-graph", "issues"])
def test_ort_partial_preserves_other_facts(bad):
    data = json.loads(ORT.read_text())
    graph = data["analyzer"]["result"]["dependency_graphs"]["PIP"]
    if bad == "edge-index": graph["edges"] = [{"from": 0, "to": 999}]
    if bad == "package-index": graph["nodes"][0]["pkg"] = -1
    if bad == "scope": graph["scopes"] = {"unmapped": [{"root": 0}]}
    if bad == "provenance": data["scanner"]["provenances"] = []
    if bad == "path": data["scanner"]["scan_results"][0]["summary"]["licenses"][0]["location"]["path"] = "../../secret"
    if bad == "score": data["scanner"]["scan_results"][0]["summary"]["licenses"][0]["score"] = -1
    if bad == "legacy-graph": graph["nodes"] = []; graph["scope_roots"] = [{"pkg": 0}]
    if bad == "issues": data["analyzer"]["result"]["issues"] = {"PIP::synthetic-project:1.0": [{"message": "SyntheticToken9"}]}
    result = OrtResultParser().parse(data, LicenseProviderSettings())
    assert result.status == "partial" and result.packages
    safe_payload(result)


@pytest.mark.parametrize("bad", ["root", "projects", "packages", "version", "version-conflict", "max-nodes", "max-dependencies", "max-detections", "missing-result", "missing-projects", "missing-scans"])
def test_ort_invalid_contract_and_limits(bad):
    data = json.loads(ORT.read_text())
    limits = LicenseProviderSettings()
    if bad == "root": data = []
    if bad == "missing-result": data["analyzer"].pop("result")
    if bad == "missing-projects": data["analyzer"]["result"].pop("projects")
    if bad == "missing-scans": data["scanner"].pop("scan_results")
    if bad == "projects": data["analyzer"]["result"]["projects"] = {}
    if bad == "packages": data["analyzer"]["result"]["packages"] = None
    if bad == "version": data["analyzer"]["environment"]["ort_version"] = "not-a-version"
    if bad == "version-conflict": data["scanner"]["environment"]["ort_version"] = "49.0.0"
    if bad == "max-nodes": limits.max_nodes = 2
    if bad == "max-dependencies":
        graph = data["analyzer"]["result"]["dependency_graphs"]["PIP"]
        graph["scopes"][":synthetic-project:1.0:runtime"] *= 3
        limits.max_dependencies = 1
    if bad == "max-detections": limits.max_detections = 1
    with pytest.raises(InvalidProviderOutput):
        OrtResultParser().parse(data, limits)


def test_direct_scancode_and_ort_wrapper_deduplicate_with_both_provenances():
    limits = LicenseProviderSettings()
    direct = ScanCodeResultParser().parse(json.loads(SCANCODE.read_text()), limits)
    wrapped = OrtResultParser().parse(json.loads(ORT.read_text()), limits)
    merged = deduplicate_facts([direct, wrapped])
    detected = [f for f in merged if f.evidence.details["source_kind"] == "detected_license"]
    assert len(detected) == 1
    assert {p.provider for p in detected[0].provenance} == {"scancode", "ort"}
    assert len(detected[0].evidence.details["provenance"]) == 2
    # Do not mutate per-provider observations or collapse differing evidence semantics.
    assert len(next(f for f in direct.licenses if f.evidence.details["source_kind"] == "detected_license").provenance) == 1
    wrapped.licenses[-1].evidence.source_span.start_line = 3
    assert len([f for f in deduplicate_facts([direct, wrapped]) if f.evidence.details["source_kind"] == "detected_license"]) == 2
