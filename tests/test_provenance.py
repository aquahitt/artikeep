import json
import unittest

from tests.helpers import TempArchive

KEY = "https://claude.ai/code/artifact/abc-123"


def rec(kind, content, **extra):
    return json.dumps(dict({"type": kind, "message": {"role": kind, "content": content}}, **extra)) + "\n"


def tool_use(tid):
    return rec("assistant", [{"type": "tool_use", "id": tid, "name": "Artifact", "input": {}}])


class ProvenanceTest(TempArchive):
    def transcript(self, *records):
        return self.write("session.jsonl", "".join(records))

    def request(self, path, tid=None):
        from artikeep import provenance
        return provenance.claude_code_request(path, tid)

    def test_request_is_the_last_real_prompt_before_the_tool_call(self):
        t = self.transcript(
            rec("user", "first ask"),
            tool_use("t1"),
            rec("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
            rec("user", "<task-notification>done</task-notification>"),
            rec("user", "<local-command-caveat>x</local-command-caveat>", isMeta=True),
            rec("user", [{"type": "text", "text": "move the filters\nto the left  <system-reminder>noise</system-reminder>"}]),
            rec("user", "side chat", isSidechain=True),
            tool_use("t2"),
            rec("user", "asked after the call"),
        )
        self.assertEqual(self.request(t, "t1"), "first ask")
        self.assertEqual(self.request(t, "t2"), "move the filters to the left")
        self.assertEqual(self.request(t), "asked after the call")  # no id: the newest

    def test_commands_pasted_text_and_length(self):
        from artikeep import provenance
        cmd = "<command-message>release</command-message><command-name>/release</command-name><command-args>0.2.1</command-args>"
        t = self.transcript(rec("user", "before"), rec("user", cmd), tool_use("t1"))
        self.assertEqual(self.request(t, "t1"), "/release 0.2.1")
        bare = "<command-name>/clear</command-name><command-args></command-args>"
        t = self.transcript(rec("user", "before"), rec("user", bare), tool_use("t1"))
        self.assertEqual(self.request(t, "t1"), "before")  # a local command is not a request
        skill = "<command-name>/review</command-name><command-args></command-args>"
        t = self.transcript(rec("user", skill), rec("user", "Base directory for this skill: x", isMeta=True), tool_use("t1"))
        self.assertEqual(self.request(t, "t1"), "/review")  # a skill expanded it
        t = self.transcript(rec("user", "fix this <pasted_content id=1>SECRET " + "x" * 900 + "</pasted_content> please"), tool_use("t1"))
        self.assertEqual(self.request(t, "t1"), "fix this [pasted text] please")
        t = self.transcript(rec("user", "long " * 400), tool_use("t1"))
        got = self.request(t, "t1")
        self.assertEqual(len(got), provenance.MAX_CHARS)
        self.assertTrue(got.endswith("…"))
        t = self.transcript(rec("user", "move the filters to the left"), tool_use("t0"), rec("user", "да"), tool_use("t1"))
        self.assertEqual(self.request(t, "t1"), "move the filters to the left → да")  # a short reply keeps its context
        self.assertIsNone(self.request(self.work / "missing.jsonl", "t1"))

    def publish(self, tid, transcript, **extra):
        from artikeep.adapters import claude_code
        page = self.work / "page.html"
        page.write_text("<!doctype html><title>Plan</title><p>%s</p>" % tid)
        payload = {"tool_name": "Artifact", "cwd": str(self.work), "session_id": "sess-9", "tool_use_id": tid,
                   "transcript_path": str(transcript), "tool_input": {"file_path": str(page)},
                   "tool_response": "Published: " + KEY}
        return claude_code.handle_artifact(self.store, dict(payload, **extra))

    def test_publish_records_request_and_search_finds_it(self):
        from artikeep import gallery, mcp_server, search
        t = self.transcript(rec("user", "make a dark theme for the dashboard"), tool_use("t1"),
                            rec("user", "now move the filters left"), tool_use("t2"))
        self.publish("t1", t)
        self.publish("t2", t)
        vs = self.manifest()["items"][KEY]["versions"]
        self.assertEqual([(v["request"], v["session"]) for v in vs],
                         [("make a dark theme for the dashboard", "sess-9"), ("now move the filters left", "sess-9")])
        m = self.store.load()
        search.update_index(self.store, m)
        self.assertEqual([h["title"] for h in search.search(self.store, "dark theme")], ["Plan"])
        data = gallery.gallery_data(self.store, m)
        self.assertEqual(data["items"][0]["versions"][1]["request"], "now move the filters left")
        out = json.loads(mcp_server.Server(self.store, scope="all", allow_save=False).call("list_versions", {"id": m["items"][KEY]["dir"]}))
        self.assertEqual(out["versions"][0]["request"], "make a dark theme for the dashboard")
        self.assertIn("archived content", out["note"])

    def test_off_switch_and_missing_transcript(self):
        t = self.transcript(rec("user", "ask"), tool_use("t1"))
        self.store.settings["provenance"] = False
        self.publish("t1", t)
        v = self.manifest()["items"][KEY]["versions"][0]
        self.assertNotIn("request", v)
        self.assertNotIn("session", v)
        self.store.settings["provenance"] = True
        self.publish("t2", self.work / "gone.jsonl")  # no transcript: the session is still known
        v = self.manifest()["items"][KEY]["versions"][1]
        self.assertNotIn("request", v)
        self.assertEqual(v["session"], "sess-9")

    def test_codex_deliverable_gets_the_request_before_it(self):
        from artikeep.adapters import codex
        doc = self.write("out/report.md", "# Report\n\ntext")

        def line(kind, payload, ts):
            return json.dumps({"timestamp": ts, "type": kind, "payload": payload}) + "\n"

        def user(text, ts):
            return line("event_msg", {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": text}]}}, ts)
        rollout = self.write("rollout.jsonl", "".join([
            line("session_meta", {"session_id": "cx-1", "cwd": str(self.work)}, "2026-10-01T10:00:00.000Z"),
            user("write the weekly report", "2026-10-01T10:00:01.000Z"),
            user("<environment_context>x</environment_context>", "2026-10-01T10:00:02.000Z"),
            line("event_msg", {"type": "item_completed", "item": {"type": "FileChange", "changes": {
                str(doc): {"type": "add", "content": "# Report\n\ntext"}}}}, "2026-10-01T10:05:00.000Z"),
            user("later, unrelated", "2026-10-01T11:00:00.000Z"),
        ]))
        codex.archive_rollout(self.store, rollout)
        e = self.manifest()["items"]["codex:" + str(doc)]
        self.assertEqual((e["versions"][0]["request"], e["versions"][0]["session"]), ("write the weekly report", "cx-1"))


if __name__ == "__main__":
    unittest.main()
