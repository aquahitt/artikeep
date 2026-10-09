"""The gallery page (index.html at the archive root): data assembly and text diffs.

The page itself is gallery.template.html with the data embedded as JSON, so it
opens from disk with no server. Thumbnails need Playwright in a `python3` on PATH.
"""
from __future__ import annotations

import datetime as dt
import difflib
import html
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from artikeep.search import version_text
from artikeep.store import Store, agent_of

TYPE_CANVAS, TYPE_DOC, TYPE_PAGE, TYPE_FILE = "canvas", "doc", "page", "file"
TEMPLATE = Path(__file__).with_name("gallery.template.html")
HOSTS = {"claude.ai": "claude.ai", "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT", "gemini.google.com": "Gemini"}


def text_diff(a: dict, b: dict, limit: int = 80) -> dict:
    """Changed lines between two versions: [{file, op: '+'|'-', text}], plus counts."""
    changes, add, rem = [], 0, 0
    for name in sorted(set(a) | set(b)):
        la, lb = a.get(name, []), b.get(name, [])
        if la == lb:
            continue
        sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("delete", "replace"):
                rem += i2 - i1
                changes += [{"file": name, "op": "-", "text": t} for t in la[i1:i2]]
            if tag in ("insert", "replace"):
                add += j2 - j1
                changes += [{"file": name, "op": "+", "text": t} for t in lb[j1:j2]]
    return {"add": add, "rem": rem, "lines": changes[:limit], "more": max(0, len(changes) - limit)}


def item_type(d: Path, e: dict) -> str:
    if (d / "project" / "canvas.json").exists() or (d / "canvas.json").exists():
        return TYPE_CANVAS
    main = (e.get("main") or "").lower()
    if e.get("kind") == "claude-doc" or e.get("aliases") or list(d.glob("doc-*.md")) or main.endswith(".md") \
            or (d / "audit.md").exists():
        return TYPE_DOC
    if e.get("restore_fidelity") == "missing":
        return TYPE_DOC if "/code/artifact/" in (e.get("url") or "") else TYPE_PAGE
    if (d / "index.html").exists() or not main or main.endswith((".html", ".htm")):
        return TYPE_PAGE
    return TYPE_FILE


def item_status(e: dict) -> str:
    if e.get("deleted"):
        return "deleted"
    return e.get("restore_fidelity") or ("live" if e.get("publishes") or e.get("kind") == "claude-doc" or e.get("versions") else "missing")


def main_file(d: Path, e: dict) -> str | None:
    """What opening the item shows: a page (published or generated viewer), else the main file."""
    if (d / "index.html").exists():
        return "index.html"
    if e.get("main") and (d / e["main"]).exists():
        return e["main"]
    return None


def origin_of(e: dict, key: str) -> dict:
    """Where the original lives, for the "open original" link."""
    url = e.get("url") or (key if key.startswith("http") else None)
    if url:
        host = urlparse(url).netloc
        return {"href": url, "label": HOSTS.get(host, host)}
    if e.get("origin"):
        return {"href": "file://" + e["origin"], "label": e["origin"]}
    return {"href": "", "label": ""}


def plural_en(n: int, word: str) -> str:
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def version_summary(d: Path, v: dict, typ: str, prev_v) -> dict:
    """Numbers only: the page words them in its own language."""
    vd = d / v["dir"]
    if typ == TYPE_CANVAS:
        boards = len(list((vd / "project").glob("*.dc.html"))) or len(list(vd.glob("*.dc.html")))
        ch = [c for c in v.get("changed", []) if c.endswith(".dc.html")] if prev_v is not None else None
        return {"boards": boards, "boardsChanged": None if ch is None else len(ch)}
    if typ == TYPE_FILE:
        return {}
    diff = v.get("diff")
    if prev_v is None or not diff:
        return {"lines": sum(len(x) for x in version_text(vd).values()) if vd.exists() else 0}
    return {"add": diff["add"], "rem": diff["rem"]}


def ensure_diffs(store: Store, m: dict) -> bool:
    """Text diff of every version against the previous one, and first against last. Cached in manifest."""
    changed = False
    for e in m["items"].values():
        d = store.item_dir(e)
        vs = e.get("versions") or []
        for i, v in enumerate(vs):
            if i == 0 or v.get("diff") is not None:
                continue
            a, b = d / vs[i - 1]["dir"], d / v["dir"]
            if a.exists() and b.exists():
                v["diff"] = text_diff(version_text(a), version_text(b))
                changed = True
        if len(vs) > 2 and (e.get("diff_first_last") or {}).get("to") != vs[-1]["n"]:
            a, b = d / vs[0]["dir"], d / vs[-1]["dir"]
            if a.exists() and b.exists():
                e["diff_first_last"] = dict(text_diff(version_text(a), version_text(b)), to=vs[-1]["n"])
                changed = True
    return changed


_REPO = {}


