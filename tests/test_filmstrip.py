import subprocess
import unittest

from tests.helpers import TempArchive

HAS_PW = subprocess.run(["python3", "-c", "import playwright"], capture_output=True).returncode == 0


class FilmstripTest(TempArchive):
    @unittest.skipUnless(HAS_PW, "no Playwright")
    def test_every_version_gets_a_thumbnail_and_stays_out_of_the_history(self):
        from artikeep import gallery
        self.store.settings["thumbnails"] = "auto"
        for i in (1, 2, 3):
            e, _ = self.store.save_item("k", {"index.html": ("<title>T</title><body style='background:#%d%d%d'><p>v%d</p>" % (i, i, i, i)).encode()},
                                        agent="codex", main="index.html")
        n = gallery.refresh_thumbs(self.store, self.store.load())
        item = self.store.item_dir(e)
        vs = self.store.load()["items"]["k"]["versions"]
        self.assertEqual(n, 4)  # the item's own and one per version
        self.assertTrue(all((item / v["dir"] / "_thumb.jpg").exists() for v in vs))
        data = gallery.gallery_data(self.store, self.store.load())["items"][0]
        self.assertEqual([v["thumb"] for v in data["versions"]], [True, True, True])
        self.assertEqual(gallery.refresh_thumbs(self.store, self.store.load()), 0)  # done: nothing again
        self.store.save_item("k", {"index.html": b"<title>T</title><body style='background:#333'><p>v3</p>"}, agent="codex", main="index.html")
        self.assertEqual(len(self.store.load()["items"]["k"]["versions"]), 3)  # the same page again: thumbnails are not changes

    def test_budget_per_pass(self):
        from artikeep import gallery
        self.assertGreater(gallery.VERSION_THUMBS_PER_PASS, 0)


if __name__ == "__main__":
    unittest.main()
