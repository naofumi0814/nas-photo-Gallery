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
GALLERY_DIR = "_gallery"
QUALITY_THUMB = 82
MANIFEST_FILE = "manifest.json"
CONTENT_HASH_CHUNK = 64 * 1024  # 64KB for fast content hashing

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


# ── マニフェスト（差分処理用）─────────────────────────────────

def load_manifest(gallery: Path) -> dict:
    """既存のマニフェストを読み込む。"""
    path = gallery / MANIFEST_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_manifest(gallery: Path, manifest: dict) -> None:
    """マニフェストを保存する。"""
    path = gallery / MANIFEST_FILE
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def content_hash(path: Path) -> str:
    """ファイルのコンテンツハッシュを計算（先頭チャンク + サイズ）。"""
    h = hashlib.md5()
    size = path.stat().st_size
    h.update(size.to_bytes(8, "little"))
    with open(path, "rb") as f:
        h.update(f.read(CONTENT_HASH_CHUNK))
    return h.hexdigest()


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

    # ライトボックス用: _gallery/ から元写真への相対パス
    view_rel = os.path.relpath(photo, gallery).replace("\\", "/")

    try:
        exif_info = extract_exif(photo)
        date = get_photo_date(photo, exif_info)

        with Image.open(photo) as img:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # サムネイルのみ生成（元写真は直接参照）
            thumb = img.copy()
            thumb.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE), Image.LANCZOS)
            to_rgb(thumb).save(thumb_path, "JPEG", quality=QUALITY_THUMB)

        return {
            "f": rel,
            "t": f"thumbnails/{name}.jpg",
            "v": view_rel,
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
.fb{
  display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;
  padding:10px 16px;background:var(--surface);
  border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;
}
.fb label{font-size:.68rem;color:var(--dim);letter-spacing:.04em}
.fb select,.fb input[type=text],.fb input[type=number]{
  background:var(--bg);color:var(--text);border:1px solid var(--border);
  padding:4px 8px;font-size:.72rem;border-radius:3px;outline:none;
  transition:border-color .2s;
}
.fb select:focus,.fb input:focus{border-color:var(--accent)}
.fb input[type=text]{width:140px}
.fb input[type=number]{width:72px}
.fb input[type=number]::-webkit-inner-spin-button{opacity:.5}
.fb .cnt{margin-left:auto;font-size:.72rem;color:var(--dim)}
.fg{display:flex;align-items:center;gap:3px}
.fg .sep{font-size:.6rem;color:var(--dim)}
.fb .fb-reset{
  background:none;border:1px solid var(--border);color:var(--dim);
  padding:3px 8px;font-size:.65rem;border-radius:3px;cursor:pointer;
  transition:color .2s,border-color .2s;
}
.fb .fb-reset:hover{color:var(--text);border-color:var(--accent)}
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
  .yg{grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;padding:16px 8px}
  .yc-y{font-size:1.5rem}.hdr{padding:32px 16px 18px}
  .hdr h1{font-size:1rem;letter-spacing:.3em}
  .grid{grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:2px}
  .fb{gap:4px 8px;padding:8px 10px}
  .fb input[type=text]{width:100px}
  .fb input[type=number]{width:56px}
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
.fb select,.fb input[type=text],.fb input[type=number]{
  background:var(--bg);color:var(--text);border:1px solid var(--border);
  padding:4px 8px;font-size:.72rem;border-radius:3px;outline:none;
  transition:border-color .2s;
}
.fb select:focus,.fb input:focus{border-color:var(--accent)}
.fb input[type=text]{width:140px}
.fb input[type=number]{width:72px}
.fb input[type=number]::-webkit-inner-spin-button{opacity:.5}
.fb .cnt{margin-left:auto;font-size:.72rem;color:var(--dim)}
.fg{display:flex;align-items:center;gap:3px}
.fg .sep{font-size:.6rem;color:var(--dim)}
.fb .fb-reset{
  background:none;border:1px solid var(--border);color:var(--dim);
  padding:3px 8px;font-size:.65rem;border-radius:3px;cursor:pointer;
  transition:color .2s,border-color .2s;
}
.fb .fb-reset:hover{color:var(--text);border-color:var(--accent)}
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
  .fb input[type=number]{width:56px}
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
  const ss=[...new Set(ALL.filter(p=>p.ss).map(p=>p.ss))].sort((a,b)=>{
    const toSec=s=>{const m=s.match(/^1\\/([0-9]+)s$/);return m?1/+m[1]:parseFloat(s)};
    return toSec(a)-toSec(b);
  });
  const sel=(id,arr)=>{const s=document.getElementById(id);
    arr.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)})};
  sel('f-cam',cams);sel('f-lens',lens);sel('f-ss',ss);
  applyFilters();
}

