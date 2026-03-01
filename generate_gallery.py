#!/usr/bin/env python3
"""
Photo Archive Gallery Generator

使い方:
  1. このファイルと PhotoArchive.cmd を写真フォルダにコピー
  2. PhotoArchive.cmd をダブルクリック
  → _gallery/ フォルダにオシャレなギャラリーが生成されます

コマンドライン:
  python generate_gallery.py [写真フォルダのパス]
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from collections import defaultdict
from datetime import datetime
from html import escape as h
from pathlib import Path

# ── Pillow 自動インストール ──────────────────────────────────
try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow をインストールしています…")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "Pillow"],
            stdout=subprocess.DEVNULL,
        )
    except Exception:
        print("[ERROR] Pillow のインストールに失敗しました。")
        print("  手動で実行してください: pip install Pillow")
        input("\nEnter キーで終了...")
        sys.exit(1)
    from PIL import Image, ImageOps

# ── 定数 ─────────────────────────────────────────────────────

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
THUMB_LONG_EDGE = 320
VIEW_LONG_EDGE = 1600
GALLERY_DIR = "_gallery"
QUALITY_THUMB = 82
QUALITY_VIEW = 90


# ── 写真検索 ─────────────────────────────────────────────────

def find_photos(root: Path) -> list[Path]:
    gallery = (root / GALLERY_DIR).resolve()
    results = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED_EXT:
            continue
        # _gallery/ 配下は除外
        try:
            p.resolve().relative_to(gallery)
            continue
        except ValueError:
            results.append(p)
    return results


# ── 日付取得 ─────────────────────────────────────────────────

def get_exif_date(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img._getexif()
            if not exif:
                return None
            for tag in (36867, 36868, 306):
                val = exif.get(tag)
                if val and isinstance(val, str):
                    try:
                        return datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        continue
    except Exception:
        pass
    return None


def get_photo_date(path: Path) -> datetime:
    d = get_exif_date(path)
    return d if d else datetime.fromtimestamp(path.stat().st_mtime)


# ── 画像処理 ─────────────────────────────────────────────────

def resize_long_edge(img: Image.Image, size: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= size:
        return img.copy()
    ratio = size / max(w, h)
    return img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)


def to_rgb(img: Image.Image) -> Image.Image:
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def process_one(photo: Path, root: Path, gallery: Path) -> dict | None:
    rel = str(photo.relative_to(root)).replace("\\", "/")
    name = hashlib.md5(rel.encode()).hexdigest()[:16]
    thumb_path = gallery / "thumbnails" / f"{name}.jpg"
    view_path = gallery / "views" / f"{name}.jpg"

    try:
        with Image.open(photo) as img:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            w, h = img.size
            date = get_photo_date(photo)

            to_rgb(resize_long_edge(img, THUMB_LONG_EDGE)).save(
                thumb_path, "JPEG", quality=QUALITY_THUMB,
            )
            to_rgb(resize_long_edge(img, VIEW_LONG_EDGE)).save(
                view_path, "JPEG", quality=QUALITY_VIEW,
            )

        return {
            "file": rel,
            "thumb": f"thumbnails/{name}.jpg",
            "view": f"views/{name}.jpg",
            "date": date.strftime("%Y-%m-%d %H:%M"),
            "year": date.year,
            "month": date.month,
            "sort": date.strftime("%Y%m%d%H%M%S"),
        }
    except Exception as e:
        print(f"\n  [SKIP] {rel}: {e}")
        return None


# ── HTML / CSS / JS テンプレート ──────────────────────────────

CSS = """\
:root{
  --bg:#0c0c0c;--surface:#151515;--border:#1e1e1e;
  --text:#e8e8e8;--dim:#555;--accent:#c9a84c;
  --thumb:180px;--gap:3px;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",
    "Hiragino Sans","Noto Sans JP","Yu Gothic",sans-serif;
  -webkit-font-smoothing:antialiased;
}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:#2a2a2a;border-radius:3px}

/* Header */
.hdr{
  text-align:center;padding:52px 20px 28px;
  animation:fadeUp .6s ease;
}
.hdr h1{
  font-size:1.3rem;font-weight:200;
  letter-spacing:.5em;text-transform:uppercase;
}
.hdr .sub{
  margin-top:8px;font-size:.75rem;
  color:var(--dim);letter-spacing:.12em;
}

/* Month nav */
.mnav{
  display:flex;flex-wrap:wrap;gap:2px 8px;
  justify-content:center;padding:12px 20px;
  background:var(--surface);
  border-top:1px solid var(--border);
  border-bottom:1px solid var(--border);
  position:sticky;top:0;z-index:100;
}
.mnav a{
  color:var(--dim);text-decoration:none;
  font-size:.7rem;letter-spacing:.04em;
  padding:4px 8px;border-radius:3px;
  transition:color .2s,background .2s;
}
.mnav a:hover{color:var(--text);background:rgba(255,255,255,.05)}

