"""Collections: named groups of related items (the page, its screenshots, the icon set).

One file, `collections.json` at the archive root, so it is tracked and synced with the rest:
  {"version": 1, "collections": {"Portal splash": ["2026-11-13-zastavka-portala", ...]}}
Items are named by their folder, which never changes. A collection with no items is removed.
An item can be in several collections.
"""
from __future__ import annotations

import json

from artikeep.store import Store

FILE = "collections.json"


def load(store: Store) -> dict:
    """{name: [item folder, ...]}"""
    try:
        data = json.loads((store.root / FILE).read_text(encoding="utf-8"))
        return {n: list(v) for n, v in (data.get("collections") or {}).items() if v}
    except Exception:
        return {}


def _save(store: Store, colls: dict) -> None:
    path = store.root / FILE
    if not colls:
        path.unlink(missing_ok=True)
        return
    path.write_text(json.dumps({"version": 1, "collections": colls}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def clean(name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("a collection needs a name")
    if len(name) > 80:
        raise ValueError("a collection name is at most 80 characters")
    return name


def of_item(colls: dict, folder: str) -> list:
    return sorted(n for n, items in colls.items() if folder in items)


def add(store: Store, name: str, folders: list) -> list:
    """Put items into a collection (made if new). Returns the folders that were added."""
    name = clean(name)
    known = {e["dir"] for e in store.load()["items"].values()}
    missing = [f for f in folders if f not in known]
    if missing:
        raise KeyError(missing[0])
    with store.lock("collections"):
        colls = load(store)
        items = colls.setdefault(name, [])
        added = [f for f in folders if f not in items]
        items.extend(added)
        _save(store, colls)
    return added


def remove(store: Store, name: str, folders: list) -> list:
    with store.lock("collections"):
        colls = load(store)
        if name not in colls:
            raise KeyError(name)
        gone = [f for f in folders if f in colls[name]]
        colls[name] = [f for f in colls[name] if f not in folders]
        if not colls[name]:
            del colls[name]
        _save(store, colls)
    return gone


def delete(store: Store, name: str) -> None:
    """Dissolve a collection; its items stay."""
    with store.lock("collections"):
        colls = load(store)
        if name not in colls:
            raise KeyError(name)
        del colls[name]
        _save(store, colls)


def rename(store: Store, old: str, new: str) -> None:
    new = clean(new)
    with store.lock("collections"):
        colls = load(store)
        if old not in colls:
            raise KeyError(old)
        if new != old and new in colls:
            colls[new] = colls[new] + [f for f in colls[old] if f not in colls[new]]
        else:
            colls[new] = colls[old]
        if new != old:
            del colls[old]
        _save(store, colls)


def forget_item(store: Store, folder: str) -> None:
    """An item left the archive: drop it from every collection."""
    with store.lock("collections"):
        colls = load(store)
        if any(folder in v for v in colls.values()):
            _save(store, {n: [f for f in v if f != folder] for n, v in colls.items() if any(f != folder for f in v)})


def replace_item(store: Store, old: str, new: str) -> None:
    """An item was folded into another: its collections point at the survivor."""
    with store.lock("collections"):
        colls = load(store)
        if not any(old in v for v in colls.values()):
            return
        out = {}
        for n, items in colls.items():
            mapped = []
            for f in items:
                f = new if f == old else f
                if f not in mapped:
                    mapped.append(f)
            out[n] = mapped
        _save(store, out)
