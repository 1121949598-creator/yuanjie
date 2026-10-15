import json

from yuanjian_agent.config import LicenseProviderSettings
from yuanjian_agent.license.adapters.scancode import ScanCodeResultParser
from license_provider_support import SCANCODE


def test_real_32_5_dependency_shape_preserves_parent_and_requirement_without_duplicates():
    data = json.loads(SCANCODE.read_text())
    data["headers"][0]["tool_version"] = "32.5.0"
    owner_uid = data["packages"][0]["package_uid"]
    nested = {
        "purl": "pkg:npm/eslint",
        "extracted_requirement": "^9.0.0",
        "scope": "devDependencies",
        "is_direct": True,
    }
    data["packages"][0]["dependencies"] = [nested]
    data["dependencies"] = [{**nested, "datafile_path": "package.json", "for_package_uid": owner_uid}]
    data["packages"][0]["datafile_paths"] = ["package.json"]
    result = ScanCodeResultParser().parse(data, LicenseProviderSettings(), "32.5.0")
    dependencies = [item for item in result.dependencies if item.package.purl == "pkg:npm/eslint"]
    assert len(dependencies) == 1
    assert dependencies[0].requirement == "^9.0.0"
    assert dependencies[0].from_package == data["packages"][0]["purl"]


def test_scan_errors_are_counted_without_retaining_messages():
    data = json.loads(SCANCODE.read_text())
    data["headers"][0]["tool_version"] = "32.5.0"
    data["headers"][0]["errors"] = ["PRIVATE HEADER ERROR"]
    data["files"][0]["scan_errors"] = ["PRIVATE FILE ERROR", "PRIVATE SECOND ERROR"]
    result = ScanCodeResultParser().parse(data, LicenseProviderSettings())
    assert result.status == "partial" and result.scan_error_count == 3
    assert "PRIVATE" not in repr(result)


def test_unknown_extra_fields_do_not_break_contract():
    data = json.loads(SCANCODE.read_text())
    data["headers"][0]["tool_version"] = "32.5.0"
    data["future_safe_field"] = {"value": 1}
    assert ScanCodeResultParser().parse(data, LicenseProviderSettings()).version == "32.5.0"


def test_32_5_anonymous_manifest_container_is_not_a_malformed_package():
    data = json.loads(SCANCODE.read_text())
    data["headers"][0]["tool_version"] = "32.5.0"
    data["files"].append({
        "path": "Cargo.lock", "type": "file", "license_detections": [], "scan_errors": [],
        "package_data": [{
            "type": "cargo", "name": None, "version": None, "purl": None,
            "declared_license_expression": None,
            "declared_license_expression_spdx": None,
            "dependencies": [{"purl": "pkg:cargo/serde@1.0.197", "extracted_requirement": "1.0.197"}],
        }],
    })
    result = ScanCodeResultParser().parse(data, LicenseProviderSettings())
    assert result.status == "success"
    assert all(package.name for package in result.packages)
    assert not any(item.evidence.source_span.path == "Cargo.lock" for item in result.licenses)
