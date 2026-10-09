"""Importers: one-off sources run by hand (`artikeep import ...`)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path


def read_export_json(src: Path, name: str = "conversations.json"):
    """conversations.json from an export: the .zip itself, its unpacked folder, or the file."""
    src = Path(src).expanduser()
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            members = [n for n in z.namelist() if n.rsplit("/", 1)[-1] == name]
            if not members:
                raise SystemExit("%s: no %s inside the archive" % (src, name))
            return json.loads(z.read(sorted(members, key=len)[0]).decode("utf-8"))
    if src.is_dir():
        hits = sorted(src.rglob(name), key=lambda p: len(p.parts))
        if not hits:
            raise SystemExit("%s: no %s in this folder" % (src, name))
        src = hits[0]
    return json.loads(src.read_text(encoding="utf-8"))
