#!/usr/bin/env python3
"""
Photo Archive Gallery Generator

使い方:
  1. このファイルと PhotoArchive.cmd を写真フォルダにコピー
  2. PhotoArchive.cmd をダブルクリック
  → _gallery/ フォルダにギャラリーが生成されます

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

MONTH_JA = [
    "", "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
]


# ── 写真検索 ─────────────────────────────────────────────────

def find_photos(root: Path) -> list[Path]:
    gallery = (root / GALLERY_DIR).resolve()
    results = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED_EXT:
            continue
        try:
            p.resolve().relative_to(gallery)
            continue
        except ValueError:
            results.append(p)
    return results


# ── EXIF 抽出 ────────────────────────────────────────────────

def extract_exif(path: Path) -> dict:
    """画像から EXIF メタデータを抽出。"""
    info = {"camera": "", "lens": "", "focal": 0, "fnum": 0.0,
            "iso": 0, "shutter": "", "date_dt": None}
    try:
        with Image.open(path) as img:
            exif = img._getexif()
            if not exif:
                return info

            # Camera
            make = str(exif.get(271, "")).strip()
            model = str(exif.get(272, "")).strip()
            if make and model:
                info["camera"] = model if model.upper().startswith(make.upper()) else f"{make} {model}"
            elif model:
                info["camera"] = model

            # Lens
            lens = exif.get(42036)
            if lens:
                info["lens"] = str(lens).strip()

            # Focal length
            focal = exif.get(37386)
            if focal:
                try:
                    info["focal"] = round(float(focal))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # F-number
            fnum = exif.get(33437)
            if fnum:
                try:
                    info["fnum"] = round(float(fnum), 1)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # ISO
            iso = exif.get(34855)
            if iso:
                try:
                    info["iso"] = int(iso)
                except (ValueError, TypeError):
                    pass

            # Shutter speed
            exposure = exif.get(33434)
            if exposure:
                try:
                    val = float(exposure)
                    if val >= 1:
                        info["shutter"] = f"{val:.1f}s"
                    elif val > 0:
                        info["shutter"] = f"1/{round(1 / val)}s"
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Date
            for tag in (36867, 36868, 306):
                val = exif.get(tag)
                if val and isinstance(val, str):
                    try:
                        info["date_dt"] = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                        break
                    except ValueError:
                        continue
    except Exception:
        pass
    return info


def get_photo_date(path: Path, exif_info: dict) -> datetime:
    if exif_info.get("date_dt"):
        return exif_info["date_dt"]
    return datetime.fromtimestamp(path.stat().st_mtime)


# ── 画像処理 ─────────────────────────────────────────────────

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
        exif_info = extract_exif(photo)
        date = get_photo_date(photo, exif_info)

        with Image.open(photo) as img:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # View (from original)
            view = img.copy()
            view.thumbnail((VIEW_LONG_EDGE, VIEW_LONG_EDGE), Image.LANCZOS)
            to_rgb(view).save(view_path, "JPEG", quality=QUALITY_VIEW)

            # Thumbnail (from view — faster)
            thumb = view.copy()
            thumb.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE), Image.LANCZOS)
            to_rgb(thumb).save(thumb_path, "JPEG", quality=QUALITY_THUMB)

        return {
            "f": rel,
            "t": f"thumbnails/{name}.jpg",
            "v": f"views/{name}.jpg",
            "d": date.strftime("%Y-%m-%d %H:%M"),
            "s": date.strftime("%Y%m%d%H%M%S"),
            "y": date.year,
            "m": date.month,
            "cam": exif_info["camera"],
            "lens": exif_info["lens"],
            "fl": exif_info["focal"],
            "fn": exif_info["fnum"],
            "ss": exif_info["shutter"],
            "iso": exif_info["iso"],
        }
    except Exception as e:
        print(f"\n  [SKIP] {rel}: {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════

CSS_BASE = """\
:root{
  --bg:#0c0c0c;--surface:#151515;--border:#1e1e1e;
  --text:#e8e8e8;--dim:#555;--accent:#c9a84c;--gap:3px;
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
a{color:inherit;text-decoration:none}
.hdr{text-align:center;padding:48px 20px 24px;animation:fadeUp .6s ease}
.hdr h1{font-size:1.3rem;font-weight:200;letter-spacing:.5em;text-transform:uppercase}
.hdr .sub{margin-top:8px;font-size:.75rem;color:var(--dim);letter-spacing:.12em}
.ft{text-align:center;padding:32px 20px;font-size:.65rem;color:#333;letter-spacing:.08em}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
"""

CSS_INDEX = CSS_BASE + """\
.yg{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
  gap:12px;max-width:1200px;margin:0 auto;padding:24px 16px 60px;
}
.yc{
  position:relative;aspect-ratio:16/10;overflow:hidden;
  border-radius:4px;display:block;background:var(--surface);
}
.yc img{width:100%;height:100%;object-fit:cover;transition:transform .5s ease;display:block}
.yc:hover img{transform:scale(1.08)}
.yc-ov{
  position:absolute;inset:0;
  background:linear-gradient(transparent 40%,rgba(0,0,0,.85));
  display:flex;flex-direction:column;justify-content:flex-end;padding:24px;
}
.yc-y{font-size:2.2rem;font-weight:200;letter-spacing:.3em}
.yc-n{font-size:.8rem;color:rgba(255,255,255,.55);margin-top:4px}
@media(max-width:600px){
  .yg{grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;padding:16px 8px}
  .yc-y{font-size:1.5rem}.hdr{padding:32px 16px 18px}
  .hdr h1{font-size:1rem;letter-spacing:.3em}
}
"""

CSS_YEAR = CSS_BASE + """\
.back{
  position:absolute;left:16px;top:50%;transform:translateY(-50%);
  font-size:.8rem;color:var(--dim);transition:color .2s;
}
.back:hover{color:var(--text)}
.hdr{position:relative}
.fb{
  display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;
  padding:10px 16px;background:var(--surface);
  border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;
}
.fb label{font-size:.68rem;color:var(--dim);letter-spacing:.04em}
.fb select,.fb input[type=text]{
  background:var(--bg);color:var(--text);border:1px solid var(--border);
  padding:4px 8px;font-size:.72rem;border-radius:3px;outline:none;
  transition:border-color .2s;
}
.fb select:focus,.fb input:focus{border-color:var(--accent)}
.fb input[type=text]{width:140px}
.fb .cnt{margin-left:auto;font-size:.72rem;color:var(--dim)}
.main{max-width:1440px;margin:0 auto;padding:16px 12px 60px}
.mo{margin-bottom:32px;opacity:0;transform:translateY(14px);
  transition:opacity .5s ease,transform .5s ease}
.mo.vis{opacity:1;transform:translateY(0)}
.mo-t{
  font-size:.68rem;font-weight:600;letter-spacing:.2em;text-transform:uppercase;
  color:var(--dim);padding-bottom:8px;margin-bottom:8px;border-bottom:1px solid var(--border);
}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:var(--gap)}
.gi{aspect-ratio:1;overflow:hidden;cursor:pointer;background:var(--surface);position:relative}
.gi img{width:100%;height:100%;object-fit:cover;transition:transform .35s ease;display:block}
.gi:hover img{transform:scale(1.05)}
.gi-ov{
  position:absolute;bottom:0;left:0;right:0;padding:3px 5px;
  background:linear-gradient(transparent,rgba(0,0,0,.75));
  font-size:.55rem;color:rgba(255,255,255,.65);
  opacity:0;transition:opacity .2s;pointer-events:none;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.gi:hover .gi-ov{opacity:1}
.empty{text-align:center;padding:60px 20px;color:var(--dim);font-size:.85rem}
.lb{
  display:none;position:fixed;inset:0;z-index:1000;
  background:rgba(0,0,0,.97);flex-direction:column;
  align-items:center;justify-content:center;
}
.lb.open{display:flex}
.lb img{max-width:92vw;max-height:80vh;object-fit:contain;
  user-select:none;opacity:0;transition:opacity .25s ease}
.lb img.ld{opacity:1}
.lb-x{
  position:absolute;top:10px;right:16px;background:none;border:none;
  color:#fff;font-size:2rem;cursor:pointer;opacity:.5;transition:opacity .2s;z-index:1001;
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
  position:absolute;bottom:12px;text-align:center;width:100%;
  font-size:.7rem;color:rgba(255,255,255,.4);letter-spacing:.03em;
  pointer-events:none;line-height:1.6;
}
@media(max-width:600px){
  .grid{grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:2px}
  .hdr{padding:32px 16px 18px}.hdr h1{font-size:1rem;letter-spacing:.3em}
  .fb{gap:4px 8px;padding:8px 10px}
  .fb input[type=text]{width:100px}
  .back{left:10px;font-size:.7rem}
}
"""

# ══════════════════════════════════════════════════════════════
#  JavaScript (year page)
# ══════════════════════════════════════════════════════════════

JS_YEAR = """\
const ALL=__DATA__;
const MN=['','1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
let vis=[],ci=0;
const lb=document.getElementById('lb'),
      li=document.getElementById('li'),
      ln=document.getElementById('ln'),
      gr=document.getElementById('grid-root'),
      ct=document.getElementById('cnt');

/* ── Filters ── */
function init(){
  const cams=[...new Set(ALL.filter(p=>p.cam).map(p=>p.cam))].sort();
  const lens=[...new Set(ALL.filter(p=>p.lens).map(p=>p.lens))].sort();
  const sel=(id,arr)=>{const s=document.getElementById(id);
    arr.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)})};
  sel('f-cam',cams);sel('f-lens',lens);
  applyFilters();
}

