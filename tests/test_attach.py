import json
import os
import subprocess
import unittest
from unittest import mock

from tests.helpers import ENTRY, TempArchive

HAS_PW = subprocess.run(["python3", "-c", "import playwright"], capture_output=True).returncode == 0


class FakeGh:
    """Stands in for the gh command: records calls, answers like GitHub for one private repo."""

    def __init__(self, private=True, comments=()):
        self.calls, self.files, self.private, self.comments = [], {}, private, list(comments)
        self.branch = False

    def __call__(self, *args, input=None):
        from artikeep.attach import AttachError
        self.calls.append((args, input))
        a = " ".join(args)
        if a.endswith("--jq .private"):
            return "true" if self.private else "false"
        if "user --jq" in a:
            return "me\n"
        if "/git/ref/heads/artikeep-attachments" in a:
            if not self.branch:
                raise AttachError("not found")
            return "sha"
        if a.startswith("api repos/o/r --jq .default_branch"):
            return "main"
        if "/git/ref/heads/main" in a:
            return "abc123"
        if "git/refs" in a:
            self.branch = True
            return ""
        if "/contents/" in a and "-X PUT" in a:
            self.files[args[args.index("-X") + 2].split("/contents/")[1]] = True
            return ""
        if "/contents/" in a:
            path = args[1].split("/contents/")[1].split("?")[0]
            if path in self.files:
                return "sha"
            raise AttachError("not found")
        if "--paginate" in a:
            return "\n".join(str(i) for i, body in self.comments if body in args[-1]) + "\n"
        if "-X PATCH" in a:
            return "https://github.com/o/r/pull/7#issuecomment-1\n"
        if "issues/7/comments" in a:
            return "https://github.com/o/r/pull/7#issuecomment-2\n"
        raise AssertionError("unexpected gh call: %s" % a)


class AttachTest(TempArchive):
    def make(self):
        page = "<!doctype html><title>Dash</title><h1>%s</h1><p>filters</p>"
        e, _ = self.store.save_item("k", {"index.html": (page % "one").encode()}, agent="claude-code", main="index.html", title="Dash",
                                    url="https://claude.ai/artifact/x", request="move the filters")
        self.store.save_item("k", {"index.html": (page % "two").encode()}, agent="claude-code", main="index.html", title="Dash", request="secret ask")
        return e["dir"]

    def run_attach(self, gh, d, **kw):
        from artikeep import attach
        with mock.patch.object(attach, "_gh", gh):
            return attach.run(self.store, d, 7, repo="o/r", **kw)

    def test_comment_text_only(self):
        d = self.make()
        gh = FakeGh()
        r = self.run_attach(gh, d, images=False)
        body = [c[1] for c in gh.calls if c[1]][0]
        self.assertIn("<!-- artikeep:attach:%s:1-2 -->" % d, body)
        self.assertIn("### Dash: v1 → v2", body)
        self.assertIn("- Dash one", body)
        self.assertIn("+ Dash two", body)
        self.assertIn("Original: https://claude.ai/artifact/x", body)
        self.assertNotIn("secret ask", body)  # a request is opt-in
        self.assertNotIn("![", body)
        self.assertEqual((r["updated"], r["url"].endswith("issuecomment-2")), (False, True))

    def test_with_request_and_versions(self):
        d = self.make()
        gh = FakeGh()
        self.run_attach(gh, d, images=False, with_request=True, frm=1, to=2)
        self.assertIn("> secret ask", [c[1] for c in gh.calls if c[1]][0])

    def test_same_marker_updates_the_comment(self):
        d = self.make()
        from artikeep.attach import marker
        gh = FakeGh(comments=[(99, marker(d, 1, 2))])
        r = self.run_attach(gh, d, images=False)
        self.assertTrue(r["updated"])
        self.assertTrue(any("-X PATCH" in " ".join(c[0]) and "comments/99" in " ".join(c[0]) for c in gh.calls))

    def test_public_repo_is_refused_without_the_flag(self):
        from artikeep.attach import AttachError
        d = self.make()
        gh = FakeGh(private=False)
        with self.assertRaises(AttachError) as c:
            self.run_attach(gh, d, images=False)
        self.assertIn("--public", str(c.exception))
        self.assertFalse(any("issues/7/comments" in " ".join(x[0]) for x in gh.calls))
        self.run_attach(FakeGh(private=False), d, images=False, public=True)

    def test_dry_run_touches_nothing(self):
        d = self.make()
        gh = FakeGh()
        r = self.run_attach(gh, d, images=False, dry_run=True)
        self.assertEqual(gh.calls, [])
        self.assertIn("v1 → v2", r["body"])

    def test_bad_input(self):
        from artikeep.attach import AttachError
        d = self.make()
        for kw in ({"frm": 1, "to": 1}, {"frm": 1, "to": 9}):
            with self.assertRaises(AttachError):
                self.run_attach(FakeGh(), d, images=False, **kw)
        one, _ = self.store.save_item("solo", {"index.html": b"<title>S</title>"}, agent="codex", main="index.html")
        with self.assertRaises(AttachError):
            self.run_attach(FakeGh(), one["dir"], images=False)
        with self.assertRaises(AttachError):
            self.run_attach(FakeGh(), "nope", images=False)

    @unittest.skipUnless(HAS_PW, "no Playwright")
    def test_images_go_to_the_attachments_branch(self):
        d = self.make()
        gh = FakeGh()
        self.run_attach(gh, d)
        body = [c[1] for c in gh.calls if c[1]][0]
        self.assertEqual(body.count("](https://github.com/o/r/blob/artikeep-attachments/artikeep/%s/v" % d), 2)
        self.assertEqual(len(gh.files), 2)
        self.assertTrue(gh.branch)
        before = len(gh.calls)
        self.run_attach(gh, d)  # again: same bytes, nothing uploaded twice
        self.assertEqual(len(gh.files), 2)

    def test_cli_dry_run_and_errors(self):
        d = self.make()
        env = dict(os.environ, ARTIKEEP_HOME=str(self.home))
        run = lambda *a: subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "attach", *a], capture_output=True, text=True, env=env)
        r = run(d, "--pr", "7", "--repo", "o/r", "--no-images", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("v1 → v2", r.stdout)
        bad = run(d, "--pr", "7")  # no remote on the item's project
        self.assertEqual(bad.returncode, 1)
        self.assertIn("--repo", bad.stderr)


if __name__ == "__main__":
    unittest.main()
