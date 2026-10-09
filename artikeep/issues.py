"""GitHub issues that link to archived items, found with the gh CLI at most once a day.

Searched in the GitHub repositories of the projects items were made in, for links
to the archive's own remote (".../blob/main/items") and to the hosts items came
from. An item matches an issue when its folder name or origin id appears in it.
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
import time
from pathlib import Path

from artikeep.store import Store

HOST_QUERIES = ('"claude.ai/artifact"', '"claude.ai/code/artifact"', '"chatgpt.com/c/"')


def _remote_repo(path) -> str | None:
    r = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+/[^/.\s]+)", r.stdout)
    return m.group(1) if m else None


def refresh(store: Store, m: dict, force: bool = False) -> bool:
    stamp = store.log / "issues_refresh.stamp"
    if not store.settings.get("issue_links") or not shutil.which("gh"):
        return False
    if not force and stamp.exists() and time.time() - stamp.stat().st_mtime < 86400:
        return False
    repos = {_remote_repo(e["project"]) for e in m["items"].values() if e.get("project") and Path(e["project"]).exists()}
    repos.discard(None)
    own = _remote_repo(store.root)
    queries = (('"%s/blob/main/items"' % own.split("/", 1)[1],) if own else ()) + HOST_QUERIES
    found = {}
    for repo in sorted(repos):
        for q in queries:
            r = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f", "q=repo:%s %s" % (repo, q),
                                "-f", "per_page=100", "-q", ".items[].number"], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                store.note("gallery.log", "issues search %s: %s" % (repo, r.stderr.strip()[:200]))
                continue
            for n in r.stdout.split():
                found.setdefault(repo, set()).add(int(n))
    texts = {}
    for repo, nums in found.items():
        for n in sorted(nums):
            r = subprocess.run(["gh", "api", "repos/%s/issues/%d" % (repo, n), "-q", ".body"], capture_output=True, text=True, timeout=60)
            c = subprocess.run(["gh", "api", "--paginate", "repos/%s/issues/%d/comments" % (repo, n), "-q", ".[].body"],
                               capture_output=True, text=True, timeout=60)
            texts[(repo, n)] = (r.stdout or "") + "\n" + (c.stdout or "")
    for e in m["items"].values():
        keys = [e["dir"], (e.get("url") or "").rstrip("/").rsplit("/", 1)[-1]] + [a.rsplit("/", 1)[-1] for a in e.get("aliases", [])]
        keys = [k for k in keys if k and len(k) > 8]
        hit = {n for (repo, n), t in texts.items() if any(k in t for k in keys)}
        if hit:
            e["issues"] = sorted(set(e.get("issues") or []) | hit)
    stamp.write_text(dt.datetime.now().isoformat(), encoding="utf-8")
    return True