function applyFilters(){
  const cam=document.getElementById('f-cam').value;
  const lens=document.getElementById('f-lens').value;
  const q=document.getElementById('f-q').value.toLowerCase();
  const sort=document.getElementById('f-sort').value;

  vis=ALL.filter(p=>{
    if(cam&&p.cam!==cam)return false;
    if(lens&&p.lens!==lens)return false;
    if(q&&!p.f.toLowerCase().includes(q)
       &&!p.cam.toLowerCase().includes(q)
       &&!p.lens.toLowerCase().includes(q))return false;
    return true;
  });

  /* sort */
  const [key,dir]=sort.split('_');
  const asc=dir==='a';
  vis.sort((a,b)=>{
    let va,vb;
    if(key==='date'){va=a.s;vb=b.s}
    else if(key==='cam'){va=a.cam||'\\uffff';vb=b.cam||'\\uffff'}
    else if(key==='lens'){va=a.lens||'\\uffff';vb=b.lens||'\\uffff'}
    else if(key==='fl'){va=a.fl||99999;vb=b.fl||99999}
    else if(key==='iso'){va=a.iso||99999;vb=b.iso||99999}
    else if(key==='fn'){va=a.fn||99999;vb=b.fn||99999}
    else{va=a.s;vb=b.s}
    if(typeof va==='string')return asc?va.localeCompare(vb):vb.localeCompare(va);
    return asc?va-vb:vb-va;
  });

  vis.forEach((p,i)=>p._i=i);
  ct.textContent=vis.length+' 枚';
  renderGrid();
}

