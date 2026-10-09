"""Pages generated next to archived files so they open locally in a browser.

  canvas viewer   a Claude Design canvas (canvas.json + artboard pages) laid out as on the host
  doc viewer      Markdown documents (doc-*.md, or a Markdown main file) with tabs
  offline copy    index.offline.html with CDN scripts, styles and fonts vendored into _vendor/
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from pathlib import Path

from artikeep.util import now_iso, with_charset

CANVAS_MARKS = ("<!-- artikeep canvas viewer -->", "<!-- claude-artifacts canvas viewer -->")
DOC_MARKS = ("<!-- artikeep doc viewer -->", "<!-- claude-artifacts doc viewer -->")
VENDOR_HOSTS = (
    "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com", "cdn.tailwindcss.com",
    "code.jquery.com", "fonts.googleapis.com", "fonts.gstatic.com",
)
LANG_JS = 'const RU = /^ru\\b/i.test(navigator.language || "");'


def _generated(page: Path, marks) -> bool:
    return any(m in page.read_text(encoding="utf-8", errors="ignore")[:300] for m in marks)


# ---------------------------------------------------------------- canvas

CANVAS_VIEWER = """<!doctype html>
""" + CANVAS_MARKS[0] + """
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#e9e7e2;--panel:#fff;--fg:#1d1d1b;--muted:#6b6a66;--line:#d6d3cc;--accent:#b4501c}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#121211;--panel:#21211f;--fg:#ecebe7;--muted:#9c9a94;--line:#34332f;--accent:#f08a50}}
:root[data-theme="dark"]{--bg:#121211;--panel:#21211f;--fg:#ecebe7;--muted:#9c9a94;--line:#34332f;--accent:#f08a50}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 -apple-system,system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--panel);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center}
h1{font-size:16px;margin:0}.tabs,.zoom{display:flex;flex-wrap:wrap;gap:6px}
button{border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:999px;padding:5px 12px;font:inherit;cursor:pointer}
button[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}
.note{color:var(--muted);font-size:12px}
#vp{overflow:auto;height:calc(100vh - 58px)}#stage{position:relative;transform-origin:0 0}
.board{position:absolute}.board .t{position:absolute;bottom:100%;left:0;padding-bottom:6px;font-size:13px;font-weight:600;white-space:nowrap}
.board .t a{color:var(--fg);text-decoration:none}.board .t a:hover{color:var(--accent)}
.board iframe{border:0;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.18);display:block}
.cn{position:absolute;white-space:pre-wrap}.cn.title1{font-size:40px;font-weight:700}.cn.title2{font-size:26px;font-weight:600}.cn.body{font-size:18px;color:var(--muted)}
</style></head><body>
<header><h1>__TITLE__</h1><div class="tabs" id="tabs"></div><div class="zoom" id="zoom"></div>
<span class="note" id="note"></span></header>
<div id="vp"><div id="stage"></div></div>
<script>
""" + LANG_JS + """
const C = __CANVAS__, BASE = "__BASE__";
document.documentElement.lang = RU ? "ru" : "en";
document.getElementById("note").textContent = RU ? "Локальная копия холста: артборды — отдельные страницы, клик по названию открывает артборд целиком." : "Local copy of the canvas: each artboard is its own page; click a title to open it.";
const pages = (C.pages && C.pages.length) ? C.pages : [{id: "", name: RU ? "Холст" : "Canvas"}];
let page = (C.launch && C.launch.page) || pages[0].id, zoom = "fit";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const onPage = o => !C.pages || !C.pages.length || (o.page || pages[0].id) === page;
function render(){
  const order = (C.order || Object.keys(C.boards)).filter(k => C.boards[k] && onPage(C.boards[k]));
  const notes = Object.values(C.notes || {}).filter(onPage);
  let W = 0, H = 0, x0 = Infinity, y0 = Infinity;
  for (const k of order){ const b = C.boards[k]; x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y - 30); W = Math.max(W, b.x + b.w); H = Math.max(H, b.y + b.h); }
  for (const n of notes){ x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); W = Math.max(W, n.x + (n.maxW || n.w || 400)); H = Math.max(H, n.y + 60); }
  if (!isFinite(x0)) { x0 = 0; y0 = 0; }
  x0 -= 40; y0 -= 40; W = W - x0 + 40; H = H - y0 + 40;
  const st = document.getElementById("stage");
  st.style.width = W + "px"; st.style.height = H + "px";
  st.innerHTML = notes.map(n => `<div class="cn ${esc(n.kind)}" style="left:${n.x - x0}px;top:${n.y - y0}px;max-width:${n.maxW || 900}px">${esc(n.text)}</div>`).join("") +
    order.map(k => { const b = C.boards[k]; const src = BASE + encodeURI(k);
      return `<div class="board" style="left:${b.x - x0}px;top:${b.y - y0}px;width:${b.w}px;height:${b.h}px"><div class="t"><a href="${src}" target="_blank">${esc(b.title || k)}</a></div><iframe loading="lazy" src="${src}" width="${b.w}" height="${b.h}" title="${esc(b.title || k)}"></iframe></div>`; }).join("");
  const vw = document.getElementById("vp").clientWidth;
  const s = zoom === "fit" ? Math.min(1, (vw - 24) / W) : zoom;
  st.style.transform = `scale(${s})`; st.style.marginBottom = `${-(1 - s) * H}px`; st.style.marginRight = `${-(1 - s) * W}px`;
  document.getElementById("tabs").innerHTML = pages.length > 1 ? pages.map(p => `<button data-p="${esc(p.id)}" aria-pressed="${p.id === page}">${esc(p.name)}</button>`).join("") : "";
  document.getElementById("zoom").innerHTML = [["fit", RU ? "Вписать" : "Fit"],[0.5,"50%"],[1,"100%"]].map(([z,l]) => `<button data-z="${z}" aria-pressed="${z === zoom}">${l}</button>`).join("");
}
document.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.p !== undefined) { page = b.dataset.p; render(); document.getElementById("vp").scrollTo(0, 0); }
  if (b.dataset.z) { zoom = b.dataset.z === "fit" ? "fit" : Number(b.dataset.z); render(); } });
