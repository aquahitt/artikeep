"""`artikeep merge`: fold copies of the same work into one item.

Before 0.5.1 a republish under another Claude account made a second item. This joins
such copies: every version of every item, ordered by time and renumbered, the files of
the newest version as the current files, the earlier links in `former_urls`. Marks,
requests, stars and collections come along. Nothing is lost that git did not already
keep: the folders that disappear are still in the archive's history.

`find` suggests which items look like copies: the same agent and session and the same
source file (or the same canvas type and title).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from artikeep import collections
from artikeep.store import VERSION_SKIP_DIRS, VERSION_SKIP_FILES, Store


class MergeError(Exception):
    pass


def _stamp(at: str) -> str:
    return at[:16].replace(":", "").replace("-", "")


def find(store: Store) -> list:
    """Groups of item folders that look like copies of one work: [[dir, ...], ...]."""
    m = store.load()
    parent = {}

    def root(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    seen = {}
    for key, e in m["items"].items():
        if e.get("deleted"):
            continue
        agent = e.get("agent", "claude-code")
        for p in e.get("publishes", []):
            if p.get("session") and p.get("source") and not p.get("asset"):
                k = (agent, p["session"], p["source"])
                if k in seen:
                    parent[root(e["dir"])] = root(seen[k])
                seen.setdefault(k, e["dir"])
        if e.get("type_url") and e.get("title"):
            for s in {p.get("session") for p in e.get("publishes", []) if p.get("session")}:
                k = (agent, s, e["type_url"], e["title"].strip())
                if k in seen:
                    parent[root(e["dir"])] = root(seen[k])
                seen.setdefault(k, e["dir"])
    groups = {}
    for d in list(parent):
        groups.setdefault(root(d), set()).add(d)
    return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: g[0])


def plan(store: Store, folders: list) -> dict:
    """What merging would do, without doing it."""
    if len(set(folders)) < 2:
        raise MergeError("name at least two different items")
    m = store.load()
    by_dir = {e["dir"]: (k, e) for k, e in m["items"].items()}
    missing = [f for f in folders if f not in by_dir]
    if missing:
        raise MergeError("no item %s" % missing[0])
    items = [by_dir[f] for f in dict.fromkeys(folders)]
    if any(e.get("deleted") for _, e in items):
        raise MergeError("an item is deleted")
    target_dir = items[0][1]["dir"]
    rows = []
    for order, (key, e) in enumerate(items):
        for v in e.get("versions") or []:
            rows.append((v.get("at") or "", order, v["n"], e["dir"], v))
    if not rows:
        raise MergeError("these items have no versions to merge")
    rows.sort(key=lambda r: r[:3])
    newest_key, newest = max(items, key=lambda it: it[1].get("updated") or "")
    return {"target": target_dir, "key": newest_key, "versions": len(rows), "rows": rows, "items": items,
            "sources": [e["dir"] for _, e in items[1:]], "newest_dir": newest["dir"]}


def run(store: Store, folders: list) -> dict:
    p = plan(store, folders)
    with store.lock("manifest"):
        m = store.load()
        # re-read under the lock: the plan was made on a possibly older manifest
        p = plan(store, folders)
        items = p["items"]
        target = items[0][1]
        troot = store.item_dir(target)
        stage = store.cache / ("merge-" + target["dir"])
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        # 1. every version folder to a staging name, so renumbering cannot collide
        moved = []
        for i, (at, order, n, d, v) in enumerate(p["rows"], 1):
            src = store.items / d / v["dir"]
            dst = stage / ("%03d" % i)
            if src.exists():
                shutil.move(str(src), str(dst))
            else:
                dst.mkdir()
            moved.append((i, at, v, dst))
        # 2. the target's own versions folder is empty now; put them back under final names
        (troot / "versions").mkdir(parents=True, exist_ok=True)
        versions, before = [], {}
        for i, at, v, dst in moved:
            name = "versions/%03d-%s" % (i, _stamp(at))
            shutil.move(str(dst), str(troot / name))
            files = store.version_files(troot / name)
            changed = sorted(k for k in files if before.get(k) != files[k]) + sorted("-" + k for k in before if k not in files)
            nv = {k: x for k, x in v.items() if k not in ("diff", "dir", "n", "changed")}
            nv.update({"n": i, "dir": name, "changed": changed})
            versions.append(nv)
            before = files
        # 3. current files: the newest version's
        for f in list(troot.iterdir()):
            if f.name in VERSION_SKIP_DIRS or (f.name in VERSION_SKIP_FILES and f.name != "_thumb.jpg"):
                continue
            shutil.rmtree(f) if f.is_dir() else f.unlink()
        (troot / "_thumb.jpg").unlink(missing_ok=True)
        last = troot / versions[-1]["dir"]
        for f in sorted(last.rglob("*")):
            rel = f.relative_to(last)
            if f.is_file() and rel.name not in VERSION_SKIP_FILES:
                dst = troot / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
        # 4. the entry
        merged = dict(target)
        merged["versions"] = versions
        merged["publishes"] = sorted([x for _, e in items for x in e.get("publishes", [])], key=lambda x: x.get("at") or "")
        merged.pop("diff_first_last", None)
        newest = max(items, key=lambda it: it[1].get("updated") or "")[1]
        merged["updated"] = newest.get("updated") or merged.get("updated")
        merged["created"] = min((e.get("created") or "" for _, e in items if e.get("created")), default=merged.get("created"))
        keys = [k for k, _ in items]
        former = []
        for k, e in items:
            former += [u for u in e.get("former_urls", []) if u not in former]
        former += [k for k in keys if k != p["key"] and k not in former and k.startswith("http")]
        merged["former_urls"] = [u for u in former if u != p["key"]]
        if not merged["former_urls"]:
            merged.pop("former_urls")
        if p["key"].startswith("http"):
            merged["url"] = p["key"]
        if any(e.get("star") for _, e in items):
            merged["star"] = True
        for _, e in items:
            for k2 in ("title", "description", "type_url", "layout", "project"):
                if e is newest and e.get(k2):
                    merged[k2] = e[k2]
        for k in keys:
            del m["items"][k]
        m["items"][p["key"]] = merged
        store.save(m)
        # 5. the folders of the folded items are empty of versions; drop them, and point collections at the target
        for _, e in items[1:]:
            shutil.rmtree(store.items / e["dir"], ignore_errors=True)
            collections.replace_item(store, e["dir"], target["dir"])
        shutil.rmtree(stage, ignore_errors=True)
    return {"target": target["dir"], "versions": len(versions), "folded": p["sources"], "key": p["key"]}
