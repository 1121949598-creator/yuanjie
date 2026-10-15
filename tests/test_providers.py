from pathlib import Path

import pytest

from yuanjian_agent.providers import OpenAICompatibleProvider
from yuanjian_agent.secrets import SecretScanner


def test_external_provider_is_default_off(tmp_path: Path):
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1",
        model="test-model",
        api_key="not-used",
        cache_dir=tmp_path,
        secret_scanner=SecretScanner(b"0" * 32),
    )
    with pytest.raises(RuntimeError, match="disabled"):
        provider.explain("task", "tool", "description")
