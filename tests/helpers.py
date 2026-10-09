"""Shared fixtures: a throwaway archive and fake host data."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "bin" / "artikeep"


class TempArchive(unittest.TestCase):
    """Each test gets its own archive folder and scratch folder; ARTIKEEP_HOME points there."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="artikeep-test-")).resolve()
        self.home = self.tmp / "archive"
        self.work = self.tmp / "work"
        self.work.mkdir()
        self._env = os.environ.get("ARTIKEEP_HOME")
        os.environ["ARTIKEEP_HOME"] = str(self.home)
        from artikeep.store import Store
        self.store = Store(self.home).ensure()
        self.store.kick = lambda: None  # no detached workers in tests
        (self.home / "artikeep.json").write_text(json.dumps({"issue_links": False, "thumbnails": "off", "git_push": False, "notify": False}))
        self.store.settings.update({"issue_links": False, "thumbnails": "off", "git_push": False, "notify": False})

    def tearDown(self):
        if self._env is None:
            os.environ.pop("ARTIKEEP_HOME", None)
        else:
            os.environ["ARTIKEEP_HOME"] = self._env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def manifest(self) -> dict:
        return json.loads((self.home / "manifest.json").read_text(encoding="utf-8"))
