from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from yuanjian_agent.config import Settings
from yuanjian_agent.web import create_app


def test_home_page(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "state")))
    response = client.get("/")
    assert response.status_code == 200
    assert "源界" in response.text


def test_zip_api_scan_preview_and_rescan(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "state")))
    raw_secret = "sk-webDemo_1234567890abcdefgh"
    archive = BytesIO()
    with ZipFile(archive, "w") as target:
        target.writestr("demo/.env", f'OPENAI_API_KEY="{raw_secret}"\n')
    created = client.post(
        "/api/scans",
        files={"file": ("demo.zip", archive.getvalue(), "application/zip")},
    )
    assert created.status_code == 201
    scan_id = created.json()["scan_id"]
    detail = client.get(f"/api/scans/{scan_id}")
    assert detail.status_code == 200
    assert raw_secret not in detail.text
    finding_id = detail.json()["findings"][0]["id"]
    preview = client.post(
        f"/api/findings/{finding_id}/repair-preview",
        params={"scan_id": scan_id},
    )
    assert preview.status_code == 200
    assert preview.json()["automatic"] is True
    rescanned = client.post(f"/api/scans/{scan_id}/rescan")
    assert rescanned.status_code == 200
    assert rescanned.json()["comparison"]["counts"]["resolved"] >= 1
