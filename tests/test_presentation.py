from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from yuanjian_agent.config import Settings
from yuanjian_agent.web import create_app
from yuanjian_agent.storage import ScanStore


def client_for(tmp_path: Path):
    return TestClient(create_app(Settings(data_dir=tmp_path / "state", demo_mode=True)))


def test_system_reports_real_provider_policy(tmp_path):
    data = client_for(tmp_path).get('/api/system').json()
    assert data['mode'] == 'demo'
    assert data['authentication'] == 'none'
    assert data['license_provider_configured'] is False
    assert data['max_upload_bytes'] == 104857600


def test_sample_scan_persists_actual_findings_and_history(tmp_path):
    client = client_for(tmp_path)
    response = client.post('/api/examples/research/scan')
    assert response.status_code == 201
    scan_id = response.json()['scan_id']
    result = client.get(f'/api/scans/{scan_id}').json()
    assert result['agents'] and result['tools']
    assert any(f['category'] == 'tool_exposure' for f in result['findings'])
    history = client.get('/api/scans').json()['items']
    assert history[0]['id'] == scan_id
    assert history[0]['is_example'] is True
    assert 'source_path' not in history[0]
    assert client_for(tmp_path).get('/api/scans').json()['items'][0]['id'] == scan_id


def test_example_allowlist_and_download(tmp_path):
    client = client_for(tmp_path)
    assert client.post('/api/examples/unknown/scan').status_code == 404
    response = client.get('/api/examples/research/archive')
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        assert any(n.endswith('agent.py') for n in archive.namelist())


def test_report_uses_saved_masked_values_without_internal_paths(tmp_path):
    client = client_for(tmp_path)
    scan_id = client.post('/api/examples/secrets/scan').json()['scan_id']
    response = client.get(f'/api/scans/{scan_id}/report')
    assert response.status_code == 200
    assert response.json()['findings']
    assert 'source_path' not in response.text
    assert 'fingerprint' not in response.text
    assert str(tmp_path).replace('\\', '\\\\') not in response.text
    assert client.get('/api/scans/not-found/report').status_code == 404


def test_invalid_zip_returns_actionable_error_and_does_not_persist(tmp_path):
    client = client_for(tmp_path)
    response = client.post('/api/scans', files={'file': ('broken.zip', b'not a zip', 'application/zip')})
    assert response.status_code == 400
    assert client.get('/api/scans').json()['items'] == []


def test_upload_retains_readable_project_name(tmp_path):
    client = client_for(tmp_path)
    content = BytesIO()
    with ZipFile(content, 'w') as archive:
        archive.writestr('README.md', 'A safe project')
    created = client.post('/api/scans', files={'file': ('my-project.zip', content.getvalue(), 'application/zip')})
    result = client.get('/api/scans/' + created.json()['scan_id']).json()
    assert result['project_name'] == 'my-project'


def test_report_withholds_legacy_secret_lines_and_internal_metadata(tmp_path):
    client = client_for(tmp_path)
    scan_id = client.post('/api/examples/secrets/scan').json()['scan_id']
    store = ScanStore(Settings(data_dir=tmp_path / 'state'))
    result = store.get(scan_id)
    secret = result.findings[0]
    raw = 'LEGACY_INTERNAL_SECRET_MUST_NOT_APPEAR'
    secret.metadata.update(raw_value=raw, source_text=raw)
    secret.evidence[0].details['matched_value'] = raw
    secret.evidence[0].masked_excerpt = f'API_KEY="sk-****abcd"; other="{raw}"'
    secret.rationale = [raw]
    result.warnings = [raw]
    store.save(result)
    response = client.get(f'/api/scans/{scan_id}/report')
    assert response.status_code == 200
    assert raw not in response.text
    item = next(f for f in response.json()['findings'] if f['id'] == secret.id)
    assert item['evidence'][0]['masked_excerpt'] == '****'
    assert 'metadata' not in item
    assert response.json()['warnings'] == ['保存的扫描含诊断记录，请结合各模块的状态与覆盖信息复核。']


def test_upload_name_uses_invocation_known_secret_redaction(tmp_path):
    client = client_for(tmp_path)
    content = BytesIO()
    raw = 'n8R2v5X7q9M3s6T4z1P0'
    with ZipFile(content, 'w') as archive:
        archive.writestr('config.py', f'API_KEY="{raw}"')
    created = client.post('/api/scans', files={'file': (f'{raw}.zip', content.getvalue(), 'application/zip')})
    assert created.status_code == 201
    scan_id = created.json()['scan_id']
    for path in ['/api/scans', f'/api/scans/{scan_id}', f'/api/scans/{scan_id}/report']:
        assert raw not in client.get(path).text
