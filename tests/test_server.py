import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.helpers import TempArchive


def free_pair() -> int:
    """A port p with p and p + 1 free."""
    for _ in range(50):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        t = socket.socket()
        try:
            t.bind(("127.0.0.1", p + 1))
            return p
        except OSError:
            continue
        finally:
            t.close()
    raise RuntimeError("no free port pair")


class ServerTest(TempArchive):
    def setUp(self):
        super().setUp()
        from artikeep import server
        self.e1, _ = self.store.save_item("a", {"index.html": "<title>Кухня</title><p>планировка кухни</p>".encode()},
                                          agent="codex", main="index.html")
        self.store.save_item("a", {"index.html": "<title>Кухня</title><p>планировка кухни и гостиной</p>".encode()},
                             agent="codex", main="index.html")
        port = free_pair()
        self.app = server.App(self.store, port)
        self.api = ThreadingHTTPServer(("127.0.0.1", port), server.app_handler(self.app))
        self.content = ThreadingHTTPServer(("127.0.0.1", port + 1), server.content_handler(self.app))
        for s in (self.api, self.content):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        self.B, self.C = "http://127.0.0.1:%d" % port, "http://127.0.0.1:%d" % (port + 1)
        self.H = {"X-Artikeep-Token": self.app.token}

    def tearDown(self):
        for s in (self.api, self.content):
            s.shutdown()
            s.server_close()
        super().tearDown()

    def req(self, url, method="GET", data=None, headers=None):
        r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path, body):
        return self.req(self.B + path, "POST", json.dumps(body).encode(), dict(self.H, **{"Content-Type": "application/json"}))

    def test_api_needs_token_and_local_host(self):
        self.assertEqual(self.req(self.B + "/api/data")[0], 403)
        self.assertEqual(self.req(self.B + "/api/data", headers={"X-Artikeep-Token": "x"})[0], 403)
        self.assertEqual(self.req(self.B + "/api/data", headers=dict(self.H, Host="attacker.example"))[0], 403)
        self.assertEqual(self.req(self.B + "/api/data", "OPTIONS")[0], 403)
        st, body = self.req(self.B + "/api/data", headers=self.H)
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["items"][0]["title"], "Кухня")
        st, page = self.req(self.B + "/")
        self.assertIn(self.app.token.encode(), page)  # the page carries the token; other origins cannot read it

    def test_content_origin_serves_items_only(self):
        d = self.e1["dir"]
        self.assertEqual(self.req(self.C + "/items/%s/index.html" % d)[0], 200)
        for bad in ("/manifest.json", "/.hooklog/errors.log", "/items/../manifest.json", "/api/data"):
            self.assertEqual(self.req(self.C + bad, headers=self.H)[0], 404, bad)
        self.assertEqual(self.req(self.B + "/items/%s/index.html" % d)[0], 404)  # artifacts never on the app origin

    def test_full_text_search(self):
        st, body = self.req(self.B + "/api/search?q=%D0%B3%D0%BE%D1%81%D1%82%D0%B8%D0%BD%D0%BE%D0%B9", headers=self.H)  # гостиной
        hits = json.loads(body)["hits"]
        self.assertEqual([h["id"] for h in hits], [self.e1["dir"]])
        self.assertIn("[гостиной]", hits[0]["snippet"])

    def test_edit_restore_delete(self):
        d = self.e1["dir"]
        sig = json.loads(self.req(self.B + "/api/version", headers=self.H)[1])["sig"]
        self.assertEqual(self.post("/api/item/%s/edit" % d, {"title": "Кухня 2", "description": "заметка"})[0], 200)
        self.assertNotEqual(json.loads(self.req(self.B + "/api/version", headers=self.H)[1])["sig"], sig)
        self.assertEqual(self.post("/api/item/%s/restore" % d, {"n": 1})[0], 200)
        e = self.manifest()["items"]["a"]
        self.assertEqual((e["title"], e["description"]), ("Кухня 2", "заметка"))
        self.assertEqual([v["label"] for v in e["versions"]], [None, None, "restored v1"])
        self.assertNotIn("гостиной", (self.home / "items" / d / "index.html").read_text())
        self.assertEqual(self.post("/api/item/%s/restore" % d, {"n": 9})[0], 404)
        self.assertEqual(self.post("/api/item/%s/delete" % d, {})[0], 200)
        self.assertNotIn("a", self.manifest()["items"])
        self.assertFalse((self.home / "items" / d).exists())

    def test_upload_detects_exports(self):
        conv = [{"uuid": "c", "name": "n", "chat_messages": [{"content": [{"type": "tool_use", "name": "artifacts",
                 "input": {"id": "x", "type": "text/markdown", "title": "Notes", "command": "create", "content": "# N"}}]}]}]
        st, body = self.req(self.B + "/api/upload?name=conversations.json", "POST", json.dumps(conv).encode(), self.H)
        self.assertEqual((st, json.loads(body)["kind"]), (200, "claude-ai"))
        st, body = self.req(self.B + "/api/upload?name=report.md", "POST", b"# Report", self.H)
        self.assertEqual(json.loads(body)["kind"], "file")
        agents = sorted(e["agent"] for e in self.manifest()["items"].values())
        self.assertEqual(agents, ["claude-ai", "codex", "import"])


class NotifyTest(TempArchive):
    def test_rate_limited_and_text_passed_as_argument(self):
        from artikeep import notify
        self.store.settings["notify"] = True
        calls = []
        with mock.patch.object(notify.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd)), \
                mock.patch.object(notify.shutil, "which", lambda name: "/usr/bin/" + name), \
                mock.patch.object(notify.sys, "platform", "darwin"):
            self.assertTrue(notify.notify(self.store, "publish", 'copy "not" saved'))
            self.assertFalse(notify.notify(self.store, "publish", "again"))  # within the hour
            self.assertTrue(notify.notify(self.store, "push", "other kind"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "osascript")
        self.assertIn('copy "not" saved', calls[0])  # an argv item, never spliced into AppleScript
        self.assertFalse(any('copy "not" saved' in part for part in calls[0][1:-2]))

    def test_off_switch(self):
        from artikeep import notify
        self.store.settings["notify"] = False
        self.assertFalse(notify.notify(self.store, "x", "y"))


if __name__ == "__main__":
    unittest.main()
