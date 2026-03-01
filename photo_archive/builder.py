"""Builder — orchestrates the full build pipeline."""

import json
import logging
import os
import shutil
import time
import webbrowser
from typing import Optional

from .config import Config
from .exif import extract_exif
from .html_gen import export_metadata_json, generate_all_html
from .imaging import generate_thumbnail, generate_view
from .lock import BuildLock
from .manifest import Manifest, compute_file_sha1
from .scanner import FileEntry, scan_directory

logger = logging.getLogger(__name__)


class BuildResult:
    def __init__(self):
        self.new_count = 0
        self.updated_count = 0
        self.skipped_count = 0
        self.deleted_count = 0
        self.duplicate_count = 0
        self.error_count = 0
        self.total_active = 0
        self.elapsed = 0.0

    def summary(self) -> str:
        return (
            f"新規: {self.new_count}  更新: {self.updated_count}  "
            f"スキップ: {self.skipped_count}  削除扱い: {self.deleted_count}  "
            f"重複: {self.duplicate_count}  "
            f"エラー: {self.error_count}  合計アクティブ: {self.total_active}  "
            f"所要時間: {self.elapsed:.1f}秒"
        )


def _output_path_for(relative_path: str, prefix: str) -> str:
    """Convert relative photo path to output path with prefix, using .jpg extension."""
    base, _ = os.path.splitext(relative_path)
    return os.path.join(prefix, base + ".jpg").replace("\\", "/")


