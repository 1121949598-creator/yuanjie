import pytest

from yuanjian_agent.core.registry import ScannerRegistry
from yuanjian_agent.core.scanner import ScannerResult, SecurityModule


class EmptyScanner:
    def __init__(self, name):
        self.name = name

    def scan(self, context):
        return ScannerResult()


def test_registry_enforces_three_modules_and_pipeline_order():
    registry = ScannerRegistry()
    for module in reversed(list(SecurityModule)):
        registry.register(EmptyScanner(module))
    assert [scanner.name for scanner in registry] == list(SecurityModule)
    with pytest.raises(ValueError):
        registry.register(EmptyScanner(SecurityModule.SECRET))
    with pytest.raises(ValueError):
        registry.register(EmptyScanner("unrelated-business"))


def test_builtin_secret_scanner_is_the_existing_implementation():
    from yuanjian_agent.secret.scanner import BuiltinSecretScanner
    from yuanjian_agent.secrets import SecretScanner

    assert BuiltinSecretScanner is SecretScanner
