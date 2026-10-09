"""Full-text search over the archive: SQLite FTS5 in .cache/index.sqlite.

The index holds title, description and the readable text of each item's newest
version. It is rebuilt incrementally by the background pass and on demand; when
SQLite lacks FTS5, search falls back to a plain scan of the same text.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
from pathlib import Path

from artikeep.store import Store, agent_of

SCRIPT_RE = re.compile(r"<(script|style|svg|noscript)\b.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
BLOCK_RE = re.compile(r"<(br|/p|/div|/li|/h\d|/tr|/td|/th|/section|/article|/label|/button)\b[^>]*>", re.I)
TEXT_EXT = {".md", ".txt", ".csv", ".json", ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".mmd", ".sh", ".sql"}
MAX_TEXT = 400_000


def visible_text(raw: str) -> list:
    """Readable lines of an HTML page."""
    raw = SCRIPT_RE.sub(" ", raw)
    raw = BLOCK_RE.sub("\n", raw)
    text = html.unescape(TAG_RE.sub(" ", raw))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if len(ln) > 1]


def version_text(vdir: Path) -> dict:
    """{file: [lines]} for every page, artboard and text document in a folder."""
    out = {}
    if not vdir.exists():
        return out
    for f in sorted(vdir.rglob("*")):
        rel = f.relative_to(vdir)
        if not f.is_file() or rel.parts[0] in ("versions", "_vendor", "server") or f.name == "index.offline.html":
            continue
        suf = f.suffix.lower()
        if suf in (".html", ".htm"):
            raw = f.read_text(encoding="utf-8", errors="ignore")
            if "viewer -->" in raw[:300]:
                continue
            out[str(rel)] = visible_text(raw)
        elif suf in TEXT_EXT and f.name not in ("docs-ops.jsonl", "canvas.json", "_meta.json"):
            out[str(rel)] = [ln.strip() for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    return out


def item_text(store: Store, entry: dict) -> str:
    d = store.item_dir(entry)
    vs = entry.get("versions") or []
    src = d / vs[-1]["dir"] if vs and (d / vs[-1]["dir"]).exists() else d
    return "\n".join("\n".join(lines) for lines in version_text(src).values())[:MAX_TEXT]


def _connect(store: Store):
    store.cache.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(store.cache / "index.sqlite"))
    try:
        db.execute("create virtual table if not exists docs using fts5(key unindexed, title, description, body, tokenize='unicode61 remove_diacritics 2')")
        fts = True
    except sqlite3.OperationalError:
        db.execute("create table if not exists docs(key text primary key, title text, description text, body text)")
        fts = False
    db.execute("create table if not exists sig(key text primary key, sig text)")
    return db, fts


def _sig(entry: dict) -> str:
    vs = entry.get("versions") or []
    return json.dumps([entry.get("updated"), len(vs), entry.get("title"), entry.get("description")], ensure_ascii=False)


def update_index(store: Store, m: dict | None = None) -> int:
    m = m or store.load()
    db, _ = _connect(store)
    known = dict(db.execute("select key, sig from sig"))
    changed = 0
    for key, e in m["items"].items():
        s = _sig(e)
        if known.pop(key, None) == s:
            continue
        db.execute("delete from docs where key = ?", (key,))
        db.execute("insert into docs(key, title, description, body) values (?, ?, ?, ?)",
                   (key, e.get("title") or e["dir"], e.get("description") or "", item_text(store, e)))
        db.execute("insert or replace into sig(key, sig) values (?, ?)", (key, s))
        changed += 1
    for gone in known:
        db.execute("delete from docs where key = ?", (gone,))
        db.execute("delete from sig where key = ?", (gone,))
    db.commit()
    db.close()
    return changed


def _fts_query(q: str) -> str:
    words = re.findall(r"\w+", q, re.U)
    return " ".join('"%s"*' % w for w in words)


def in_scope(entry: dict, scope: str | None) -> bool:
    return scope is None or (entry.get("project") or "") == scope


def search(store: Store, q: str, *, scope: str | None = None, agent: str | None = None,
           kind: str | None = None, limit: int = 20) -> list:
    """Items matching q (all items when q is empty), newest first among equals."""
    from artikeep.gallery import item_type  # avoid an import cycle at module load

    m = store.load()
    update_index(store, m)

    def keep(key):
        e = m["items"].get(key)
        if not e or not in_scope(e, scope):
            return False
        if agent and agent_of(e) != agent:
            return False
        return not kind or item_type(store.item_dir(e), e) == kind

    hits = []
    if q.strip():
        db, fts = _connect(store)
        if fts and _fts_query(q):
            rows = db.execute(
                "select key, snippet(docs, 3, '[', ']', ' … ', 12) from docs where docs match ? order by bm25(docs, 0, 10, 4, 1) limit 500",
                (_fts_query(q),),
            ).fetchall()
        else:
            like = "%" + q.lower() + "%"
            rows = [(k, (b or "")[:160]) for k, t, d, b in db.execute("select key, title, description, body from docs")
                    if like.strip("%") in ((t or "") + " " + (d or "") + " " + (b or "")).lower()]
        db.close()
        hits = [(k, snip) for k, snip in rows if keep(k)]
    else:
        keys = sorted((k for k in m["items"] if keep(k)), key=lambda k: m["items"][k].get("updated") or "", reverse=True)
        hits = [(k, "") for k in keys]
    out = []
    for key, snip in hits[:limit]:
        e = m["items"][key]
        out.append({
            "id": e["dir"], "title": e.get("title") or e["dir"], "agent": agent_of(e),
            "type": item_type(store.item_dir(e), e), "project": e.get("project"),
            "updated": (e.get("updated") or "")[:16], "versions": len(e.get("versions") or []),
            "origin": e.get("url") or e.get("origin") or key, "snippet": re.sub(r"\s+", " ", snip or "").strip(),
        })
    return out
