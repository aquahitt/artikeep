"""opencode: deliverables a session made that git does not already keep.

opencode keeps every session in a SQLite database (~/.local/share/opencode/opencode.db):
messages, and per message the parts, among them the tool calls. As for Codex, a file counts
when the agent wrote it (the `write` tool, with its content; `edit` and `patch` name files
that already exist), or when the final answer points at it. The rules for which files are
worth keeping are Codex's: settings["codex_extensions"], not tracked by git, under 20 MB.

The database is opened read-only; a session is read whole, so a late pass sees the same.

Hooks (the plugin `artikeep install` puts in ~/.config/opencode/plugins/ forwards them):
  stop    the session went idle: archive its deliverables.
  check   the plugin started: the same over sessions of the last days.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from artikeep import provenance
from artikeep.adapters import codex
from artikeep.store import Store

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "opencode"
DB = DATA_HOME / "opencode.db"
WRITE_TOOLS = ("write", "edit", "patch", "multiedit")


def _iso(ms) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime((ms or 0) / 1000)) + "Z"


def _connect(db=None):
    path = Path(db or DB)
    if not path.is_file():
        return None
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


class Session:
    """What one session says about files, in the shape codex.candidates reads."""

    def __init__(self, con, sid: str):
        self.session = sid
        self.cwd = None
        self.changed = {}  # abs path -> {"at", "content"}
        self.mentioned = {}  # abs path -> ts
        self.vis_dirs = set()
        self.prompts = []  # (timestamp, ask), in order
        row = con.execute("select directory from session where id = ?", (sid,)).fetchone()
        self.cwd = row["directory"] if row else None
        roles = {r["id"]: json.loads(r["data"]).get("role") for r in
                 con.execute("select id, data from message where session_id = ?", (sid,))}
        last_text = {}
        for r in con.execute("select message_id, time_created, data from part where session_id = ? "
                             "order by time_created, id", (sid,)):
            try:
                part = json.loads(r["data"])
            except Exception:
                continue
            ts = _iso(r["time_created"])
            kind = part.get("type")
            if kind == "text" and not part.get("synthetic"):
                role = roles.get(r["message_id"])
                text = part.get("text") or ""
                if role == "user" and text.strip() and not provenance.is_internal(text):
                    self.prompts.append((ts, provenance.clean(text)))
                elif role == "assistant":
                    last_text[r["message_id"]] = (ts, text)
            elif kind == "tool" and part.get("tool") in WRITE_TOOLS:
                st = part.get("state") or {}
                if st.get("status") != "completed":
                    continue
                inp = st.get("input") or {}
                path = inp.get("filePath") or inp.get("path")
                if not path:
                    continue
                prev = self.changed.get(path, {})
                content = inp.get("content") if part["tool"] == "write" else prev.get("content")
                self.changed[path] = {"at": ts, "content": content if isinstance(content, str) else None}
        for ts, text in last_text.values():
            self._mentions(text, ts)

    _mentions = codex.Rollout._mentions
    request_before = codex.Rollout.request_before


def archive(store: Store, con, sid: str) -> int:
    return codex.archive_session(store, Session(con, sid), agent="opencode")


def cmd_stop(store: Store, payload: dict) -> None:
    store.log_payload("opencode-stop", {k: payload.get(k) for k in ("session_id", "cwd")})
    try:
        con = _connect()
        sid = payload.get("session_id")
        if con is not None and sid and archive(store, con, sid):
            store.kick()
    except Exception:
        store.error("opencode stop")
        from artikeep.notify import notify
        notify(store, "opencode", "artikeep: opencode deliverables not saved, see %s/errors.log" % store.log)


def cmd_check(store: Store, payload: dict, days: int = 3) -> int:
    saved = 0
    try:
        con = _connect()
        if con is None:
            return 0
        cutoff = int((time.time() - days * 86400) * 1000)
        for row in con.execute("select id from session where time_updated >= ? order by time_updated", (cutoff,)):
            try:
                saved += archive(store, con, row["id"])
            except Exception:
                store.error("opencode check %s" % row["id"])
    except Exception:
        store.error("opencode check")
    if saved:
        store.kick()
    return saved


COMMANDS = {"stop": cmd_stop, "check": cmd_check}
