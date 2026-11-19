"""`artikeep export`: one item (or one version of it) as a file you can send.

  html   one page with scripts, styles, images and fonts inlined; Design canvases carry
         their boards inside. Opens from disk with no network when the item's CDN files
         are vendored (the offline copy), and says which are not.
  zip    the item's files as they are, with a README.
  pdf    the html export printed by Playwright (needs it importable by python3).

The archive is never changed: old versions are rendered in a scratch copy.
"""
from __future__ import annotations

import base64
import html as htmllib
import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from artikeep.store import VERSION_SKIP_FILES, Store
from artikeep.util import now_iso
from artikeep.viewers import find_canvas, make_canvas_viewer, make_offline

FORMATS = ("html", "zip", "pdf")
MAX_INLINE = 25 * 1024 * 1024  # one inlined file
MIME = {".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
        ".otf": "font/otf", ".webp": "image/webp", ".avif": "image/avif", ".mp4": "video/mp4",
        ".webm": "video/webm", ".mp3": "audio/mpeg", ".json": "application/json", ".ico": "image/x-icon"}
PAGE_EXT = (".html", ".htm")

SCRIPT_RE = re.compile(r"""<script\b([^>]*?)\bsrc\s*=\s*(["'])([^"']+)\2([^>]*)>\s*</script>""", re.I | re.S)
LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
TAG_RE = re.compile(r"<(img|source|video|audio|embed|input|image|iframe)\b[^>]*>", re.I)
ATTR_RE = re.compile(r"""\b(src|poster|xlink:href|href|data)\s*=\s*(["'])([^"']*)\2""", re.I)
STYLE_RE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.I | re.S)
STYLE_ATTR_RE = re.compile(r"""(\bstyle\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
CSS_URL_RE = re.compile(r"""url\(\s*(["']?)([^"')]+)\1\s*\)""")
REMOTE_RE = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""", re.I)


class ExportError(Exception):
    pass


class Inliner:
    """Inlines what a page loads from its own folder tree (`root`); keeps count of what it could not."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.missing = set()  # local references with no file
        self.skipped = set()  # too large

    def local(self, ref: str, base: Path):
        ref = ref.strip()
        if not ref or ref.startswith(("#", "/", "data:", "mailto:", "javascript:", "about:", "blob:")) or "://" in ref \
                or "${" in ref or "{{" in ref:  # a template, not a file
            return None
        path = (base / ref.split("#", 1)[0].split("?", 1)[0]).resolve()
        if self.root != path and self.root not in path.parents:
            return None
        if not path.is_file():
            self.missing.add(ref)
            return None
        if path.stat().st_size > MAX_INLINE:
            self.skipped.add(ref)
            return None
        return path

    def data_uri(self, path: Path) -> str:
        mime = MIME.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode())

    def css(self, text: str, base: Path) -> str:
        def one(m):
            target = self.local(m.group(2), base)
            return "url(%s)" % self.data_uri(target) if target else m.group(0)  # base64 needs no quotes
        return CSS_URL_RE.sub(one, text)

    def page(self, text: str, base: Path, depth: int = 0) -> str:
        def script(m):
            target = self.local(m.group(3), base)
            if not target:
                return m.group(0)
            attrs = re.sub(r"\s+", " ", (m.group(1) + " " + m.group(4))).strip()
            body = target.read_text(encoding="utf-8", errors="replace").replace("</script", "<\\/script")
            return "<script%s>%s</script>" % (" " + attrs if attrs else "", body)

        def link(m):
            tag = m.group(0)
            href = re.search(r"""\bhref\s*=\s*(["'])([^"']+)\1""", tag, re.I)
            rel = re.search(r"""\brel\s*=\s*["']([^"']+)""", tag, re.I)
            if not href or not rel:
                return tag
            target = self.local(href.group(2), base)
            if not target:
                return tag
            if "stylesheet" in rel.group(1).lower():
                css = self.css(target.read_text(encoding="utf-8", errors="replace"), target.parent)
                return "<style>%s</style>" % css.replace("</style", "<\\/style")
            if "icon" in rel.group(1).lower() or "preload" in rel.group(1).lower():
                return tag.replace(href.group(0), 'href="%s"' % self.data_uri(target))
            return tag

        def tag(m):
            name, out = m.group(1).lower(), m.group(0)
            for a in ATTR_RE.finditer(m.group(0)):
                attr, ref = a.group(1).lower(), a.group(3)
                target = self.local(ref, base)
                if not target:
                    continue
                if name == "iframe" and attr == "src" and target.suffix.lower() in PAGE_EXT and depth < 3:
                    inner = self.page(target.read_text(encoding="utf-8", errors="replace"), target.parent, depth + 1)
                    out = out.replace(a.group(0), 'srcdoc="%s"' % htmllib.escape(inner, quote=True))
                elif name != "iframe" and not (attr == "href" and name != "image") and target.suffix.lower() not in PAGE_EXT:
                    out = out.replace(a.group(0), '%s="%s"' % (a.group(1), self.data_uri(target)))
            return out

        text = SCRIPT_RE.sub(script, text)
        text = LINK_RE.sub(link, text)
        text = TAG_RE.sub(tag, text)
        text = STYLE_RE.sub(lambda m: m.group(1) + self.css(m.group(2), base) + m.group(3), text)
        return STYLE_ATTR_RE.sub(lambda m: m.group(1) + m.group(2) + self.css(m.group(3), base) + m.group(2), text)


def _source(store: Store, e: dict, n: int | None):
    """(folder, version number) holding the files to export."""
    item = store.item_dir(e)
    versions = e.get("versions") or []
    if not versions or n is None or n == versions[-1]["n"]:
        return item, (versions[-1]["n"] if versions else 0)
    v = next((v for v in versions if v["n"] == n), None)
    if not v:
        raise ExportError("versions are numbered 1..%d" % len(versions))
    return item / v["dir"], n


def _stem(e: dict, n: int, latest: bool) -> str:
    return e["dir"] if latest else "%s-v%d" % (e["dir"], n)


def export_html(store: Store, e: dict, n: int | None = None) -> tuple:
    """(html bytes, notes). Raises ExportError for an item that is not a page."""
    src, _ = _source(store, e, n)
    with tempfile.TemporaryDirectory(prefix="artikeep-export-") as tmp:
        work = Path(tmp) / "item"
        shutil.copytree(src, work, ignore=shutil.ignore_patterns("versions", "server", *(VERSION_SKIP_FILES - {"index.offline.html"})))
        canvas, _ = find_canvas(work)
        if canvas:
            (work / "index.html").unlink(missing_ok=True)
            make_canvas_viewer(work)  # the current template, which can carry its boards
        page = work / "index.html"
        if not page.exists():
            main = e.get("main")
            page = work / main if main and (work / main).exists() else page
        if not page.exists() or page.suffix.lower() not in PAGE_EXT:
            raise ExportError("%s has no page to turn into one file; use --format zip" % e["dir"])
        if not canvas:
            try:
                make_offline(work)  # vendors CDN files; a no-op when already vendored, best effort without a network
            except Exception:
                pass
            offline = work / "index.offline.html"
            if offline.exists() and page.name == "index.html":
                page = offline
        inl = Inliner(work)
        text = page.read_text(encoding="utf-8", errors="replace")
        if canvas:
            boards = {}
            data = json.loads(canvas.read_text(encoding="utf-8"))
            base = "" if canvas.parent == work else canvas.parent.name + "/"
            from urllib.parse import quote
            for k in (data.get("boards") or {}):
                f = canvas.parent / k
                if f.is_file():
                    boards[base + quote(k, safe="/~@!$&'()*+,;=:")] = inl.page(f.read_text(encoding="utf-8", errors="replace"), f.parent)
            text = text.replace("const INLINE = {};", "const INLINE = %s;" % json.dumps(boards, ensure_ascii=False).replace("</", "<\\/"), 1)
        text = inl.page(text, page.parent)
        notes = []
        remote = sorted({u for u in REMOTE_RE.findall(text) if re.search(r"\.(js|css|woff2?|ttf)\b|fonts\.", u)})
        if remote:
            notes.append("needs a network for %d file(s) it could not inline: %s" % (len(remote), ", ".join(remote[:3]) + (", …" if len(remote) > 3 else "")))
        if inl.missing:
            notes.append("%d referenced file(s) are not in the archive: %s" % (len(inl.missing), ", ".join(sorted(inl.missing)[:3])))
        if inl.skipped:
            notes.append("left out (over %d MB): %s" % (MAX_INLINE >> 20, ", ".join(sorted(inl.skipped)[:3])))
        if "<meta charset" not in text[:2000].lower():
            text = text.replace("<head>", '<head><meta charset="utf-8">', 1) if "<head>" in text else '<meta charset="utf-8">' + text
        return text.encode("utf-8"), notes


def export_zip(store: Store, e: dict, n: int | None = None) -> tuple:
    src, num = _source(store, e, n)
    versions = e.get("versions") or []
    v = next((v for v in versions if v["n"] == num), {})
    readme = "\n".join(filter(None, [
        e.get("title") or e["dir"], "",
        "Source:   %s" % (e.get("agent") or "claude-code"),
        "Original: %s" % (e.get("url") or e.get("origin") or "-"),
        "Version:  %s of %d, saved %s" % (num, len(versions), v.get("at", e.get("updated", "?"))) if versions else None,
        ("Request:  %s" % v["request"]) if v.get("request") else None,
        "Exported: %s by artikeep" % now_iso()[:19], "",
        "Open index.html in a browser (or the main file of the item)."]))
    import io
    buf = io.BytesIO()
    stem = _stem(e, num, src == store.item_dir(e))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src)
            if not f.is_file() or rel.parts[0] in ("versions", "server") or f.name in ("_thumb.jpg", ".artikeep-restore.json"):
                continue
            z.write(f, "%s/%s" % (stem, rel))
        z.writestr("%s/README.txt" % stem, readme + "\n")
    return buf.getvalue(), []


PDF_SCRIPT = r'''
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto("file://" + sys.argv[1], wait_until="load", timeout=60000)
        await pg.wait_for_timeout(1500)
        await pg.pdf(path=sys.argv[2], print_background=True)
        await b.close()
asyncio.run(main())
'''


def export_pdf(store: Store, e: dict, n: int | None = None) -> tuple:
    if subprocess.run(["python3", "-c", "import playwright"], capture_output=True).returncode != 0:
        raise ExportError("--format pdf needs Playwright in the python3 on PATH (pip install playwright; playwright install chromium)")
    data, notes = export_html(store, e, n)
    with tempfile.TemporaryDirectory(prefix="artikeep-pdf-") as tmp:
        page, out = Path(tmp) / "page.html", Path(tmp) / "page.pdf"
        page.write_bytes(data)
        r = subprocess.run(["python3", "-c", PDF_SCRIPT, str(page), str(out)], capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not out.exists():
            raise ExportError("printing failed: %s" % (r.stderr.strip().splitlines() or ["unknown error"])[-1])
        return out.read_bytes(), notes


def build(store: Store, folder: str, fmt: str = "html", n: int | None = None) -> tuple:
    """(file name, bytes, notes) for item `folder`."""
    if fmt not in FORMATS:
        raise ExportError("format must be one of %s" % ", ".join(FORMATS))
    try:
        _, e = store.find(store.load(), folder)
    except KeyError:
        raise ExportError("no item %s" % folder)
    data, notes = {"html": export_html, "zip": export_zip, "pdf": export_pdf}[fmt](store, e, n)
    _, num = _source(store, e, n)
    latest = not e.get("versions") or num == e["versions"][-1]["n"]
    return "%s.%s" % (_stem(e, num, latest), fmt), data, notes
