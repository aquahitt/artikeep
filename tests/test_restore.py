import json
import subprocess
import unittest
from pathlib import Path

from tests.helpers import ENTRY, TempArchive

OLD = "https://claude.ai/code/artifact/old-1"
NEW = "https://claude.ai/code/artifact/new-2"


class RestoreTest(TempArchive):
    def publish(self, path, url, **extra):
        from artikeep.adapters import claude_code
        payload = {"tool_name": "Artifact", "cwd": str(self.work), "session_id": "s1", "tool_use_id": "t-%s-%s" % (url[-3:], path.name),
                   "tool_input": dict({"file_path": str(path)}, **extra), "tool_response": "Published: " + url}
        return claude_code.handle_artifact(self.store, payload)

    def made_page(self):
        page = self.write("page.html", "<!doctype html><title>Plan</title><p>v1</p>")
        self.publish(page, OLD)
        page.write_text("<!doctype html><title>Plan</title><p>v2</p>")
        self.publish(page, OLD)
        return self.manifest()["items"][OLD]

    def test_restore_copies_a_version_and_marks_it(self):
        e = self.made_page()
        key, entry = self.store.find(self.store.load(), e["dir"])
        info = self.store.restore_files(key, entry, 1)
        folder = Path(info["folder"])
        self.assertIn(b"v1", (folder / "index.html").read_bytes())
        self.assertEqual(info["version"], 1)
        self.assertIn("file_path=%s" % (folder / "index.html"), info["publish"])
        self.assertEqual(json.loads((folder / ".artikeep-restore.json").read_text())["key"], OLD)
        newest = self.store.restore_files(key, entry)
        self.assertEqual(newest["version"], 2)
        with self.assertRaises(ValueError):
            self.store.restore_files(key, entry, 9)

    def test_destination_must_be_new_or_empty(self):
        e = self.made_page()
        key, entry = self.store.find(self.store.load(), e["dir"])
        busy = self.work / "busy"
        busy.mkdir()
        (busy / "mine.txt").write_text("keep")
        with self.assertRaises(ValueError):
            self.store.restore_files(key, entry, None, busy)
        self.assertEqual((busy / "mine.txt").read_text(), "keep")
        info = self.store.restore_files(key, entry, None, self.work / "fresh")
        self.assertTrue((Path(info["folder"]) / "index.html").exists())

    def test_publishing_restored_files_continues_the_item(self):
        e = self.made_page()
        key, entry = self.store.find(self.store.load(), e["dir"])
        info = self.store.restore_files(key, entry, 1, self.work / "again")
        self.assertEqual(self.publish(Path(info["folder"]) / "index.html", NEW), "ok")
        items = self.manifest()["items"]
        self.assertEqual(list(items), [NEW])  # one item, no duplicate
        e2 = items[NEW]
        self.assertEqual((e2["dir"], e2["url"], e2["former_urls"]), (e["dir"], NEW, [OLD]))
        self.assertEqual(e2["versions"][-1]["label"], "republished from v1")
        self.assertEqual(len(e2["versions"]), 3)
        self.assertEqual(self.publish(Path(info["folder"]) / "index.html", NEW), "ok")  # later calls: plain publishes
        self.assertEqual(list(self.manifest()["items"]), [NEW])

    def test_other_files_are_not_linked(self):
        self.made_page()
        other = self.write("other/page.html", "<!doctype html><title>Other</title>")
        self.publish(other, NEW)
        self.assertEqual(sorted(self.manifest()["items"]), sorted([OLD, NEW]))

    def test_canvas_keeps_its_tree_and_says_to_create_from_the_type(self):
        root = self.work / "cv"
        self.write("cv/project/canvas.json", '{"pages": [], "boards": {}}')
        self.write("cv/project/Main.dc.html", "<p>main</p>")
        self.publish(root / "project/canvas.json", OLD, root=str(root), type_url="https://claude.ai/artifact/type-design",
                     files={"project/Main.dc.html": "project/Main.dc.html"})
        key, entry = self.store.find(self.store.load(), self.manifest()["items"][OLD]["dir"])
        info = self.store.restore_files(key, entry, None, self.work / "cvback")
        back = Path(info["folder"])
        self.assertEqual(sorted(info["files"]), ["project/Main.dc.html", "project/canvas.json"])  # no generated viewer
        self.assertTrue((back / "project" / "Main.dc.html").exists())
        self.assertEqual(info["type_url"], "https://claude.ai/artifact/type-design")
        self.assertIn("root=%s" % back, info["publish"])
        self.assertIn("canvas.json", info["publish"])

    def test_cli_and_mcp(self):
        e = self.made_page()
        r = subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "restore", e["dir"], "--version", "1", "--to", str(self.work / "cli")],
                           capture_output=True, text=True, env={"ARTIKEEP_HOME": str(self.home), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.work / "cli" / "index.html").exists())
        bad = subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "restore", "nope"], capture_output=True, text=True,
                             env={"ARTIKEEP_HOME": str(self.home), "PATH": "/usr/bin:/bin"})
        self.assertEqual(bad.returncode, 1)
        from artikeep import mcp_server
        srv = mcp_server.Server(self.store, scope="all", allow_save=False)
        self.assertIn("restore_artifact", [t["name"] for t in srv.tools()])
        out = srv.call("restore_artifact", {"id": OLD, "to": str(self.work / "mcp")})  # the old link finds it too
        self.assertIn("archived content", out)
        self.assertTrue((self.work / "mcp" / "index.html").exists())
        scoped = mcp_server.Server(self.store, scope="/elsewhere", allow_save=False)
        with self.assertRaises(ValueError):
            scoped.call("restore_artifact", {"id": e["dir"]})


if __name__ == "__main__":
    unittest.main()
