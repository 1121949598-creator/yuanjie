import json
from pathlib import Path

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.repair import RepairService


EXAMPLES = Path(__file__).parents[1] / "examples"


def engine(tmp_path: Path) -> ScanEngine:
    return ScanEngine(Settings(data_dir=tmp_path / "state"))


def test_secret_is_masked_everywhere_and_repaired_in_copy(tmp_path: Path):
    scanner = engine(tmp_path)
    result = scanner.scan(EXAMPLES / "02_secret_project")
    assert result.summary.secrets >= 2
    payload = (scanner.settings.scans_dir / result.id / "result.json").read_text(encoding="utf-8")
    assert "sk-liveDemoOnly_1234567890abcdef" not in payload
    assert "mcp_demo_8zX91Kp2Lm4Q7Rt6" not in payload
    safe_copy = RepairService(scanner.settings, scanner.secret_scanner).create_safe_copy(result)
    repaired = (safe_copy / ".env").read_text(encoding="utf-8")
    assert repaired.count("YOUR_SECRET_HERE") == 2
    assert (EXAMPLES / "02_secret_project" / ".env").read_text(encoding="utf-8") != repaired
    compared = scanner.scan(safe_copy, parent_scan_id=result.id)
    assert compared.comparison["counts"]["resolved"] >= 2


def test_tool_exposure_and_rescan_comparison(tmp_path: Path):
    scanner = engine(tmp_path)
    result = scanner.scan(EXAMPLES / "01_langchain_research")
    assert result.summary.tool_exposures >= 1
    safe_copy = RepairService(scanner.settings, scanner.secret_scanner).create_safe_copy(result)
    compared = scanner.scan(safe_copy, parent_scan_id=result.id)
    assert compared.comparison["counts"]["resolved"] >= 1


def test_mcp_raw_config_is_not_persisted(tmp_path: Path):
    scanner = engine(tmp_path)
    result = scanner.scan(EXAMPLES / "05_mcp_static")
    payload = json.dumps(result.to_dict())
    assert "server_config" not in payload
    assert "body_source" not in payload


def test_malicious_python_is_never_executed(tmp_path: Path):
    project = tmp_path / "hostile"
    project.mkdir()
    marker = tmp_path / "executed.txt"
    (project / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
        encoding="utf-8",
    )
    engine(tmp_path).scan(project)
    assert not marker.exists()


@pytest.mark.parametrize(
    ("example", "minimum_tool_findings", "minimum_unresolved"),
    [
        ("01_langchain_research", 1, 0),
        ("03_crewai_mail", 0, 0),
        ("04_crewai_cleanup", 1, 0),
        ("05_mcp_static", 0, 1),
        ("06_dynamic_unresolved", 0, 1),
    ],
)
def test_demo_repository_expectations(
    tmp_path: Path,
    example: str,
    minimum_tool_findings: int,
    minimum_unresolved: int,
):
    result = engine(tmp_path).scan(EXAMPLES / example)
    assert result.summary.tool_exposures >= minimum_tool_findings
    assert result.summary.unresolved >= minimum_unresolved
