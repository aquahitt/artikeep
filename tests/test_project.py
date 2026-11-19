import json
import os
import subprocess
import unittest
from pathlib import Path

from tests.helpers import ENTRY, TempArchive


class ProjectTest(TempArchive):
    def setUp(self):
        super().setUp()
        self.repo = self.work / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.elsewhere = self.work / "downloads"
        self.elsewhere.mkdir()

    def cli(self, *args, cwd):
        return subprocess.run(["/usr/bin/env", "python3", str(ENTRY), *args], cwd=str(cwd), capture_output=True, text=True,
                              env=dict(os.environ, ARTIKEEP_HOME=str(self.home)))

    def projects(self):
        return {Path(e["origin"]).name: e.get("project") for e in self.manifest()["items"].values()}

    def test_add_uses_the_current_repository_for_files_outside_any(self):
        shot = self.write("downloads/shot.png", "PNG")
        r = self.cli("add", str(shot), cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.projects()["shot.png"], str(self.repo.resolve()))

    def test_add_prefers_the_repository_the_file_is_in(self):
        other = self.work / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        note = self.write("other/note.md", "# note")
        self.cli("add", str(note), cwd=self.repo)
        self.assertEqual(self.projects()["note.md"], str(other.resolve()))

    def test_no_repository_means_no_project(self):
        shot = self.write("downloads/a.png", "PNG")
        self.cli("add", str(shot), cwd=self.elsewhere)
        self.assertIsNone(self.projects()["a.png"])

    def test_explicit_project_and_no_project(self):
        a, b = self.write("downloads/a.png", "A"), self.write("downloads/b.png", "B")
        self.cli("add", str(a), "--project", str(self.repo / "."), cwd=self.elsewhere)
        self.cli("add", str(b), "--no-project", cwd=self.repo)
        self.assertEqual(self.projects()["a.png"], str(self.repo.resolve()))
        self.assertIsNone(self.projects()["b.png"])
        bad = self.cli("add", str(a), "--project", str(self.work / "missing"), cwd=self.repo)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("not a folder", bad.stderr)

    def test_import_takes_the_project(self):
        conv = [{"uuid": "c1", "name": "Chat", "chat_messages": [{"sender": "assistant", "created_at": "2026-10-01T10:00:00Z", "content": [
            {"type": "tool_use", "name": "artifacts", "input": {"id": "a1", "command": "create", "type": "text/html", "title": "Page",
                                                                  "content": "<!doctype html><title>Page</title>"}}]}]}]
        export = self.write("conversations.json", json.dumps(conv))
        self.cli("import", "claude-ai", str(export), cwd=self.repo)
        self.cli("import", "claude-ai", str(export), "--project", str(self.repo), cwd=self.elsewhere)
        items = list(self.manifest()["items"].values())
        self.assertEqual([e.get("project") for e in items], [str(self.repo.resolve())])

    def test_gallery_edit_moves_an_item(self):
        e, _ = self.store.save_item("k", {"index.html": b"<title>T</title>"}, agent="import", main="index.html")
        self.store.edit(e["dir"], project=str(self.repo))
        self.assertEqual(self.manifest()["items"]["k"]["project"], str(self.repo.resolve()))
        self.store.edit(e["dir"], project="")
        self.assertNotIn("project", self.manifest()["items"]["k"])
        with self.assertRaises(ValueError):
            self.store.edit(e["dir"], project=str(self.work / "nope"))


if __name__ == "__main__":
    unittest.main()
