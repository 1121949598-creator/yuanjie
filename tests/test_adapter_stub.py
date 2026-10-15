import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.core.context import ScanContext
from yuanjian_agent.core.exceptions import ExternalToolUnavailable
from yuanjian_agent.external.process import ExternalToolRunner, ProcessRequest, ProcessResult
from yuanjian_agent.license.adapters.ort import OrtAdapter
from yuanjian_agent.license.adapters.scancode import ScanCodeAdapter
from yuanjian_agent.license.policy import UnavailableLicensePolicy
from yuanjian_agent.secret.adapters.detect_secrets import DetectSecretsAdapter
from yuanjian_agent.secret.adapters.gitleaks import GitleaksAdapter
from yuanjian_agent.secret.adapters.trufflehog import TruffleHogAdapter


@pytest.mark.parametrize("adapter", [GitleaksAdapter, DetectSecretsAdapter, TruffleHogAdapter, ScanCodeAdapter, OrtAdapter])
def test_adapter_is_unavailable_without_invoking_runner(adapter, tmp_path):
    class ForbiddenRunner:
        def run(self, request):
            pytest.fail("A stub must never invoke an external process")

    context = ScanContext("test", tmp_path, "directory", Settings(data_dir=tmp_path), tmp_path)
    with pytest.raises(ExternalToolUnavailable):
        adapter(runner=ForbiddenRunner()).scan(context)
    assert list(tmp_path.iterdir()) == []


def test_runner_and_policy_do_not_claim_implementation(tmp_path):
    with pytest.raises(ExternalToolUnavailable):
        ExternalToolRunner().run(ProcessRequest("never-execute", cwd=tmp_path))
    with pytest.raises(ExternalToolUnavailable):
        UnavailableLicensePolicy().evaluate(None)


def test_transient_process_output_is_not_in_repr():
    raw = "synthetic-sensitive-diagnostic"
    result = ProcessResult(1, raw, raw, {"raw": raw})
    assert raw not in repr(result)
    assert raw not in repr(ProcessRequest("scancode", (raw,)))
