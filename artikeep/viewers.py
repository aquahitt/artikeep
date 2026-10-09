"""Pages generated next to archived files so they open locally in a browser.

  canvas viewer   a Claude Design canvas (canvas.json + artboard pages) laid out as on the host
  doc viewer      Markdown documents (doc-*.md, or a Markdown main file) with tabs
  react viewer    a React component (.jsx/.tsx, as claude.ai makes them) rendered with the libraries
                  claude.ai offers, from CDN; the offline copy vendors them
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


# ---------------------------------------------------------------- React components

REACT_MARKS = ("<!-- artikeep react viewer -->",)
CDN = {
    "react": "https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js",
    "react-dom": "https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js",
    "babel": "https://unpkg.com/@babel/standalone@7.25.6/babel.min.js",
    "tailwind": "https://cdn.tailwindcss.com/3.4.16",
    "prop-types": "https://unpkg.com/prop-types@15.8.1/prop-types.min.js",
    "recharts": "https://unpkg.com/recharts@2.12.7/umd/Recharts.js",
    "lucide-react": "https://unpkg.com/lucide-react@0.383.0/dist/umd/lucide-react.min.js",
    "lodash": "https://cdnjs.cloudflare.com/ajax/libs/lodash.js/4.17.21/lodash.min.js",
    "d3": "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js",
    "mathjs": "https://cdnjs.cloudflare.com/ajax/libs/mathjs/13.2.0/math.min.js",
    "papaparse": "https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js",
    "xlsx": "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js",
    "three": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
    "tone": "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.js",
    "chart.js": "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js",
}
# module name a component imports -> scripts it needs (in order)
NEEDS = {"recharts": ["prop-types", "recharts"], "lucide-react": ["lucide-react"], "lodash": ["lodash"], "d3": ["d3"],
         "mathjs": ["mathjs"], "papaparse": ["papaparse"], "xlsx": ["xlsx"], "three": ["three"], "tone": ["tone"],
         "chart.js": ["chart.js"], "chart.js/auto": ["chart.js"]}
IMPORT_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']""")