function renderGrid(){
  if(!vis.length){gr.innerHTML='<div class="empty">条件に一致する写真がありません</div>';return}
  const byM={};
  vis.forEach(p=>{const k=p.s.substring(0,6);if(!byM[k])byM[k]=[];byM[k].push(p)});
  const keys=Object.keys(byM).sort().reverse();
  let out='';
  keys.forEach(k=>{
    const m=parseInt(k.substring(4,6));
    out+='<section class="mo"><h2 class="mo-t">'+MN[m]+'</h2><div class="grid">';
    byM[k].forEach(p=>{
      let ov='';
      if(p.cam)ov+=p.cam;
      if(p.fl){ov+=(ov?' · ':'')+p.fl+'mm'}
      if(p.fn){ov+=(ov?' · ':'')+'f/'+p.fn}
      out+='<div class="gi" onclick="openLB('+p._i+')">';
      out+='<img loading="lazy" src="'+p.t+'" alt="">';
      if(ov)out+='<div class="gi-ov">'+ov+'</div>';
      out+='</div>';
    });
    out+='</div></section>';
  });
  gr.innerHTML=out;
  document.querySelectorAll('.mo').forEach(el=>obs.observe(el));
}

/* ── Lightbox ── */
function openLB(i){ci=i;showLB();lb.classList.add('open');document.body.style.overflow='hidden'}
function closeLB(){lb.classList.remove('open');document.body.style.overflow=''}
function navLB(d){ci=(ci+d+vis.length)%vis.length;showLB()}
function showLB(){
  const p=vis[ci];
  li.classList.remove('ld');li.onload=function(){this.classList.add('ld')};
  li.src=p.v;
  let l1=(ci+1)+' / '+vis.length+'  \\u00b7  '+p.d+'  \\u00b7  '+p.f;
  const parts=[];
  if(p.cam)parts.push(p.cam);if(p.lens)parts.push(p.lens);
  if(p.fl)parts.push(p.fl+'mm');if(p.fn)parts.push('f/'+p.fn);
  if(p.ss)parts.push(p.ss);if(p.iso)parts.push('ISO '+p.iso);
  let l2=parts.join('  \\u00b7  ');
  ln.innerHTML=l1+(l2?'<br>'+l2:'');
}
document.addEventListener('keydown',function(e){
  if(!lb.classList.contains('open'))return;
  if(e.key==='Escape')closeLB();
  if(e.key==='ArrowLeft')navLB(-1);
  if(e.key==='ArrowRight')navLB(1);
});
lb.addEventListener('click',function(e){if(e.target===lb)closeLB()});
let tx=0;
lb.addEventListener('touchstart',function(e){tx=e.touches[0].clientX});
lb.addEventListener('touchend',function(e){
  const dx=e.changedTouches[0].clientX-tx;
  if(dx>50)navLB(-1);else if(dx<-50)navLB(1);
});

