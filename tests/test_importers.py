import json
import unittest
import zipfile

from tests.helpers import TempArchive


def chatgpt_export():
    def msg(i, t, recipient="all", content=None, role="assistant"):
        return {"id": "m%d" % i, "message": {"id": "m%d" % i, "author": {"role": role}, "recipient": recipient, "create_time": t,
                                            "content": {"content_type": "text", "parts": [json.dumps(content) if content is not None else "hi"]}}}
    mapping = {
        "a": msg(1, 1000.0, role="user"),
        "b": msg(2, 1001.0, "canmore.create_textdoc", {"name": "Plan", "type": "document", "content": "# Plan\n\nstep one"}),
        "c": msg(3, 1002.0, "canmore.update_textdoc", {"updates": [{"pattern": "step one", "replacement": "step one\nstep two"}]}),
        "d": msg(4, 1003.0, "canmore.comment_textdoc", {"comments": []}),
        "e": msg(5, 1004.0, "canmore.create_textdoc", {"name": "Page", "type": "code/html", "content": "<title>P</title>"}),
    }
    return [{"title": "Planning chat", "conversation_id": "conv-1", "mapping": mapping}]


def claude_export():
    return [{"uuid": "c-1", "name": "Design chat", "chat_messages": [
        {"sender": "assistant", "created_at": "2026-09-01T10:00:00Z", "content": [
            {"type": "tool_use", "name": "artifacts", "input": {"id": "app", "type": "text/html", "title": "App", "command": "create", "content": "<p>one</p>"}}]},
        {"sender": "assistant", "created_at": "2026-09-01T10:05:00Z", "content": [
            {"type": "tool_use", "name": "artifacts", "input": {"id": "app", "command": "update", "old_str": "one", "new_str": "two"}},
            {"type": "text", "text": 'Old style: <antArtifact identifier="notes" type="text/markdown" title="Notes"># Notes</antArtifact>'}]},
    ]}]


class ImportersTest(TempArchive):
    def test_chatgpt_canvas_history(self):
        from artikeep.importers.chatgpt import import_export
        z = self.work / "export.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("export/conversations.json", json.dumps(chatgpt_export()))
        stats = import_export(self.store, z)
        self.assertEqual((stats["docs"], stats["versions"], stats["unparsed_calls"]), (2, 3, 0))
        items = self.manifest()["items"]
        plan = items["chatgpt:conv-1:0"]
        self.assertEqual((plan["agent"], plan["title"], len(plan["versions"])), ("chatgpt", "Plan", 2))
        self.assertIn("step two", (self.home / "items" / plan["dir"] / "Plan.md").read_text())
        self.assertEqual(items["chatgpt:conv-1:1"]["main"], "index.html")
        self.assertEqual(plan["url"], "https://chatgpt.com/c/conv-1")

    def test_claude_ai_artifacts(self):
        from artikeep.importers.claude_ai import import_export
        p = self.write("conversations.json", json.dumps(claude_export()))
        stats = import_export(self.store, p)
        self.assertEqual((stats["docs"], stats["versions"]), (2, 3))
        app = self.manifest()["items"]["claude-ai:c-1:app"]
        self.assertEqual(len(app["versions"]), 2)
        self.assertIn(b"two", (self.home / "items" / app["dir"] / "index.html").read_bytes())
        notes = self.manifest()["items"]["claude-ai:c-1:notes"]
        self.assertEqual(notes["main"], "notes.md")

    def test_add_file_and_folder(self):
        from artikeep.importers.files import add_path
        f = self.write("deck/report.pdf", "%PDF-1.4 fake")
        self.write("site/index.html", "<title>Site</title>")
        self.write("site/app.js", "1")
        e1, _ = add_path(self.store, f)
        e2, _ = add_path(self.store, self.work / "site")
        self.assertEqual((e1["main"], e2["main"], e2["title"]), ("report.pdf", "index.html", "Site"))
        self.assertNotIn("project", e1)  # outside git there is no project, not the folder name
        self.assertTrue((self.home / "items" / e2["dir"] / "app.js").exists())


if __name__ == "__main__":
    unittest.main()
