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

    def test_generates_thumb_and_links_original(self):
        r = gg.process_one(self.root / "test.jpg", self.root, self.gallery)
        self.assertIsNotNone(r)
        self.assertEqual(r["f"], "test.jpg")
        # サムネイルは生成される
        self.assertTrue((self.gallery / r["t"]).exists())
        # viewは元写真への相対パス（_galleryからの相対）
        self.assertNotIn("views/", r["v"])
        view_abs = (self.gallery / r["v"]).resolve()
        self.assertTrue(view_abs.exists())

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
        all_photos = [_sample_photo()]
        path = gg.generate_index_html(year_info, all_photos, self.gallery, "TestFolder")
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
        all_photos = [_sample_photo()]
        content = gg.generate_index_html(year_info, all_photos, self.gallery, "T").read_text()
        self.assertLess(content.index("2025"), content.index("2023"))

    def test_contains_search_filters(self):
        year_info = [{"year": 2025, "count": 1, "cover": "t/a.jpg"}]
        all_photos = [_sample_photo()]
        content = gg.generate_index_html(year_info, all_photos, self.gallery, "T").read_text()
        self.assertIn("f-iso-min", content)
        self.assertIn("f-fn-min", content)
        self.assertIn("f-fl-min", content)
        self.assertIn("f-ss", content)
        self.assertIn("applyFilters", content)


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
        self.assertIn("f-iso-min", content)
        self.assertIn("f-fn-min", content)
        self.assertIn("f-fl-min", content)
        self.assertIn("f-ss", content)
        self.assertIn("resetFilters", content)

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


# ── Monthly pagination ────────────────────────────────────────

class TestGenerateYearMonthSelectorHtml(unittest.TestCase):
    def setUp(self):
        self.gallery = Path(tempfile.mkdtemp()) / "_gallery"
        self.gallery.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.gallery.parent, ignore_errors=True)

    def test_creates_year_html_with_month_links(self):
        month_info = [
            {"month": 1, "count": 500, "cover": "t/a.jpg"},
            {"month": 6, "count": 600, "cover": "t/b.jpg"},
        ]
        path = gg.generate_year_month_selector_html(
            2025, month_info, self.gallery, "T",
        )
        self.assertEqual(path.name, "2025.html")
        content = path.read_text()
        self.assertIn("2025_01.html", content)
        self.assertIn("2025_06.html", content)
        self.assertIn("1月", content)
        self.assertIn("6月", content)
        self.assertIn("index.html", content)


class TestGenerateMonthHtml(unittest.TestCase):
    def setUp(self):
        self.gallery = Path(tempfile.mkdtemp()) / "_gallery"
        self.gallery.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.gallery.parent, ignore_errors=True)

    def test_creates_month_html(self):
        photos = [_sample_photo()]
        paths = gg.generate_month_html(2025, 3, photos, self.gallery, "T")
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].name, "2025_03.html")
        content = paths[0].read_text()
        self.assertIn("3月", content)
        self.assertIn("2025.html", content)  # back link to year page
        self.assertIn("f-cam", content)
        self.assertIn("f-iso-min", content)
        self.assertIn('id="lb"', content)

    def test_splits_large_month_into_pages(self):
        # Create enough photos to exceed YEAR_PAGE_LIMIT
        # month_chunk = YEAR_PAGE_LIMIT // 2, so limit=6 → chunk=3
        old_limit = gg.YEAR_PAGE_LIMIT
        gg.YEAR_PAGE_LIMIT = 6  # chunk = 3
        try:
            photos = [_sample_photo(f=f"photo_{i}.jpg", s=f"2025030{i}120000")
                      for i in range(10)]
            paths = gg.generate_month_html(2025, 3, photos, self.gallery, "T")
            # 10 photos / 3 per page = 4 pages
            self.assertEqual(len(paths), 4)
            self.assertEqual(paths[0].name, "2025_03_1.html")
            self.assertEqual(paths[1].name, "2025_03_2.html")
            self.assertEqual(paths[2].name, "2025_03_3.html")
            self.assertEqual(paths[3].name, "2025_03_4.html")
            # Check pagination links
            content = paths[0].read_text()
            self.assertIn("2025_03_2.html", content)
            self.assertIn("2025_03_4.html", content)
        finally:
            gg.YEAR_PAGE_LIMIT = old_limit


