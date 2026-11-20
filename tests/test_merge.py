import json
import os
import subprocess
import unittest

from tests.helpers import ENTRY, TempArchive

A, B = "https://claude.ai/code/artifact/aaa", "https://claude.ai/code/artifact/bbb"


class MergeTest(TempArchive):
    def mk(self, key, texts, times, **kw):
        for t, at in zip(texts, times):
            e, _ = self.store.save_item(key, {"index.html": ("<title>Plan</title><p>%s</p>" % t).encode()}, agent="claude-code",
                                        main="index.html", title="Plan", url=key, when=at, session="s1", **kw)
        return e

    def pair(self):
        a = self.mk(A, ["one", "two"], ["2026-11-20T10:00:00", "2026-11-20T10:10:00"], request="first ask")
        b = self.mk(B, ["three", "four"], ["2026-11-20T10:20:00", "2026-11-20T10:30:00"])
        return a["dir"], b["dir"]

    def test_find_groups_same_session_and_source(self):
        from artikeep import merge
        a, b = self.pair()
        m = self.store.load()
        for k in (A, B):
            for p in m["items"][k]["publishes"]:
                p["source"] = "/scratch/page.html"
        self.store.save(m)
        other = self.mk("https://claude.ai/code/artifact/zzz", ["x"], ["2026-11-20T11:00:00"])
        self.assertEqual(merge.find(self.store), [sorted([a, b])])
        self.assertNotIn(other["dir"], merge.find(self.store)[0])

    def test_merge_interleaves_renumbers_and_keeps_the_newest_files(self):
        from artikeep import collections, merge
        a, b = self.pair()
        self.store.star(b, True)
        self.store.mark(b, 2, "chosen")
        collections.add(self.store, "Plans", [a, b])
        r = merge.run(self.store, [a, b])
        self.assertEqual((r["target"], r["versions"], r["folded"]), (a, 4, [b]))
        items = self.manifest()["items"]
        self.assertEqual(list(items), [B])  # the newest link is the key
        e = items[B]
        self.assertEqual((e["dir"], e["url"], e["former_urls"], e["star"]), (a, B, [A], True))
        self.assertEqual([v["n"] for v in e["versions"]], [1, 2, 3, 4])
        self.assertEqual([v["at"][11:16] for v in e["versions"]], ["10:00", "10:10", "10:20", "10:30"])
        self.assertEqual((e["versions"][0].get("request"), e["versions"][3].get("mark")), ("first ask", "chosen"))
        item = self.home / "items" / a
        self.assertIn("four", (item / "index.html").read_text())  # the newest version's files
        for v in e["versions"]:
            self.assertTrue((item / v["dir"] / "index.html").exists(), v["dir"])
        self.assertIn("one", (item / e["versions"][0]["dir"] / "index.html").read_text())
        self.assertEqual(e["versions"][2]["changed"], ["index.html"])
        self.assertFalse((self.home / "items" / b).exists())
        self.assertEqual(collections.load(self.store), {"Plans": [a]})

    def test_refusals(self):
        from artikeep import merge
        a, b = self.pair()
        for folders in ([a], [a, a], [a, "nope"]):
            with self.assertRaises(merge.MergeError):
                merge.run(self.store, folders)
        self.store.delete(b)
        with self.assertRaises(merge.MergeError):
            merge.plan(self.store, [a, b])

    def test_cli(self):
        a, b = self.pair()
        env = dict(os.environ, ARTIKEEP_HOME=str(self.home))
        run = lambda *x: subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "merge", *x], capture_output=True, text=True, env=env)
        r = run(a, b, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("4 versions", r.stdout)
        self.assertEqual(len(self.manifest()["items"]), 2)  # a dry run changes nothing
        self.assertEqual(run(a, b).returncode, 0)
        self.assertEqual(len(self.manifest()["items"]), 1)
        self.assertEqual(run(a, "nope").returncode, 1)
        self.assertIn("no copies", run("--find").stdout)


if __name__ == "__main__":
    unittest.main()
