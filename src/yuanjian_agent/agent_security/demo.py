"""Small host-controlled Demo boundary; no changes to scanning or risk rules."""
from __future__ import annotations

from ..config import Settings


class DemoFeatureUnavailable(ValueError):
    def __init__(self, feature: str) -> None:
        self.feature = feature
        super().__init__(f"{feature} is disabled in Demo mode; use scan and saved results.")


def require_feature(settings: Settings, feature: str) -> None:
    if settings.demo_mode and feature in {"repair", "repair_preview", "rescan"}:
        raise DemoFeatureUnavailable(feature)


def feature_metadata(settings: Settings) -> dict:
    discovery = "enabled" if settings.scanners.enable_agent else "disabled"
    unsafe = "disabled" if settings.demo_mode else "experimental"
    return {
        "mode": "demo" if settings.demo_mode else "standard",
        "features": {
            "scan": "enabled",
            "agent_discovery": discovery,
            "tool_discovery": discovery,
            "binding_analysis": discovery,
            "risk_analysis": discovery,
            "repair": unsafe,
            "repair_preview": unsafe,
            "rescan": unsafe,
        },
    }
