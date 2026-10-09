"""Codex: deliverables a session made that git does not already keep.

Codex has no hosted artifacts: what it makes for you lands on disk. The risk is a
report or page written to a temp folder, or left untracked, then lost. A rollout
(the session transcript, ~/.codex/sessions/**/rollout-*.jsonl) names them in
three ways, all used here:
  * FileChange items: files the agent added or edited (content of added files too);
  * final answers: absolute paths the agent pointed you to;
  * the session's visualizations folder (~/.codex/visualizations/<date>/<session>/).
A file counts when its extension is in settings["codex_extensions"] (any file in the
visualizations folder counts), it is not tracked by git, and it is under 20 MB.

Hooks:
  stop    Stop: archive deliverables of this session (transcript_path from the hook).
  check   SessionStart: the same over sessions of the last days, for missed turns.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from artikeep.store import Store
from artikeep.util import git_tracked, local_refs, now_iso, project_root, title_of

CODEX_HOME = Path.home() / ".codex"
SESSIONS = CODEX_HOME / "sessions"
MAX_BYTES = 20 * 1024 * 1024
PATH_RE = re.compile(r"(?:file://)?(/(?:Users|home|private|tmp|var)/[^\s`'\"()<>\[\]]+)")
SKIP_PARTS = {"node_modules", ".git", "__pycache__", ".venv", "site-packages"}
INTERESTING = ('"FileChange"', '"final_answer"', '"task_complete"', '"session_meta"', '"turn_context"')


class Rollout:
    """What one session transcript says about files."""

    def __init__(self, path: Path):
        self.path = path
        self.session = None
        self.cwd = None
        self.changed = {}  # abs path -> {"at": ts, "content": str|None}
        self.mentioned = {}  # abs path -> ts
        self.vis_dirs = set()
        self._parse()

    def _parse(self):
        with open(self.path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not any(k in line for k in INTERESTING):
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                ts = o.get("timestamp") or ""
                p = o.get("payload") or {}
                if not isinstance(p, dict):
                    continue
                t = o.get("type")
                if t == "session_meta":
                    self.session = p.get("session_id") or p.get("id") or self.session
                    self.cwd = p.get("cwd") or self.cwd
                elif t == "turn_context":
                    self.cwd = p.get("cwd") or self.cwd
                    for r in p.get("workspace_roots") or []:
                        if "/.codex/visualizations/" in r:
                            self.vis_dirs.add(Path(r))
                elif p.get("type") == "task_complete":
                    self._mentions(p.get("last_agent_message") or "", ts)
                item = p.get("item") if isinstance(p.get("item"), dict) else None
                if not item:
                    continue
                if item.get("type") == "FileChange":
                    for path, ch in (item.get("changes") or {}).items():
                        if not isinstance(ch, dict) or ch.get("type") == "delete":
                            continue
                        prev = self.changed.get(path, {})
                        content = ch.get("content") if ch.get("type") == "add" else prev.get("content")
                        self.changed[path] = {"at": ts, "content": content}
                elif item.get("type") == "AgentMessage" and item.get("phase") == "final_answer":
                    for c in item.get("content") or []:
                        if isinstance(c, dict):
                            self._mentions(c.get("text") or "", ts)

    def _mentions(self, text: str, ts: str):
        for m in PATH_RE.findall(text):
            path = m.rstrip(".,;:!?")
            path = re.sub(r":\d+(?::\d+)?$", "", path)  # file.md:12 -> file.md
            self.mentioned.setdefault(path, ts)


def candidates(r: Rollout, exts) -> dict:
    """{abs path: (timestamp, bytes)} worth archiving from this rollout."""
    out = {}
    exts = {e.lower() for e in exts}

    def consider(path: str, ts: str, content=None, any_ext=False):
        p = Path(path)
        if SKIP_PARTS & set(p.parts):
            return
        if not any_ext and p.suffix.lower() not in exts:
            return
        data = None
        if p.is_file():
            if p.stat().st_size > MAX_BYTES or git_tracked(p):
                return
            data = p.read_bytes()
        elif content is not None:
            data = content.encode("utf-8")  # the file is gone, the transcript kept it
        if data:
            out[str(p)] = (ts, data)

    for path, ch in r.changed.items():
        consider(path, ch["at"], ch.get("content"))
    for path, ts in r.mentioned.items():
        if path not in out:
            consider(path, ts)
    for d in r.vis_dirs:
        if d.is_dir():
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))
                    consider(str(f), ts, any_ext=True)
    return out


def archive_rollout(store: Store, path: Path) -> int:
    r = Rollout(path)
    found = candidates(r, store.settings.get("codex_extensions") or [])
    if not found:
        return 0
    m = store.load()
    project = project_root(r.cwd) if r.cwd else None
    saved = 0
    for src, (ts, data) in sorted(found.items()):
        if str(store.root) in src:
            continue
        key = "codex:" + src
        p = Path(src)
        rel = "index.html" if p.suffix.lower() in (".html", ".htm") else p.name
        files = {rel: data}
        if p.suffix.lower() in (".html", ".htm", ".md", ".svg"):
            for ref, blob in local_refs(p, data).items():
                files.setdefault(ref, blob)  # images and styles the document shows
        h = hashlib.sha256()
        for name in sorted(files):
            h.update(name.encode() + b"\0" + files[name])
        digest = h.hexdigest()
        if (m["items"].get(key) or {}).get("sha256") == digest:
            continue
        _, vdir = store.save_item(
            key, files, agent="codex", title=title_of(p, data), main=rel, project=project,
            origin=src, when=ts or now_iso(), session=r.session, extra={"sha256": digest},
        )
        saved += 1 if vdir else 0
    return saved


def find_rollout(payload: dict):
    tp = payload.get("transcript_path")
    if tp and Path(tp).is_file():
        return Path(tp)
    sid = payload.get("session_id")
    if sid and SESSIONS.exists():
        hits = sorted(SESSIONS.rglob("*%s*.jsonl" % sid))
        if hits:
            return hits[-1]
    return None


def cmd_stop(store: Store, payload: dict) -> None:
    store.log_payload("codex-stop", {k: payload.get(k) for k in ("session_id", "transcript_path", "cwd", "turn_id")})
    try:
        path = find_rollout(payload)
        if path and archive_rollout(store, path):
            store.kick()
    except Exception:
        store.error("codex stop")
        from artikeep.notify import notify
        notify(store, "codex", "artikeep: Codex deliverables not saved, see %s/errors.log" % store.log)
    print("{}")  # Codex expects JSON on stdout from a Stop hook


def cmd_check(store: Store, payload: dict, days: int = 3) -> int:
    cutoff = time.time() - days * 86400
    saved = 0
    for f in sorted(SESSIONS.rglob("*.jsonl")) if SESSIONS.exists() else []:
        try:
            if f.stat().st_mtime >= cutoff:
                saved += archive_rollout(store, f)
        except Exception:
            store.error("codex check %s" % f)
    if saved:
        store.kick()
    return saved


COMMANDS = {"stop": cmd_stop, "check": cmd_check}
