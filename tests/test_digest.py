import datetime as dt
import os
import subprocess
import unittest

from tests.helpers import ENTRY, TempArchive

NOW = dt.datetime(2026, 11, 20, 12, 0, 0)


class DigestTest(TempArchive):
    def setUp(self):
        super().setUp()
        self.repo = self.work / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def save(self, key, text, when, **kw):
        return self.store.save_item(key, {"index.html": ("<title>%s</title><p>%s</p>" % (key, text)).encode()}, agent="claude-code",
                                    main="index.html", title=key, when=when, **kw)[0]

    def test_window_groups_and_new_vs_updated(self):
        from artikeep import digest
        proj = str(self.repo)
        self.save("fresh", "a", "2026-11-19T10:00:00", project=proj, request="make the dashboard")
        self.save("old-then-edited", "a", "2026-10-01T10:00:00", project=proj)
        self.save("old-then-edited", "b", "2026-11-18T10:00:00", project=proj, request="fix the filters")
        self.save("old", "a", "2026-10-02T10:00:00", project=proj)
        self.save("loose", "a", "2026-11-17T10:00:00")
        gone = self.save("gone", "a", "2026-11-19T11:00:00", project=proj)
        self.store.delete(gone["dir"])
        d = digest.collect(self.store, 7, now=NOW)
        by = {i["title"]: i for p in d["projects"] for i in p["items"]}
        self.assertEqual(sorted(by), ["fresh", "loose", "old-then-edited"])  # not "old", not the deleted one
        self.assertEqual((by["fresh"]["new"], by["old-then-edited"]["new"], by["old-then-edited"]["added"]), (True, False, 1))
        self.assertEqual(by["old-then-edited"]["asks"], ["fix the filters"])
        self.assertEqual((d["new"], d["updated"], d["versions"]), (2, 1, 3))
        self.assertEqual([p["name"] for p in d["projects"]], ["repo", ""])  # no project last
        self.assertEqual(len(digest.collect(self.store, 60, now=NOW)["projects"][0]["items"]), 3)
        self.assertEqual([p["name"] for p in digest.collect(self.store, 7, "repo", now=NOW)["projects"]], ["repo"])
        self.assertEqual(digest.collect(self.store, 7, "nope", now=NOW)["projects"], [])

    def test_outputs(self):
        from artikeep import digest
        self.save("A <b>page</b>", "a", "2026-11-19T10:00:00", project=str(self.repo), request="ask <script>x</script>")
        d = digest.collect(self.store, 7, now=NOW)
        md = digest.to_markdown(d, self.store)
        self.assertIn("## repo", md)
        self.assertIn("1 new item(s)", md)
        self.assertIn("asked: ask <script>x</script>", md)
        out = self.work / "out" / "digest.html"
        out.parent.mkdir()
        page = digest.to_html(d, self.store, out.parent)
        self.assertNotIn("<script>", page)  # titles and asks are escaped
        self.assertIn("&lt;script&gt;", page)
        self.assertIn('href="../../archive/items/', page)  # relative to where the file sits
        self.assertIn("Nothing new in the last 7 days", digest.to_html(digest.collect(self.store, 7, "nope", now=NOW), self.store, out.parent))

    def test_cli(self):
        self.save("fresh", "a", dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), project=str(self.repo))
        env = dict(os.environ, ARTIKEEP_HOME=str(self.home))
        run = lambda *a: subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "digest", *a], capture_output=True, text=True, env=env)
        r = run("--format", "md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("**fresh**", r.stdout)
        r = run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 new", r.stdout)
        self.assertTrue((self.home / "digest.html").exists())
        self.assertIn("fresh", (self.home / "digest.html").read_text())


if __name__ == "__main__":
    unittest.main()
