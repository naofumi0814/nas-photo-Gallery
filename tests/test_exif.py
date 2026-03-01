"""Tests for EXIF extraction — taken_at priority logic."""

import os
import time
import unittest
from unittest.mock import MagicMock, patch

from photo_archive.exif import _exif_date_to_dt, extract_exif


class TestExifDateParsing(unittest.TestCase):
    def test_standard_exif_format(self):
        dt = _exif_date_to_dt("2024:01:15 14:30:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)

    def test_iso_format(self):
        dt = _exif_date_to_dt("2024-01-15 14:30:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2024)

    def test_date_only(self):
        dt = _exif_date_to_dt("2024:06:20")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.month, 6)

    def test_invalid_returns_none(self):
        self.assertIsNone(_exif_date_to_dt("not a date"))
        self.assertIsNone(_exif_date_to_dt(""))

    def test_none_input(self):
        self.assertIsNone(_exif_date_to_dt(None))


class TestTakenAtPriority(unittest.TestCase):
    """Test that taken_at uses correct priority:
    1. DateTimeOriginal
    2. CreateDate / DateTimeDigitized / DateTime
    3. mtime
    """

    def test_mtime_fallback_when_no_pil(self):
        """Without PIL, should fall back to mtime."""
        mtime = 1700000000.0  # some timestamp
        with patch("photo_archive.exif.HAS_PIL", False):
            meta = extract_exif("/fake/path.jpg", mtime)
        self.assertEqual(meta["taken_at_source"], "mtime")
        self.assertIn("2023", meta["taken_at"])  # 2023-11-14 approx

    def test_mtime_fallback_when_no_exif(self):
        """When image has no EXIF, should use mtime."""
        mtime = 1700000000.0
        mock_img = MagicMock()
        mock_img.size = (4000, 3000)
        mock_img._getexif.return_value = None

        with patch("photo_archive.exif.HAS_PIL", True), \
             patch("photo_archive.exif.Image") as MockImage:
            MockImage.open.return_value = mock_img
            meta = extract_exif("/fake/path.jpg", mtime)

        self.assertEqual(meta["taken_at_source"], "mtime")

    def test_datetime_original_has_highest_priority(self):
        """DateTimeOriginal should be used when present."""
        from PIL.ExifTags import TAGS

        # Find the tag number for DateTimeOriginal
        tag_num = None
        for k, v in TAGS.items():
            if v == "DateTimeOriginal":
                tag_num = k
                break

        if tag_num is None:
            self.skipTest("Cannot find DateTimeOriginal tag number")

        mtime = 1700000000.0
        mock_img = MagicMock()
        mock_img.size = (4000, 3000)
        mock_img._getexif.return_value = {
            tag_num: "2024:06:15 10:30:00",
        }

        with patch("photo_archive.exif.HAS_PIL", True), \
             patch("photo_archive.exif.Image") as MockImage:
            MockImage.open.return_value = mock_img
            meta = extract_exif("/fake/path.jpg", mtime)

        self.assertEqual(meta["taken_at_source"], "exif_original")
        self.assertIn("2024-06-15", meta["taken_at"])


if __name__ == "__main__":
    unittest.main()
