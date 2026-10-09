"""`artikeep serve`: the gallery as a local app — full-text search, live updates, actions.

Two servers, both bound to 127.0.0.1 only:
  app      PORT     the gallery page and its JSON API
  content  PORT+1   archived files (items/, drafts/), read-only

Archived pages run arbitrary JavaScript. Serving them from another origin keeps that
code away from the API: it can neither read the app page nor send the per-run token
the API requires on every call. The Host header must name 127.0.0.1 or localhost, so a
web page cannot reach the API through DNS rebinding either. Nothing listens beyond
this machine.
"""
from __future__ import annotations

import contextlib
import io
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from artikeep import gallery, search
from artikeep.store import Store
from artikeep.util import now_iso, title_of

MAX_UPLOAD = 200 * 1024 * 1024
CONTENT_DIRS = ("items", "drafts")
mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".jsx")


def _hosts(port: int) -> set:
    return {"127.0.0.1:%d" % port, "localhost:%d" % port}


class App:
    def __init__(self, store: Store, port: int):
        self.store = store
        self.port = port
        self.content_port = port + 1
        self.token = secrets.token_urlsafe(24)

    # ------------------------------------------------------------ data

    def signature(self) -> str:
        """Changes whenever anything the gallery shows changes."""
        parts = []
        for p in (self.store.manifest_path, self.store.root / "drafts"):
            try:
                parts.append(str(p.stat().st_mtime_ns))
            except FileNotFoundError:
                parts.append("-")
        droot = self.store.root / "drafts"
        if droot.exists():
            parts += [str(d.stat().st_mtime_ns) for d in droot.iterdir() if d.is_dir()]
        return ":".join(parts)

    def data(self) -> dict:
        d = gallery.gallery_data(self.store, self.store.load())
        d["sig"] = self.signature()
        return d

    def page(self) -> bytes:
        live = {"api": "http://127.0.0.1:%d/api/" % self.port, "content": "http://127.0.0.1:%d/" % self.content_port,
                "token": self.token}
        blob = json.dumps(self.data(), ensure_ascii=False).replace("</", "<\\/")
        html = gallery.TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", blob)
        inject = "<script>window.ARTIKEEP_LIVE = %s;</script>\n" % json.dumps(live)
        return html.replace('<script type="application/json" id="data">', inject + '<script type="application/json" id="data">', 1).encode()

    # ------------------------------------------------------------ actions

    def after_change(self) -> None:
        gallery.build(self.store, self.store.load())  # the static page stays current too
        self.store.kick()  # viewers, index, commit

    def act(self, folder: str, action: str, body: dict) -> dict:
        st = self.store
        if action == "edit":
            st.edit(folder, body.get("title"), body.get("description"))
        elif action == "restore":
            if not st.restore(folder, int(body["n"])):
                return {"ok": True, "note": "unchanged"}
        elif action == "delete":
            st.delete(folder)
        elif action == "reveal":
            target = st.items / folder
            if not target.is_dir():
                raise KeyError(folder)
            opener = ["open", "-R", str(target / "index.html") if (target / "index.html").exists() else str(target)] \
                if sys.platform == "darwin" else ["xdg-open", str(target)]
            subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True}
        else:
            raise ValueError("unknown action %s" % action)
        self.after_change()
        return {"ok": True}

    def upload(self, name: str, data: bytes) -> dict:
        """A dropped file: a chat export is imported, anything else is kept as is."""
        name = Path(name).name or "upload"
        tmp = self.store.cache / "uploads" / name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        try:
            kind = None
            if name.lower().endswith((".zip", ".json")):
                from artikeep.importers import read_export_json
                try:
                    conv = read_export_json(tmp)
                    first = conv[0] if isinstance(conv, list) and conv else {}
                    kind = "chatgpt" if "mapping" in first else "claude-ai" if "chat_messages" in first else None
                except (SystemExit, Exception):
                    kind = None
            if kind == "chatgpt":
                from artikeep.importers.chatgpt import import_export
                stats = import_export(self.store, tmp)
            elif kind == "claude-ai":
                from artikeep.importers.claude_ai import import_export
                stats = import_export(self.store, tmp)
            else:
                main = "index.html" if name.lower().endswith((".html", ".htm")) else name
                entry, vdir = self.store.save_item("upload:" + name, {main: data}, agent="import", main=main,
                                                   title=title_of(name, data), origin=name, when=now_iso())
                stats = {"saved": entry["dir"], "new_version": bool(vdir)}
            self.after_change()
            return dict(stats, ok=True, kind=kind or "file")
        finally:
            tmp.unlink(missing_ok=True)

    def doctor(self) -> str:
        from artikeep import install
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            install.doctor(self.store, quick=True)
        return out.getvalue()


