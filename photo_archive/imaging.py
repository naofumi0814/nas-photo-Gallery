"""Image processing — thumbnail and view-size generation with orientation fix."""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Max retries for NAS file read
READ_RETRIES = 3
READ_RETRY_DELAY = 0.5  # seconds


def _open_with_retry(filepath: str) -> "Image.Image":
    """Open image with retries (handles NAS transfer-in-progress files)."""
    last_err = None
    for attempt in range(READ_RETRIES):
        try:
            img = Image.open(filepath)
            img.load()  # Force read from disk
            return img
        except Exception as exc:
            last_err = exc
            if attempt < READ_RETRIES - 1:
                time.sleep(READ_RETRY_DELAY)
    raise last_err


def _apply_orientation(img: "Image.Image") -> "Image.Image":
    """Apply EXIF orientation tag and return correctly rotated image."""
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def _resize_to_long_edge(img: "Image.Image", max_edge: int) -> "Image.Image":
    """Resize so longest edge equals max_edge, preserving aspect ratio."""
    w, h = img.size
    if w <= max_edge and h <= max_edge:
        return img.copy()

    if w >= h:
        new_w = max_edge
        new_h = int(h * max_edge / w)
    else:
        new_h = max_edge
        new_w = int(w * max_edge / h)

    return img.resize((new_w, new_h), Image.LANCZOS)


def generate_thumbnail(src_path: str, dst_path: str, size: int = 360) -> bool:
    """Generate a thumbnail image (long edge = size px).

    Returns True on success.
    """
    if not HAS_PIL:
        logger.error("Pillow not installed — cannot generate thumbnails")
        return False

    try:
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        img = _open_with_retry(src_path)
        img = _apply_orientation(img)
        thumb = _resize_to_long_edge(img, size)

        # Convert to RGB if necessary (for PNG with alpha, HEIC, etc.)
        if thumb.mode in ("RGBA", "P", "LA"):
            thumb = thumb.convert("RGB")

        thumb.save(dst_path, "JPEG", quality=82, optimize=True)
        img.close()
        thumb.close()
        return True
    except Exception as exc:
        logger.error("Thumbnail generation failed for %s: %s", src_path, exc)
        return False


def generate_view(src_path: str, dst_path: str, size: int = 1600) -> bool:
    """Generate a view-size image (long edge = size px).

    Returns True on success.
    """
    if not HAS_PIL:
        logger.error("Pillow not installed — cannot generate views")
        return False

    try:
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        img = _open_with_retry(src_path)
        img = _apply_orientation(img)
        view = _resize_to_long_edge(img, size)

        if view.mode in ("RGBA", "P", "LA"):
            view = view.convert("RGB")

        view.save(dst_path, "JPEG", quality=88, optimize=True)
        img.close()
        view.close()
        return True
    except Exception as exc:
        logger.error("View generation failed for %s: %s", src_path, exc)
        return False
