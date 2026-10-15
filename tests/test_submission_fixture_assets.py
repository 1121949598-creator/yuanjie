"""Protect synthetic delivery assets without reading any real environment file."""
from pathlib import Path

import pytest

from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import ScanLimits


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("relative", [
    "examples/02_secret_project", "tests/fixtures/secret_e2e_project",
])
def test_synthetic_env_asset_is_present_and_included_in_scan(relative):
    directory = ROOT / relative
    fixture = directory / ".env"
    assert fixture.is_file(), "Synthetic .env asset missing from delivered source"
    assert fixture.read_text(encoding="utf-8").startswith("# Synthetic scanner fixture only:")
    files, _warnings = iter_text_files(directory, ScanLimits())
    assert ".env" in {item.relative_path for item in files}
