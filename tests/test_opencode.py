import json
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import ENTRY, TempArchive

SCHEMA = """
create table session (id text primary key, directory text not null, time_created integer, time_updated integer);
create table message (id text primary key, session_id text, time_created integer, time_updated integer, data text);
create table part (id text primary key, message_id text, session_id text, time_created integer, time_updated integer, data text);
"""
T0 = 1_790_000_000_000


class OpencodeTest(TempArchive):
    def make_db(self, repo):
        db = self.work / "opencode.db"
        con = sqlite3.connect(db)
        con.executescript(SCHEMA)
        con.execute("insert into session values ('ses_1', ?, ?, ?)", (str(repo), T0, T0 + 9000))
        n = [0]

        def msg(role, *parts, at=0):
            n[0] += 1
            mid = "m%d" % n[0]
            con.execute("insert into message values (?, 'ses_1', ?, ?, ?)", (mid, T0 + at, T0 + at, json.dumps({"role": role})))
            for i, p in enumerate(parts):
                con.execute("insert into part values (?, ?, 'ses_1', ?, ?, ?)", ("%s-%d" % (mid, i), mid, T0 + at + i, T0 + at + i, json.dumps(p)))

        report = self.work / "tmp" / "report.md"
        report.parent.mkdir()
        report.write_text("# Weekly report\n\nnumbers")
        tool = lambda name, path, **inp: {"type": "tool", "tool": name, "state": {"status": "completed", "input": dict({"filePath": path}, **inp)}}
        msg("user", {"type": "text", "text": "write the weekly report"}, at=0)
        msg("assistant", tool("write", str(report), content="# Weekly report\n\nnumbers"),
            tool("write", str(self.work / "tmp" / "gone.html"), content="<title>Gone page</title>kept by the log"),
            tool("edit", str(repo / "README.md"), oldString="a", newString="b"),
            tool("write", str(self.work / "tmp" / "script.py"), content="print(1)"),
            {"type": "tool", "tool": "write", "state": {"status": "error", "input": {"filePath": str(self.work / "tmp" / "failed.md"), "content": "x"}}},
            {"type": "reasoning", "text": "thinking"}, at=1000)
        msg("user", {"type": "text", "text": "tweak it", "synthetic": True}, {"type": "text", "text": "later: add a chart"}, at=5000)
        msg("assistant", {"type": "text", "text": "Done, see %s" % (self.work / "tmp" / "chart.svg")}, at=6000)
        (self.work / "tmp" / "chart.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        con.commit()
        con.close()
        return db

    def make_repo(self):
        repo = self.work / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "README.md").write_text("# tracked")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        return repo

    def test_session_deliverables(self):
        from artikeep.adapters import opencode
        repo = self.make_repo()
        con = opencode._connect(self.make_db(repo))
        n = opencode.archive(self.store, con, "ses_1")
        items = self.manifest()["items"]
        self.assertEqual(sorted(Path(e["origin"]).name for e in items.values()), ["chart.svg", "gone.html", "report.md"])
        self.assertEqual(n, 3)  # not the tracked README, not .py, not the failed write
        e = items["opencode:" + str(self.work / "tmp" / "report.md")]
        self.assertEqual((e["agent"], e["title"], e["project"]), ("opencode", "Weekly report", str(repo.resolve())))
        v = e["versions"][0]
        self.assertEqual((v["request"], v["session"]), ("write the weekly report", "ses_1"))
        self.assertEqual(items["opencode:" + str(self.work / "tmp" / "chart.svg")]["versions"][0]["request"], "later: add a chart")
        self.assertEqual(opencode.archive(self.store, con, "ses_1"), 0)  # unchanged: nothing new

    def test_check_and_stop_use_the_database(self):
        from artikeep.adapters import opencode
        db = self.make_db(self.make_repo())
        with mock.patch.object(opencode, "DB", db):
            opencode.cmd_stop(self.store, {"session_id": "ses_1"})
            self.assertEqual(len(self.manifest()["items"]), 3)
            self.assertEqual(opencode.cmd_check(self.store, {}, days=100000), 0)  # already saved
            self.assertEqual(opencode.cmd_check(self.store, {}, days=0), 0)  # nothing recent enough
        with mock.patch.object(opencode, "DB", self.work / "missing.db"):
            self.assertEqual(opencode.cmd_check(self.store, {}), 0)  # no database: quietly nothing
            opencode.cmd_stop(self.store, {"session_id": "ses_1"})

    def test_hook_entry_point_is_quiet_without_opencode(self):
        r = subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "hook", "opencode", "stop"], input='{"session_id": "x"}',
                           capture_output=True, text=True, env={"ARTIKEEP_HOME": str(self.home), "PATH": "/usr/bin:/bin", "XDG_DATA_HOME": str(self.work)})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_install_and_uninstall_the_plugin(self):
        from artikeep import install
        conf = self.work / "oc" / "opencode.json"
        conf.parent.mkdir()
        conf.write_text(json.dumps({"plugin": ["file:///other.js"], "mcp": {"mine": {"type": "local", "command": ["x"]}}}))
        plugin = conf.parent / "plugins" / "artikeep.js"
        with mock.patch.multiple(install, OPENCODE_DIR=conf.parent, OPENCODE_PLUGIN=plugin, OPENCODE_CONFIG=conf):
            install.install_opencode(install.Plan(False), False)
            data = json.loads(conf.read_text())
            self.assertEqual(data["plugin"], ["file:///other.js", "file://" + str(plugin)])
            self.assertEqual(data["mcp"]["artikeep"]["command"][-1], "mcp")
            self.assertIn("mine", data["mcp"])
            js = plugin.read_text()
            self.assertIn(" hook opencode stop ", js)
            self.assertIn(" hook opencode check ", js)
            self.assertIn("session.idle", js)
            install.install_opencode(install.Plan(False), False)  # again: no duplicates
            self.assertEqual(json.loads(conf.read_text())["plugin"].count("file://" + str(plugin)), 1)
            install.install_opencode(install.Plan(False), True)
            data = json.loads(conf.read_text())
            self.assertEqual((data["plugin"], list(data["mcp"])), (["file:///other.js"], ["mine"]))
            self.assertFalse(plugin.exists())
            conf.write_text("{ // comments make it JSONC\n}")
            install.install_opencode(install.Plan(False), False)
            self.assertEqual(conf.read_text(), "{ // comments make it JSONC\n}")  # not rewritten


if __name__ == "__main__":
    unittest.main()