def build(config: Config) -> BuildResult:
    """Run the full build pipeline."""
    result = BuildResult()
    t0 = time.time()

    # Setup logging
    log_dir = os.path.join(config.output_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    _setup_file_logging(log_dir)

    logger.info("=== Photo Archive Build Start ===")
    logger.info("input_root:  %s", config.input_root)
    logger.info("output_root: %s", config.output_root)
    logger.info("thumb_size:  %d", config.thumb_size)
    logger.info("view_size:   %d", config.view_size)
    logger.info("rebuild:     %s", config.rebuild)

    # Lock
    lock_dir = os.path.join(config.output_root, "locks")
    lock = BuildLock(lock_dir)
    if not lock.acquire():
        print("ERROR: 前回のビルドが実行中です。ロックファイルを確認してください。")
        logger.error("Cannot acquire build lock — aborting")
        result.elapsed = time.time() - t0
        return result

    try:
        _do_build(config, result)
    except Exception as exc:
        logger.exception("Build failed: %s", exc)
        result.error_count += 1
    finally:
        lock.release()
        result.elapsed = time.time() - t0
        logger.info("=== Build Complete === %s", result.summary())
        _write_run_log(log_dir, config, result)

    return result


def _do_build(config: Config, result: BuildResult):
    """Core build logic."""
    # Determine working output root (temp or direct)
    use_temp = config.temp_root is not None
    if use_temp:
        work_root = config.temp_root
        os.makedirs(work_root, exist_ok=True)
        logger.info("Using temp directory: %s", work_root)
    else:
        work_root = config.output_root

    # Ensure output directories exist
    for subdir in ("thumbnails", "views", "data", "assets", "logs", "locks"):
        os.makedirs(os.path.join(work_root, subdir), exist_ok=True)

    # Open manifest (always in final output root for persistence)
    manifest_path = os.path.join(config.output_root, "data", "manifest.sqlite")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    manifest = Manifest(manifest_path)

    # Scan input
    entries = scan_directory(config.input_root, config.supported_extensions)

    # Compute diff
    diff = manifest.compute_diff(entries, force_rebuild=config.rebuild)
    result.skipped_count = len(diff.unchanged)
    result.deleted_count = len(diff.deleted)

    # Mark deleted
    if diff.deleted:
        manifest.mark_deleted(diff.deleted)
        manifest.commit()
        logger.info("Marked %d entries as deleted", len(diff.deleted))

    # Error log
    error_log_path = os.path.join(config.output_root, "logs", "errors.log")
    error_log = open(error_log_path, "a", encoding="utf-8")

    # Build a set of new file paths for identifying new vs updated
    new_file_set = set(e.relative_path for e in diff.new)

    # Process new and updated files
    to_process = diff.new + diff.updated
    total = len(to_process)
    for i, entry in enumerate(to_process, 1):
        if i % 50 == 0 or i == 1 or i == total:
            logger.info("Processing %d/%d: %s", i, total, entry.relative_path)

        try:
            is_new = entry.relative_path in new_file_set

            # --- Duplicate detection (sha1) for NEW files ---
            if is_new:
                dup_result = _check_duplicate(entry, manifest)
                if dup_result == "skip":
                    result.duplicate_count += 1
                    logger.info(
                        "[DUPLICATE] Skipped: %s (same content already in gallery)",
                        entry.relative_path,
                    )
                    continue
                # dup_result == "moved" means old entry was deleted and
                # we proceed to process the new path normally

            _process_one(entry, config, work_root, manifest)
            if is_new:
                result.new_count += 1
            else:
                result.updated_count += 1
        except Exception as exc:
            result.error_count += 1
            msg = f"[ERROR] {entry.relative_path}: {exc}\n"
            logger.error(msg.strip())
            error_log.write(msg)

    error_log.close()
    manifest.commit()

    # If using temp, sync generated files to output
    if use_temp:
        logger.info("Syncing from temp to output…")
        for subdir in ("thumbnails", "views"):
            src = os.path.join(work_root, subdir)
            dst = os.path.join(config.output_root, subdir)
            if os.path.isdir(src):
                # Copy tree
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

    # Generate metadata.json
    all_active = manifest.get_all_active_meta()
    export_metadata_json(all_active, config.output_root, hide_gps=config.hide_gps)

    # Generate HTML
    generate_all_html(
        photos=all_active,
        output_root=config.output_root,
        site_title=config.site_title,
        recent_count=config.recent_count,
        hide_gps=config.hide_gps,
        enable_open_original=config.enable_open_original,
        input_root=config.input_root,
    )

    result.total_active = manifest.active_count
    manifest.close()

    # Clean up temp
    if use_temp and os.path.isdir(work_root):
        try:
            shutil.rmtree(work_root)
        except OSError as exc:
            logger.warning("Could not clean temp dir: %s", exc)


def _check_duplicate(entry: FileEntry, manifest: Manifest) -> str:
    """Check if a new file is a duplicate by sha1.

    Returns:
        "skip"    — same sha1 exists as active, skip this file
        "moved"   — same sha1 was deleted (file moved), old entry marked deleted
        "unique"  — no duplicate found, process normally
    """
    try:
        sha1 = compute_file_sha1(entry.absolute_path)
    except OSError as exc:
        logger.warning("Cannot compute sha1 for %s: %s", entry.relative_path, exc)
        return "unique"

    # Store sha1 on the entry object for later use in _process_one
    entry._sha1 = sha1

    # Check active entries with same hash
    existing_path = manifest.find_active_by_sha1(sha1)
    if existing_path:
        logger.info(
            "[DUPLICATE] %s is duplicate of active %s (sha1=%s)",
            entry.relative_path, existing_path, sha1,
        )
        return "skip"

    # Check deleted entries — possible file move
    deleted_path = manifest.find_deleted_by_sha1(sha1)
    if deleted_path:
        manifest.adopt_moved_file(deleted_path, entry.relative_path,
                                  entry.size_bytes, entry.mtime)
        logger.info(
            "[MOVE] %s appears to be moved from deleted %s (sha1=%s)",
            entry.relative_path, deleted_path, sha1,
        )
        return "moved"

    return "unique"


def _process_one(entry: FileEntry, config: Config, work_root: str, manifest: Manifest):
    """Process a single photo: extract EXIF, generate thumb + view, update manifest."""
    # Extract EXIF
    meta = extract_exif(entry.absolute_path, entry.mtime)

    # Thumbnail path
    thumb_rel = _output_path_for(entry.relative_path, "thumbnails")
    thumb_abs = os.path.join(work_root, thumb_rel)

    # View path
    view_rel = _output_path_for(entry.relative_path, "views")
    view_abs = os.path.join(work_root, view_rel)

    # Generate thumbnail
    ok_thumb = generate_thumbnail(entry.absolute_path, thumb_abs, config.thumb_size)
    if not ok_thumb:
        raise RuntimeError(f"Thumbnail generation failed: {entry.relative_path}")

    # Generate view
    ok_view = generate_view(entry.absolute_path, view_abs, config.view_size)
    if not ok_view:
        raise RuntimeError(f"View generation failed: {entry.relative_path}")

    # Get sha1 (may have been computed during duplicate check, or compute now)
    sha1 = getattr(entry, "_sha1", None)
    if sha1 is None:
        try:
            sha1 = compute_file_sha1(entry.absolute_path)
        except OSError:
            sha1 = None

    # Upsert manifest
    manifest.upsert(
        relative_path=entry.relative_path,
        size_bytes=entry.size_bytes,
        mtime=entry.mtime,
        meta_json=json.dumps(meta, ensure_ascii=False),
        thumb_path=thumb_rel,
        view_path=view_rel,
        sha1=sha1,
    )


def _setup_file_logging(log_dir: str):
    """Add file handler for run.log."""
    run_log_path = os.path.join(log_dir, "run.log")
    handler = logging.FileHandler(run_log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(handler)


def _write_run_log(log_dir: str, config: Config, result: BuildResult):
    """Append summary to run.log."""
    run_log_path = os.path.join(log_dir, "run.log")
    with open(run_log_path, "a", encoding="utf-8") as f:
        f.write(f"\n=== Summary ===\n")
        f.write(result.summary() + "\n")
        f.write(f"input_root:  {config.input_root}\n")
        f.write(f"output_root: {config.output_root}\n")
        f.write(f"thumb_size:  {config.thumb_size}\n")
        f.write(f"view_size:   {config.view_size}\n")
        f.write(f"rebuild:     {config.rebuild}\n")
        f.write(f"include_heic: {config.include_heic}\n")
        f.write(f"hide_gps:    {config.hide_gps}\n")
        f.write(f"===============\n\n")