def project_repo(path):
    """owner/name of the project's GitHub remote, for issue links."""
    if not path or not Path(path).exists():
        return None
    if path not in _REPO:
        r = subprocess.run(["git", "-C", path, "remote", "get-url", "origin"], capture_output=True, text=True)
        m = re.search(r"github\.com[:/]([^/]+/[^/.\s]+)", r.stdout)
        _REPO[path] = m.group(1) if m else None
    return _REPO[path]


def project_label(path) -> str:
    return Path(path).name if path else ""


def gallery_data(store: Store, m: dict) -> dict:
    items = []
    for key, e in m["items"].items():
        d = store.item_dir(e)
        typ = item_type(d, e)
        vs = e.get("versions") or []
        versions = [{
            "n": v["n"], "at": v["at"][:16].replace("T", " "), "label": v.get("label") or "", "dir": v["dir"],
            "sum": version_summary(d, v, typ, vs[i - 1] if i else None), "diff": v.get("diff"),
            "main": main_file(d / v["dir"], e),
        } for i, v in enumerate(vs)]
        main = main_file(d, e)
        items.append({
            "key": key, "title": e.get("title") or e["dir"], "dir": e["dir"], "url": e.get("url") or "",
            "origin": origin_of(e, key), "agent": agent_of(e), "main": main,
            "project": project_label(e.get("project")), "repo": project_repo(e.get("project")), "type": typ,
            "status": item_status(e), "created": (e.get("created") or "")[:10],
            "updated": (e.get("updated") or e.get("created") or "")[:16].replace("T", " "),
            "desc": e.get("description") or "", "issues": e.get("issues") or [], "versions": versions,
            "firstLast": e.get("diff_first_last"), "local": main is not None,
            "offline": (d / "index.offline.html").exists(), "server": (d / "server" / "index.html").exists(),
            "thumb": (d / "_thumb.jpg").exists(), "service": bool(e.get("service")),
        })
    drafts = []
    droot = store.root / "drafts"
    if droot.exists():
        for folder in sorted(droot.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            meta = {}
            try:
                meta = json.loads((folder / "_meta.json").read_text(encoding="utf-8"))
            except Exception:
                pass
            for f in sorted(folder.rglob("*.htm*")):
                t = re.search(r"<title[^>]*>(.*?)</title>", f.read_text(encoding="utf-8", errors="ignore")[:6000], re.S | re.I)
                drafts.append({
                    "title": html.unescape(t.group(1).strip()) if t else f.stem.replace("-", " "),
                    "path": str(f.relative_to(store.root)), "folder": folder.name, "date": folder.name[:10],
                    "project": project_label(meta.get("project")), "agent": meta.get("agent") or "claude-code",
                    "origin": "brainstorm" if "brainstorm" in folder.name else "scratchpad",
                })
    return {"items": items, "drafts": drafts, "built": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "lang": store.settings.get("lang") or "auto"}


def build(store: Store, m: dict) -> dict:
    data = gallery_data(store, m)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (store.root / "index.html").write_text(TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", blob), encoding="utf-8")
    return data


# ---------------------------------------------------------------- thumbnails (Playwright, separate interpreter)

THUMB_SCRIPT = r'''
import asyncio, json, sys
from playwright.async_api import async_playwright
jobs = json.loads(sys.argv[1])
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for page, out in jobs:
            pg = await b.new_page(viewport={"width": 1200, "height": 750})
            try:
                await pg.goto("file://" + page, wait_until="load", timeout=30000)
                await pg.wait_for_timeout(1500)
                await pg.screenshot(path=out, type="jpeg", quality=70)
            except Exception as e:
                print("thumb failed", page, e, file=sys.stderr)
            await pg.close()
        await b.close()
asyncio.run(main())
'''


def refresh_thumbs(store: Store, m: dict) -> int:
    if store.settings.get("thumbnails") in (False, "off"):
        return 0
    jobs = []
    for e in m["items"].values():
        d = store.item_dir(e)
        main = main_file(d, e)
        if not main or not main.lower().endswith((".html", ".htm", ".svg", ".png", ".jpg", ".jpeg", ".pdf")):
            continue
        page, out = d / main, d / "_thumb.jpg"
        if not out.exists() or out.stat().st_mtime < page.stat().st_mtime:
            jobs.append([str(page), str(out)])
    if not jobs:
        return 0
    probe = subprocess.run(["python3", "-c", "import playwright"], capture_output=True)
    if probe.returncode != 0:
        if store.settings.get("thumbnails") is True:
            store.note("gallery.log", "thumbnails: no Playwright in python3 on PATH")
        return 0
    try:
        r = subprocess.run(["python3", "-c", THUMB_SCRIPT, json.dumps(jobs)], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            store.note("gallery.log", "thumbs: %s" % r.stderr.strip()[-300:])
    except Exception as ex:
        store.note("gallery.log", "thumbs: %s" % ex)
    return len(jobs)
