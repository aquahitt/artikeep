"""The archive on disk: items, versions, manifest, locks, error log.

Layout (see FORMAT.md):
    manifest.json            one entry per item, keyed by origin (URL, file path, export id)
    items/<date>-<slug>/     the newest files of an item
        versions/NNN-<time>/ frozen copy of every distinct state
    drafts/                  unpublished pages mirrored from agent scratch folders
    index.html               the gallery
    .hooklog/                errors, payload log, locks (not committed)
    .cache/                  search index (not committed)
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from artikeep import config
from artikeep.util import now_iso, slugify, title_of, write_bytes
from artikeep.viewers import CANVAS_MARKS, DOC_MARKS, REACT_MARKS

AGENTS = ("claude-code", "codex", "chatgpt", "claude-ai", "import", "mcp")
GITIGNORE = [".hooklog/", ".cache/", "*.tmp", ".DS_Store"]
VERSION_SKIP_DIRS = {"versions", "_vendor", "server"}
VERSION_SKIP_FILES = {"index.offline.html", "docs-ops.jsonl", "_thumb.jpg"}
VIEWER_MARKS = CANVAS_MARKS + DOC_MARKS + REACT_MARKS


class Lock:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "w")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else config.home()
        self.manifest_path = self.root / "manifest.json"
        self.log = self.root / ".hooklog"
        self.cache = self.root / ".cache"
        self.items = self.root / "items"
        self.settings = config.settings(self.root)

    # ------------------------------------------------------------ housekeeping

    def ensure(self) -> "Store":
        self.root.mkdir(parents=True, exist_ok=True)
        self.log.mkdir(parents=True, exist_ok=True)
        gi = self.root / ".gitignore"
        have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
        missing = [x for x in GITIGNORE if x not in have]
        if missing:
            gi.write_text("\n".join(have + missing) + "\n", encoding="utf-8")
        return self

    def lock(self, name: str) -> Lock:
        return Lock(self.log / (name + ".lock"))

    def error(self, where: str) -> None:
        try:
            self.log.mkdir(parents=True, exist_ok=True)
            with open(self.log / "errors.log", "a", encoding="utf-8") as f:
                f.write("--- %s %s\n%s\n" % (now_iso(), where, traceback.format_exc()))
        except Exception:
            pass

    def note(self, logname: str, msg: str) -> None:
        try:
            with open(self.log / logname, "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (now_iso(), msg))
        except Exception:
            pass

    def log_payload(self, kind: str, payload) -> None:
        """Raw hook input, for debugging format changes of the host tools."""
        try:
            slim = json.loads(json.dumps(payload, default=str))
            ti = slim.get("tool_input") if isinstance(slim, dict) else None
            if isinstance(ti, dict) and isinstance(ti.get("content"), str) and len(ti["content"]) > 500:
                ti["content"] = ti["content"][:500] + "…"
            with open(self.log / "payloads.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": kind, "at": now_iso(), "payload": slim}, ensure_ascii=False)[:200000] + "\n")
        except Exception:
            pass

    # ------------------------------------------------------------ manifest

    def load(self) -> dict:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                self.error("load manifest")
                shutil.copy(self.manifest_path, self.log / ("manifest.broken.%d.json" % time.time()))
        return {"version": 1, "items": {}}

    def save(self, m: dict) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def item_dir(self, entry: dict) -> Path:
        return self.items / entry["dir"]

    def entry_for(self, m: dict, key: str, title: str | None, when: str | None = None) -> dict:
        """The manifest entry for key, created with a fresh dated folder name if new."""
        entry = m["items"].get(key)
        if entry:
            return entry
        when = when or now_iso()
        name = "%s-%s" % (when[:10], slugify(title or key.rsplit("/", 1)[-1]))
        taken = {e["dir"] for e in m["items"].values()}
        final, n = name, 2
        while final in taken or (self.items / final).exists():
            final, n = "%s-%d" % (name, n), n + 1
        entry = {"dir": final, "created": when, "publishes": []}
        m["items"][key] = entry
        return entry

    # ------------------------------------------------------------ versions

    @staticmethod
    def version_files(item: Path) -> dict:
        out = {}
        for f in sorted(item.rglob("*")):
            rel = f.relative_to(item)
            if not f.is_file() or rel.parts[0] in VERSION_SKIP_DIRS or rel.name in VERSION_SKIP_FILES:
                continue
            if rel.name == "index.html":
                head = f.read_text(encoding="utf-8", errors="ignore")[:300]
                if any(mark in head for mark in VIEWER_MARKS):
                    continue  # generated viewers are rebuilt per version
            out[str(rel)] = f.read_bytes()
        return out

    def snapshot(self, item: Path, entry: dict, at: str, label: str | None = None) -> str | None:
        """Freeze what the item holds now as the next version; skip if nothing changed."""
        files = self.version_files(item)
        if not files:
            return None
        versions = entry.setdefault("versions", [])
        before = {}
        if versions:
            prev = item / versions[-1]["dir"]
            before = self.version_files(prev) if prev.exists() else {}
            if before == files:
                return None
        n = len(versions) + 1
        vdir = "versions/%03d-%s" % (n, at[:16].replace(":", "").replace("-", ""))
        for rel, data in files.items():
            dst = item / vdir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        changed = sorted(k for k in files if before.get(k) != files[k]) + sorted("-" + k for k in before if k not in files)
        versions.append({"n": n, "at": at[:19], "label": label, "dir": vdir, "changed": changed})
        return vdir

    # ------------------------------------------------------------ generic save

    def save_item(self, key: str, files: dict, *, agent: str, title: str | None = None, main: str | None = None,
                  project: str | None = None, origin: str | None = None, url: str | None = None,
                  when: str | None = None, label: str | None = None, description: str | None = None,
                  session: str | None = None, replace: bool = True, extra: dict | None = None):
        """Store files {relative path: bytes} as the newest state of item `key`.

        Used by every source except the Claude Code Artifact hook, which keeps its own
        richer bookkeeping. Returns (entry, new version dir or None).
        """
        when = when or now_iso()
        with self.lock("manifest"):
            m = self.load()
            if not title and main and main in files:
                title = title_of(main, files[main])
            entry = self.entry_for(m, key, title, when)
            item = self.item_dir(entry)
            if replace and item.exists():
                for f in item.iterdir():
                    if f.name in VERSION_SKIP_DIRS or f.name in VERSION_SKIP_FILES:
                        continue
                    shutil.rmtree(f) if f.is_dir() else f.unlink()
            for rel, data in files.items():
                write_bytes(item / rel, data)
            entry["agent"] = agent
            for k, v in (("title", title), ("main", main), ("project", project), ("origin", origin),
                         ("url", url), ("description", description)):
                if v:
                    entry[k] = v
            if extra:
                entry.update(extra)
            if when >= entry.get("updated", ""):
                entry["updated"] = when
            entry.setdefault("publishes", []).append({"at": when, "session": session, "source": origin, "copied": len(files)})
            vdir = self.snapshot(item, entry, when, label)
            if vdir is None:
                entry["publishes"].pop()  # same content again: not a new publish
            self.save(m)
        return entry, vdir

    # ------------------------------------------------------------ background work

    def kick(self) -> None:
        """Start the background pass (viewers, gallery, index, git) detached from the hook."""
        try:
            pkg_parent = str(Path(__file__).resolve().parent.parent)
            env = dict(os.environ, ARTIKEEP_HOME=str(self.root))
            env["PYTHONPATH"] = pkg_parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            subprocess.Popen(
                [sys.executable, "-m", "artikeep", "worker"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=open(self.log / "worker.log", "a"), start_new_session=True, env=env,
            )
        except Exception:
            self.error("kick worker")


def agent_of(entry: dict) -> str:
    """Entries written before agents were recorded all came from Claude Code."""
    return entry.get("agent") or "claude-code"


def date_of(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).date().isoformat()
