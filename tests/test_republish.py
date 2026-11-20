import unittest

from tests.helpers import TempArchive

A, B = "https://claude.ai/code/artifact/aaa", "https://claude.ai/code/artifact/bbb"


class RepublishTest(TempArchive):
    def publish(self, url, path=None, session="s1", **extra):
        from artikeep.adapters import claude_code
        self.calls.append(1)
        payload = {"tool_name": "Artifact", "cwd": str(self.work), "session_id": session, "tool_use_id": "t%d" % len(self.calls),
                   "tool_input": dict({"file_path": str(path)} if path else {}, **extra), "tool_response": "Published: " + url}
        return claude_code.handle_artifact(self.store, payload)

    def setUp(self):
        super().setUp()
        self.calls = []
        self.page = self.work / "scratch" / "page.html"
        self.page.parent.mkdir()
        self.page.write_text("<!doctype html><title>Plan</title><p>1</p>")

    def edit(self, n):
        self.page.write_text("<!doctype html><title>Plan</title><p>%s</p>" % n)

    def test_same_file_same_session_continues_the_item(self):
        self.publish(A, self.page)
        self.edit(2)
        self.publish(A, self.page)
        self.edit(3)
        self.publish(B, self.page)  # the account changed: a new artifact for the same file
        items = self.manifest()["items"]
        self.assertEqual(list(items), [B])
        e = items[B]
        self.assertEqual((e["url"], e["former_urls"], len(e["versions"])), (B, [A], 3))
        self.assertEqual(e["versions"][-1]["label"], "continued on a new link")
        self.edit(4)
        self.publish(B, self.page)  # then plainly the new link
        self.assertEqual(len(self.manifest()["items"][B]["versions"]), 4)

    def test_the_old_link_finds_the_item_again(self):
        self.publish(A, self.page)
        self.edit(2)
        self.publish(B, self.page)
        self.edit(3)
        self.publish(A, self.page)  # switched back to the first account
        items = self.manifest()["items"]
        self.assertEqual(list(items), [A])
        self.assertEqual((items[A]["former_urls"], len(items[A]["versions"])), ([B], 3))

    def test_other_session_file_or_setting_keeps_them_apart(self):
        self.publish(A, self.page)
        self.publish(B, self.page, session="s2")  # another session: a different piece of work
        other = self.work / "scratch" / "other.html"
        other.write_text("<!doctype html><title>Other</title>")
        self.publish("https://claude.ai/code/artifact/ccc", other)
        self.assertEqual(len(self.manifest()["items"]), 3)
        self.store.settings["continue_republished"] = False
        self.edit(9)
        self.publish("https://claude.ai/code/artifact/ddd", self.page)
        self.assertEqual(len(self.manifest()["items"]), 4)

    def test_a_canvas_made_from_a_type_continues(self):
        t = {"type_url": "https://claude.ai/artifact/type-design", "title": "Stage"}
        root = self.work / "cv"
        (root / "project").mkdir(parents=True)
        (root / "project" / "canvas.json").write_text('{"pages": [], "boards": {}}')
        self.publish(A, **t)
        self.publish(A, root / "project/canvas.json", root=str(root))
        self.publish(B, **t)  # the same canvas made again under the new account: empty so far
        self.assertEqual(len(self.manifest()["items"]), 1)  # type and title say it is the same work already
        self.publish(B, root / "project/canvas.json", root=str(root))
        items = self.manifest()["items"]
        self.assertEqual(list(items), [B])
        self.assertEqual(items[B]["former_urls"], [A])
        self.assertTrue(items[B]["type_url"])
        self.assertEqual(len([d for d in (self.home / "items").iterdir()]), 1)  # no empty folder left behind

    def test_an_empty_new_canvas_is_folded_in_at_its_first_file(self):
        root = self.work / "cv"
        (root / "project").mkdir(parents=True)
        (root / "project" / "canvas.json").write_text('{"pages": [], "boards": {}}')
        # the first link was only seen through its updates (no type or title known)
        self.publish(A, root / "project/canvas.json", root=str(root))
        self.publish(B, type_url="https://claude.ai/artifact/type-design", title="Stage")  # created empty
        self.assertEqual(len(self.manifest()["items"]), 2)
        self.publish(B, root / "project/canvas.json", root=str(root))  # its first file is the same one
        items = self.manifest()["items"]
        self.assertEqual(list(items), [B])
        self.assertEqual(items[B]["former_urls"], [A])
        self.assertEqual(len(list((self.home / "items").iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