addEventListener("resize", () => zoom === "fit" && render());
render();
</script></body></html>
"""

SUPPORT_STUB = (
    "// stub: the Design runtime lives on the host; static artboards render without it.\n"
    "window.DCLogic = window.DCLogic || class DCLogic {};\n"
)


def find_canvas(item: Path):
    for c in (item / "project" / "canvas.json", item / "canvas.json"):
        if c.exists():
            try:
                d = json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d.get("boards"), dict):
                return c, d
    return None, None


def make_canvas_viewer(item: Path) -> None:
    c, d = find_canvas(item)
    if not c:
        return
    page = item / "index.html"
    if page.exists() and not _generated(page, CANVAS_MARKS):
        return  # a real page was published; keep it
    if page.exists() and page.stat().st_mtime >= c.stat().st_mtime:
        return
    support = c.parent / "support.js"
    if not support.exists():
        support.write_text(SUPPORT_STUB, encoding="utf-8")
    base = "" if c.parent == item else c.parent.name + "/"
    page.write_text(
        CANVAS_VIEWER.replace("__TITLE__", html.escape(d.get("title") or item.name))
        .replace("__BASE__", base)
        .replace("__CANVAS__", json.dumps(d, ensure_ascii=False).replace("</", "<\\/")),
        encoding="utf-8",
    )


# ---------------------------------------------------------------- documents

DOC_VIEWER = """<!doctype html>
""" + DOC_MARKS[0] + """
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<style>
:root{--bg:#f6f5f2;--surface:#fff;--fg:#1d1d1b;--muted:#6b6a66;--line:#e2e0da;--accent:#b4501c;--code:#f0eee9}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#171716;--surface:#21211f;--fg:#ecebe7;--muted:#9c9a94;--line:#34332f;--accent:#f08a50;--code:#2b2a27}}
:root[data-theme="dark"]{--bg:#171716;--surface:#21211f;--fg:#ecebe7;--muted:#9c9a94;--line:#34332f;--accent:#f08a50;--code:#2b2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
.meta{font-size:13px;color:var(--muted);margin-bottom:16px;overflow-wrap:anywhere}.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px}
.tabs button{border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:999px;padding:5px 12px;font:inherit;font-size:14px;cursor:pointer}
.tabs button[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}
h1{font-size:28px;line-height:1.2}h2{font-size:21px;margin-top:32px}p,li{max-width:72ch}a{color:var(--accent)}
code{background:var(--code);border-radius:4px;padding:1px 4px;font-size:.9em}pre code{display:block;padding:10px;overflow-x:auto}
.tbl{overflow-x:auto}table{border-collapse:collapse;font-size:14px;background:var(--surface)}th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:var(--code)}
</style></head><body><main>
<div class="meta" id="meta"></div>
<div class="tabs" id="tabs"></div><article id="doc"></article>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
""" + LANG_JS + """
const D = JSON.parse(document.getElementById("data").textContent), T = D.tabs;
document.documentElement.lang = RU ? "ru" : "en";
const meta = document.getElementById("meta");
meta.textContent = (RU ? "Копия документа из архива, сохранена " : "Archived copy of the document, saved ") + D.saved + (D.origin ? (RU ? ". Оригинал: " : ". Original: ") : "");
if (D.origin) { const a = document.createElement(/^https?:/.test(D.origin) ? "a" : "span"); a.textContent = D.origin; if (a.tagName === "A") a.href = D.origin; meta.appendChild(a); }
let cur = 0;
function render(){
  const md = T[cur].md, doc = document.getElementById("doc");
  if (window.marked) { doc.innerHTML = marked.parse(md); doc.querySelectorAll("table").forEach(t => { const w = document.createElement("div"); w.className = "tbl"; t.replaceWith(w); w.appendChild(t); }); }
  else { doc.innerHTML = ""; const p = document.createElement("pre"); p.style.whiteSpace = "pre-wrap"; p.textContent = md; doc.appendChild(p); }
  document.getElementById("tabs").innerHTML = T.length > 1 ? T.map((t, i) => `<button data-i="${i}" aria-pressed="${i === cur}">${t.name.replace(/[&<>]/g, "")}</button>`).join("") : "";
}
document.addEventListener("click", e => { const b = e.target.closest("button[data-i]"); if (b) { cur = +b.dataset.i; render(); } });
render();
</script></body></html>
"""


def doc_sources(item: Path, entry: dict) -> list:
    mds = sorted(item.glob("doc-*.md"))
    main = entry.get("main")
    if not mds and main and main.lower().endswith(".md") and (item / main).exists():
        mds = [item / main]
    return mds


def make_doc_viewer(item: Path, entry: dict) -> None:
    mds = doc_sources(item, entry)
    if not mds:
        return
    page = item / "index.html"
    if page.exists():
        if not _generated(page, DOC_MARKS):
            return  # a real page lives here (e.g. a restored copy)
        if page.stat().st_mtime >= max(f.stat().st_mtime for f in mds):
            return
    tabs = []
    for f in mds:
        md = f.read_text(encoding="utf-8", errors="ignore")
        h = re.search(r"^#\s+(.+)$", md, re.M)
        tabs.append({"name": h.group(1).strip() if h else re.sub(r"^doc-", "", f.stem), "md": md})
    data = {
        "tabs": tabs,
        "origin": entry.get("url") or entry.get("origin") or "",
        "saved": (entry.get("exported") or entry.get("updated") or now_iso())[:16].replace("T", " "),
    }
    page.write_text(
        DOC_VIEWER.replace("__TITLE__", html.escape(entry.get("title") or tabs[0]["name"]))
        .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")),
        encoding="utf-8",
    )


# ---------------------------------------------------------------- offline copy


def _fetch(url: str, dst: Path) -> None:
    if dst.exists() and dst.stat().st_size:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) artikeep"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)


def _vendor_name(url: str) -> str:
    tail = re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[-1])[-80:]
    return hashlib.sha1(url.encode()).hexdigest()[:10] + "_" + tail


def make_offline(item: Path) -> None:
    page = item / "index.html"
    if not page.exists():
        return
    out = item / "index.offline.html"
    if out.exists() and out.stat().st_mtime >= page.stat().st_mtime:
        return
    src = page.read_text(encoding="utf-8", errors="ignore")
    vend = item / "_vendor"
    refs = set(re.findall(r"""(?:src|href)\s*=\s*["'](https://[^"']+)["']""", src))
    refs |= set(re.findall(r"""import\s[^'"]*?from\s*["'](https://[^"']+)["']""", src))
    refs |= set(re.findall(r"""import\s*\(\s*["'](https://[^"']+)["']""", src))
    failed = []
    for url in sorted(refs):
        if not any(h in url for h in VENDOR_HOSTS):
            continue
        name = _vendor_name(url)
        try:
            _fetch(url, vend / name)
        except Exception:
            failed.append(url)
            continue
        if "fonts.googleapis.com" in url:
            css = (vend / name).read_text(encoding="utf-8", errors="ignore")
            for furl in set(re.findall(r"url\((https://[^)]+)\)", css)):
                fname = _vendor_name(furl)
                try:
                    _fetch(furl, vend / fname)
                    css = css.replace(furl, fname)
                except Exception:
                    failed.append(furl)
            (vend / name).write_text(css, encoding="utf-8")
        src = src.replace(url, "_vendor/" + name)
    note = "<!-- offline copy %s; not vendored: %s -->\n" % (now_iso(), ", ".join(failed) or "none")
    out.write_bytes(with_charset((note + src).encode("utf-8")))
