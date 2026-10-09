"""`artikeep add PATH...`: keep any file or page folder, from any tool, by hand."""
from __future__ import annotations

from pathlib import Path

from artikeep.store import Store
from artikeep.util import git_root, local_refs, now_iso, title_of

MAX_BYTES = 50 * 1024 * 1024
SKIP_PARTS = {"node_modules", ".git", "__pycache__"}


def add_path(store: Store, path, title=None, agent="import", label=None, project=None) -> tuple:
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        files = {}
        for f in sorted(p.rglob("*")):
            rel = f.relative_to(p)
            if f.is_file() and not (SKIP_PARTS & set(rel.parts)) and f.stat().st_size <= MAX_BYTES:
                files[str(rel)] = f.read_bytes()
        if not files:
            raise SystemExit("%s: nothing to keep (empty, or every file over 50 MB)" % p)
        main = "index.html" if "index.html" in files else sorted(files)[0]
        title = title or (title_of(p / main, files[main]) if main == "index.html" else p.name)
    elif p.is_file():
        if p.stat().st_size > MAX_BYTES:
            raise SystemExit("%s: over 50 MB" % p)
        data = p.read_bytes()
        main = "index.html" if p.suffix.lower() in (".html", ".htm") else p.name
        files = {main: data}
        if p.suffix.lower() in (".html", ".htm", ".md", ".svg"):
            for ref, blob in local_refs(p, data).items():
                files.setdefault(ref, blob)
        title = title or title_of(p, data)
    else:
        raise SystemExit("%s: no such file or folder" % p)
    return store.save_item(
        "file:" + str(p), files, agent=agent, title=title, main=main, origin=str(p),
        project=project or git_root(p), when=now_iso(), label=label,
    )
