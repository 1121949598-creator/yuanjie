import json
from pathlib import Path

from yuanjian_agent.cli import main


EXAMPLES = Path(__file__).parents[1] / "examples"


def test_cli_scan(tmp_path: Path, capsys):
    status = main(["--data-dir", str(tmp_path / "state"), "scan", str(EXAMPLES / "01_langchain_research")])
    output = json.loads(capsys.readouterr().out)
    assert status == 0
    assert output["summary"]["tool_exposures"] == 1
