import json
import unittest

from tests.helpers import TempArchive


class InstallTest(TempArchive):
    def test_merge_keeps_foreign_hooks_and_replaces_ours(self):
        from artikeep.install import hook_command, merge_hooks
        hooks = {
            "Stop": [{"hooks": [{"type": "command", "command": "other-tool --stop"}]},
                     {"hooks": [{"type": "command", "command": "python3 ~/claude-artifacts/tools/artifact_archive.py drafts"}]}],
            "PostToolUse": [{"matcher": "Artifact", "hooks": [{"type": "command", "command": hook_command("claude-code", "publish")}]}],
        }
        wanted = [("Stop", "", hook_command("codex", "stop"), 30)]
        merge_hooks(hooks, wanted, uninstall=False)
        cmds = [h["command"] for g in hooks["Stop"] for h in g["hooks"]]
        self.assertEqual(len(cmds), 2)
        self.assertIn("other-tool --stop", cmds)
        self.assertNotIn("PostToolUse", hooks)  # our old entry gone, nothing else there
        merge_hooks(hooks, wanted, uninstall=True)
        self.assertEqual([h["command"] for g in hooks["Stop"] for h in g["hooks"]], ["other-tool --stop"])

    def test_codex_stop_command_always_prints_json(self):
        from artikeep.install import hook_command
        self.assertTrue(hook_command("codex", "stop").endswith("|| echo '{}'"))
        self.assertTrue(hook_command("claude-code", "stop").endswith("|| true"))

    def test_rules_block_replaces_old_block(self):
        from artikeep.install import MARK_BEGIN, OLD_MARKS, rules, strip_block
        text = "# Mine\n\n%s\nold rules\n%s\n\n## After\n" % OLD_MARKS
        out = strip_block(strip_block(text, *OLD_MARKS), MARK_BEGIN, "<!-- artikeep:end -->").rstrip("\n") + "\n\n" + rules(self.store, "codex")
        self.assertNotIn("old rules", out)
        self.assertIn("## After", out)
        self.assertEqual(out.count(MARK_BEGIN), 1)


class DoctorTest(TempArchive):
    def doctor_output(self, settings: dict) -> tuple:
        import contextlib
        import io
        from unittest import mock
        from artikeep import install
        path = self.tmp / "settings.json"
        path.write_text(json.dumps(settings))
        out = io.StringIO()
        with mock.patch.object(install, "CLAUDE_SETTINGS", path), mock.patch.object(install, "CODEX_HOOKS", self.tmp / "none.json"), \
                mock.patch.object(install.shutil, "which", lambda _: None), contextlib.redirect_stdout(out):
            rc = install.doctor(self.store)
        return rc, out.getvalue()

    def test_plugin_counts_as_installed(self):
        rc, out = self.doctor_output({"enabledPlugins": {"artikeep@artikeep": True}, "cleanupPeriodDays": 3650})
        self.assertEqual(rc, 0, out)
        self.assertIn("from the artikeep plugin", out)

    def test_plugin_plus_installer_is_flagged(self):
        from artikeep.install import hook_command
        hooks = {"Stop": [{"hooks": [{"type": "command", "command": hook_command("claude-code", "stop")}]}]}
        rc, out = self.doctor_output({"enabledPlugins": {"artikeep@artikeep": True}, "hooks": hooks, "cleanupPeriodDays": 3650})
        self.assertEqual(rc, 1)
        self.assertIn("saved twice", out)

    def test_short_transcript_retention_says_how_to_fix(self):
        rc, out = self.doctor_output({"enabledPlugins": {"artikeep@artikeep": True}})
        self.assertEqual(rc, 1)
        self.assertIn('"cleanupPeriodDays": 3650', out)


class ReactViewerTest(TempArchive):
    def test_viewer_loads_only_what_the_component_imports(self):
        from artikeep.viewers import make_react_viewer
        code = 'import { LineChart } from "recharts";\nimport { Home } from "lucide-react";\nexport default () => <Home/>;'
        e, _ = self.store.save_item("r", {"app.jsx": code.encode()}, agent="claude-ai", main="app.jsx", title="App")
        d = self.store.item_dir(e)
        make_react_viewer(d, e)
        page = (d / "index.html").read_text(encoding="utf-8")
        self.assertIn("artikeep react viewer", page)
        for lib in ("react.production", "babel.min.js", "Recharts.js", "prop-types", "lucide-react"):
            self.assertIn(lib, page)
        for lib in ("three.min.js", "d3.min.js", "Tone.js"):
            self.assertNotIn(lib, page)
        self.assertLess(page.index("window.react = window.React"), page.index("lucide-react.min.js"))
        self.assertNotIn("index.html", self.store.version_files(d))  # the viewer is rebuilt, not versioned

    def test_real_page_is_not_replaced(self):
        from artikeep.viewers import make_react_viewer
        e, _ = self.store.save_item("r2", {"index.html": b"<title>Real</title>", "app.jsx": b"export default () => null"},
                                    agent="import", main="app.jsx")
        d = self.store.item_dir(e)
        make_react_viewer(d, e)
        self.assertEqual((d / "index.html").read_bytes(), b'<meta charset="utf-8">\n<title>Real</title>')


class SearchGalleryTest(TempArchive):
    def test_search_and_gallery_build(self):
        from artikeep import gallery, search, worker
        self.store.save_item("p", {"index.html": "<title>Тепловая карта</title><p>расходы по месяцам</p>".encode()},
                             agent="codex", main="index.html")
        self.store.save_item("f", {"deck.pptx": b"PK fake"}, agent="import", main="deck.pptx", title="Deck")
        hits = search.search(self.store, "РАСХОДЫ")
        self.assertEqual([h["title"] for h in hits], ["Тепловая карта"])
        worker.one_pass(self.store, push=False)
        html = (self.home / "index.html").read_text(encoding="utf-8")
        data = json.loads(html.split('id="data">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
        types = {i["title"]: (i["type"], i["agent"], i["main"]) for i in data["items"]}
        self.assertEqual(types["Deck"], ("file", "import", "deck.pptx"))
        self.assertEqual(types["Тепловая карта"], ("page", "codex", "index.html"))
        self.assertEqual(gallery.origin_of({"url": "https://chatgpt.com/c/x"}, "k")["label"], "ChatGPT")


if __name__ == "__main__":
    unittest.main()
