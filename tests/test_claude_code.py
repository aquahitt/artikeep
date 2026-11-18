import base64
import json
import unittest

from tests.helpers import TempArchive


class ClaudeCodeTest(TempArchive):
    def publish(self, path, url="https://claude.ai/code/artifact/abc-123", **extra):
        from artikeep.adapters import claude_code
        payload = {"tool_name": "Artifact", "cwd": str(self.work), "session_id": "s1", "tool_use_id": "t%d" % len(extra),
                   "tool_input": dict({"file_path": str(path)}, **extra), "tool_response": "Published: %s" % url}
        return claude_code.handle_artifact(self.store, payload)

    def test_publish_copies_page_and_versions(self):
        page = self.write("page.html", "<!doctype html><title>Plan</title><p>v1</p>")
        self.assertEqual(self.publish(page), "ok")
        page.write_text("<!doctype html><title>Plan</title><p>v2</p>")
        self.assertEqual(self.publish(page, label="second"), "ok")
        m = self.manifest()["items"]["https://claude.ai/code/artifact/abc-123"]
        self.assertEqual(m["agent"], "claude-code")
        self.assertEqual(m["title"], "Plan")
        self.assertEqual(len(m["versions"]), 2)
        self.assertIn(b"v2", (self.home / "items" / m["dir"] / "index.html").read_bytes())

    def call(self, n, url="https://claude.ai/artifact/canvas1", **ti):
        from artikeep.adapters import claude_code
        payload = {"tool_name": "Artifact", "cwd": str(self.work), "session_id": "s1", "tool_use_id": "c%d" % n,
                   "timestamp": "2026-11-17T22:%02d:00+03:00" % n, "tool_input": dict(ti, url=url) if url else ti,
                   "tool_response": "Published: https://claude.ai/artifact/canvas1"}
        return claude_code.handle_artifact(self.store, payload)

    def canvas(self, boards, pages=1):
        return json.dumps({"title": "Widgets", "pages": [{"id": "p%d" % i, "name": "P%d" % i} for i in range(pages)],
                           "boards": {b: {"x": i * 400, "y": 0, "w": 360, "h": 640, "page": "p0"} for i, b in enumerate(boards)}})

    def test_design_canvas_lands_in_one_tree(self):
        # the call shapes of issue #6: create from the type, then the index + a board, then a board per call
        root = self.work / "tgw"
        self.write("tgw/project/canvas.json", self.canvas(["Main.dc.html", "A_Card.dc.html"]))
        self.write("tgw/project/Main.dc.html", "<p>main</p>")
        self.write("tgw/project/A_Card.dc.html", "<p>card</p>")
        self.call(0, url=None, type_url="https://claude.ai/artifact/type-design", title="Widgets")
        self.call(1, root=str(root), file_path=str(root / "project/canvas.json"),
                  files={"project/Main.dc.html": "project/Main.dc.html"})
        self.call(2, root=str(root), file_path=str(root / "project/A_Card.dc.html"))
        e = self.manifest()["items"]["https://claude.ai/artifact/canvas1"]
        d = self.home / "items" / e["dir"]
        self.assertFalse((d / "data").exists())
        for f in ("canvas.json", "Main.dc.html", "A_Card.dc.html"):
            self.assertTrue((d / "project" / f).exists(), f)
        self.assertEqual(e["layout"], 2)
        self.assertEqual(e["versions"][-1]["changed"], ["project/A_Card.dc.html"])

    def split_canvas(self):
        """An item as 0.2.0 archived it: file_path copies under data/, the files map at the served path."""
        from artikeep.adapters import claude_code
        old, new = self.canvas(["Main.dc.html"]), self.canvas(["Main.dc.html", "A_Card.dc.html", "B.dc.html"], pages=3)
        key = "https://claude.ai/artifact/canvas1"
        with self.store.lock("manifest"):
            m = self.store.load()
            e = self.store.entry_for(m, key, "Widgets", "2026-11-17T22:00:00")
            e.update(type_url="https://claude.ai/artifact/type-design", url=key, agent="claude-code")
            d = self.store.item_dir(e)
            states = [  # (files written in this publish, ...) replayed in order
                {"data/project/canvas.json": old, "project/Main.dc.html": "<p>main</p>"},
                {"data/project/A_Card.dc.html": "<p>card</p>"},
                {"data/project/B.dc.html": "<p>b</p>", "project/canvas.json": old},
                {"data/project/canvas.json": new},
            ]
            for i, files in enumerate(states):
                for rel, text in files.items():
                    (d / rel).parent.mkdir(parents=True, exist_ok=True)
                    (d / rel).write_text(text)
                self.store.snapshot(d, e, "2026-11-17T22:%02d:00" % i)
            self.store.save(m)
        return key, d, new, claude_code

    def test_split_canvas_is_merged_newest_index_wins(self):
        from artikeep import worker
        key, d, new, _ = self.split_canvas()
        worker.one_pass(self.store, push=False)
        e = self.manifest()["items"][key]
        self.assertEqual(e["layout"], 2)
        self.assertFalse((d / "data").exists())
        self.assertEqual((d / "project/canvas.json").read_text(), new)
        self.assertEqual(sorted(p.name for p in (d / "project").glob("*.dc.html")), ["A_Card.dc.html", "B.dc.html", "Main.dc.html"])
        self.assertIn('"P2"', (d / "index.html").read_text())  # the viewer embeds the newest index: three pages
        v3 = d / e["versions"][2]["dir"]
        self.assertFalse((v3 / "data").exists())
        self.assertIn('"A_Card.dc.html"', (d / e["versions"][3]["dir"] / "project/canvas.json").read_text())
        self.assertNotIn("A_Card", (v3 / "project/canvas.json").read_text())  # at version 3 the index was the old one
        self.assertTrue((v3 / "project/B.dc.html").exists())
        self.assertEqual(len(e["versions"]), 4)  # the merge is not a new version

    def test_merge_runs_once_per_item(self):
        key, d, _, claude_code = self.split_canvas()
        m = self.store.load()
        self.assertTrue(claude_code.merge_typed_data(self.store, m))
        self.store.save(m)
        (d / "data").mkdir()
        (d / "data" / "rows.json").write_text("[]")  # a file the type really serves under data/
        m = self.store.load()
        self.assertFalse(claude_code.merge_typed_data(self.store, m))
        self.assertTrue((d / "data" / "rows.json").exists())

    def test_missing_source_reports_partial(self):
        r = self.publish(self.work / "gone.html")
        self.assertTrue(r.startswith("partial"))

    def test_docs_export_is_decoded(self):
        from artikeep.adapters import claude_code
        doc = "11111111-2222-3333-4444-555555555555"
        md = "# Отчёт\n\nТекст".encode()
        payload = {"tool_name": "mcp__claude_ai_Claude_Docs__export", "session_id": "s1", "cwd": str(self.work),
                   "tool_input": {"container": {"kind": "project", "id": doc}, "file": "aaaa1111-bbbb", "format": "markdown"},
                   "tool_response": [{"type": "text", "text": json.dumps({"base64": base64.b64encode(md).decode()})}]}
        claude_code.cmd_docs(self.store, payload)
        m = self.manifest()["items"]["https://claude.ai/code/artifact/" + doc]
        self.assertEqual(m["kind"], "claude-doc")
        self.assertEqual((self.home / "items" / m["dir"] / "doc-aaaa1111-bbbb.md").read_bytes(), md)

    def test_docs_reminder_once_per_series(self):
        from artikeep.adapters import claude_code
        doc = "11111111-2222-3333-4444-666666666666"
        write = {"tool_name": "mcp__claude_ai_Claude_Docs__update", "session_id": "s9", "cwd": str(self.work),
                 "tool_input": {"container": {"kind": "project", "id": doc}}, "tool_response": "ok"}
        claude_code.cmd_docs(self.store, write)
        self.assertIsNotNone(claude_code.docs_reminder(self.store, {"session_id": "s9"}))
        self.assertIsNone(claude_code.docs_reminder(self.store, {"session_id": "s9"}))


if __name__ == "__main__":
    unittest.main()
