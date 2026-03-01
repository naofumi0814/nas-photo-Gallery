"""Filesystem scanner — recursively finds photo files under input_root."""

import os
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    """Represents a discovered photo file."""
    relative_path: str      # forward-slash normalised, relative to input_root
    absolute_path: str
    size_bytes: int
    mtime: float


def normalise_rel_path(path: str) -> str:
    """Normalise a relative path to forward slashes for consistent keys."""
    return path.replace("\\", "/")


def scan_directory(input_root: str, extensions: tuple) -> List[FileEntry]:
    """Walk input_root recursively and return FileEntry list for supported extensions."""
    entries: List[FileEntry] = []
    input_root = os.path.normpath(input_root)

    for dirpath, _dirnames, filenames in os.walk(input_root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, input_root)
            rel_path = normalise_rel_path(rel_path)

            try:
                st = os.stat(abs_path)
                entries.append(FileEntry(
                    relative_path=rel_path,
                    absolute_path=abs_path,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                ))
            except OSError as exc:
                logger.warning("Cannot stat %s: %s", abs_path, exc)

    logger.info("Scanned %d files under %s", len(entries), input_root)
    return entries
