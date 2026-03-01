"""Configuration loading and defaults."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    input_root: str = ""
    output_root: str = ""
    temp_root: Optional[str] = None
    thumb_size: int = 360
    view_size: int = 1600
    include_heic: bool = False
    hide_gps: bool = False
    enable_open_original: bool = False
    site_title: str = "Photo Archive"
    recent_count: int = 50
    rebuild: bool = False
    open_after: bool = True

    # Supported extensions (always lowercase, with dot)
    EXTENSIONS_BASE: tuple = (".jpg", ".jpeg", ".png")
    EXTENSIONS_HEIC: tuple = (".heic",)

    @property
    def supported_extensions(self) -> tuple:
        exts = self.EXTENSIONS_BASE
        if self.include_heic:
            exts = exts + self.EXTENSIONS_HEIC
        return exts

    @classmethod
    def from_file(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_args(cls, args) -> "Config":
        """Build config from CLI argparse namespace, overlaying on config file if present."""
        if args.config and os.path.isfile(args.config):
            cfg = cls.from_file(args.config)
        else:
            cfg = cls()

        # CLI overrides
        if args.input:
            cfg.input_root = args.input
        if args.output:
            cfg.output_root = args.output
        if args.thumb_size is not None:
            cfg.thumb_size = args.thumb_size
        if args.view_size is not None:
            cfg.view_size = args.view_size
        if args.include_heic:
            cfg.include_heic = True
        if args.hide_gps:
            cfg.hide_gps = True
        if args.rebuild:
            cfg.rebuild = True
        if args.use_temp:
            cfg.temp_root = args.use_temp
        if hasattr(args, "open") and args.open is not None:
            cfg.open_after = args.open
        return cfg

    def validate(self):
        if not self.input_root:
            raise ValueError("input_root is required")
        if not self.output_root:
            raise ValueError("output_root is required")
        if not os.path.isdir(self.input_root):
            raise ValueError(f"input_root does not exist: {self.input_root}")