/* Main */
.main{max-width:1440px;margin:0 auto;padding:20px 12px 60px}

/* Month section */
.mo{margin-bottom:36px;opacity:0;transform:translateY(16px);
  transition:opacity .5s ease,transform .5s ease}
.mo.vis{opacity:1;transform:translateY(0)}
.mo-t{
  font-size:.68rem;font-weight:600;
  letter-spacing:.2em;text-transform:uppercase;
  color:var(--dim);padding-bottom:8px;
  margin-bottom:8px;border-bottom:1px solid var(--border);
}

/* Grid */
.grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(var(--thumb),1fr));
  gap:var(--gap);
}
.gi{
  aspect-ratio:1;overflow:hidden;cursor:pointer;
  background:var(--surface);
}
.gi img{
  width:100%;height:100%;object-fit:cover;
  transition:transform .35s ease;display:block;
}
.gi:hover img{transform:scale(1.05)}

/* Lightbox */
.lb{
  display:none;position:fixed;inset:0;z-index:1000;
  background:rgba(0,0,0,.97);
  flex-direction:column;align-items:center;justify-content:center;
}
.lb.open{display:flex}
.lb img{
  max-width:92vw;max-height:84vh;object-fit:contain;
  user-select:none;opacity:0;transition:opacity .25s ease;
}
.lb img.ld{opacity:1}
.lb-x{
  position:absolute;top:10px;right:16px;
  background:none;border:none;color:#fff;font-size:2rem;
  cursor:pointer;opacity:.5;transition:opacity .2s;z-index:1001;
}
.lb-x:hover{opacity:1}
.lb-n{
  position:absolute;top:50%;transform:translateY(-50%);
  background:rgba(255,255,255,.05);border:none;color:#fff;
  font-size:2.5rem;padding:20px 14px;cursor:pointer;
  opacity:.4;transition:opacity .2s,background .2s;
}
.lb-n:hover{opacity:.9;background:rgba(255,255,255,.1)}
.lb-p{left:0;border-radius:0 4px 4px 0}
.lb-nx{right:0;border-radius:4px 0 0 4px}
.lb-i{
  position:absolute;bottom:16px;text-align:center;width:100%;
  font-size:.72rem;color:rgba(255,255,255,.35);
  letter-spacing:.04em;pointer-events:none;
}

/* Footer */
.ft{
  text-align:center;padding:32px 20px;
  font-size:.65rem;color:#333;letter-spacing:.08em;
}

@keyframes fadeUp{
  from{opacity:0;transform:translateY(12px)}
  to{opacity:1;transform:translateY(0)}
}
@media(max-width:600px){
  :root{--thumb:110px;--gap:2px}
  .hdr{padding:32px 16px 20px}
  .hdr h1{font-size:1rem;letter-spacing:.3em}
  .mnav{gap:2px 4px;padding:8px 12px}
}
"""

JS = """\
const P=__DATA__;
let ci=0;
const lb=document.getElementById('lb'),
      li=document.getElementById('li'),
      ln=document.getElementById('ln');

function openLB(i){
  ci=i;showLB();lb.classList.add('open');
  document.body.style.overflow='hidden';
}
function closeLB(){
  lb.classList.remove('open');
  document.body.style.overflow='';
}
function navLB(d){ci=(ci+d+P.length)%P.length;showLB()}
function showLB(){
  li.classList.remove('ld');
  li.onload=function(){this.classList.add('ld')};
  li.src=P[ci].v;
  ln.textContent=(ci+1)+' / '+P.length+'  \\u00b7  '+P[ci].d+'  \\u00b7  '+P[ci].f;
}
document.addEventListener('keydown',function(e){
  if(!lb.classList.contains('open'))return;
  if(e.key==='Escape')closeLB();
  if(e.key==='ArrowLeft')navLB(-1);
  if(e.key==='ArrowRight')navLB(1);
});
lb.addEventListener('click',function(e){if(e.target===lb)closeLB()});

/* Touch swipe */
let tx=0;
lb.addEventListener('touchstart',function(e){tx=e.touches[0].clientX});
lb.addEventListener('touchend',function(e){
  const dx=e.changedTouches[0].clientX-tx;
  if(dx>50)navLB(-1);else if(dx<-50)navLB(1);
});

