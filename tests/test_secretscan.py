import json
import subprocess
import unittest

from tests.helpers import ENTRY, TempArchive

AWS = "AKIA" + "QWERTYUIOPASDFGH"
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True, check=True).stdout


class ScanTest(TempArchive):
    def test_rules_and_false_alarms(self):
        from artikeep.secretscan import scan_line
        rules = lambda s: [r for r, _ in scan_line(s)]
        self.assertEqual(rules("key = %s" % AWS), ["AWS access key"])
        self.assertEqual(rules("token: %s" % GH), ["GitHub token", "secret-looking value"][:1] + rules("token: %s" % GH)[1:])
        self.assertIn("private key", rules("-----BEGIN RSA PRIVATE KEY-----"))
        self.assertIn("Telegram bot token", rules("bot 123456789:" + "AAH" * 11 + "AA"))
        self.assertEqual(rules('const apiKey = "Zq8vN2xLm4Rt7YpWd1KsHb6JcFg3UeAo"'), ["secret-looking value"])
        for fine in ("AKIAIOSFODNN7EXAMPLE", 'api_key = "your-api-key-goes-here-1234567890"', 'token: "aaaaaaaaaaaaaaaaaaaaaaaa"',
                     'password = "${DB_PASSWORD_VALUE_FROM_ENV}"', "plain prose about tokens and keys", 'secret = "short"'):
            self.assertEqual(rules(fine), [], fine)

    def test_diff_scan_reports_file_and_line(self):
        from artikeep.secretscan import scan_diff
        diff = ("diff --git a/items/x/index.html b/items/x/index.html\n--- a/items/x/index.html\n+++ b/items/x/index.html\n"
                "@@ -1,2 +10,3 @@\n+<p>ok</p>\n+key=%s\n context\n" % AWS
                + "+++ b/items/x/_vendor/lib.js\n@@ -0,0 +1 @@\n+%s\n" % AWS)
        got = scan_diff(diff)
        self.assertEqual([(f["file"], f["line"], f["item"]) for f in got], [("items/x/index.html", 11, "x")])  # vendored files are skipped
        self.assertEqual(scan_diff(diff, allow={got[0]["fp"]}), [])


class PushTest(TempArchive):
    def setUp(self):
        super().setUp()
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        git(self.home, "init", "-q", "-b", "main")
        git(self.home, "config", "user.email", "t@example.com")
        git(self.home, "config", "user.name", "t")
        git(self.home, "remote", "add", "origin", str(self.remote))
        self.store.settings.update({"git_push": True})

    def save(self, text, key="k"):
        e, _ = self.store.save_item(key, {"index.html": text.encode()}, agent="codex", main="index.html", title="Page")
        return e["dir"]

    def sync(self):
        from artikeep import worker
        worker.sync(self.store, True)

    def pushed(self):
        r = subprocess.run(["git", "-C", str(self.remote), "log", "--all", "-p", "--format=%s"], capture_output=True, text=True)
        return r.stdout

    def test_clean_archive_is_pushed(self):
        self.save("<p>fine</p>")
        self.sync()
        self.assertIn("fine", self.pushed())

    def test_secret_holds_the_push_and_allow_releases_it(self):
        d = self.save("<p>debug</p><pre>aws=%s</pre>" % AWS)
        self.sync()
        self.assertNotIn(AWS, self.pushed())
        held = json.loads((self.store.log / "secrets.json").read_text())
        self.assertEqual((held[0]["rule"], held[0]["item"]), ("AWS access key", d))
        self.assertIn(AWS, git(self.home, "log", "-p", "--all"))  # kept locally
        from artikeep import secretscan
        self.assertTrue(secretscan.allow(self.store, d))
        self.sync()
        self.assertIn(AWS, self.pushed())
        self.assertFalse((self.store.log / "secrets.json").exists())

    def test_removed_secret_is_squashed_away_before_the_push(self):
        self.save("<p>one</p>")
        self.sync()
        leaky = self.save("<p>two</p><pre>%s</pre>" % GH, key="leaky")
        git(self.home, "add", "-A")
        git(self.home, "commit", "-q", "-m", "with secret")
        self.store.delete(leaky)  # the item is deleted again (its versions keep old text, so an edit would not do)
        self.save("<p>three</p>", key="third")
        self.sync()
        out = self.pushed()
        self.assertIn("three", out)
        self.assertNotIn(GH, out)
        self.assertFalse((self.store.log / "secrets.json").exists())

    def test_first_push_checks_the_whole_tree(self):
        from artikeep import secretscan
        self.save("<pre>%s</pre>" % AWS)
        git(self.home, "add", "-A")
        git(self.home, "commit", "-q", "-m", "x")
        history, net, base = secretscan.unpushed(self.store)  # nothing pushed yet: no remote branch
        self.assertIsNone(base)
        self.assertTrue(history)
        self.assertTrue(net)  # the net change is the whole tree, not an empty diff

    def test_modes(self):
        self.store.settings["secret_scan"] = "warn"
        self.save("<pre>%s</pre>" % AWS)
        self.sync()
        self.assertIn(AWS, self.pushed())  # warn pushes anyway
        self.store.settings["secret_scan"] = "off"
        self.save("<pre>%s</pre>" % GH)
        self.sync()
        self.assertIn(GH, self.pushed())

    def test_cli_lists_and_allows(self):
        import os
        d = self.save("<pre>%s</pre>" % AWS)
        git(self.home, "add", "-A")
        git(self.home, "commit", "-q", "-m", "x")
        env = dict(os.environ, ARTIKEEP_HOME=str(self.home))
        run = lambda *a: subprocess.run(["/usr/bin/env", "python3", str(ENTRY), *a], capture_output=True, text=True, env=env)
        r = run("secrets")
        self.assertEqual(r.returncode, 1)
        self.assertIn("AWS access key", r.stdout)
        self.assertIn(d, r.stdout)
        self.assertEqual(run("allow", "nope").returncode, 1)
        self.assertEqual(run("allow", d, "--rule", "aws access key").returncode, 0)
        self.assertEqual(run("secrets").returncode, 0)
        self.assertIn(json.loads((self.home / "artikeep.json").read_text())["secret_allow"][0], "".join(json.loads((self.home / "artikeep.json").read_text())["secret_allow"]))


if __name__ == "__main__":
    unittest.main()
