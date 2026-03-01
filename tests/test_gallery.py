"""Tests for generate_gallery.py"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_gallery as gg


# ── find_photos ──────────────────────────────────────────────

class TestFindPhotos(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "a.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
        (self.tmp / "b.png").write_bytes(b"\x89PNGfake")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "c.jpeg").write_bytes(b"\xff\xd8\xff\xe0fake")
        (self.tmp / "readme.txt").write_text("hello")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_supported_images(self):
        names = {p.name for p in gg.find_photos(self.tmp)}
        self.assertIn("a.jpg", names)
        self.assertIn("b.png", names)
        self.assertIn("c.jpeg", names)
        self.assertNotIn("readme.txt", names)

    def test_excludes_gallery_dir(self):
        gallery = self.tmp / "_gallery" / "thumbnails"
        gallery.mkdir(parents=True)
        (gallery / "thumb.jpg").write_bytes(b"\xff\xd8fake")
        names = {p.name for p in gg.find_photos(self.tmp)}
        self.assertNotIn("thumb.jpg", names)

    def test_empty_folder(self):
        empty = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(gg.find_photos(empty), [])
        finally:
            shutil.rmtree(empty, ignore_errors=True)


# ── EXIF extraction ──────────────────────────────────────────

class TestExtractExif(unittest.TestCase):
    def test_returns_dict_for_non_image(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "test.txt"
            f.write_text("hello")
            info = gg.extract_exif(f)
            self.assertIsInstance(info, dict)
            self.assertEqual(info["camera"], "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_returns_dict_for_jpeg_without_exif(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "test.jpg"
            gg.Image.new("RGB", (10, 10)).save(str(f), "JPEG")
            info = gg.extract_exif(f)
            self.assertEqual(info["camera"], "")
            self.assertEqual(info["iso"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ── get_photo_date ───────────────────────────────────────────

class TestGetPhotoDate(unittest.TestCase):
    def test_uses_exif_date_when_available(self):
        dt = datetime(2025, 6, 15, 10, 30, 0)
        info = {"date_dt": dt}
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "test.txt"
            f.write_text("data")
            result = gg.get_photo_date(f, info)
            self.assertEqual(result, dt)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_falls_back_to_mtime(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "test.txt"
            f.write_text("data")
            result = gg.get_photo_date(f, {"date_dt": None})
            self.assertIsInstance(result, datetime)
            self.assertAlmostEqual(result.timestamp(), f.stat().st_mtime, delta=2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ── Image processing ─────────────────────────────────────────

class TestToRgb(unittest.TestCase):
    def test_rgb_unchanged(self):
        self.assertEqual(gg.to_rgb(gg.Image.new("RGB", (10, 10))).mode, "RGB")

    def test_rgba_converted(self):
        self.assertEqual(gg.to_rgb(gg.Image.new("RGBA", (10, 10))).mode, "RGB")

    def test_palette_converted(self):
        self.assertEqual(gg.to_rgb(gg.Image.new("P", (10, 10))).mode, "RGB")


class TestProcessOne(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.gallery = self.root / "_gallery"
        (self.gallery / "thumbnails").mkdir(parents=True)
        (self.gallery / "views").mkdir(parents=True)
        gg.Image.new("RGB", (800, 600), (128, 128, 128)).save(
            str(self.root / "test.jpg"), "JPEG",
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_generates_thumb_and_view(self):
        r = gg.process_one(self.root / "test.jpg", self.root, self.gallery)
        self.assertIsNotNone(r)
        self.assertEqual(r["f"], "test.jpg")
        self.assertTrue((self.gallery / r["t"]).exists())
        self.assertTrue((self.gallery / r["v"]).exists())

    def test_returns_none_for_invalid_file(self):
        bad = self.root / "bad.jpg"
        bad.write_bytes(b"not a real image")
        self.assertIsNone(gg.process_one(bad, self.root, self.gallery))

    def test_has_exif_fields(self):
        r = gg.process_one(self.root / "test.jpg", self.root, self.gallery)
        for key in ("cam", "lens", "fl", "fn", "iso", "ss", "d", "s", "y", "m"):
            self.assertIn(key, r)

    def test_thumbnail_fits_within_long_edge(self):
        r = gg.process_one(self.root / "test.jpg", self.root, self.gallery)
        thumb = gg.Image.open(self.gallery / r["t"])
        self.assertLessEqual(max(thumb.size), gg.THUMB_LONG_EDGE)


# ── HTML generation ──────────────────────────────────────────

def _sample_photo(**overrides):
    base = {
        "f": "test.jpg", "t": "thumbnails/abc.jpg", "v": "views/abc.jpg",
        "d": "2025-03-15 10:30", "s": "20250315103000",
        "y": 2025, "m": 3,
        "cam": "Canon EOS R5", "lens": "RF 50mm F1.2L",
        "fl": 50, "fn": 1.4, "ss": "1/250s", "iso": 400,
    }
    base.update(overrides)
    return base


class TestGenerateIndexHtml(unittest.TestCase):
    def setUp(self):
        self.gallery = Path(tempfile.mkdtemp()) / "_gallery"
        self.gallery.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.gallery.parent, ignore_errors=True)

    def test_creates_index_html(self):
        year_info = [
            {"year": 2025, "count": 100, "cover": "thumbnails/abc.jpg"},
            {"year": 2024, "count": 200, "cover": "thumbnails/def.jpg"},
        ]
        path = gg.generate_index_html(year_info, self.gallery, "TestFolder")
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("Photo Archive", content)
        self.assertIn("TestFolder", content)
        self.assertIn("2025", content)
        self.assertIn("2024", content)
        self.assertIn("300", content)  # total
        self.assertIn("2025.html", content)

    def test_year_order_preserved(self):
        year_info = [
            {"year": 2025, "count": 10, "cover": "t/a.jpg"},
            {"year": 2023, "count": 20, "cover": "t/b.jpg"},
        ]
        content = gg.generate_index_html(year_info, self.gallery, "T").read_text()
        self.assertLess(content.index("2025"), content.index("2023"))


class TestGenerateYearHtml(unittest.TestCase):
    def setUp(self):
        self.gallery = Path(tempfile.mkdtemp()) / "_gallery"
        self.gallery.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.gallery.parent, ignore_errors=True)

    def test_creates_year_html(self):
        photos = [_sample_photo()]
        path = gg.generate_year_html(2025, photos, self.gallery, "Test")
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "2025.html")

    def test_contains_filter_controls(self):
        photos = [_sample_photo()]
        content = gg.generate_year_html(2025, photos, self.gallery, "T").read_text()
        self.assertIn("f-cam", content)
        self.assertIn("f-lens", content)
        self.assertIn("f-sort", content)
        self.assertIn("f-q", content)

    def test_contains_photo_data(self):
        photos = [_sample_photo(cam="Nikon Z9", fl=85)]
        content = gg.generate_year_html(2025, photos, self.gallery, "T").read_text()
        self.assertIn("Nikon Z9", content)
        self.assertIn('"fl": 85', content)

    def test_contains_lightbox(self):
        photos = [_sample_photo()]
        content = gg.generate_year_html(2025, photos, self.gallery, "T").read_text()
        self.assertIn('id="lb"', content)
        self.assertIn("openLB", content)
        self.assertIn("closeLB", content)

    def test_contains_back_link(self):
        photos = [_sample_photo()]
        content = gg.generate_year_html(2025, photos, self.gallery, "T").read_text()
        self.assertIn("index.html", content)
        self.assertIn("戻る", content)

    def test_sort_options(self):
        photos = [_sample_photo()]
        content = gg.generate_year_html(2025, photos, self.gallery, "T").read_text()
        self.assertIn("日付", content)
        self.assertIn("カメラ", content)
        self.assertIn("焦点距離", content)
        self.assertIn("ISO", content)


if __name__ == "__main__":
    unittest.main()
