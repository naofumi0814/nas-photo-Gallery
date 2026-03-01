"""Tests for scanner — path normalisation and filtering."""

import os
import tempfile
import unittest

from photo_archive.scanner import normalise_rel_path, scan_directory


class TestPathNormalisation(unittest.TestCase):
    def test_backslash_to_forward(self):
        self.assertEqual(normalise_rel_path("2024\\01\\photo.jpg"), "2024/01/photo.jpg")

    def test_forward_slash_unchanged(self):
        self.assertEqual(normalise_rel_path("2024/01/photo.jpg"), "2024/01/photo.jpg")

    def test_mixed_slashes(self):
        self.assertEqual(normalise_rel_path("2024\\01/photo.jpg"), "2024/01/photo.jpg")

    def test_single_filename(self):
        self.assertEqual(normalise_rel_path("photo.jpg"), "photo.jpg")


class TestScanDirectory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_jpg_files(self):
        # Create test files
        os.makedirs(os.path.join(self.tmpdir, "2024", "01"), exist_ok=True)
        for name in ["photo1.jpg", "photo2.JPG", "photo3.png"]:
            path = os.path.join(self.tmpdir, "2024", "01", name)
            with open(path, "w") as f:
                f.write("fake")

        entries = scan_directory(self.tmpdir, (".jpg", ".jpeg", ".png"))
        names = [e.relative_path for e in entries]
        self.assertEqual(len(entries), 3)

    def test_ignores_unsupported_extensions(self):
        for name in ["doc.txt", "video.mp4", "data.csv"]:
            with open(os.path.join(self.tmpdir, name), "w") as f:
                f.write("fake")

        entries = scan_directory(self.tmpdir, (".jpg", ".jpeg", ".png"))
        self.assertEqual(len(entries), 0)

    def test_relative_paths_use_forward_slashes(self):
        os.makedirs(os.path.join(self.tmpdir, "a", "b"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "a", "b", "c.jpg"), "w") as f:
            f.write("fake")

        entries = scan_directory(self.tmpdir, (".jpg",))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].relative_path, "a/b/c.jpg")
        self.assertNotIn("\\", entries[0].relative_path)

    def test_heic_included_when_allowed(self):
        with open(os.path.join(self.tmpdir, "img.heic"), "w") as f:
            f.write("fake")

        entries_without = scan_directory(self.tmpdir, (".jpg", ".jpeg", ".png"))
        self.assertEqual(len(entries_without), 0)

        entries_with = scan_directory(self.tmpdir, (".jpg", ".jpeg", ".png", ".heic"))
        self.assertEqual(len(entries_with), 1)


if __name__ == "__main__":
    unittest.main()
