"""Tests for generate_gallery.py"""

import json
import os
import shutil
import struct
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Import from the script at repo root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_gallery as gg


class TestFindPhotos(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # Create some fake image files
        (self.tmp / "a.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
        (self.tmp / "b.png").write_bytes(b"\x89PNGfake")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "c.jpeg").write_bytes(b"\xff\xd8\xff\xe0fake")
        # Non-image file
        (self.tmp / "readme.txt").write_text("hello")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_supported_images(self):
        result = gg.find_photos(self.tmp)
        names = {p.name for p in result}
        self.assertIn("a.jpg", names)
        self.assertIn("b.png", names)
        self.assertIn("c.jpeg", names)
        self.assertNotIn("readme.txt", names)

    def test_excludes_gallery_dir(self):
        gallery = self.tmp / "_gallery" / "thumbnails"
        gallery.mkdir(parents=True)
        (gallery / "thumb.jpg").write_bytes(b"\xff\xd8fake")
        result = gg.find_photos(self.tmp)
        names = {p.name for p in result}
        self.assertNotIn("thumb.jpg", names)

    def test_empty_folder(self):
        empty = Path(tempfile.mkdtemp())
        try:
            result = gg.find_photos(empty)
            self.assertEqual(result, [])
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class TestGetPhotoDate(unittest.TestCase):
    def test_falls_back_to_mtime(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "test.txt"
            f.write_text("data")
            date = gg.get_photo_date(f)
            self.assertIsInstance(date, datetime)
            self.assertAlmostEqual(
                date.timestamp(), f.stat().st_mtime, delta=2,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestResizeLongEdge(unittest.TestCase):
    def test_no_resize_if_small(self):
        img = gg.Image.new("RGB", (100, 50))
        result = gg.resize_long_edge(img, 320)
        self.assertEqual(result.size, (100, 50))

    def test_resize_landscape(self):
        img = gg.Image.new("RGB", (1000, 500))
        result = gg.resize_long_edge(img, 320)
        self.assertEqual(result.size[0], 320)
        self.assertEqual(result.size[1], 160)

    def test_resize_portrait(self):
        img = gg.Image.new("RGB", (500, 1000))
        result = gg.resize_long_edge(img, 320)
        self.assertEqual(result.size[0], 160)
        self.assertEqual(result.size[1], 320)


class TestToRgb(unittest.TestCase):
    def test_rgb_unchanged(self):
        img = gg.Image.new("RGB", (10, 10))
        result = gg.to_rgb(img)
        self.assertEqual(result.mode, "RGB")

    def test_rgba_converted(self):
        img = gg.Image.new("RGBA", (10, 10))
        result = gg.to_rgb(img)
        self.assertEqual(result.mode, "RGB")

    def test_palette_converted(self):
        img = gg.Image.new("P", (10, 10))
        result = gg.to_rgb(img)
        self.assertEqual(result.mode, "RGB")


def _make_minimal_jpeg(path: Path, width: int = 2, height: int = 2) -> None:
    """Create a minimal valid JPEG using PIL."""
    img = gg.Image.new("RGB", (width, height), color=(128, 128, 128))
    img.save(str(path), "JPEG")


class TestProcessOne(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.gallery = self.root / "_gallery"
        (self.gallery / "thumbnails").mkdir(parents=True)
        (self.gallery / "views").mkdir(parents=True)
        # Create a real JPEG
        _make_minimal_jpeg(self.root / "test.jpg")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_generates_thumb_and_view(self):
        result = gg.process_one(self.root / "test.jpg", self.root, self.gallery)
        self.assertIsNotNone(result)
        self.assertEqual(result["file"], "test.jpg")
        self.assertTrue(result["thumb"].startswith("thumbnails/"))
        self.assertTrue(result["view"].startswith("views/"))
        # Files actually exist
        self.assertTrue((self.gallery / result["thumb"]).exists())
        self.assertTrue((self.gallery / result["view"]).exists())

    def test_returns_none_for_invalid_file(self):
        bad = self.root / "bad.jpg"
        bad.write_bytes(b"not a real image")
        result = gg.process_one(bad, self.root, self.gallery)
        self.assertIsNone(result)

    def test_metadata_fields(self):
        result = gg.process_one(self.root / "test.jpg", self.root, self.gallery)
        self.assertIn("date", result)
        self.assertIn("year", result)
        self.assertIn("month", result)
        self.assertIn("sort", result)


class TestGenerateHtml(unittest.TestCase):
    def setUp(self):
        self.gallery = Path(tempfile.mkdtemp()) / "_gallery"
        self.gallery.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.gallery.parent, ignore_errors=True)

    def test_creates_index_html(self):
        photos = [
            {
                "file": "test.jpg",
                "thumb": "thumbnails/abc.jpg",
                "view": "views/abc.jpg",
                "date": "2025-03-15 10:30",
                "year": 2025,
                "month": 3,
                "sort": "20250315103000",
            }
        ]
        path = gg.generate_html(photos, self.gallery, "TestFolder")
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("Photo Archive", content)
        self.assertIn("TestFolder", content)
        self.assertIn("2025年 3月", content)
        self.assertIn("thumbnails/abc.jpg", content)

    def test_multiple_months_sorted(self):
        photos = [
            {
                "file": "a.jpg", "thumb": "t/a.jpg", "view": "v/a.jpg",
                "date": "2025-01-01 00:00", "year": 2025, "month": 1,
                "sort": "20250101000000",
            },
            {
                "file": "b.jpg", "thumb": "t/b.jpg", "view": "v/b.jpg",
                "date": "2025-03-15 00:00", "year": 2025, "month": 3,
                "sort": "20250315000000",
            },
        ]
        path = gg.generate_html(photos, self.gallery, "Test")
        content = path.read_text(encoding="utf-8")
        # March should appear before January (reverse chronological)
        pos_mar = content.index("2025-03")
        pos_jan = content.index("2025-01")
        self.assertLess(pos_mar, pos_jan)


if __name__ == "__main__":
    unittest.main()
