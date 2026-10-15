import base64
from pathlib import Path

from fastapi.testclient import TestClient

from yuanjian_agent.config import Settings
from yuanjian_agent.web import create_app


def test_shared_preview_rejects_missing_wrong_and_malformed_credentials(tmp_path: Path):
    app = create_app(
        Settings(data_dir=tmp_path / "state", demo_mode=True),
        share_password="Correct-Team-Key-2026",
    )

    with TestClient(app) as client:
        missing = client.get("/api/system")
        wrong = client.get("/api/system", auth=("yuanjian", "Wrong-Team-Key"))
        malformed = client.get("/api/system", headers={"Authorization": "Basic !!!"})
        unicode_username = base64.b64encode("测试用户:Correct-Team-Key-2026".encode()).decode()
        non_ascii = client.get(
            "/api/system", headers={"Authorization": f"Basic {unicode_username}"}
        )

    for response in (missing, wrong, malformed, non_ascii):
        assert response.status_code == 401
        assert response.headers["www-authenticate"].startswith('Basic realm="yuanjian team preview"')
        assert "Correct-Team-Key-2026" not in response.text


def test_shared_preview_accepts_credentials_for_api_and_ui(tmp_path: Path):
    app = create_app(
        Settings(data_dir=tmp_path / "state", demo_mode=True),
        share_password="Correct-Team-Key-2026",
    )

    with TestClient(app) as client:
        api = client.get("/api/system", auth=("yuanjian", "Correct-Team-Key-2026"))
        ui = client.get("/app/", auth=("yuanjian", "Correct-Team-Key-2026"))

    assert api.status_code == 200
    assert api.json()["name"] == "源界"
    assert ui.status_code == 200
    assert "<div id=\"app\"></div>" in ui.text


def test_local_preview_remains_open_when_share_password_is_absent(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "state", demo_mode=True))

    with TestClient(app) as client:
        response = client.get("/api/system")

    assert response.status_code == 200
