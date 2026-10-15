"""Synthetic credentials only. Target snippets are read as text, never executed."""
import base64
from dataclasses import asdict, replace
import json
from pathlib import Path
import re

import pytest

from yuanjian_agent.config import ScannerSettings, Settings
from yuanjian_agent.core.context import ScanContext
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.files import TextFile
from yuanjian_agent.models import Severity
from yuanjian_agent.reporting import render_html_report
from yuanjian_agent.secret.rules import SECRET_RULES, SecretRule
from yuanjian_agent.secret.scanner import SecretScanner as SecretModule
from yuanjian_agent.secrets import SecretScanner, mask_secret, shannon_entropy


RAW = "sk-test-8KJd82kdlQ93kdl20f"
GENERIC = "8KJd82kdlQ93kdl20fSynThetic"


@pytest.fixture
def scanner():
    return SecretScanner(b"synthetic-test-fingerprint-key")


def text_file(text, name="app/config.py"):
    return TextFile(Path(name), name, text)


def detect(scanner, text, name="app/config.py"):
    return scanner.scan([text_file(text, name)])


def jwt():
    def segment(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return ".".join((segment({"alg": "HS256", "typ": "JWT"}),
                     segment({"sub": "synthetic-user"}), "SyntheticSignature123456"))


def test_detect_private_key(scanner):
    assert detect(scanner, "-----BEGIN PRIVATE KEY-----")[0].severity == Severity.CRITICAL


def test_detect_rsa_private_key(scanner):
    assert detect(scanner, "-----BEGIN RSA PRIVATE KEY-----")[0].metadata["secret_type"] == "private_key"


def test_detect_openssh_private_key(scanner):
    assert detect(scanner, "-----BEGIN OPENSSH PRIVATE KEY-----")[0].confidence >= 0.9


@pytest.mark.parametrize("kind", ["PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "OPENSSH PRIVATE KEY"])
def test_private_key_entire_body_is_masked(scanner, kind):
    body = "U3ludGhldGljUHJpdmF0ZUtleU1hdGVyaWFs"
    raw = f"-----BEGIN {kind}-----\n{body}\n-----END {kind}-----"
    findings = detect(scanner, raw, "key.pem")
    assert len(findings) == 1
    assert findings[0].location.end_line == 3
    assert body not in json.dumps([asdict(f) for f in findings]) + scanner.redact_text(raw)
    assert scanner.redactor_for([text_file(raw)]).redact_text(body) == mask_secret(body)


def test_detect_aws_access_key(scanner):
    raw = "AKIA0123456789ABCDEF"
    finding, = detect(scanner, f'key = "{raw}"')
    assert finding.rule_id == "secret.aws-access-key"
    assert finding.severity == Severity.HIGH and finding.confidence >= 0.9


@pytest.mark.parametrize("raw", ["AWS", "AWS_KEY", "AKIAshort", "AKIAabcdefghijklmnop",
                                    "AKIA0123456789ABCDEFG", "xAKIA0123456789ABCDEF"])
def test_ignore_invalid_aws_format(scanner, raw):
    assert not detect(scanner, raw)


def test_detect_jwt(scanner):
    finding, = detect(scanner, f'api_key = "{jwt()}"')
    assert finding.metadata["secret_type"] == "jwt"
    assert finding.severity == Severity.MEDIUM
    assert 0.5 <= finding.confidence < 0.9


@pytest.mark.parametrize("raw", ["eyJxxxxx.yyyyy.zzzzz", "eyJhbGciOiJIUzI1NiJ9.bm90anNvbg.signature",
                                    "eyJ9.e30.signature"])
def test_ignore_malformed_jwt(scanner, raw):
    assert not detect(scanner, raw)


@pytest.mark.parametrize("scheme", ["mysql", "postgres", "postgresql", "mongodb", "mongodb+srv", "redis"])
def test_detect_database_url_with_password(scanner, scheme):
    finding, = detect(scanner, f'url = "{scheme}://root:123456@localhost/test"')
    assert finding.metadata["secret_type"] == "database_credential"
    assert finding.severity == Severity.HIGH


@pytest.mark.parametrize("name", ["password", "passwd", "pwd", "db_password", "secret", "client_secret"])
def test_detect_generic_password(scanner, name):
    finding, = detect(scanner, f'{name} = "admin123456"')
    assert finding.severity == Severity.MEDIUM


def test_detect_six_character_password(scanner):
    assert detect(scanner, 'passwd = "abcdef"')


def test_detect_generic_api_key(scanner):
    finding, = detect(scanner, f'API_KEY = "{GENERIC}"')
    assert finding.rule_id == "secret.generic-api-key"
    assert finding.metadata["secret_type"] == "api_key"
    assert finding.severity == Severity.HIGH


@pytest.mark.parametrize("name", ["token", "access_token", "auth_token", "mcp_token"])
def test_detect_generic_token(scanner, name):
    finding, = detect(scanner, f'{name} = "{GENERIC}"')
    assert finding.metadata["secret_type"] == "token"
    assert finding.severity == Severity.MEDIUM


def test_required_api_key_example(scanner):
    finding, = detect(scanner, f'API_KEY = "{RAW}"')
    assert finding.metadata["secret_type"] == "api_key"
    assert finding.severity == Severity.HIGH
    assert finding.location.path == "app/config.py"
    assert finding.location.start_line == 1


@pytest.mark.parametrize("value", ["YOUR_API_KEY", "your-api-key", "Your_Api_Key_Here",
    "password", "secret", "token", "changeme", "EXAMPLE", "dummy", "test", "xxx", "xxxx", "xxxxx"])
def test_ignore_placeholder_api_key(scanner, value):
    assert not detect(scanner, f'API_KEY = "{value}"')


@pytest.mark.parametrize("value", ["example", "YOUR_TOKEN", "your-token", "XXXXXX", "test-token"])
def test_ignore_placeholder_token(scanner, value):
    assert not detect(scanner, f'TOKEN = "{value}"')


@pytest.mark.parametrize("value", ["changeme", "password", "secret", "Your_Password_Here", "xxxxxxxx"])
def test_ignore_placeholder_password(scanner, value):
    assert not detect(scanner, f'password = "{value}"')


def test_test_substring_is_not_blanket_ignored(scanner):
    assert detect(scanner, f'API_KEY = "{RAW}"')


def test_ignore_empty_password(scanner):
    assert not detect(scanner, 'password = ""\ntoken = ""\n')


@pytest.mark.parametrize("text", [
    'password = os.getenv("PASSWORD")', 'api_key = os.environ["API_KEY"]',
    'password = os.environ.get("PASSWORD")', 'token = process.env.API_KEY',
    'password = get_password()', 'password = System.getenv("PASSWORD")',
])
def test_ignore_env_reference(scanner, text):
    assert not detect(scanner, text)


@pytest.mark.parametrize("value", ["\u0024{API_KEY}", "{{ API_KEY }}", "<YOUR_API_KEY>", "$API_KEY", "%API_KEY%"])
def test_ignore_template_variable(scanner, value):
    assert not detect(scanner, f'password = "{value}"\nAPI_KEY = "{value}"')


@pytest.mark.parametrize("uri", ["mysql://localhost/test", "redis://localhost:6379",
    "postgres://root@localhost/test", "mongodb://root:@localhost/test",
    "mysql://root:YOUR_PASSWORD@localhost/test", "mysql://root:%24%7BPASSWORD%7D@localhost/test"])
def test_ignore_database_url_without_password(scanner, uri):
    assert not detect(scanner, f'url = "{uri}"')


@pytest.mark.parametrize("name", ["uuid", "commit_hash", "checksum", "random_id", "monkey", "tokenizer"])
def test_entropy_without_credential_semantics_is_not_a_secret(scanner, name):
    assert not detect(scanner, f'{name} = "{GENERIC}"')


@pytest.mark.parametrize("value", ["0123456789abcdef0123456789abcdef",
    "01234567-89ab-cdef-0123-456789abcdef", "0123456789abcdef0123456789abcdef01234567",
    "a" * 40, "Ab1" * 20])
def test_generic_rejects_hash_uuid_and_low_complexity(scanner, value):
    assert not detect(scanner, f'api_key = "{value}"')


@pytest.mark.parametrize("text", [
    f'{{"api_key": "{GENERIC}"}}', f"api_key: '{GENERIC}'",
    f"export API_KEY={GENERIC}", "db_password=admin123456",
])
def test_configuration_literal_syntax(scanner, text):
    assert len(detect(scanner, text)) == 1


def test_mask_secret():
    assert mask_secret(RAW) == "sk-t****l20f"


@pytest.mark.parametrize("value", ["a", "abcd", "12345678", ""])
def test_short_secret_masked(value):
    assert mask_secret(value) == "****"


def test_finding_does_not_contain_raw_secret(scanner):
    finding, = detect(scanner, f'API_KEY = "{RAW}"; unknown="{GENERIC}"')
    for value in (RAW, GENERIC):
        assert value not in repr(finding) + repr(finding.evidence) + json.dumps(asdict(finding))


def test_serialized_result_does_not_contain_raw_secret(scanner, tmp_path, capsys, caplog):
    context = ScanContext("test", tmp_path, "directory", Settings(data_dir=tmp_path), tmp_path,
                          files=[text_file(f'API_KEY = "{RAW}"')])
    result = SecretModule(scanner).scan(context)
    assert len(result.findings) == 1 and result.status == ScanStatus.SUCCESS
    assert RAW not in repr(result) + json.dumps(asdict(result)) + caplog.text + capsys.readouterr().out


def test_secret_line_number(scanner):
    finding, = detect(scanner, f'# comment\r\n\r\nAPI_KEY = "{RAW}"\r\n')
    assert finding.location.start_line == 3


def test_secret_column_range(scanner):
    line = f'  API_KEY = "{RAW}"'
    finding, = detect(scanner, line)
    assert finding.location.start_column == line.index(RAW)
    assert finding.location.end_column == line.index(RAW) + len(RAW)


def test_repeated_secret_on_same_line_retains_both_columns(scanner):
    text = f'API_KEY="{RAW}"; token="{RAW}"'
    findings = detect(scanner, text)
    assert len(findings) == 2
    assert {f.location.start_column for f in findings} == {text.index(RAW), text.rindex(RAW)}


def test_rule_registry_is_extensible(scanner):
    rule = SecretRule("secret.synthetic", "Synthetic prefix", "api_key",
                      re.compile(r"SYNTH_[a-z0-9]{12}"), Severity.HIGH, 0.9)
    scanner.compiled = (*SECRET_RULES, rule)
    assert detect(scanner, "SYNTH_abc123def456")[0].rule_id == "secret.synthetic"


def test_entropy_is_independent():
    assert shannon_entropy("") == 0
    assert shannon_entropy("aaaa") == 0
    assert shannon_entropy("aabb") == 1
    assert shannon_entropy("abcd") == 2


def test_rule_failure_is_partial_and_preserves_other_rules(scanner, tmp_path, caplog):
    class BrokenPattern:
        def finditer(self, text):
            raise RuntimeError(RAW)
    scanner.compiled = (replace(SECRET_RULES[0], pattern=BrokenPattern()), *SECRET_RULES[1:])
    context = ScanContext("test", tmp_path, "directory", Settings(data_dir=tmp_path), tmp_path,
                          files=[text_file(f'API_KEY="{RAW}"')])
    result = SecretModule(scanner).scan(context)
    assert len(result.findings) == 1
    assert result.status == ScanStatus.PARTIAL
    assert result.providers["builtin-secret"] == ScanStatus.PARTIAL
    assert RAW not in json.dumps(asdict(result)) + caplog.text


def test_file_failure_does_not_stop_next_file(scanner, tmp_path, monkeypatch):
    original = scanner.scan_file
    def fail_one(file):
        if file.relative_path == "bad.py":
            raise PermissionError(RAW)
        return original(file)
    monkeypatch.setattr(scanner, "scan_file", fail_one)
    context = ScanContext("test", tmp_path, "directory", Settings(data_dir=tmp_path), tmp_path,
        files=[text_file("", "bad.py"), text_file(f'API_KEY="{RAW}"')])
    result = SecretModule(scanner).scan(context)
    assert len(result.findings) == 1 and result.status == ScanStatus.PARTIAL
    assert RAW not in repr(result)


def test_secret_scanner_integrates_with_scan_engine(tmp_path):
    project = tmp_path / "input"
    project.mkdir()
    (project / "config.py").write_text(f'API_KEY = "{RAW}"\n', encoding="utf-8")
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    result = engine.scan(project)
    assert result.summary.secrets == 1
    assert result.metadata["scanners"]["secret"]["status"] == "success"
    assert result.metadata["scanners"]["agent_security"]["status"] == "success"
    assert result.metadata["scanners"]["license"]["status"] == "unavailable"
    payloads = [json.dumps(result.to_dict()), repr(result),
                engine.store.result_path(result.id).read_text(encoding="utf-8"),
                render_html_report(result), json.dumps(engine.store.get(result.id).to_dict())]
    with engine.store._connect() as connection:
        payloads.append(connection.execute("SELECT result_json FROM scans").fetchone()[0])
    assert all(RAW not in payload for payload in payloads)


def test_private_body_redacted_in_other_modules_when_secret_disabled(tmp_path):
    body = "U3ludGhldGljUHJpdmF0ZUtleU1hdGVyaWFs"
    project = tmp_path / "input"
    project.mkdir()
    (project / "key.pem").write_text(
        f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----", encoding="utf-8")
    (project / "agent.py").write_text(
        f'agent=create_agent("local", tools=discover("{body}"), system_prompt="{body}")', encoding="utf-8")
    engine = ScanEngine(Settings(data_dir=tmp_path / "state",
                                scanners=ScannerSettings(enable_secret=False)))
    result = engine.scan(project)
    assert body not in json.dumps(result.to_dict())


@pytest.mark.parametrize("name", ["password", "api_key", "token"])
def test_uri_without_credentials_is_not_rescued_by_generic_rule(scanner, name):
    assert not detect(scanner, f'{name}="mysql://localhost/test"')


def test_severity_is_not_reduced_with_context_confidence(scanner):
    ordinary, = detect(scanner, '-----BEGIN PRIVATE KEY-----', 'key.pem')
    example, = detect(scanner, '-----BEGIN PRIVATE KEY-----', 'docs/key.pem')
    assert ordinary.severity == example.severity == Severity.CRITICAL
    assert example.confidence < ordinary.confidence


def test_scan_file_masks_secret_in_target_controlled_path(scanner):
    findings = scanner.scan_file(text_file(f'API_KEY="{RAW}"', f'{RAW}.py'))
    assert RAW not in repr(findings)


def test_scan_context_files_are_not_read_or_enumerated_again(scanner, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Secret module must consume the existing TextFile list")
    monkeypatch.setattr(Path, "rglob", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    context = ScanContext("test", tmp_path, "directory", Settings(data_dir=tmp_path), tmp_path,
                          files=[text_file(f'API_KEY="{RAW}"')])
    assert len(SecretModule(scanner).scan(context).findings) == 1


def test_placeholder_redaction_does_not_corrupt_result_types(scanner):
    findings = detect(scanner, f'token="token"\npassword="password"\napi_key="{GENERIC}"\n'
                      f'token="{GENERIC}"\npassword="admin123456"')
    assert {f.metadata["secret_type"] for f in findings} == {"api_key", "token", "password"}
    assert all(f.rule_id.startswith("secret.") for f in findings)


def test_dynamic_string_prefix_is_not_a_known_one_character_secret(scanner):
    file = text_file('password = f"{os.getenv(\'PASSWORD\')}"')
    assert scanner.redactor_for([file]).redact_text("fixed finding information") == "fixed finding information"