/* ── Scroll reveal ── */
const obs=new IntersectionObserver(function(es){
  es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('vis');obs.unobserve(e.target)}});
},{threshold:0.05});

init();
"""


# ══════════════════════════════════════════════════════════════
#  HTML 生成
# ══════════════════════════════════════════════════════════════

def generate_index_html(year_info: list[dict], gallery: Path, title: str) -> Path:
    """年選択ページを生成。"""
    total = sum(y["count"] for y in year_info)

    cards = []
    for yi in year_info:
        cards.append(
            f'<a class="yc" href="{yi["year"]}.html">'
            f'<img src="{h(yi["cover"])}" alt="">'
            f'<div class="yc-ov">'
            f'<div class="yc-y">{yi["year"]}</div>'
            f'<div class="yc-n">{yi["count"]:,} 枚</div>'
            f'</div></a>'
        )

    html = f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)} — Photo Archive</title>
<style>
{CSS_INDEX}</style>
</head>
<body>
<header class="hdr">
  <h1>Photo Archive</h1>
  <p class="sub">{total:,} Photos &mdash; {h(title)}</p>
</header>
<div class="yg">
{"".join(cards)}
</div>
<footer class="ft">Generated by Photo Archive</footer>
</body>
</html>"""

    path = gallery / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def generate_year_html(
    year: int, photos: list[dict], gallery: Path, title: str,
) -> Path:
    """年別ページを生成（フィルタ/ソート/ライトボックス付き）。"""
    # JSON用にy, m, date_dtは不要 — 必要なキーだけ
    js_photos = []
    for p in photos:
        js_photos.append({
            "f": p["f"], "t": p["t"], "v": p["v"],
            "d": p["d"], "s": p["s"], "cam": p["cam"],
            "lens": p["lens"], "fl": p["fl"], "fn": p["fn"],
            "ss": p["ss"], "iso": p["iso"],
        })

    js_data = json.dumps(js_photos, ensure_ascii=False)

    html = f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{year} — {h(title)} — Photo Archive</title>