REACT_VIEWER = """<!doctype html>
""" + REACT_MARKS[0] + """
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
#artikeep-error{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:16px;padding:14px 16px;border:1px solid #d9a6a0;border-radius:10px;background:#fdf3f2;color:#5e1b14}
#artikeep-error pre{white-space:pre-wrap;overflow:auto;max-height:60vh;background:#fff;border:1px solid #eee;padding:10px;border-radius:6px;color:#222}
</style>
__SCRIPTS__
</head><body>
<div id="root"></div>
<script type="application/json" id="artikeep-src">__SRC__</script>
<script>
(function () {
  const RU = /^ru\\b/i.test(navigator.language || "");
  const src = JSON.parse(document.getElementById("artikeep-src").textContent);
  function fail(msg) {
    const box = document.createElement("div"); box.id = "artikeep-error";
    const h = document.createElement("b"); h.textContent = (RU ? "Компонент не отрисовался: " : "The component did not render: ") + msg;
    const d = document.createElement("details"); const s = document.createElement("summary"); s.textContent = RU ? "Исходник" : "Source";
    const pre = document.createElement("pre"); pre.textContent = src.code; d.append(s, pre); box.append(h, d);
    document.body.prepend(box);
  }
  window.addEventListener("error", e => fail(e.message));
  const h = React.createElement, cx = (...a) => a.filter(Boolean).join(" ");
  const part = (tag, base) => React.forwardRef(({className, ...p}, ref) => h(tag, {ref, className: cx(base, className), ...p}));
  const UI = {
    Card: part("div", "rounded-lg border bg-white text-slate-950 shadow-sm"), CardHeader: part("div", "flex flex-col space-y-1.5 p-6"),
    CardTitle: part("h3", "text-2xl font-semibold leading-none tracking-tight"), CardDescription: part("p", "text-sm text-slate-500"),
    CardContent: part("div", "p-6 pt-0"), CardFooter: part("div", "flex items-center p-6 pt-0"),
    Button: part("button", "inline-flex items-center justify-center rounded-md text-sm font-medium h-10 px-4 py-2 bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"),
    Input: part("input", "flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"),
    Textarea: part("textarea", "flex min-h-[80px] w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"),
    Label: part("label", "text-sm font-medium leading-none"), Badge: part("span", "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold"),
    Alert: part("div", "relative w-full rounded-lg border p-4"), AlertTitle: part("h5", "mb-1 font-medium leading-none tracking-tight"),
    AlertDescription: part("div", "text-sm"), Separator: part("div", "shrink-0 bg-slate-200 h-px w-full"),
    Progress: ({value = 0, className}) => h("div", {className: cx("relative h-4 w-full overflow-hidden rounded-full bg-slate-100", className)},
      h("div", {className: "h-full bg-slate-900", style: {width: value + "%"}})),
    Checkbox: ({checked, onCheckedChange, className, ...p}) => h("input", {type: "checkbox", checked: !!checked, onChange: e => onCheckedChange && onCheckedChange(e.target.checked), className, ...p}),
    Switch: ({checked, onCheckedChange, className, ...p}) => h("input", {type: "checkbox", role: "switch", checked: !!checked, onChange: e => onCheckedChange && onCheckedChange(e.target.checked), className, ...p}),
    Slider: ({value = [0], onValueChange, min = 0, max = 100, step = 1, className}) => h("input", {type: "range", min, max, step, value: value[0], className: cx("w-full", className), onChange: e => onValueChange && onValueChange([+e.target.value])}),
  };
  const TabsCtx = React.createContext(null);
  UI.Tabs = ({defaultValue, value, onValueChange, className, children}) => { const [v, setV] = React.useState(defaultValue);
    const cur = value !== undefined ? value : v; return h(TabsCtx.Provider, {value: {cur, set: x => { setV(x); onValueChange && onValueChange(x); }}}, h("div", {className}, children)); };
  UI.TabsList = part("div", "inline-flex h-10 items-center justify-center rounded-md bg-slate-100 p-1");
  UI.TabsTrigger = ({value, className, children}) => { const c = React.useContext(TabsCtx);
    return h("button", {type: "button", onClick: () => c.set(value), className: cx("inline-flex items-center rounded-sm px-3 py-1.5 text-sm font-medium", c.cur === value && "bg-white shadow-sm", className)}, children); };
  UI.TabsContent = ({value, className, children}) => React.useContext(TabsCtx).cur === value ? h("div", {className}, children) : null;
  const passthrough = name => UI[name] || (UI[name] = part("div", ""));
  const uiModule = new Proxy({}, {get: (_, k) => k === "__esModule" ? false : typeof k === "string" ? passthrough(k) : undefined});
  window.react = React;  // lucide-react's UMD build looks React up under this name
  const MODULES = {"react": () => React, "react-dom": () => ReactDOM, "react-dom/client": () => ReactDOM,
    "recharts": () => window.Recharts, "lucide-react": () => window.LucideReact, "lodash": () => window._,
    "d3": () => window.d3, "mathjs": () => window.math, "papaparse": () => window.Papa, "xlsx": () => window.XLSX,
    "three": () => window.THREE, "tone": () => window.Tone, "chart.js": () => window.Chart, "chart.js/auto": () => window.Chart};
  function require(name) {
    if (name.startsWith("@/components/ui/")) return uiModule;
    const get = MODULES[name];
    const mod = get && get();
    if (!mod) throw new Error((RU ? "библиотека недоступна без сети: " : "library not available offline: ") + name);
    return mod;
  }
  let Comp;
  try {
    const out = Babel.transform(src.code, {filename: src.name, presets: [["react"], ["typescript", {isTSX: true, allExtensions: true}]],
      plugins: ["transform-modules-commonjs"]}).code;
    const module = {exports: {}};
    new Function("require", "module", "exports", "React", out)(require, module, module.exports, React);
    const ex = module.exports;
    Comp = ex.default || (typeof ex === "function" ? ex : Object.values(ex).find(v => typeof v === "function"));
    if (!Comp) throw new Error(RU ? "в файле нет экспортированного компонента" : "the file exports no component");
  } catch (e) { fail(e.message); return; }
  try { ReactDOM.createRoot(document.getElementById("root")).render(h(Comp)); } catch (e) { fail(e.message); }
})();
</script></body></html>
"""


def react_source(item: Path, entry: dict):
    main = entry.get("main") or entry.get("source_name") or ""
    if main.lower().endswith((".jsx", ".tsx")) and (item / main).exists():
        return item / main
    return None


def make_react_viewer(item: Path, entry: dict) -> None:
    srcf = react_source(item, entry)
    if not srcf:
        return
    page = item / "index.html"
    if page.exists():
        if not _generated(page, REACT_MARKS):
            return  # a real page lives here
        if page.stat().st_mtime >= srcf.stat().st_mtime:
            return
    code = srcf.read_text(encoding="utf-8", errors="ignore")
    wanted = ["react", "react-dom", "babel", "tailwind"]
    for mod in IMPORT_RE.findall(code):
        for need in NEEDS.get(mod, []):
            if need not in wanted:
                wanted.append(need)
    scripts = "\n".join('<script src="%s"></script>' % CDN[k] for k in wanted if k != "lucide-react")
    if "lucide-react" in wanted:  # needs window.react before it loads
        scripts += '\n<script>window.react = window.React;</script>\n<script src="%s"></script>' % CDN["lucide-react"]
    page.write_text(
        REACT_VIEWER.replace("__TITLE__", html.escape(entry.get("title") or srcf.stem))
        .replace("__SCRIPTS__", scripts)
        .replace("__SRC__", json.dumps({"name": srcf.name, "code": code}, ensure_ascii=False).replace("</", "<\\/")),
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
