"""Local SQLite store for uploaded documents and their parsed result.

Everything stays on the student's machine. A successful parse is cached by the
SHA-256 of the file's bytes, so if parsing later fails for the same document
(for example during a live demo) the cached result can be used instead.
``delete_all`` wipes the store; the app exposes it as a button.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from course_planner.models import Course, ParseResult

DB_ENV_VAR = "COURSE_PLANNER_DB"
DEFAULT_DB = Path(".course_planner") / "app.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    sha256 TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content BLOB NOT NULL,
    parsed_json TEXT NOT NULL,
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


@dataclass(frozen=True)
class StoredDocument:
    sha256: str
    filename: str
    saved_at: str


def default_db_path() -> Path:
    return Path(os.environ.get(DB_ENV_VAR, DEFAULT_DB))


def document_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def result_to_json(result: ParseResult) -> str:
    return json.dumps(
        {
            "courses": [
                {
                    "code": c.code,
                    "title": c.title,
                    "credits": c.credits,
                    "prerequisites": [list(g) for g in c.prerequisites],
                    "assessments": c.assessments,
                    "elective": c.elective,
                }
                for c in result.courses
            ],
            "warnings": result.warnings,
        }
    )


def result_from_json(text: str) -> ParseResult:
    data = json.loads(text)
    return ParseResult(
        courses=[
            Course(
                code=c["code"],
                title=c["title"],
                credits=c["credits"],
                prerequisites=tuple(tuple(g) for g in c["prerequisites"]),
                assessments=c["assessments"],
                elective=c.get("elective", False),
            )
            for c in data["courses"]
        ],
        warnings=list(data["warnings"]),
    )


class DocumentStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(_SCHEMA)
        return conn

    def save(self, filename: str, content: bytes, result: ParseResult) -> str:
        """Store a document and its parse result; returns the content hash."""
        digest = document_hash(content)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents (sha256, filename, content, parsed_json) "
                "VALUES (?, ?, ?, ?)",
                (digest, filename, content, result_to_json(result)),
            )
        return digest

    def load_parsed(self, content: bytes) -> ParseResult | None:
        """Cached parse result for exactly these bytes, if any."""
        if not self.path.exists():
            return None
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT parsed_json FROM documents WHERE sha256 = ?", (document_hash(content),)
            ).fetchone()
        return result_from_json(row[0]) if row else None

    def list_documents(self) -> list[StoredDocument]:
        if not self.path.exists():
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT sha256, filename, saved_at FROM documents ORDER BY saved_at DESC"
            ).fetchall()
        return [StoredDocument(*row) for row in rows]

    def delete_all(self) -> int:
        """Delete every stored document; returns how many were removed."""
        if not self.path.exists():
            return 0
        with closing(self._connect()) as conn, conn:
            return conn.execute("DELETE FROM documents").rowcount
