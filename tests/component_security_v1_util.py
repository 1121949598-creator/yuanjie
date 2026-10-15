from __future__ import annotations

import pathlib

from yuanjian_agent.files import TextFile, iter_text_files
from yuanjian_agent.models import ScanLimits


def load_fixture(root: str | pathlib.Path) -> list[TextFile]:
    root = pathlib.Path(root)
    files, _warnings = iter_text_files(root, ScanLimits())
    return files
