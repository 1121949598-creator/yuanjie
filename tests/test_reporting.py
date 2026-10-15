from pathlib import Path

from yuanjian_agent.config import Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.reporting import render_html_report


EXAMPLES = Path(__file__).parents[1] / "examples"


def test_html_report_contains_masked_evidence_only(tmp_path: Path):
    result = ScanEngine(Settings(data_dir=tmp_path / "state")).scan(EXAMPLES / "02_secret_project")
    report = render_html_report(result)
    assert "Masked evidence" in report
    assert "sk-liveDemoOnly_1234567890abcdef" not in report
    assert "****" in report
