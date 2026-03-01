"""Tests for duplicate detection — sha1-based dedup and file move handling."""

import hashlib
import os
import tempfile
import shutil
import unittest

from photo_archive.manifest import Manifest, compute_file_sha1
from photo_archive.scanner import FileEntry


class TestComputeFileSha1(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_computes_correct_hash(self):
        path = os.path.join(self.tmpdir, "test.bin")
        content = b"Hello, Photo Archive!"
        with open(path, "wb") as f:
            f.write(content)

        expected = hashlib.sha1(content).hexdigest()
        self.assertEqual(compute_file_sha1(path), expected)

    def test_same_content_same_hash(self):
        content = b"identical content across two files"
        path_a = os.path.join(self.tmpdir, "a.jpg")
        path_b = os.path.join(self.tmpdir, "b.jpg")
        for p in (path_a, path_b):
            with open(p, "wb") as f:
                f.write(content)

        self.assertEqual(compute_file_sha1(path_a), compute_file_sha1(path_b))

    def test_different_content_different_hash(self):
        path_a = os.path.join(self.tmpdir, "a.jpg")
        path_b = os.path.join(self.tmpdir, "b.jpg")
        with open(path_a, "wb") as f:
            f.write(b"content A")
        with open(path_b, "wb") as f:
            f.write(b"content B")

        self.assertNotEqual(compute_file_sha1(path_a), compute_file_sha1(path_b))


class TestDuplicateDetection(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "data", "manifest.sqlite")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_find_active_by_sha1_returns_match(self):
        m = Manifest(self.db_path)
        sha1 = "abc123"
        m.upsert("photos/a.jpg", 1000, 1700000000.0, '{}', "t/a.jpg", "v/a.jpg", sha1=sha1)
        m.commit()

        result = m.find_active_by_sha1(sha1)
        self.assertEqual(result, "photos/a.jpg")
        m.close()

    def test_find_active_by_sha1_returns_none_for_missing(self):
        m = Manifest(self.db_path)
        m.upsert("photos/a.jpg", 1000, 1700000000.0, '{}', "t/a.jpg", "v/a.jpg", sha1="abc123")
        m.commit()

        result = m.find_active_by_sha1("zzz999")
        self.assertIsNone(result)
        m.close()

    def test_find_active_by_sha1_ignores_deleted(self):
        m = Manifest(self.db_path)
        sha1 = "abc123"
        m.upsert("photos/a.jpg", 1000, 1700000000.0, '{}', "t/a.jpg", "v/a.jpg", sha1=sha1)
        m.mark_deleted(["photos/a.jpg"])
        m.commit()

        result = m.find_active_by_sha1(sha1)
        self.assertIsNone(result)
        m.close()

    def test_find_deleted_by_sha1_returns_match(self):
        m = Manifest(self.db_path)
        sha1 = "abc123"
        m.upsert("photos/old.jpg", 1000, 1700000000.0, '{}', "t/old.jpg", "v/old.jpg", sha1=sha1)
        m.mark_deleted(["photos/old.jpg"])
        m.commit()

        result = m.find_deleted_by_sha1(sha1)
        self.assertEqual(result, "photos/old.jpg")
        m.close()

    def test_find_deleted_by_sha1_returns_none_for_active(self):
        m = Manifest(self.db_path)
        sha1 = "abc123"
        m.upsert("photos/a.jpg", 1000, 1700000000.0, '{}', "t/a.jpg", "v/a.jpg", sha1=sha1)
        m.commit()

        result = m.find_deleted_by_sha1(sha1)
        self.assertIsNone(result)
        m.close()

    def test_duplicate_of_active_is_detected(self):
        """When two files have same sha1, second should be detectable as duplicate."""
        m = Manifest(self.db_path)
        sha1 = "deadbeef"
        m.upsert("folder1/photo.jpg", 5000, 1700000000.0, '{}', "t/1.jpg", "v/1.jpg", sha1=sha1)
        m.commit()

        # Simulate finding the same sha1 for a new path
        found = m.find_active_by_sha1(sha1)
        self.assertIsNotNone(found)
        self.assertEqual(found, "folder1/photo.jpg")
        m.close()

    def test_file_move_detected_via_deleted_sha1(self):
        """File moved = old path deleted + new path with same sha1."""
        m = Manifest(self.db_path)
        sha1 = "moved123"

        # Original file
        m.upsert("old/path.jpg", 5000, 1700000000.0, '{}', "t/old.jpg", "v/old.jpg", sha1=sha1)
        m.commit()

        # Simulate delete (file disappeared from old location)
        m.mark_deleted(["old/path.jpg"])
        m.commit()

        # New file appears with same sha1
        found = m.find_deleted_by_sha1(sha1)
        self.assertEqual(found, "old/path.jpg")

        # Adopt move
        m.adopt_moved_file("old/path.jpg", "new/path.jpg", 5000, 1700000001.0)
        m.commit()

        # Old path should still be deleted
        active = m.get_active_paths()
        self.assertNotIn("old/path.jpg", active)
        m.close()

    def test_sha1_none_not_matched(self):
        """Entries without sha1 should not match each other."""
        m = Manifest(self.db_path)
        m.upsert("a.jpg", 1000, 1700000000.0, '{}', "t/a.jpg", "v/a.jpg", sha1=None)
        m.commit()

        result = m.find_active_by_sha1("")
        # sha1 is NULL, so "" won't match
        self.assertIsNone(result)
        m.close()


if __name__ == "__main__":
    unittest.main()
