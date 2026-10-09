"""Background pass: viewers, offline copies, search index, gallery, git commit + push.

Hooks only copy files and start this detached, so a tool call never waits on the
network. One worker runs at a time; a late arrival marks the archive dirty and the
running one loops until nothing is left, so a burst of saves lands in one commit.
"""
from __future__ import annotations

import fcntl
import json
import subprocess
import time

from artikeep import gallery, issues, search
from artikeep.store import Store
from artikeep.util import now_iso
from artikeep.viewers import make_canvas_viewer, make_doc_viewer, make_offline


def run(store: Store, push: bool = True, wait: bool = False) -> None:
    store.ensure()
    dirty = store.log / "dirty"
    dirty.touch()
    lock = open(store.log / "worker.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        return
    try:
        while dirty.exists():
            time.sleep(0 if wait else 1)
            dirty.unlink()
            one_pass(store, push)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def one_pass(store: Store, push: bool) -> None:
    try:
        m = store.load()
        by_dir = {e["dir"]: e for e in m["items"].values()}
        for item in sorted(store.items.iterdir()) if store.items.exists() else []:
            if not item.is_dir():
                continue
            entry = by_dir.get(item.name, {})
            try:
                make_doc_viewer(item, entry)
                make_canvas_viewer(item)
                for vd in sorted((item / "versions").iterdir()) if (item / "versions").exists() else []:
                    make_canvas_viewer(vd)
                    make_doc_viewer(vd, entry)
                make_offline(item)
            except Exception:
                store.error("viewers %s" % item.name)
        with store.lock("manifest"):
            m = store.load()
            if gallery.ensure_diffs(store, m):
                store.save(m)
        try:
            gallery.refresh_thumbs(store, m)
        except Exception:
            store.error("thumbs")
        try:
            snapshot = json.loads(json.dumps(m))
            if issues.refresh(store, snapshot):
                with store.lock("manifest"):
                    m = store.load()
                    for k, e in snapshot["items"].items():
                        if k in m["items"] and e.get("issues"):
                            m["items"][k]["issues"] = e["issues"]
                    store.save(m)
        except Exception:
            store.error("issue links")
        try:
            search.update_index(store)
        except Exception:
            store.error("search index")
        gallery.build(store, store.load())
    except Exception:
        store.error("worker build")
    sync(store, push)


def git(store: Store, *args, check: bool = True):
    return subprocess.run(["git", "-C", str(store.root)] + list(args), capture_output=True, text=True, check=check)


def sync(store: Store, push: bool) -> None:
    try:
        if not (store.root / ".git").exists():
            return
        git(store, "add", "-A")
        if git(store, "diff", "--cached", "--quiet", check=False).returncode != 0:
            git(store, "commit", "-q", "-m", "archive: %s" % now_iso())
        if push and store.settings.get("git_push") and git(store, "remote", check=False).stdout.strip():
            branch = git(store, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip() or "main"
            # Another machine may have pushed: replay local commits on top, then push.
            r = git(store, "pull", "--rebase", "-q", "origin", branch, check=False)
            if r.returncode != 0:
                git(store, "rebase", "--abort", check=False)
                store.note("push.log", "pull --rebase failed, local commits kept: %s" % r.stderr.strip())
            r = git(store, "push", "-q", "origin", "HEAD", check=False)
            if r.returncode != 0:
                store.note("push.log", r.stderr.strip())
    except Exception:
        store.error("worker git")
