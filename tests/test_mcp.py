import json
import os
import subprocess
import unittest

from tests.helpers import ENTRY, TempArchive


class McpTest(TempArchive):
    def setUp(self):
        super().setUp()
        self.repo = self.work / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.store.save_item("in", {"index.html": "<title>Кухня</title><p>Планировка кухни</p>".encode()}, agent="codex",
                             main="index.html", project=str(self.repo))
        self.store.save_item("in", {"index.html": "<title>Кухня</title><p>Планировка кухни и гостиной</p>".encode()},
                             agent="codex", main="index.html", project=str(self.repo))
        self.store.save_item("out", {"doc.md": "# Secret plan".encode()}, agent="import", main="doc.md", project="/elsewhere")

    def session(self, *calls, args=(), cwd=None):
        p = subprocess.Popen(["/usr/bin/env", "python3", str(ENTRY), "mcp", *args], cwd=str(cwd or self.repo),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                             env=dict(os.environ, ARTIKEEP_HOME=str(self.home)))
        out = []
        msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"}]
        msgs += [{"jsonrpc": "2.0", "id": i + 1, "method": m, "params": prm} for i, (m, prm) in enumerate(calls)]
        stdout, _ = p.communicate("\n".join(json.dumps(x) for x in msgs) + "\n", timeout=60)
        for ln in stdout.splitlines():
            out.append(json.loads(ln))
        return out

    def tool(self, name, **a):
        return ("tools/call", {"name": name, "arguments": a})

    def text(self, reply):
        return reply["result"]["content"][0]["text"]

    def test_handshake_and_scope(self):
        r = self.session(("tools/list", {}), self.tool("search_artifacts", query="кухни"), self.tool("search_artifacts"))
        self.assertEqual(r[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(len(r), 4)  # the notification gets no reply
        names = [t["name"] for t in r[1]["result"]["tools"]]
        self.assertNotIn("save_artifact", names)
        self.assertIn("Кухня", self.text(r[2]))
        self.assertNotIn("Secret", self.text(r[3]))  # other project stays hidden

    def test_read_versions_diff_and_guards(self):
        hits = json.loads(self.text(self.session(self.tool("search_artifacts", query="кухня"))[1]).split("\n", 1)[1])
        iid = hits[0]["id"]
        r = self.session(self.tool("read_artifact", id=iid), self.tool("list_versions", id=iid), self.tool("diff_versions", id=iid),
                         self.tool("read_artifact", id=iid, file="../../manifest.json"), self.tool("save_artifact", title="x", content="y"))
        self.assertIn("Планировка кухни и гостиной", self.text(r[1]))
        self.assertEqual(len(json.loads(self.text(r[2]))["versions"]), 2)
        self.assertIn("гостиной", self.text(r[3]))
        self.assertTrue(r[4]["result"]["isError"])
        self.assertTrue(r[5]["result"]["isError"])
        self.assertIn("--allow-save", self.text(r[5]))
        out_dir = [e["dir"] for k, e in self.manifest()["items"].items() if k == "out"][0]
        r = self.session(self.tool("read_artifact", id=out_dir))
        self.assertIn("outside", self.text(r[1]))

    def test_save_when_allowed(self):
        r = self.session(("tools/list", {}), self.tool("save_artifact", title="Notes", content="# Notes\n\nA", filename="notes.md"),
                         self.tool("save_artifact", title="Notes", content="# Notes\n\nB", filename="notes.md"), args=("--allow-save",))
        self.assertIn("save_artifact", [t["name"] for t in r[1]["result"]["tools"]])
        self.assertIn("version 1", self.text(r[2]))
        self.assertIn("version 2", self.text(r[3]))
        e = [e for k, e in self.manifest()["items"].items() if k.startswith("mcp:")][0]
        self.assertEqual((e["agent"], e["project"]), ("mcp", str(self.repo)))


if __name__ == "__main__":
    unittest.main()
