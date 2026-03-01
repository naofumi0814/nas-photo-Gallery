"""SQLite manifest (台帳) — tracks all known photos for incremental updates."""

import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .scanner import FileEntry

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS photos (
    relative_path TEXT PRIMARY KEY,
    size_bytes    INTEGER NOT NULL,
    mtime         REAL NOT NULL,
    sha1          TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    meta_json     TEXT,
    thumb_path    TEXT,
    view_path     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_SHA1_INDEX = """
CREATE INDEX IF NOT EXISTS idx_photos_sha1 ON photos(sha1) WHERE sha1 IS NOT NULL;
"""

CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def compute_file_sha1(filepath: str) -> str:
    """Compute SHA1 hash of a file. Reads in 64KB chunks."""
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dataclass
class DiffResult:
    new: List[FileEntry]
    updated: List[FileEntry]
    deleted: List[str]         # relative_path list
    unchanged: List[str]       # relative_path list


@dataclass
class DuplicateInfo:
    """Info about a duplicate detection."""
    new_path: str              # the new file that is a duplicate
    existing_path: str         # the already-registered path with same sha1
    sha1: str


class Manifest:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(CREATE_TABLE)
        cur.execute(CREATE_SHA1_INDEX)
        cur.execute(CREATE_META)
        cur.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        self.conn.commit()

    def get_active_paths(self) -> Dict[str, Tuple[int, float]]:
        """Return {relative_path: (size_bytes, mtime)} for active entries."""
        cur = self.conn.execute(
            "SELECT relative_path, size_bytes, mtime FROM photos WHERE status = 'active'"
        )
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    def compute_diff(self, entries: List[FileEntry], force_rebuild: bool = False) -> DiffResult:
        """Compare scanned entries against manifest to determine what needs processing."""
        existing = self.get_active_paths()
        existing_keys = set(existing.keys())
        scanned_keys: Set[str] = set()

        new_files: List[FileEntry] = []
        updated_files: List[FileEntry] = []
        unchanged_files: List[str] = []

        for entry in entries:
            scanned_keys.add(entry.relative_path)

            if entry.relative_path not in existing_keys:
                new_files.append(entry)
            elif force_rebuild:
                updated_files.append(entry)
            else:
                old_size, old_mtime = existing[entry.relative_path]
                if entry.size_bytes != old_size or abs(entry.mtime - old_mtime) > 1.0:
                    updated_files.append(entry)
                else:
                    unchanged_files.append(entry.relative_path)

        deleted_paths = list(existing_keys - scanned_keys)

        logger.info(
            "Diff: %d new, %d updated, %d deleted, %d unchanged",
            len(new_files), len(updated_files), len(deleted_paths), len(unchanged_files),
        )
        return DiffResult(
            new=new_files,
            updated=updated_files,
            deleted=deleted_paths,
            unchanged=unchanged_files,
        )

    # --- Duplicate detection ---

    def find_active_by_sha1(self, sha1: str) -> Optional[str]:
        """Return relative_path of an active entry with this sha1, or None."""
        cur = self.conn.execute(
            "SELECT relative_path FROM photos WHERE sha1 = ? AND status = 'active' LIMIT 1",
            (sha1,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def find_deleted_by_sha1(self, sha1: str) -> Optional[str]:
        """Return relative_path of a deleted entry with this sha1, or None.

        Used for detecting file moves: same content at a new path,
        old path marked deleted.
        """
        cur = self.conn.execute(
            "SELECT relative_path FROM photos WHERE sha1 = ? AND status = 'deleted' LIMIT 1",
            (sha1,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def adopt_moved_file(self, old_path: str, new_path: str,
                         size_bytes: int, mtime: float):
        """Handle a file that moved: copy metadata from old entry to new path,
        then mark old path as deleted.

        The old entry's meta_json/thumb_path/view_path are preserved under
        the new relative_path. The caller should still regenerate thumb/view
        since paths have changed.
        """
        cur = self.conn.execute(
            "SELECT sha1, meta_json FROM photos WHERE relative_path = ?",
            (old_path,),
        )
        row = cur.fetchone()
        if not row:
            return
        sha1, meta_json = row

        # Mark old path as deleted
        self.conn.execute(
            "UPDATE photos SET status = 'deleted', updated_at = datetime('now') WHERE relative_path = ?",
            (old_path,),
        )
        logger.info("File move detected: %s -> %s (sha1=%s)", old_path, new_path, sha1)

    # --- Standard CRUD ---

    def upsert(self, relative_path: str, size_bytes: int, mtime: float,
               meta_json: str, thumb_path: str, view_path: str,
               sha1: Optional[str] = None):
        self.conn.execute("""
            INSERT INTO photos (relative_path, size_bytes, mtime, sha1, status, meta_json, thumb_path, view_path, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, datetime('now'))
            ON CONFLICT(relative_path) DO UPDATE SET
                size_bytes = excluded.size_bytes,
                mtime = excluded.mtime,
                sha1 = excluded.sha1,
                status = 'active',
                meta_json = excluded.meta_json,
                thumb_path = excluded.thumb_path,
                view_path = excluded.view_path,
                updated_at = datetime('now')
        """, (relative_path, size_bytes, mtime, sha1, meta_json, thumb_path, view_path))

    def mark_deleted(self, relative_paths: List[str]):
        if not relative_paths:
            return
        for rp in relative_paths:
            self.conn.execute(
                "UPDATE photos SET status = 'deleted', updated_at = datetime('now') WHERE relative_path = ?",
                (rp,),
            )

    def get_all_active_meta(self) -> list:
        """Return list of dicts for all active photos (for metadata.json export)."""
        cur = self.conn.execute(
            "SELECT relative_path, meta_json, thumb_path, view_path FROM photos WHERE status = 'active'"
        )
        results = []
        for row in cur.fetchall():
            try:
                meta = json.loads(row[1]) if row[1] else {}
            except json.JSONDecodeError:
                meta = {}
            meta["relative_path"] = row[0]
            meta["thumb_path"] = row[2]
            meta["view_path"] = row[3]
            results.append(meta)
        return results

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

    @property
    def active_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM photos WHERE status = 'active'")
        return cur.fetchone()[0]
