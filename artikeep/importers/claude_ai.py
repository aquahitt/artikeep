"""claude.ai data export (Settings → Privacy → Export data): artifacts made in chats.

Each conversation lists chat_messages; an artifact is a tool call named "artifacts"
with input {id, type, title, command, content | old_str/new_str}. Older exports carry
artifacts inline in the text as <antArtifact identifier=… type=… title=…>…</antArtifact>.
Every create/rewrite/update becomes a version of the artifact.

Checked against the documented shapes and a synthetic export, not yet a real one:
anything unrecognised is counted and reported instead of guessed.
"""
from __future__ import annotations

import html
import re

from artikeep.importers import read_export_json
from artikeep.store import Store

EXT = {"text/html": ".html", "application/vnd.ant.react": ".jsx", "text/markdown": ".md",
       "image/svg+xml": ".svg", "application/vnd.ant.mermaid": ".mmd", "text/plain": ".txt"}
LANG_EXT = {"python": ".py", "javascript": ".js", "typescript": ".ts", "html": ".html", "css": ".css",
            "json": ".json", "bash": ".sh", "sql": ".sql", "java": ".java", "go": ".go", "rust": ".rs"}
INLINE_RE = re.compile(r"<antArtifact\b([^>]*)>(.*?)</antArtifact>", re.S)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _ext(kind: str, language: str = "") -> str:
    if kind == "application/vnd.ant.code":
        return LANG_EXT.get((language or "").lower(), ".txt")
    return EXT.get(kind, ".txt")


def _calls(msg: dict):
    """(input dict) for each artifact operation in a message, in order."""
    for c in msg.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "artifacts":
            yield c.get("input") or {}
        elif isinstance(c, dict) and c.get("type") == "text":
            for attrs, body in INLINE_RE.findall(c.get("text") or ""):
                a = dict(ATTR_RE.findall(attrs))
                yield {"id": a.get("identifier"), "type": a.get("type"), "title": html.unescape(a.get("title", "")),
                       "language": a.get("language"), "command": "create", "content": body.strip("\n")}
    if not msg.get("content") and msg.get("text"):
        for attrs, body in INLINE_RE.findall(msg["text"]):
            a = dict(ATTR_RE.findall(attrs))
            yield {"id": a.get("identifier"), "type": a.get("type"), "title": html.unescape(a.get("title", "")),
                   "language": a.get("language"), "command": "create", "content": body.strip("\n")}


def import_export(store: Store, src) -> dict:
    data = read_export_json(src)
    stats = {"conversations": len(data), "docs": 0, "versions": 0, "unparsed_calls": 0}
    for conv in data:
        cid = conv.get("uuid") or ""
        arts = {}
        for msg in conv.get("chat_messages") or []:
            for inp in _calls(msg):
                aid, cmd = inp.get("id"), inp.get("command") or "create"
                if not aid:
                    stats["unparsed_calls"] += 1
                    continue
                a = arts.setdefault(aid, {"type": inp.get("type") or "text/plain", "title": inp.get("title") or aid,
                                          "language": inp.get("language") or "", "content": ""})
                for k in ("type", "title", "language"):
                    if inp.get(k):
                        a[k] = inp[k]
                if cmd in ("create", "rewrite"):
                    a["content"] = inp.get("content") or ""
                elif cmd == "update" and inp.get("old_str") is not None:
                    a["content"] = a["content"].replace(inp["old_str"], inp.get("new_str") or "", 1)
                else:
                    stats["unparsed_calls"] += 1
                    continue
                ext = _ext(a["type"], a["language"])
                rel = "index.html" if ext == ".html" else re.sub(r"[^\w.-]+", "-", aid).strip("-") + ext
                _, vdir = store.save_item(
                    "claude-ai:%s:%s" % (cid, aid), {rel: a["content"].encode("utf-8")}, agent="claude-ai",
                    title=a["title"], main=rel, origin="https://claude.ai/chat/%s" % cid,
                    url="https://claude.ai/chat/%s" % cid, when=msg.get("created_at") or conv.get("updated_at"),
                    description=conv.get("name") or None,
                )
                stats["versions"] += 1 if vdir else 0
        stats["docs"] += len(arts)
    return stats
