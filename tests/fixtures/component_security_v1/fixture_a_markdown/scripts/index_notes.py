"""Index Markdown files under a user-selected directory."""
from pathlib import Path


def index_notes(selected_dir: Path) -> list[Path]:
    if not selected_dir.is_dir():
        return []
    md_files = list(selected_dir.glob("*.md"))
    index: list[Path] = []
    for path in md_files:
        content = path.read_text(encoding="utf-8")
        if content.strip():
            index.append(path)
    return index
