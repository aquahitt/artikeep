import unittest

from tests.helpers import TempArchive


class StoreTest(TempArchive):
    def test_versions_only_on_change(self):
        e, v1 = self.store.save_item("k", {"index.html": b"<title>A</title>one"}, agent="import", main="index.html")
        _, v2 = self.store.save_item("k", {"index.html": b"<title>A</title>one"}, agent="import", main="index.html")
        _, v3 = self.store.save_item("k", {"index.html": b"<title>A</title>two"}, agent="import", main="index.html", label="second")
        self.assertTrue(v1)
        self.assertIsNone(v2)
        self.assertTrue(v3)
        entry = self.manifest()["items"]["k"]
        self.assertEqual([v["n"] for v in entry["versions"]], [1, 2])
        self.assertEqual(entry["versions"][1]["label"], "second")
        self.assertEqual(entry["title"], "A")
        self.assertEqual(len(entry["publishes"]), 2)  # the identical save is not a publish

    def test_html_gets_charset_and_dir_names_are_unique(self):
        e1, _ = self.store.save_item("a", {"index.html": "<p>Привет</p>".encode()}, agent="import", title="Same", main="index.html")
        e2, _ = self.store.save_item("b", {"index.html": b"<p>x</p>"}, agent="import", title="Same", main="index.html")
        self.assertNotEqual(e1["dir"], e2["dir"])
        data = (self.store.item_dir(e1) / "index.html").read_bytes()
        self.assertTrue(data.startswith(b'<meta charset="utf-8">'))

    def test_gitignore_lists_local_folders(self):
        text = (self.home / ".gitignore").read_text()
        for x in (".hooklog/", ".cache/"):
            self.assertIn(x, text)

    def test_slugify_transliterates(self):
        from artikeep.util import slugify
        self.assertEqual(slugify("Экран комнаты — варианты"), "ekran-komnaty-varianty")
        self.assertEqual(slugify(""), "artifact")


if __name__ == "__main__":
    unittest.main()
