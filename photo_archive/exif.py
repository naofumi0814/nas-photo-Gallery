"""EXIF extraction — pulls shooting metadata from image files."""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import PIL/Pillow
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _exif_date_to_dt(value: str) -> Optional[datetime]:
    """Parse EXIF date string like '2024:01:15 14:30:00' to datetime."""
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
    return str(v).strip() or None


def _dms_to_decimal(dms, ref: str) -> Optional[float]:
    """Convert EXIF GPS DMS (degrees, minutes, seconds) to decimal."""
    try:
        d, m, s = [float(x) for x in dms]
        dec = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            dec = -dec
        return round(dec, 6)
    except Exception:
        return None


def extract_exif(filepath: str, mtime: float) -> Dict[str, Any]:
    """Extract EXIF metadata. Returns a dict with standardised keys.

    taken_at priority:
      1. DateTimeOriginal
      2. CreateDate (DateTimeDigitized, DateTime)
      3. File mtime (fallback)
    """
    meta: Dict[str, Any] = {
        "taken_at": datetime.fromtimestamp(mtime).isoformat(),
        "taken_at_source": "mtime",
        "width": None,
        "height": None,
        "camera_make": None,
        "camera_model": None,
        "lens": None,
        "focal_length": None,
        "aperture": None,
        "shutter_speed": None,
        "iso": None,
        "orientation": 1,
        "has_gps": False,
        "gps_lat": None,
        "gps_lon": None,
    }

    if not HAS_PIL:
        return meta

    try:
        img = Image.open(filepath)
    except Exception as exc:
        logger.debug("Cannot open image for EXIF: %s — %s", filepath, exc)
        return meta

    try:
        meta["width"], meta["height"] = img.size
    except Exception:
        pass

    exif_data = {}
    try:
        raw = img._getexif()
        if raw:
            exif_data = {TAGS.get(k, k): v for k, v in raw.items()}
    except Exception:
        pass

    if not exif_data:
        try:
            img.close()
        except Exception:
            pass
        return meta

    # --- Taken at ---
    taken_dt = None

    # Priority 1: DateTimeOriginal
    dto = _safe_str(exif_data.get("DateTimeOriginal"))
    if dto:
        taken_dt = _exif_date_to_dt(dto)
        if taken_dt:
            meta["taken_at"] = taken_dt.isoformat()
            meta["taken_at_source"] = "exif_original"

    # Priority 2: DateTimeDigitized, DateTime
    if not taken_dt:
        for tag in ("DateTimeDigitized", "DateTime"):
            val = _safe_str(exif_data.get(tag))
            if val:
                taken_dt = _exif_date_to_dt(val)
                if taken_dt:
                    meta["taken_at"] = taken_dt.isoformat()
                    meta["taken_at_source"] = "exif_create"
                    break

    # Priority 3: mtime (already set as default)

    # --- Camera info ---
    meta["camera_make"] = _safe_str(exif_data.get("Make"))
    meta["camera_model"] = _safe_str(exif_data.get("Model"))

    # Lens
    lens = _safe_str(exif_data.get("LensModel"))
    if not lens:
        lens = _safe_str(exif_data.get("LensInfo"))
    meta["lens"] = lens

    # Focal length
    fl = exif_data.get("FocalLength")
    if fl:
        try:
            meta["focal_length"] = f"{float(fl):.0f}mm"
        except (TypeError, ValueError):
            pass

    # Aperture
    fn = exif_data.get("FNumber")
    if fn:
        try:
            meta["aperture"] = f"f/{float(fn):.1f}"
        except (TypeError, ValueError):
            pass

    # Shutter speed
    et = exif_data.get("ExposureTime")
    if et:
        try:
            val = float(et)
            if val >= 1:
                meta["shutter_speed"] = f"{val:.1f}s"
            else:
                denom = round(1 / val)
                meta["shutter_speed"] = f"1/{denom}s"
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # ISO
    iso = exif_data.get("ISOSpeedRatings")
    if iso:
        try:
            meta["iso"] = int(iso) if not isinstance(iso, tuple) else int(iso[0])
        except (TypeError, ValueError):
            pass

    # Orientation
    orient = exif_data.get("Orientation")
    if orient:
        try:
            meta["orientation"] = int(orient)
        except (TypeError, ValueError):
            pass

    # --- GPS ---
    gps_info = exif_data.get("GPSInfo")
    if gps_info and isinstance(gps_info, dict):
        gps_decoded = {}
        for k, v in gps_info.items():
            tag = GPSTAGS.get(k, k)
            gps_decoded[tag] = v

        lat = gps_decoded.get("GPSLatitude")
        lat_ref = gps_decoded.get("GPSLatitudeRef", "N")
        lon = gps_decoded.get("GPSLongitude")
        lon_ref = gps_decoded.get("GPSLongitudeRef", "E")

        if lat and lon:
            dec_lat = _dms_to_decimal(lat, lat_ref)
            dec_lon = _dms_to_decimal(lon, lon_ref)
            if dec_lat is not None and dec_lon is not None:
                meta["has_gps"] = True
                meta["gps_lat"] = dec_lat
                meta["gps_lon"] = dec_lon

    try:
        img.close()
    except Exception:
        pass

    return meta