# ── Photo organization ───────────────────────────────────────

class TestOrganizePhotos(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        # Create a simple JPEG
        self.img_path = self.root / "test.jpg"
        gg.Image.new("RGB", (10, 10)).save(str(self.img_path), "JPEG")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_moves_photo_to_date_folder(self):
        photos = [self.img_path]
        new_photos = gg.organize_photos(self.root, photos)
        self.assertEqual(len(new_photos), 1)
        # Photo should now be inside a YYYY/MM/ folder
        rel = new_photos[0].relative_to(self.root)
        parts = rel.parts
        self.assertEqual(len(parts), 3)  # YYYY/MM/filename
        self.assertTrue(parts[0].isdigit())
        self.assertTrue(parts[1].isdigit())

    def test_skips_already_organized(self):
        # Move photo first
        new_photos = gg.organize_photos(self.root, [self.img_path])
        # Run again — should skip
        result = gg.organize_photos(self.root, new_photos)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], new_photos[0])


# ── Manifest & incremental processing ────────────────────────

class TestManifest(unittest.TestCase):
    def setUp(self):
        self.gallery = Path(tempfile.mkdtemp()) / "_gallery"
        self.gallery.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.gallery.parent, ignore_errors=True)

    def test_load_empty_manifest(self):
        m = gg.load_manifest(self.gallery)
        self.assertEqual(m, {})

    def test_save_and_load_manifest(self):
        data = {"test.jpg": {"mt": 123.0, "sz": 456, "ch": "abc",
                             "data": _sample_photo()}}
        gg.save_manifest(self.gallery, data)
        loaded = gg.load_manifest(self.gallery)
        self.assertEqual(loaded["test.jpg"]["ch"], "abc")

    def test_load_corrupt_manifest(self):
        (self.gallery / gg.MANIFEST_FILE).write_text("not json")
        m = gg.load_manifest(self.gallery)
        self.assertEqual(m, {})


class TestContentHash(unittest.TestCase):
    def test_same_content_same_hash(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f1 = tmp / "a.bin"
            f2 = tmp / "b.bin"
            data = os.urandom(1024)
            f1.write_bytes(data)
            f2.write_bytes(data)
            self.assertEqual(gg.content_hash(f1), gg.content_hash(f2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_different_content_different_hash(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f1 = tmp / "a.bin"
            f2 = tmp / "b.bin"
            f1.write_bytes(os.urandom(1024))
            f2.write_bytes(os.urandom(1024))
            self.assertNotEqual(gg.content_hash(f1), gg.content_hash(f2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestIncrementalProcessing(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.gallery = self.root / "_gallery"
        (self.gallery / "thumbnails").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_process_reuses_cached_entry(self):
        """process_one の結果をマニフェストに保存し、再利用できる。"""
        img_path = self.root / "photo.jpg"
        gg.Image.new("RGB", (100, 100), (200, 100, 50)).save(
            str(img_path), "JPEG",
        )
        result = gg.process_one(img_path, self.root, self.gallery)
        self.assertIsNotNone(result)

        st = img_path.stat()
        ch = gg.content_hash(img_path)
        manifest = {
            "photo.jpg": {
                "mt": st.st_mtime,
                "sz": st.st_size,
                "ch": ch,
                "data": result,
            }
        }
        gg.save_manifest(self.gallery, manifest)
        loaded = gg.load_manifest(self.gallery)
        self.assertEqual(loaded["photo.jpg"]["data"]["f"], "photo.jpg")

    def test_duplicate_files_have_same_hash(self):
        """同一内容のファイルは同じハッシュになる。"""
        img_path = self.root / "photo.jpg"
        gg.Image.new("RGB", (100, 100), (200, 100, 50)).save(
            str(img_path), "JPEG",
        )
        sub = self.root / "sub"
        sub.mkdir()
        dup_path = sub / "copy.jpg"
        shutil.copy2(str(img_path), str(dup_path))
        self.assertEqual(
            gg.content_hash(img_path),
            gg.content_hash(dup_path),
        )


if __name__ == "__main__":
    unittest.main()
