"""Tests for manifest (台帳) — incremental diff detection."""

import os
import tempfile
import unittest

from photo_archive.manifest import Manifest
from photo_archive.scanner import FileEntry


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "data", "manifest.sqlite")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_new_files_detected(self):
        m = Manifest(self.db_path)
        entries = [
            FileEntry("2024/01/photo1.jpg", "/abs/2024/01/photo1.jpg", 1000, 1700000000.0),
            FileEntry("2024/01/photo2.jpg", "/abs/2024/01/photo2.jpg", 2000, 1700000001.0),
        ]
        diff = m.compute_diff(entries)
        self.assertEqual(len(diff.new), 2)
        self.assertEqual(len(diff.updated), 0)
        self.assertEqual(len(diff.deleted), 0)
        self.assertEqual(len(diff.unchanged), 0)
        m.close()

    def test_unchanged_files_skipped(self):
        m = Manifest(self.db_path)
        # Simulate first run
        m.upsert("2024/01/photo1.jpg", 1000, 1700000000.0, '{}', "t/p1.jpg", "v/p1.jpg")
        m.commit()

        entries = [
            FileEntry("2024/01/photo1.jpg", "/abs/2024/01/photo1.jpg", 1000, 1700000000.0),
        ]
        diff = m.compute_diff(entries)
        self.assertEqual(len(diff.new), 0)
        self.assertEqual(len(diff.updated), 0)
        self.assertEqual(len(diff.unchanged), 1)
        m.close()

    def test_updated_files_detected_by_size(self):
        m = Manifest(self.db_path)
        m.upsert("photo.jpg", 1000, 1700000000.0, '{}', "t/p.jpg", "v/p.jpg")
        m.commit()

        entries = [
            FileEntry("photo.jpg", "/abs/photo.jpg", 2000, 1700000000.0),  # size changed
        ]
        diff = m.compute_diff(entries)
        self.assertEqual(len(diff.updated), 1)
        self.assertEqual(len(diff.unchanged), 0)
        m.close()

    def test_updated_files_detected_by_mtime(self):
        m = Manifest(self.db_path)
        m.upsert("photo.jpg", 1000, 1700000000.0, '{}', "t/p.jpg", "v/p.jpg")
        m.commit()

        entries = [
            FileEntry("photo.jpg", "/abs/photo.jpg", 1000, 1700005000.0),  # mtime changed
        ]
        diff = m.compute_diff(entries)
        self.assertEqual(len(diff.updated), 1)
        m.close()

    def test_deleted_files_detected(self):
        m = Manifest(self.db_path)
        m.upsert("photo1.jpg", 1000, 1700000000.0, '{}', "t/1.jpg", "v/1.jpg")
        m.upsert("photo2.jpg", 2000, 1700000000.0, '{}', "t/2.jpg", "v/2.jpg")
        m.commit()

        # Only photo1 exists now
        entries = [
            FileEntry("photo1.jpg", "/abs/photo1.jpg", 1000, 1700000000.0),
        ]
        diff = m.compute_diff(entries)
        self.assertEqual(len(diff.deleted), 1)
        self.assertIn("photo2.jpg", diff.deleted)
        m.close()

    def test_force_rebuild_marks_all_as_updated(self):
        m = Manifest(self.db_path)
        m.upsert("photo.jpg", 1000, 1700000000.0, '{}', "t/p.jpg", "v/p.jpg")
        m.commit()

        entries = [
            FileEntry("photo.jpg", "/abs/photo.jpg", 1000, 1700000000.0),
        ]
        diff = m.compute_diff(entries, force_rebuild=True)
        self.assertEqual(len(diff.updated), 1)
        self.assertEqual(len(diff.unchanged), 0)
        m.close()

    def test_mark_deleted_excludes_from_active(self):
        m = Manifest(self.db_path)
        m.upsert("photo.jpg", 1000, 1700000000.0, '{}', "t/p.jpg", "v/p.jpg")
        m.commit()

        m.mark_deleted(["photo.jpg"])
        m.commit()

        self.assertEqual(m.active_count, 0)
        active = m.get_all_active_meta()
        self.assertEqual(len(active), 0)
        m.close()


if __name__ == "__main__":
    unittest.main()