function nv(id){const v=document.getElementById(id).value;return v===''?null:parseFloat(v)}

function resetFilters(){
  ['f-cam','f-lens','f-ss','f-sort'].forEach(id=>{document.getElementById(id).selectedIndex=0});
  ['f-iso-min','f-iso-max','f-fn-min','f-fn-max','f-fl-min','f-fl-max','f-q'].forEach(id=>{document.getElementById(id).value=''});
  applyFilters();
}

function applyFilters(){
  const cam=document.getElementById('f-cam').value;
  const lens=document.getElementById('f-lens').value;
  const ss=document.getElementById('f-ss').value;
  const q=document.getElementById('f-q').value.toLowerCase();
  const sort=document.getElementById('f-sort').value;
  const isoMin=nv('f-iso-min'),isoMax=nv('f-iso-max');
  const fnMin=nv('f-fn-min'),fnMax=nv('f-fn-max');
  const flMin=nv('f-fl-min'),flMax=nv('f-fl-max');

  vis=ALL.filter(p=>{
    if(cam&&p.cam!==cam)return false;
    if(lens&&p.lens!==lens)return false;
    if(ss&&p.ss!==ss)return false;
    if(isoMin!==null&&(!p.iso||p.iso<isoMin))return false;
    if(isoMax!==null&&(!p.iso||p.iso>isoMax))return false;
    if(fnMin!==null&&(!p.fn||p.fn<fnMin))return false;
    if(fnMax!==null&&(!p.fn||p.fn>fnMax))return false;
    if(flMin!==null&&(!p.fl||p.fl<flMin))return false;
    if(flMax!==null&&(!p.fl||p.fl>flMax))return false;
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
#  JavaScript (index page — search mode)
# ══════════════════════════════════════════════════════════════

JS_INDEX = """\
const ALL=__DATA__;
const YEARS=__YEARS__;
const MN=['','1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
let vis=[],ci=0,searchMode=false;
const lb=document.getElementById('lb'),
      li=document.getElementById('li'),
      ln=document.getElementById('ln'),
      gr=document.getElementById('grid-root'),
      ct=document.getElementById('cnt'),
      yg=document.getElementById('year-grid'),
      fb=document.getElementById('filter-bar');

function init(){
  const cams=[...new Set(ALL.filter(p=>p.cam).map(p=>p.cam))].sort();
  const lens=[...new Set(ALL.filter(p=>p.lens).map(p=>p.lens))].sort();
  const ss=[...new Set(ALL.filter(p=>p.ss).map(p=>p.ss))].sort((a,b)=>{
    const toSec=s=>{const m=s.match(/^1\\\\/([0-9]+)s$/);return m?1/+m[1]:parseFloat(s)};
    return toSec(a)-toSec(b);
  });
  const sel=(id,arr)=>{const s=document.getElementById(id);
    arr.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)})};
  sel('f-cam',cams);sel('f-lens',lens);sel('f-ss',ss);
}

function nv(id){const v=document.getElementById(id).value;return v===''?null:parseFloat(v)}

function hasAnyFilter(){
  if(document.getElementById('f-cam').value)return true;
  if(document.getElementById('f-lens').value)return true;
  if(document.getElementById('f-ss').value)return true;
  if(document.getElementById('f-q').value)return true;
  const ids=['f-iso-min','f-iso-max','f-fn-min','f-fn-max','f-fl-min','f-fl-max'];
  return ids.some(id=>document.getElementById(id).value!=='');
}

function applyFilters(){
  searchMode=hasAnyFilter();
  if(!searchMode){
    yg.style.display='';gr.style.display='none';gr.innerHTML='';
    ct.textContent=ALL.length+' 枚';return;
  }
  yg.style.display='none';gr.style.display='';

  const cam=document.getElementById('f-cam').value;
  const lens=document.getElementById('f-lens').value;
  const ss=document.getElementById('f-ss').value;
  const q=document.getElementById('f-q').value.toLowerCase();
  const sort=document.getElementById('f-sort').value;
  const isoMin=nv('f-iso-min'),isoMax=nv('f-iso-max');
  const fnMin=nv('f-fn-min'),fnMax=nv('f-fn-max');
  const flMin=nv('f-fl-min'),flMax=nv('f-fl-max');

  vis=ALL.filter(p=>{
    if(cam&&p.cam!==cam)return false;
    if(lens&&p.lens!==lens)return false;
    if(ss&&p.ss!==ss)return false;
    if(isoMin!==null&&(!p.iso||p.iso<isoMin))return false;
    if(isoMax!==null&&(!p.iso||p.iso>isoMax))return false;
    if(fnMin!==null&&(!p.fn||p.fn<fnMin))return false;
    if(fnMax!==null&&(!p.fn||p.fn>fnMax))return false;
    if(flMin!==null&&(!p.fl||p.fl<flMin))return false;
    if(flMax!==null&&(!p.fl||p.fl>flMax))return false;
    if(q&&!p.f.toLowerCase().includes(q)
       &&!p.cam.toLowerCase().includes(q)
       &&!p.lens.toLowerCase().includes(q))return false;
    return true;
  });

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
  const byYM={};
  vis.forEach(p=>{const k=p.s.substring(0,6);if(!byYM[k])byYM[k]=[];byYM[k].push(p)});
  const keys=Object.keys(byYM).sort().reverse();
  let out='';
  keys.forEach(k=>{
    const y=k.substring(0,4),m=parseInt(k.substring(4,6));
    out+='<section class="mo"><h2 class="mo-t">'+y+'年 '+MN[m]+'</h2><div class="grid">';
    byYM[k].forEach(p=>{
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

function resetFilters(){
  ['f-cam','f-lens','f-ss','f-sort'].forEach(id=>{document.getElementById(id).selectedIndex=0});
  ['f-iso-min','f-iso-max','f-fn-min','f-fn-max','f-fl-min','f-fl-max','f-q'].forEach(id=>{document.getElementById(id).value=''});
  applyFilters();
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

const obs=new IntersectionObserver(function(es){
  es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('vis');obs.unobserve(e.target)}});
},{threshold:0.05});

init();
"""


# ══════════════════════════════════════════════════════════════
#  HTML 生成
# ══════════════════════════════════════════════════════════════

def generate_index_html(
    year_info: list[dict], all_photos: list[dict],
    gallery: Path, title: str,
) -> Path:
    """年選択ページを生成（検索機能付き）。"""
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

    # JSON for all photos (index page search)
    js_photos = []
    for p in all_photos:
        js_photos.append({
            "f": p["f"], "t": p["t"], "v": p["v"],
            "d": p["d"], "s": p["s"], "cam": p["cam"],
            "lens": p["lens"], "fl": p["fl"], "fn": p["fn"],
            "ss": p["ss"], "iso": p["iso"],
        })
    js_data = json.dumps(js_photos, ensure_ascii=False)
    js_years = json.dumps(
        [{"year": yi["year"], "count": yi["count"]} for yi in year_info],
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
{CSS_INDEX}</style>
</head>
<body>
<header class="hdr">
  <h1>Photo Archive</h1>
  <p class="sub">{total:,} Photos &mdash; {h(title)}</p>
</header>

<div class="fb" id="filter-bar">
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
  <label>ISO</label>
  <div class="fg"><input type="number" id="f-iso-min" placeholder="下限" onchange="applyFilters()"><span class="sep">–</span><input type="number" id="f-iso-max" placeholder="上限" onchange="applyFilters()"></div>
  <label>F値</label>
  <div class="fg"><input type="number" id="f-fn-min" step="0.1" placeholder="下限" onchange="applyFilters()"><span class="sep">–</span><input type="number" id="f-fn-max" step="0.1" placeholder="上限" onchange="applyFilters()"></div>
  <label>焦点距離</label>
  <div class="fg"><input type="number" id="f-fl-min" placeholder="下限" onchange="applyFilters()"><span class="sep">–</span><input type="number" id="f-fl-max" placeholder="上限" onchange="applyFilters()"></div>
  <label>SS</label>
  <select id="f-ss" onchange="applyFilters()"><option value="">すべて</option></select>
  <label>検索</label>
  <input type="text" id="f-q" placeholder="ファイル名・カメラ…" oninput="applyFilters()">
  <button class="fb-reset" onclick="resetFilters()">リセット</button>
  <span class="cnt" id="cnt">{total:,} 枚</span>
</div>

<div class="yg" id="year-grid">
{"".join(cards)}
</div>

<main class="main" id="grid-root" style="display:none"></main>

<div class="lb" id="lb">
  <button class="lb-x" onclick="closeLB()" aria-label="Close">&times;</button>
  <button class="lb-n lb-p" onclick="navLB(-1)" aria-label="Previous">&#8249;</button>
  <button class="lb-n lb-nx" onclick="navLB(1)" aria-label="Next">&#8250;</button>
  <img id="li" src="" alt="">
  <div class="lb-i" id="ln"></div>
</div>

<footer class="ft">Generated by Photo Archive</footer>

<script>
{JS_INDEX.replace("__DATA__", js_data).replace("__YEARS__", js_years)}
</script>
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
  <label>ISO</label>
  <div class="fg"><input type="number" id="f-iso-min" placeholder="下限" onchange="applyFilters()"><span class="sep">–</span><input type="number" id="f-iso-max" placeholder="上限" onchange="applyFilters()"></div>
  <label>F値</label>
  <div class="fg"><input type="number" id="f-fn-min" step="0.1" placeholder="下限" onchange="applyFilters()"><span class="sep">–</span><input type="number" id="f-fn-max" step="0.1" placeholder="上限" onchange="applyFilters()"></div>
  <label>焦点距離</label>
  <div class="fg"><input type="number" id="f-fl-min" placeholder="下限" onchange="applyFilters()"><span class="sep">–</span><input type="number" id="f-fl-max" placeholder="上限" onchange="applyFilters()"></div>
  <label>SS</label>
  <select id="f-ss" onchange="applyFilters()"><option value="">すべて</option></select>
  <label>検索</label>
  <input type="text" id="f-q" placeholder="ファイル名・カメラ…" oninput="applyFilters()">
  <button class="fb-reset" onclick="resetFilters()">リセット</button>
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

    # 出力フォルダ準備（サムネイルのみ生成、元写真は直接リンク）
    gallery = root / GALLERY_DIR
    thumb_dir = gallery / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    # マニフェスト読み込み（差分処理用）
    manifest = load_manifest(gallery)
    current_rels = set()

    # 写真処理（差分）
    results = []
    total = len(photos)
    skip = 0
    cached = 0
    dedup = 0
    seen_hashes: dict[str, str] = {}  # content_hash -> rel path (dedup)

    # マニフェストから既知のハッシュを復元
    for rel, entry in manifest.items():
        ch = entry.get("ch")
        if ch:
            seen_hashes[ch] = rel

    for i, photo in enumerate(photos):
        pct = (i + 1) * 100 // total
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r  [{bar}] {i+1:,}/{total:,} ({pct}%)", end="", flush=True)

        rel = str(photo.relative_to(root)).replace("\\", "/")

        # 重複チェック（コンテンツハッシュ）
        try:
            ch = content_hash(photo)
        except OSError:
            skip += 1
            continue

        if ch in seen_hashes and seen_hashes[ch] != rel:
            dedup += 1
            continue

        seen_hashes[ch] = rel
        current_rels.add(rel)

        # キャッシュヒット判定（mtime + size が同じならスキップ）
        st = photo.stat()
        entry = manifest.get(rel)
        if entry:
            if (entry.get("mt") == st.st_mtime
                    and entry.get("sz") == st.st_size
                    and (gallery / entry["data"]["t"]).exists()):
                results.append(entry["data"])
                cached += 1
                continue

        # 新規 or 変更あり → 処理
        result = process_one(photo, root, gallery)
        if result:
            results.append(result)
            manifest[rel] = {
                "mt": st.st_mtime,
                "sz": st.st_size,
                "ch": ch,
                "data": result,
            }
        else:
            skip += 1

    # 削除された写真のサムネイルとマニフェスト項目をクリーンアップ
    removed = [r for r in manifest if r not in current_rels]
    for r in removed:
        entry = manifest.pop(r)
        old_thumb = gallery / entry["data"]["t"]
        if old_thumb.exists():
            old_thumb.unlink()

    save_manifest(gallery, manifest)

    print()
    status = []
    if cached:
        status.append(f"キャッシュ {cached}")
    if len(results) - cached > 0:
        status.append(f"新規処理 {len(results) - cached}")
    if dedup:
        status.append(f"重複除外 {dedup}")
    if skip:
        status.append(f"スキップ {skip}")
    if removed:
        status.append(f"削除 {len(removed)}")
    if status:
        print(f"  ({', '.join(status)})")
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
    index_path = generate_index_html(year_info, results, gallery, root.name)

    print()
    print("=" * 56)
    print(f"  完了！ {len(results):,} 枚のギャラリーを生成しました")
    print(f"  → {index_path}")
    print("=" * 56)
    print()

    webbrowser.open(str(index_path))


if __name__ == "__main__":
    main()
