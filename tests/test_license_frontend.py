from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from test_license_query import license_scan
from yuanjian_agent.config import Settings
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app


ROOT = Path(__file__).parents[1]


def frontend_client(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    ScanStore(settings).save(license_scan())
    return TestClient(create_app(settings))


def test_license_overview_page_uses_existing_layout_and_loading_state(tmp_path):
    response = frontend_client(tmp_path).get("/scans/scan-a/licenses")
    assert response.status_code == 200
    assert "许可证与依赖" in response.text
    assert 'data-license-overview' in response.text
    assert 'role="status"' in response.text
    assert "/static/license-pages.js" in response.text


def test_license_overview_has_all_backend_filters_and_accessible_table(tmp_path):
    response = frontend_client(tmp_path).get("/scans/scan-a/licenses")
    for name in ("package_name", "license_expression", "classification", "severity",
                 "manual_review_required", "file_path", "page_size"):
        assert f'name="{name}"' in response.text
    assert 'aria-label="许可证评估表，可横向滚动"' in response.text
    assert 'aria-label="许可证评估分页"' in response.text


def test_license_detail_route_is_assessment_id_based(tmp_path):
    response = frontend_client(tmp_path).get("/scans/scan-a/licenses/assess-strong")
    assert response.status_code == 200
    assert 'data-assessment-id="assess-strong"' in response.text
    for heading in ("评估", "依赖包", "许可证表达式", "关联发现", "检测来源", "审核提示"):
        assert heading in response.text


def test_license_pages_keep_query_state_without_leaking_it_into_detail_api(tmp_path):
    response = frontend_client(tmp_path).get(
        "/scans/scan-a/licenses/assess-strong?page=2&classification=strong_copyleft"
    )
    assert response.status_code == 200
    source = (ROOT / "src/yuanjian_agent/static/license-pages.js").read_text(encoding="utf-8")
    assert "overviewBackHref(scanId, location.search)" in source
    assert "getLicenseDetail(scanId, assessmentId)" in source


def test_dashboard_links_existing_scan_to_license_overview(tmp_path):
    response = frontend_client(tmp_path).get("/scans/scan-a")
    assert response.status_code == 200
    assert 'href="/scans/scan-a/licenses"' in response.text


def test_license_page_scan_not_found_is_existing_web_404(tmp_path):
    response = frontend_client(tmp_path).get("/scans/missing/licenses")
    assert response.status_code == 404


def test_license_static_assets_are_served(tmp_path):
    client = frontend_client(tmp_path)
    assert client.get("/static/license-api.js").status_code == 200
    assert client.get("/static/license-pages.js").status_code == 200
    assert "table-scroll" in client.get("/static/style.css").text


def test_frontend_client_contains_only_saved_license_get_endpoints():
    api = (ROOT / "src/yuanjian_agent/static/license-api.js").read_text(encoding="utf-8")
    pages = (ROOT / "src/yuanjian_agent/static/license-pages.js").read_text(encoding="utf-8")
    assert 'method: "GET"' in api
    assert "/api/scans/${encodeURIComponent(scanId)}/licenses" in api
    for forbidden in ("scancode", "result.json", "sqlite", "source_path", "/api/scans\"", "fetch(\"/scans"):
        assert forbidden not in api.lower()
    assert "source_path" not in pages


def test_openapi_still_exposes_both_license_contracts(tmp_path):
    spec = frontend_client(tmp_path).get("/openapi.json").json()
    assert "get" in spec["paths"]["/api/scans/{scan_id}/licenses"]
    assert "get" in spec["paths"]["/api/scans/{scan_id}/licenses/{assessment_id}"]


def test_license_frontend_javascript_behavior():
    completed = subprocess.run(
        ["node", "--test", str(ROOT / "tests/license_frontend.test.mjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