def app_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "artikeep"

        def log_message(self, *a):
            pass

        def send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def json(self, obj, code: int = 200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode())

        def guard(self) -> bool:
            if self.headers.get("Host") not in _hosts(app.port):
                self.json({"error": "bad host"}, 403)
                return False
            if self.path.startswith("/api/") and not secrets.compare_digest(self.headers.get("X-Artikeep-Token") or "", app.token):
                self.json({"error": "missing or wrong token"}, 403)
                return False
            return True

        def do_GET(self):
            if not self.guard():
                return
            url = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(url.query)
            try:
                if url.path in ("/", "/index.html"):
                    self.send(200, app.page(), "text/html; charset=utf-8",
                              {"Content-Security-Policy": "frame-ancestors 'none'", "Referrer-Policy": "no-referrer"})
                elif url.path == "/api/version":
                    self.json({"sig": app.signature()})
                elif url.path == "/api/data":
                    self.json(app.data())
                elif url.path == "/api/search":
                    hits = search.search(app.store, (q.get("q") or [""])[0], limit=int((q.get("limit") or ["200"])[0]))
                    self.json({"hits": [{"id": h["id"], "snippet": h["snippet"]} for h in hits]})
                elif url.path == "/api/doctor":
                    self.json({"text": app.doctor()})
                else:
                    self.json({"error": "not found"}, 404)
            except Exception as ex:
                app.store.error("serve GET %s" % url.path)
                self.json({"error": str(ex)}, 500)

        def do_POST(self):
            if not self.guard():
                return
            url = urllib.parse.urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                self.json({"error": "too large"}, 413)
                return
            raw = self.rfile.read(length) if length else b""
            parts = url.path.strip("/").split("/")
            try:
                if parts[:2] == ["api", "item"] and len(parts) == 4:
                    body = json.loads(raw or b"{}")
                    self.json(app.act(urllib.parse.unquote(parts[2]), parts[3], body))
                elif url.path == "/api/upload":
                    name = urllib.parse.parse_qs(url.query).get("name", ["upload"])[0]
                    self.json(app.upload(name, raw))
                else:
                    self.json({"error": "not found"}, 404)
            except KeyError as ex:
                self.json({"error": "no such item or version: %s" % ex}, 404)
            except Exception as ex:
                app.store.error("serve POST %s" % url.path)
                self.json({"error": str(ex)}, 500)

        def do_OPTIONS(self):  # no CORS: preflights from other origins are refused
            self.send(403, b"")

    return Handler


def content_handler(app: App):
    roots = [(app.store.root / d).resolve() for d in CONTENT_DIRS]

    class Handler(BaseHTTPRequestHandler):
        server_version = "artikeep"

        def log_message(self, *a):
            pass

        def do_GET(self):
            self.serve(body=True)

        def do_HEAD(self):
            self.serve(body=False)

        def deny(self, code: int):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def serve(self, body: bool):
            if self.headers.get("Host") not in _hosts(app.content_port):
                return self.deny(403)
            rel = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).lstrip("/")
            target = (app.store.root / rel).resolve()
            if not any(target == r or r in target.parents for r in roots):
                return self.deny(404)  # only items/ and drafts/: never the manifest, logs or cache
            if target.is_dir():
                if not self.path.split("?")[0].endswith("/"):
                    self.send_response(301)
                    self.send_header("Location", self.path.split("?")[0] + "/")
                    self.end_headers()
                    return
                index = target / "index.html"
                if index.is_file():
                    target = index
                else:
                    names = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
                    page = "<!doctype html><meta charset=utf-8><ul>%s</ul>" % "".join(
                        '<li><a href="%s">%s</a>' % (urllib.parse.quote(n), n.replace("<", "&lt;")) for n in names)
                    data = page.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if body:
                        self.wfile.write(data)
                    return
            if not target.is_file():
                return self.deny(404)
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
                ctype += "; charset=utf-8"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if body:
                self.wfile.write(data)

    return Handler


def serve(store: Store, port: int = 8765, open_browser: bool = False) -> int:
    store.ensure()
    app = App(store, port)
    try:
        api = ThreadingHTTPServer(("127.0.0.1", port), app_handler(app))
        content = ThreadingHTTPServer(("127.0.0.1", port + 1), content_handler(app))
    except OSError as ex:
        print("artikeep serve: ports %d and %d must be free (%s); try --port" % (port, port + 1, ex), file=sys.stderr)
        return 1
    api.daemon_threads = content.daemon_threads = True
    threading.Thread(target=content.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % port
    print("artikeep: %s  (archive %s; Ctrl+C stops)" % (url, store.root), flush=True)
    if open_browser and not os.environ.get("ARTIKEEP_NO_BROWSER"):
        webbrowser.open(url)
    try:
        api.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        api.server_close()
        content.shutdown()
        content.server_close()
    return 0
