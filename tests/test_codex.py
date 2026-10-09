import json
import subprocess
import unittest

from tests.helpers import ENTRY, TempArchive


def line(kind, payload, ts="2026-10-01T10:00:00.000Z"):
    return json.dumps({"timestamp": ts, "type": kind, "payload": payload}) + "\n"


class CodexTest(TempArchive):
    def rollout(self, repo):
        report = self.write("tmp/report.md", "# Weekly report\n\nnumbers ![chart](img/chart.png) [up](../secret.txt)")
        self.write("tmp/img/chart.png", "PNGDATA")
        self.write("secret.txt", "outside the document folder")
        gone = self.work / "tmp" / "deleted.html"
        tracked = repo / "README.md"
        lines = [
            line("session_meta", {"session_id": "sess-1", "cwd": str(repo)}),
            line("event_msg", {"type": "item_completed", "item": {"type": "FileChange", "changes": {
                str(report): {"type": "add", "content": "# Weekly report\n\nnumbers"},
                str(gone): {"type": "add", "content": "<title>Gone page</title>kept by transcript"},
                str(tracked): {"type": "update"},
                str(self.work / "tmp" / "script.py"): {"type": "add", "content": "print(1)"},
            }}}),
            line("event_msg", {"type": "item_completed", "item": {"type": "AgentMessage", "phase": "final_answer", "content": [
                {"type": "Text", "text": "Done: see %s:12 and %s." % (self.work / "tmp" / "chart.svg", self.work / "nope.pdf")}]}}),
        ]
        self.write("tmp/chart.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>")
        return self.write("rollout.jsonl", "".join(lines))

    def make_repo(self):
        repo = self.work / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "README.md").write_text("# tracked")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        return repo

    def test_rollout_deliverables(self):
        from artikeep.adapters import codex
        repo = self.make_repo()
        n = codex.archive_rollout(self.store, self.rollout(repo))
        items = self.manifest()["items"]
        origins = sorted(e["origin"].rsplit("/", 1)[-1] for e in items.values())
        self.assertEqual(origins, ["chart.svg", "deleted.html", "report.md"])  # not tracked README, not .py, not missing pdf
        self.assertEqual(n, 3)
        e = items["codex:" + str(self.work / "tmp" / "report.md")]
        self.assertEqual((e["agent"], e["title"], e["main"]), ("codex", "Weekly report", "report.md"))
        self.assertEqual(e["project"], str(repo))
        item = self.home / "items" / e["dir"]
        self.assertEqual((item / "img" / "chart.png").read_text(), "PNGDATA")  # the image it shows came along
        self.assertFalse((item / "secret.txt").exists())  # a reference climbing out is left alone
        self.assertEqual(codex.archive_rollout(self.store, self.rollout(repo)), 0)  # unchanged: nothing new

    def test_stop_hook_prints_json_even_when_broken(self):
        r = subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "hook", "codex", "stop"], input="not json",
                           capture_output=True, text=True, env={"ARTIKEEP_HOME": str(self.home), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout), {})


if __name__ == "__main__":
    unittest.main()
