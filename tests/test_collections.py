import json
import os
import subprocess
import unittest

from tests.helpers import ENTRY, TempArchive


class CollectionsTest(TempArchive):
    def setUp(self):
        super().setUp()
        mk = lambda key, **kw: self.store.save_item(key, {"index.html": ("<title>%s</title><p>%s</p>" % (key, key)).encode()},
                                                  agent="codex", main="index.html", title=key, **kw)[0]["dir"]
        self.repo = self.work / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.page, self.shot = mk("page", project=str(self.repo)), mk("shot", project=str(self.repo))
        self.other = mk("elsewhere", project="/elsewhere")

    def test_add_remove_rename_delete(self):
        from artikeep import collections as c
        self.assertEqual(c.add(self.store, "  Portal   splash ", [self.page, self.shot]), [self.page, self.shot])
        self.assertEqual(c.add(self.store, "Portal splash", [self.page]), [])  # already in
        c.add(self.store, "Icons", [self.shot])
        colls = c.load(self.store)
        self.assertEqual(sorted(colls), ["Icons", "Portal splash"])
        self.assertEqual(c.of_item(colls, self.shot), ["Icons", "Portal splash"])
        self.assertEqual(json.loads((self.home / "collections.json").read_text())["version"], 1)
        c.rename(self.store, "Icons", "Portal splash")  # into an existing one: merged
        self.assertEqual(sorted(c.load(self.store)), ["Portal splash"])
        self.assertEqual(c.remove(self.store, "Portal splash", [self.page, self.shot]), [self.page, self.shot])
        self.assertFalse((self.home / "collections.json").exists())  # an empty collection is not kept
        with self.assertRaises(KeyError):
            c.add(self.store, "X", ["no-such-item"])
        with self.assertRaises(ValueError):
            c.add(self.store, "   ", [self.page])
        with self.assertRaises(KeyError):
            c.delete(self.store, "nope")

    def test_deleting_an_item_leaves_its_collections(self):
        from artikeep import collections as c
        c.add(self.store, "A", [self.page, self.shot])
        c.add(self.store, "Solo", [self.shot])
        self.store.delete(self.shot)
        self.assertEqual(c.load(self.store), {"A": [self.page]})

    def test_gallery_search_and_mcp(self):
        from artikeep import collections as c, gallery, mcp_server, search
        c.add(self.store, "Portal", [self.page, self.shot, self.other])
        data = gallery.gallery_data(self.store, self.store.load())
        self.assertEqual(data["collections"], ["Portal"])
        self.assertEqual({i["title"]: i["collections"] for i in data["items"]}, {"page": ["Portal"], "shot": ["Portal"], "elsewhere": ["Portal"]})
        self.assertEqual(sorted(h["title"] for h in search.search(self.store, "", collection="Portal")), ["elsewhere", "page", "shot"])
        self.assertEqual(search.search(self.store, "", collection="Nothing"), [])
        srv = mcp_server.Server(self.store, scope="all", allow_save=False)
        srv.scope = str(self.repo)  # as if started in that repository
        self.assertEqual([h["title"] for h in json.loads(srv.call("search_artifacts", {"collection": "Portal", "query": "page"}).split("\n", 1)[1])], ["page"])
        meta = json.loads(srv.call("read_artifact", {"id": self.page}).split("\n", 1)[1].split("\n\n", 1)[0])
        self.assertEqual(meta["collections"], {"Portal": [self.shot]})  # the item outside the project scope is not named

    def test_cli(self):
        env = dict(os.environ, ARTIKEEP_HOME=str(self.home))
        run = lambda *a: subprocess.run(["/usr/bin/env", "python3", str(ENTRY), *a], capture_output=True, text=True, env=env, cwd=str(self.repo))
        self.assertEqual(run("collection", "add", "Portal", self.page, self.shot).returncode, 0)
        out = run("collection", "list").stdout
        self.assertIn("Portal", out)
        self.assertIn("2 item(s)", out)
        self.assertIn(self.shot, run("collection", "show", "Portal").stdout)
        self.assertEqual(run("search", "--collection", "Portal", "--json").returncode, 0)
        shot = self.write("new.png", "PNG")
        r = run("add", str(shot), "--collection", "Portal", "--no-project")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("3 item(s)", run("collection", "list").stdout)
        self.assertEqual(run("collection", "add", "Portal", "nope").returncode, 1)
        self.assertEqual(run("collection", "rename", "Portal", "Splash").returncode, 0)
        self.assertEqual(run("collection", "delete", "Splash").returncode, 0)
        self.assertIn("no collections", run("collection", "list").stdout)


if __name__ == "__main__":
    unittest.main()
