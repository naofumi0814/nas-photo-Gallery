"""Tests for config — defaults, apply_defaults, validation."""

import os
import tempfile
import shutil
import unittest

from photo_archive.config import Config


class TestConfigDefaults(unittest.TestCase):
    def test_output_root_defaults_to_gallery_subfolder(self):
        cfg = Config(input_root="/photos/vacation")
        cfg.apply_defaults()
        self.assertEqual(cfg.output_root, os.path.join("/photos/vacation", "_gallery"))

    def test_output_root_not_overwritten_if_set(self):
        cfg = Config(input_root="/photos", output_root="/custom/output")
        cfg.apply_defaults()
        self.assertEqual(cfg.output_root, "/custom/output")

    def test_output_root_not_set_when_input_root_empty(self):
        cfg = Config()
        cfg.apply_defaults()
        self.assertEqual(cfg.output_root, "")


class TestConfigValidation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_validates_input_root_required(self):
        cfg = Config(output_root="/some/output")
        with self.assertRaises(ValueError) as ctx:
            cfg.validate()
        self.assertIn("input_root", str(ctx.exception))

    def test_validates_output_root_required(self):
        cfg = Config(input_root=self.tmpdir)
        with self.assertRaises(ValueError) as ctx:
            cfg.validate()
        self.assertIn("output_root", str(ctx.exception))

    def test_validates_input_root_exists(self):
        cfg = Config(input_root="/nonexistent/path", output_root="/some/output")
        with self.assertRaises(ValueError) as ctx:
            cfg.validate()
        self.assertIn("does not exist", str(ctx.exception))

    def test_valid_config_passes(self):
        cfg = Config(input_root=self.tmpdir, output_root="/some/output")
        cfg.validate()  # Should not raise

    def test_apply_defaults_then_validate_works(self):
        """With only input_root set, apply_defaults fills output_root."""
        cfg = Config(input_root=self.tmpdir)
        cfg.apply_defaults()
        cfg.validate()  # Should not raise
        self.assertTrue(cfg.output_root.endswith("_gallery"))


if __name__ == "__main__":
    unittest.main()