/* Scroll reveal */
const obs=new IntersectionObserver(function(es){
  es.forEach(function(e){
    if(e.isIntersecting){e.target.classList.add('vis');obs.unobserve(e.target)}
  });
},{threshold:0.05});
document.querySelectorAll('.mo').forEach(function(el){obs.observe(el)});
"""

MONTH_JA = [
    "", "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
]


# ── HTML 生成 ─────────────────────────────────────────────────

def generate_html(photos: list[dict], gallery: Path, title: str) -> Path:
    # 年月ごとにグループ化
    by_month: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for p in photos:
        by_month[(p["year"], p["month"])].append(p)

    months = sorted(by_month.keys(), reverse=True)
    for k in months:
        by_month[k].sort(key=lambda x: x["sort"], reverse=True)

    # ライトボックス用フラット配列（新しい順）
    flat: list[dict] = []
    for k in months:
        flat.extend(by_month[k])
    for i, p in enumerate(flat):
        p["idx"] = i

    total = len(flat)

    # 月ナビゲーション
    nav_parts = []
    for y, m in months:
        nav_parts.append(f'<a href="#{y}-{m:02d}">{y}.{m:02d}</a>')
    nav_html = "\n".join(nav_parts)

    # 月セクション
    sections = []
    for y, m in months:
        items = by_month[(y, m)]
        grid_items = []
        for p in items:
            grid_items.append(
                f'<div class="gi" onclick="openLB({p["idx"]})">'
                f'<img loading="lazy" src="{h(p["thumb"])}" alt="">'
                f'</div>'
            )
        section = (
            f'<section class="mo" id="{y}-{m:02d}">\n'
            f'  <h2 class="mo-t">{y}年 {MONTH_JA[m]}</h2>\n'
            f'  <div class="grid">\n    '
            + "\n    ".join(grid_items)
            + "\n  </div>\n</section>"
        )
        sections.append(section)

    sections_html = "\n\n".join(sections)

    # JS用データ
    js_data = json.dumps(
        [{"v": p["view"], "f": p["file"], "d": p["date"]} for p in flat],
        ensure_ascii=False,
    )

    html = f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)} — Photo Archive</title>
<style>
{CSS}</style>
</head>
<body>

<header class="hdr">
  <h1>Photo Archive</h1>
  <p class="sub">{total} Photos &mdash; {h(title)}</p>
</header>

<nav class="mnav">
{nav_html}
</nav>

<main class="main">
{sections_html}
</main>

<div class="lb" id="lb">
  <button class="lb-x" onclick="closeLB()" aria-label="Close">&times;</button>
  <button class="lb-n lb-p" onclick="navLB(-1)" aria-label="Previous">&#8249;</button>
  <button class="lb-n lb-nx" onclick="navLB(1)" aria-label="Next">&#8250;</button>
  <img id="li" src="" alt="">
  <div class="lb-i" id="ln"></div>
</div>

<footer class="ft">Generated by Photo Archive</footer>

<script>
{JS.replace("__DATA__", js_data)}
</script>
</body>
</html>"""

    index_path = gallery / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


# ── メインエントリ ───────────────────────────────────────────

def main():
    # 対象フォルダ決定
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()
    else:
        root = Path(__file__).resolve().parent

    print()
    print("=" * 56)
    print("  Photo Archive Gallery Generator")
    print("=" * 56)
    print()
    print(f"  写真フォルダ: {root}")
    print()

    if not root.is_dir():
        print(f"  [ERROR] フォルダが見つかりません: {root}")
        input("\n  Enter キーで終了...")
        sys.exit(1)

    # 写真検索
    print("  写真を検索中…")
    photos = find_photos(root)
    if not photos:
        print("  写真が見つかりませんでした。")
        print(f"  対応形式: {', '.join(sorted(SUPPORTED_EXT))}")
        input("\n  Enter キーで終了...")
        return

    print(f"  → {len(photos)} 枚見つかりました")
    print()

    # 出力フォルダ準備（前回出力をクリア）
    gallery = root / GALLERY_DIR
    for subdir in ("thumbnails", "views"):
        d = gallery / subdir
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # 写真処理
    results = []
    total = len(photos)
    skip = 0
    for i, photo in enumerate(photos):
        pct = (i + 1) * 100 // total
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r  [{bar}] {i+1}/{total} ({pct}%)", end="", flush=True)

        result = process_one(photo, root, gallery)
        if result:
            results.append(result)
        else:
            skip += 1

    print()
    if skip:
        print(f"  ({skip} 枚スキップ)")
    print()

    if not results:
        print("  処理できた写真がありません。")
        input("\n  Enter キーで終了...")
        return

    # HTML 生成
    print("  HTMLを生成中…")
    index_path = generate_html(results, gallery, root.name)

    print()
    print("=" * 56)
    print(f"  完了！ {len(results)} 枚のギャラリーを生成しました")
    print(f"  → {index_path}")
    print("=" * 56)
    print()

    webbrowser.open(str(index_path))


if __name__ == "__main__":
    main()
