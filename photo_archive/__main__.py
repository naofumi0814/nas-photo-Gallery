"""CLI entry point — python -m photo_archive build [options]"""

import argparse
import logging
import os
import sys
import webbrowser

from .builder import build
from .config import Config


def main():
    parser = argparse.ArgumentParser(
        prog="photo_archive",
        description="Photo Archive — static photo gallery generator with incremental updates",
    )
    sub = parser.add_subparsers(dest="command")

    # build sub-command
    build_p = sub.add_parser("build", help="Build or update the photo gallery")
    build_p.add_argument("--config", "-c", default="config.json", help="Path to config.json")
    build_p.add_argument("--input", "-i", help="Input photos root path (overrides config)")
    build_p.add_argument("--output", "-o", help="Output gallery root path (overrides config)")
    build_p.add_argument("--thumb-size", type=int, default=None, help="Thumbnail long edge in px (default: 360)")
    build_p.add_argument("--view-size", type=int, default=None, help="View image long edge in px (default: 1600)")
    build_p.add_argument("--include-heic", action="store_true", help="Enable HEIC support")
    build_p.add_argument("--hide-gps", action="store_true", help="Hide GPS data from output")
    build_p.add_argument("--rebuild", action="store_true", help="Force full rebuild (ignore manifest)")
    build_p.add_argument("--use-temp", default=None, help="Use local temp dir for intermediate files")
    build_p.add_argument("--open", dest="open", action="store_true", default=None, help="Open index.html after build")
    build_p.add_argument("--no-open", dest="open", action="store_false", help="Do not open index.html after build")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Setup console logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "build":
        try:
            config = Config.from_args(args)
            config.apply_defaults()
            config.validate()
        except (ValueError, FileNotFoundError) as exc:
            print(f"設定エラー: {exc}", file=sys.stderr)
            sys.exit(1)

        result = build(config)

        print()
        print("=" * 60)
        print(f"  {result.summary()}")
        print("=" * 60)

        if result.error_count > 0:
            print(f"\n  エラー詳細: {os.path.join(config.output_root, 'logs', 'errors.log')}")

        # Open index.html
        if config.open_after and result.total_active > 0:
            index_path = os.path.join(config.output_root, "index.html")
            if os.path.isfile(index_path):
                webbrowser.open(index_path)

        sys.exit(1 if result.error_count > 0 and result.new_count == 0 else 0)


if __name__ == "__main__":
    main()
