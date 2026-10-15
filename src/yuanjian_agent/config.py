from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import ScanLimits


def _default_data_dir() -> Path:
    configured = os.getenv("YUANJIAN_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / ".yuanjian-data").resolve()


def _default_component_model_dir() -> Path | None:
    configured = os.getenv("YUANJIAN_COMPONENT_MODEL_DIR")
    return Path(configured).expanduser().resolve() if configured else None


@dataclass(slots=True)
class ScannerSettings:
    enable_secret: bool = True
    enable_license: bool = True
    enable_agent: bool = True
    enable_gitleaks: bool = False
    enable_detect_secrets: bool = False
    enable_trufflehog: bool = False
    enable_scancode: bool = False
    enable_ort: bool = False


@dataclass(slots=True)
class LicenseProviderSettings:
    """Trusted host configuration only; never loaded from the scanned project."""

    scancode_executable: Path | None = field(default=None, repr=False)
    scancode_version: str | None = None
    ort_result_path: Path | None = field(default=None, repr=False)
    timeout_seconds: float = 120.0
    probe_timeout_seconds: float = 10.0
    max_stream_bytes: int = 256 * 1024
    max_json_bytes: int = 16 * 1024 * 1024
    max_files: int = 5_000
    max_packages: int = 10_000
    max_dependencies: int = 20_000
    max_detections: int = 20_000
    max_string_length: int = 16_384
    max_depth: int = 40
    max_nodes: int = 300_000

    def __post_init__(self) -> None:
        import math

        for value in (self.timeout_seconds, self.probe_timeout_seconds):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 3600:
                raise ValueError("Invalid License provider timeout")
        for name in ("max_stream_bytes", "max_json_bytes", "max_files", "max_packages",
                     "max_dependencies", "max_detections", "max_string_length", "max_depth", "max_nodes"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError("Invalid License provider limit")


@dataclass(slots=True)
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    limits: ScanLimits = field(default_factory=ScanLimits)
    app_version: str = "0.1.0"
    scanners: ScannerSettings = field(default_factory=ScannerSettings)
    license_providers: LicenseProviderSettings = field(default_factory=LicenseProviderSettings)
    # Trusted host configuration only. The License scanner rejects paths inside
    # the scanned project so a repository cannot weaken its own assessment.
    license_policy_profile: Path | None = field(default=None, repr=False)
    # Opt-in host policy. scripts/demo.ps1 always enables it; never read from targets.
    demo_mode: bool = False
    # Trusted host configuration only. Target projects cannot choose model files.
    component_model_dir: Path | None = field(default_factory=_default_component_model_dir, repr=False)

    @property
    def scans_dir(self) -> Path:
        return self.data_dir / "scans"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "yuanjian.sqlite3"

    @property
    def fingerprint_key_path(self) -> Path:
        return self.data_dir / ".fingerprint-key"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.scans_dir, self.uploads_dir, self.models_dir):
            path.mkdir(parents=True, exist_ok=True)
