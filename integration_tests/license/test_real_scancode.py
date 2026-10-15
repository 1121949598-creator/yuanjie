"""Explicit real-tool acceptance suite.

Run separately from unit tests:
  pytest integration_tests/license

Absence of YUANJIAN_SCANCODE_EXE is a failure, never a skipped success.
"""
from __future__ import annotations

import os
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from yuanjian_agent.config import LicenseProviderSettings, ScannerSettings, Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app


FIXTURES = Path(__file__).parents[2] / "tests" / "fixtures" / "license_projects"
EXPECTED = {
    # Package totals include dependency identities, not only the root package.
    "python": (3, 2, 8),
    "node": (3, 2, 5),
    "java": (2, 1, 3),
    "go": (2, 1, 3),
    "rust": (3, 3, 5),
    "generic": (0, 0, 2),
    "mixed": (0, 0, 2),
    "malformed": (0, 0, 0),
}


@pytest.fixture(scope="module")
def real_matrix(tmp_path_factory):
    configured = os.environ.get("YUANJIAN_SCANCODE_EXE")
    assert configured, "YUANJIAN_SCANCODE_EXE must name the trusted ScanCode 32.5.0 executable"
    executable = Path(configured)
    assert executable.is_absolute() and executable.is_file()
    root = tmp_path_factory.mktemp("real-scancode-32-5")
    outcomes = {}
    for ecosystem in EXPECTED:
        settings = Settings(
            data_dir=root / ecosystem,
            scanners=ScannerSettings(enable_secret=False, enable_license=True, enable_agent=False,
                                     enable_scancode=True, enable_ort=False),
            license_providers=LicenseProviderSettings(
                scancode_executable=executable, scancode_version="32.5.0",
                timeout_seconds=120, probe_timeout_seconds=15,
            ),
        )
        started = time.monotonic()
        engine = ScanEngine(settings)
        result = engine.scan(FIXTURES / ecosystem)
        duration = time.monotonic() - started
        inventory = result.metadata["module_data"]["license"]
        outcomes[ecosystem] = {
            "scan_id": result.id, "data_dir": settings.data_dir,
            "duration": duration, "inventory": inventory,
            "result_status": result.status,
        }
        del result, engine
    return outcomes


@pytest.mark.parametrize("ecosystem", EXPECTED)
def test_real_fixture_provider_to_store_matrix(real_matrix, ecosystem):
    outcome = real_matrix[ecosystem]
    inventory = outcome["inventory"]
    assert outcome["result_status"] == "completed"
    assert inventory["schema_version"] == 1
    assert inventory["providers"] == [{
        "name": "scancode", "status": "success", "reason": "ok",
        "version": "32.5.0", "execution_mode": "local-cli", "scan_error_count": 0,
    }, {
        "name": "ort", "status": "disabled", "reason": "disabled",
        "version": None, "execution_mode": "result-import", "scan_error_count": 0,
    }]
    summary = inventory["summary"]
    assert (summary["packages"], summary["dependencies"], summary["licenses"]) == EXPECTED[ecosystem]
    assert summary["licenses"] == summary["assessments"]
    assert inventory["coverage"] == {
        "status": "success", "inventory_complete": True, "providers_complete": True,
        "assessment_complete": True, "dropped_records": 0, "issues": [],
    }
    assert outcome["duration"] < 120
    assert ScanStore(Settings(data_dir=outcome["data_dir"])).get(outcome["scan_id"]).id == outcome["scan_id"]


def test_real_python_store_restart_overview_and_detail_api(real_matrix):
    outcome = real_matrix["python"]
    settings = Settings(data_dir=outcome["data_dir"])
    app = create_app(settings)
    with TestClient(app) as client:
        overview = client.get(f"/api/scans/{outcome['scan_id']}/licenses")
        assert overview.status_code == 200
        payload = overview.json()
        assert payload["providers"][0]["version"] == "32.5.0"
        assert payload["providers"][0]["scan_error_count"] == 0
        assert payload["summary"]["packages"] == 3
        assessment_id = payload["items"][0]["assessment_id"]
        detail = client.get(f"/api/scans/{outcome['scan_id']}/licenses/{assessment_id}")
        assert detail.status_code == 200
        assert detail.json()["assessment"]["assessment_id"] == assessment_id
