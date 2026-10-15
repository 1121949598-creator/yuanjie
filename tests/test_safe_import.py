from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from yuanjian_agent.models import ScanLimits
from yuanjian_agent.safe_import import UnsafeProjectError, prepare_project


def test_zip_path_traversal_is_rejected(tmp_path: Path):
    archive = tmp_path / "evil.zip"
    with ZipFile(archive, "w") as target:
        target.writestr("../escaped.py", "raise RuntimeError('must never run')")
    with pytest.raises(UnsafeProjectError):
        prepare_project(archive, ScanLimits(), tmp_path / "workspace")


def test_zip_symlink_is_rejected(tmp_path: Path):
    archive = tmp_path / "link.zip"
    info = ZipInfo("link")
    info.external_attr = (0o120777 << 16)
    with ZipFile(archive, "w") as target:
        target.writestr(info, "outside")
    with pytest.raises(UnsafeProjectError):
        prepare_project(archive, ScanLimits(), tmp_path / "workspace")


def test_oversized_member_is_rejected(tmp_path: Path):
    archive = tmp_path / "large.zip"
    with ZipFile(archive, "w") as target:
        target.writestr("large.txt", "x" * 101)
    with pytest.raises(UnsafeProjectError):
        prepare_project(archive, ScanLimits(max_file_bytes=100), tmp_path / "workspace")