<style>
{CSS_YEAR}</style>
</head>
<body>
<header class="hdr">
  <a class="back" href="index.html">&#8249; 戻る</a>
  <h1>{year}</h1>
  <p class="sub">{len(photos):,} Photos &mdash; {h(title)}</p>
</header>

<div class="fb">
  <label>並べ替え</label>
  <select id="f-sort" onchange="applyFilters()">
    <option value="date_d">日付（新→旧）</option>
    <option value="date_a">日付（旧→新）</option>
    <option value="cam_a">カメラ名</option>
    <option value="lens_a">レンズ名</option>
    <option value="fl_a">焦点距離（広角→望遠）</option>
    <option value="fl_d">焦点距離（望遠→広角）</option>
    <option value="fn_a">絞り（開放→）</option>
    <option value="iso_a">ISO（低→高）</option>
    <option value="iso_d">ISO（高→低）</option>
  </select>
  <label>カメラ</label>
  <select id="f-cam" onchange="applyFilters()"><option value="">すべて</option></select>
  <label>レンズ</label>
  <select id="f-lens" onchange="applyFilters()"><option value="">すべて</option></select>
  <label>検索</label>
  <input type="text" id="f-q" placeholder="ファイル名・カメラ…" oninput="applyFilters()">
  <span class="cnt" id="cnt"></span>
</div>

<main class="main" id="grid-root"></main>

<div class="lb" id="lb">
  <button class="lb-x" onclick="closeLB()" aria-label="Close">&times;</button>
  <button class="lb-n lb-p" onclick="navLB(-1)" aria-label="Previous">&#8249;</button>
  <button class="lb-n lb-nx" onclick="navLB(1)" aria-label="Next">&#8250;</button>
  <img id="li" src="" alt="">
  <div class="lb-i" id="ln"></div>
</div>

<footer class="ft">Generated by Photo Archive</footer>

<script>
{JS_YEAR.replace("__DATA__", js_data)}
</script>
</body>
</html>"""

    path = gallery / f"{year}.html"
    path.write_text(html, encoding="utf-8")
    return path


# ══════════════════════════════════════════════════════════════
#  メインエントリ
# ══════════════════════════════════════════════════════════════

def main():
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

    print(f"  → {len(photos):,} 枚見つかりました")
    print()

    # 出力フォルダ準備
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
        print(f"\r  [{bar}] {i+1:,}/{total:,} ({pct}%)", end="", flush=True)

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

    # 年ごとにグループ化
    by_year: dict[int, list[dict]] = defaultdict(list)
    for p in results:
        by_year[p["y"]].append(p)

    for year in by_year:
        by_year[year].sort(key=lambda x: x["s"], reverse=True)

    # 年別ページ生成
    print("  HTMLを生成中…")
    year_info = []
    for year in sorted(by_year.keys(), reverse=True):
        yr_photos = by_year[year]
        generate_year_html(year, yr_photos, gallery, root.name)
        year_info.append({
            "year": year,
            "count": len(yr_photos),
            "cover": yr_photos[0]["t"],
        })
        print(f"    {year}: {len(yr_photos):,} 枚")

    # インデックスページ生成
    index_path = generate_index_html(year_info, gallery, root.name)

    print()
    print("=" * 56)
    print(f"  完了！ {len(results):,} 枚のギャラリーを生成しました")
    print(f"  → {index_path}")
    print("=" * 56)
    print()

    webbrowser.open(str(index_path))


if __name__ == "__main__":
    main()
