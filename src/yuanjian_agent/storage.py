from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .config import Settings
from .models import ScanResult
from .serialization import scan_result_from_dict


SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_scan_id TEXT,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT NOT NULL,
    scan_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    title TEXT NOT NULL,
    review_status TEXT NOT NULL,
    PRIMARY KEY(scan_id, id),
    FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_signature ON findings(signature);
"""


class ScanStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_directories()
        # sqlite3's context manager commits/rolls back, but does not close.
        # Close explicitly so Windows does not retain database file handles.
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)
            self._migrate_findings_key(connection)

    @staticmethod
    def _migrate_findings_key(connection: sqlite3.Connection) -> None:
        columns = connection.execute("PRAGMA table_info(findings)").fetchall()
        primary_keys = [row["name"] for row in columns if row["pk"]]
        if primary_keys != ["id"]:
            return
        connection.executescript(
            """
            ALTER TABLE findings RENAME TO findings_legacy;
            CREATE TABLE findings (
                id TEXT NOT NULL,
                scan_id TEXT NOT NULL,
                signature TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL,
                title TEXT NOT NULL,
                review_status TEXT NOT NULL,
                PRIMARY KEY(scan_id, id),
                FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE CASCADE
            );
            INSERT INTO findings
            SELECT id, scan_id, signature, category, severity, confidence, title, review_status
            FROM findings_legacy;
            DROP TABLE findings_legacy;
            CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id);
            CREATE INDEX IF NOT EXISTS idx_findings_signature ON findings(signature);
            """
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def save(self, result: ScanResult) -> None:
        payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        scan_dir = self.settings.scans_dir / result.id
        scan_dir.mkdir(parents=True, exist_ok=True)
        temporary = scan_dir / "result.json.tmp"
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(scan_dir / "result.json")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO scans(id, project_name, created_at, status, parent_scan_id, result_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_name=excluded.project_name,
                    created_at=excluded.created_at,
                    status=excluded.status,
                    parent_scan_id=excluded.parent_scan_id,
                    result_json=excluded.result_json
                """,
                (result.id, result.project_name, result.created_at, result.status, result.parent_scan_id, payload),
            )
            connection.execute("DELETE FROM findings WHERE scan_id = ?", (result.id,))
            connection.executemany(
                """
                INSERT INTO findings(
                    id, scan_id, signature, category, severity, confidence, title, review_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        finding.id,
                        result.id,
                        finding.signature,
                        finding.category.value,
                        finding.severity.value,
                        finding.confidence,
                        finding.title,
                        finding.review_status.value,
                    )
                    for finding in result.findings
                ],
            )

    def get(self, scan_id: str) -> ScanResult:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT result_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown scan: {scan_id}")
        return scan_result_from_dict(json.loads(row["result_json"]))

    def list(self, limit: int = 50) -> list[ScanResult]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT result_json FROM scans ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [scan_result_from_dict(json.loads(row["result_json"])) for row in rows]

    def result_path(self, scan_id: str) -> Path:
        return self.settings.scans_dir / scan_id / "result.json"
