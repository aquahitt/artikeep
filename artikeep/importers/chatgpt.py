"""ChatGPT data export (Settings → Data controls → Export data): canvas documents.

conversations.json holds every conversation as a tree of messages (`mapping`). A
canvas is not a file there: it is a series of tool calls the assistant makes —
`canmore.create_textdoc` with {name, type, content}, then `canmore.update_textdoc`
with regex edits {updates: [{pattern, multiple, replacement}]}. Replaying them in
order rebuilds every state of the document; each state becomes a version.

Checked against the documented message shapes and a synthetic export, not yet a
real one: anything unrecognised is counted and reported instead of guessed.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from artikeep.importers import read_export_json
from artikeep.store import Store

EXT = {"document": ".md", "code/html": ".html", "code/react": ".jsx", "code/javascript": ".js",
       "code/typescript": ".ts", "code/python": ".py", "code/css": ".css", "code/json": ".json"}


def _iso(ts) -> str:
    if not ts:
        return dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return dt.datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds")


def _messages(conv: dict) -> list:
    """Messages of the conversation in time order (all branches: edits are history too)."""
    msgs = [n["message"] for n in (conv.get("mapping") or {}).values() if isinstance(n, dict) and n.get("message")]
    return sorted(msgs, key=lambda m: m.get("create_time") or 0)


def _text(msg: dict) -> str:
    c = msg.get("content") or {}
    if isinstance(c.get("parts"), list):
        return "".join(p if isinstance(p, str) else "" for p in c["parts"])
    return c.get("text") or ""


def _apply(content: str, updates: list) -> str:
    for u in updates or []:
        pat, rep = u.get("pattern", ""), u.get("replacement", "")
        try:
            content = re.sub(pat, lambda _m: rep, content, count=0 if u.get("multiple") else 1, flags=re.S)
        except re.error:
            pass
    return content


def import_export(store: Store, src) -> dict:
    data = read_export_json(src)
    stats = {"conversations": len(data), "docs": 0, "versions": 0, "unparsed_calls": 0}
    for conv in data:
        cid = conv.get("conversation_id") or conv.get("id") or ""
        docs, order, last = {}, [], None  # doc key -> {"name","type","content"}
        for msg in _messages(conv):
            recipient = msg.get("recipient") or ""
            if not recipient.startswith("canmore.") or recipient == "canmore.comment_textdoc":
                continue
            try:
                args = json.loads(_text(msg))
            except Exception:
                stats["unparsed_calls"] += 1
                continue
            when = _iso(msg.get("create_time"))
            if recipient == "canmore.create_textdoc":
                key = "%s:%d" % (cid, len(order))
                docs[key] = {"name": args.get("name") or "canvas", "type": args.get("type") or "document",
                             "content": args.get("content") or ""}
                order.append(key)
                last = key
            elif recipient == "canmore.update_textdoc" and last:
                docs[last]["content"] = _apply(docs[last]["content"], args.get("updates"))
            else:
                stats["unparsed_calls"] += 1
                continue
            d = docs[last]
            ext = EXT.get(d["type"], ".txt")
            rel = "index.html" if ext == ".html" else re.sub(r"[^\w.-]+", "-", d["name"]).strip("-") + ext
            _, vdir = store.save_item(
                "chatgpt:" + last, {rel: d["content"].encode("utf-8")}, agent="chatgpt",
                title=d["name"], main=rel, origin="https://chatgpt.com/c/%s" % cid,
                url="https://chatgpt.com/c/%s" % cid, when=when,
                description=conv.get("title") or None,
            )
            stats["versions"] += 1 if vdir else 0
        stats["docs"] += len(order)
    return stats
