from __future__ import annotations

from .scanner import Scanner, SecurityModule


class ScannerRegistry:
    """Explicit registration, ordered by pipeline; no dynamic plugin imports."""

    def __init__(self) -> None:
        self._scanners: dict[SecurityModule, Scanner] = {}

    def register(self, scanner: Scanner) -> None:
        name = SecurityModule(scanner.name)
        if name in self._scanners:
            raise ValueError("A scanner is already registered for this security module")
        self._scanners[name] = scanner

    def __iter__(self):
        for module in SecurityModule:
            if module in self._scanners:
                yield self._scanners[module]
