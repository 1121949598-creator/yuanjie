"""Fixed diagnostics: never attach source, stdout/stderr, or original errors."""


class ScannerError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Scanner failed; raw diagnostic details are suppressed")


class ExternalToolUnavailable(ScannerError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "External scanner integration is not implemented")


class ExternalToolTimeout(ScannerError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "External scanner timed out")


class ExternalToolProcessError(ScannerError):
    def __init__(self) -> None:
        RuntimeError.__init__(self, "External scanner process failed")
