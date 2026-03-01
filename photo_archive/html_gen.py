"""HTML generation — builds index, year/month pages from templates."""

import json
import logging
import os
import shutil
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Templates are embedded as strings to keep deployment simple.
# They use simple {variable} substitution.


def _load_template(name: str) -> str:
    """Load a template file from the templates directory."""
    tmpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    path = os.path.join(tmpl_dir, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _photo_card_html(photo: dict, hide_gps: bool = False) -> str:
    """Generate HTML for a single photo card."""
    taken = photo.get("taken_at", "")
    source = photo.get("taken_at_source", "")
    camera = photo.get("camera_model") or ""
    aperture = photo.get("aperture") or ""
    shutter = photo.get("shutter_speed") or ""
    iso = photo.get("iso") or ""
    focal = photo.get("focal_length") or ""
    lens = photo.get("lens") or ""
    has_gps = photo.get("has_gps", False) and not hide_gps
    thumb = photo.get("thumb_path", "")
    view = photo.get("view_path", "")
    rel_path = photo.get("relative_path", "")

    # Date display
    try:
        dt = datetime.fromisoformat(taken)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_str = taken[:16] if taken else ""

    source_badge = ""
    if source == "mtime":
        source_badge = '<span class="badge badge-mtime" title="EXIF無し（mtime代替）">mtime</span>'

    # EXIF summary for card
    exif_parts = []
    if camera:
        exif_parts.append(camera)
    if focal:
        exif_parts.append(focal)

    exif_line = " &middot; ".join(exif_parts) if exif_parts else ""

    # Data attributes for filtering
    data_attrs = f'data-date="{taken}" data-camera="{camera}" data-lens="{lens}"'
    data_attrs += f' data-iso="{iso}" data-aperture="{aperture}" data-focal="{focal}"'
    if has_gps:
        data_attrs += ' data-gps="yes"'

    gps_badge = '<span class="badge badge-gps" title="GPS情報あり">GPS</span>' if has_gps else ""

    return f'''<div class="photo-card" {data_attrs}>
  <a href="javascript:void(0)" class="photo-link" data-view="{view}" data-index="">
    <img class="photo-thumb" data-src="{thumb}" alt="" loading="lazy">
  </a>
  <div class="photo-info">
    <span class="photo-date">{date_str}</span>
    {source_badge}{gps_badge}
    <span class="photo-exif-brief">{exif_line}</span>
  </div>
</div>'''


def _group_by_year_month(photos: List[dict]) -> Dict[str, Dict[str, List[dict]]]:
    """Group photos into {year: {month: [photos]}} by taken_at."""
    tree: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for p in photos:
        taken = p.get("taken_at", "")
        try:
            dt = datetime.fromisoformat(taken)
            year = dt.strftime("%Y")
            month = dt.strftime("%m")
        except Exception:
            year = "unknown"
            month = "00"
        tree[year][month].append(p)
    return tree


def _sort_photos(photos: List[dict], reverse: bool = True) -> List[dict]:
    """Sort photos by taken_at descending."""
    def key(p):
        try:
            return datetime.fromisoformat(p.get("taken_at", ""))
        except Exception:
            return datetime.min
    return sorted(photos, key=key, reverse=reverse)


def generate_all_html(
    photos: List[dict],
    output_root: str,
    site_title: str = "Photo Archive",
    recent_count: int = 50,
    hide_gps: bool = False,
    enable_open_original: bool = False,
    input_root: str = "",
):
    """Generate all HTML pages: index, year/month pages."""
    logger.info("Generating HTML pages…")

    # Sort all photos by date descending
    sorted_photos = _sort_photos(photos)
    tree = _group_by_year_month(sorted_photos)

    # Load templates
    index_tmpl = _load_template("index.html")
    month_tmpl = _load_template("month.html")

    # Copy assets
    assets_src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets_src")
    assets_dst = os.path.join(output_root, "assets")
    if os.path.isdir(assets_src):
        os.makedirs(assets_dst, exist_ok=True)
        for fname in os.listdir(assets_src):
            src = os.path.join(assets_src, fname)
            dst = os.path.join(assets_dst, fname)
            if os.path.isfile(src):
                shutil.copy2(src, dst)

    # --- Year/Month navigation ---
    sorted_years = sorted(tree.keys(), reverse=True)
    nav_items = []
    for year in sorted_years:
        months = sorted(tree[year].keys(), reverse=True)
        month_links = []
        for m in months:
            count = len(tree[year][m])
            month_links.append(f'<a href="{year}/{m}/index.html" class="nav-month">{m}月 <span class="nav-count">{count}</span></a>')
        nav_items.append(f'<div class="nav-year"><span class="nav-year-label">{year}</span>{"".join(month_links)}</div>')
    nav_html = "\n".join(nav_items)

    # --- Recent photos for index ---
    recent = sorted_photos[:recent_count]
    recent_cards = "\n".join(_photo_card_html(p, hide_gps) for p in recent)

    # Total count
    total_count = len(sorted_photos)

    # --- Generate index.html ---
    index_html = index_tmpl.replace("{{SITE_TITLE}}", site_title)
    index_html = index_html.replace("{{NAV_ITEMS}}", nav_html)
    index_html = index_html.replace("{{RECENT_CARDS}}", recent_cards)
    index_html = index_html.replace("{{TOTAL_COUNT}}", str(total_count))
    index_html = index_html.replace("{{RECENT_COUNT}}", str(len(recent)))
    index_html = index_html.replace("{{ASSETS_PREFIX}}", "assets")
    index_html = index_html.replace("{{DATA_PREFIX}}", "data")

    index_path = os.path.join(output_root, "index.html")
    os.makedirs(output_root, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    logger.info("Wrote %s", index_path)

    # --- Generate year/month pages ---
    for year in sorted_years:
        months = sorted(tree[year].keys(), reverse=True)
        for m in months:
            month_photos = _sort_photos(tree[year][m])

            # Group by day
            days: Dict[str, List[dict]] = defaultdict(list)
            for p in month_photos:
                try:
                    dt = datetime.fromisoformat(p.get("taken_at", ""))
                    day = dt.strftime("%d")
                except Exception:
                    day = "00"
                days[day].append(p)

            day_sections = []
            for day in sorted(days.keys()):
                day_cards = "\n".join(_photo_card_html(p, hide_gps) for p in days[day])
                day_sections.append(
                    f'<section class="day-section">'
                    f'<h3 class="day-heading">{year}年{m}月{day}日 '
                    f'<span class="day-count">{len(days[day])}枚</span></h3>'
                    f'<div class="photo-grid">{day_cards}</div>'
                    f'</section>'
                )

            # Depth prefix for assets/data references
            depth_prefix = "../../"

            month_html = month_tmpl.replace("{{SITE_TITLE}}", site_title)
            month_html = month_html.replace("{{YEAR}}", year)
            month_html = month_html.replace("{{MONTH}}", m)
            month_html = month_html.replace("{{MONTH_COUNT}}", str(len(month_photos)))
            month_html = month_html.replace("{{NAV_ITEMS}}", nav_html.replace('href="', f'href="{depth_prefix}'))
            month_html = month_html.replace("{{DAY_SECTIONS}}", "\n".join(day_sections))
            month_html = month_html.replace("{{ASSETS_PREFIX}}", f"{depth_prefix}assets")
            month_html = month_html.replace("{{DATA_PREFIX}}", f"{depth_prefix}data")
            # Fix thumb/view paths in month pages to be relative to output root
            month_html = month_html.replace('data-src="thumbnails/', f'data-src="{depth_prefix}thumbnails/')
            month_html = month_html.replace('data-view="views/', f'data-view="{depth_prefix}views/')
            month_html = month_html.replace('src="thumbnails/', f'src="{depth_prefix}thumbnails/')

            month_dir = os.path.join(output_root, year, m)
            os.makedirs(month_dir, exist_ok=True)
            month_path = os.path.join(month_dir, "index.html")
            with open(month_path, "w", encoding="utf-8") as f:
                f.write(month_html)

    logger.info("HTML generation complete (%d photos, %d year/month pages)", total_count, sum(len(tree[y]) for y in tree))


def export_metadata_json(photos: List[dict], output_root: str, hide_gps: bool = False):
    """Write data/metadata.json for front-end search/filter."""
    data_dir = os.path.join(output_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, "metadata.json")

    export = []
    for p in photos:
        entry = {
            "relative_path": p.get("relative_path"),
            "thumb_path": p.get("thumb_path"),
            "view_path": p.get("view_path"),
            "taken_at": p.get("taken_at"),
            "taken_at_source": p.get("taken_at_source"),
            "camera_make": p.get("camera_make"),
            "camera_model": p.get("camera_model"),
            "lens": p.get("lens"),
            "focal_length": p.get("focal_length"),
            "aperture": p.get("aperture"),
            "shutter_speed": p.get("shutter_speed"),
            "iso": p.get("iso"),
            "width": p.get("width"),
            "height": p.get("height"),
        }
        if not hide_gps:
            entry["has_gps"] = p.get("has_gps", False)
            entry["gps_lat"] = p.get("gps_lat")
            entry["gps_lon"] = p.get("gps_lon")
        else:
            entry["has_gps"] = False
        export.append(entry)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=1)
    logger.info("Wrote metadata.json (%d entries)", len(export))
