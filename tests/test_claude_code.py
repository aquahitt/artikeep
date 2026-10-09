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
