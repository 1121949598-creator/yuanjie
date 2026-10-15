from __future__ import annotations

import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .models import ProjectSource, ScanLimits


class UnsafeProjectError(ValueError):
    """Raised when a source archive violates an import safety boundary."""


def _normalized_member(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeProjectError(f"Archive member has an unsafe path: {name!r}")
    if path.parts and ":" in path.parts[0]:
        raise UnsafeProjectError(f"Archive member has a drive-qualified path: {name!r}")
    return path


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def inspect_zip(path: Path, limits: ScanLimits) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen_paths: set[str] = set()
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > limits.max_files:
            raise UnsafeProjectError(f"Archive contains {len(infos)} entries; limit is {limits.max_files}")
        for info in infos:
            member_path = _normalized_member(info.filename)
            collision_key = member_path.as_posix().casefold()
            if collision_key in seen_paths:
                raise UnsafeProjectError(f"Archive contains a duplicate or case-colliding path: {info.filename!r}")
            seen_paths.add(collision_key)
            if _is_zip_symlink(info):
                raise UnsafeProjectError(f"Archive contains a symbolic link: {info.filename!r}")
            if info.is_dir():
                members.append((info, member_path))
                continue
            if info.file_size > limits.max_file_bytes:
                raise UnsafeProjectError(f"Archive member exceeds per-file limit: {info.filename!r}")
            total += info.file_size
            if total > limits.max_total_bytes:
                raise UnsafeProjectError("Archive exceeds total uncompressed-size limit")
            compressed = max(info.compress_size, 1)
            if info.file_size / compressed > limits.max_archive_ratio:
                raise UnsafeProjectError(f"Archive member has a suspicious compression ratio: {info.filename!r}")
            members.append((info, member_path))
    return members


def extract_zip_safely(path: Path, destination: Path, limits: ScanLimits) -> Path:
    members = inspect_zip(path, limits)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(path) as archive:
        for info, relative in members:
            target = (destination / Path(*relative.parts)).resolve()
            if destination != target and destination not in target.parents:
                raise UnsafeProjectError(f"Archive member escapes destination: {info.filename!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    children = [item for item in destination.iterdir() if item.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination


def prepare_project(path: str | Path, limits: ScanLimits, workspace: Path | None = None) -> ProjectSource:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.is_dir():
        return ProjectSource(root=source, display_name=source.name, original_path=source)
    if source.suffix.lower() != ".zip":
        raise UnsafeProjectError("Only a directory or ZIP archive is accepted")
    if workspace is None:
        workspace = Path(tempfile.mkdtemp(prefix="yuanjian-import-"))
        destination = workspace / "source"
    else:
        workspace.mkdir(parents=True, exist_ok=True)
        destination = workspace / "source"
    root = extract_zip_safely(source, destination, limits)
    return ProjectSource(
        root=root,
        display_name=source.stem,
        original_path=source,
        temporary=True,
    )
