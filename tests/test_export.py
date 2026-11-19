import io
import json
import os
import subprocess
import unittest
import zipfile
from pathlib import Path

from tests.helpers import ENTRY, TempArchive

PAGE = """<!doctype html><html><head><title>Plan</title>
<link rel="stylesheet" href="css/app.css"><link rel="icon" href="img/i.png">
<script src="js/app.js"></script>
<script src="https://cdn.example.com/lib.js"></script>
<style>.hero{background:url(img/bg.png)}</style></head>
<body style="background:url('img/bg.png')"><img src="img/pic.png" alt=""><a href="other.html">next</a>
<img src="img/gone.png"><iframe src="inner.html"></iframe></body></html>"""


class ExportTest(TempArchive):
    def make(self):
        files = {"index.html": PAGE, "css/app.css": "body{font:url(../img/f.woff2)}", "js/app.js": "var x=1;</script><b>",
                 "img/pic.png": "PNG1", "img/bg.png": "PNG2", "img/i.png": "PNG3", "img/f.woff2": "FONT",
                 "inner.html": '<img src="img/pic.png"><script src="js/app.js"></script>', "other.html": "<p>other</p>"}
        e, _ = self.store.save_item("k", {k: v.encode() for k, v in files.items()}, agent="claude-code", main="index.html", title="Plan")
        files["index.html"] = PAGE.replace("Plan", "Plan 2")
        self.store.save_item("k", {k: v.encode() for k, v in files.items()}, agent="claude-code", main="index.html", title="Plan 2")
        return e["dir"]

    def test_html_is_one_file(self):
        from artikeep import export
        name, data, notes = export.build(self.store, self.make(), "html")
        text = data.decode()
        self.assertTrue(name.endswith(".html"))
        for gone in ('href="css/app.css"', 'src="js/app.js"', 'src="img/pic.png"', "url(img/bg.png)", "url('img/bg.png')", 'src="inner.html"'):
            self.assertNotIn(gone, text)
        self.assertIn("font:url(data:font/woff2;base64,", text)  # a url inside the stylesheet
        self.assertIn("var x=1;<\\/script><b>", text)  # a closing tag in a script stays inert
        self.assertIn('src="data:image/png;base64,', text)
        self.assertIn('srcdoc="', text)  # the frame carries its page, and its own files
        self.assertIn('href="other.html"', text)  # a plain link is left as it is
        self.assertIn("https://cdn.example.com/lib.js", text)
        self.assertTrue(any("cdn.example.com" in n for n in notes))
        self.assertTrue(any("img/gone.png" in n for n in notes))

    def test_a_version_and_the_archive_stays_untouched(self):
        from artikeep import export
        d = self.make()
        before = sorted(str(p.relative_to(self.home)) for p in (self.home / "items" / d).rglob("*"))
        name, data, _ = export.build(self.store, d, "html", 1)
        self.assertEqual(name, "%s-v1.html" % d)
        self.assertIn("<title>Plan</title>", data.decode())
        self.assertEqual(export.build(self.store, d, "html", 2)[0], "%s.html" % d)
        self.assertEqual(sorted(str(p.relative_to(self.home)) for p in (self.home / "items" / d).rglob("*")), before)
        with self.assertRaises(export.ExportError):
            export.build(self.store, d, "html", 9)

    def test_zip_has_the_files_and_a_readme(self):
        from artikeep import export
        d = self.make()
        name, data, _ = export.build(self.store, d, "zip", 1)
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertIn("%s-v1/index.html" % d, names)
        self.assertIn("%s-v1/img/pic.png" % d, names)
        self.assertFalse([n for n in names if "/versions/" in n])
        self.assertIn("Version:  1 of 2", zipfile.ZipFile(io.BytesIO(data)).read("%s-v1/README.txt" % d).decode())

    def test_not_a_page_and_bad_input(self):
        from artikeep import export
        e, _ = self.store.save_item("m", {"notes.md": b"# n"}, agent="import", main="notes.md")
        with self.assertRaises(export.ExportError) as c:
            export.build(self.store, e["dir"], "html")
        self.assertIn("--format zip", str(c.exception))
        self.assertTrue(export.build(self.store, e["dir"], "zip")[0].endswith(".zip"))
        with self.assertRaises(export.ExportError):
            export.build(self.store, "nope", "html")
        with self.assertRaises(export.ExportError):
            export.build(self.store, e["dir"], "docx")

    def test_canvas_boards_come_along(self):
        from artikeep import export
        canvas = {"title": "W", "pages": [], "boards": {"A one.dc.html": {"x": 0, "y": 0, "w": 300, "h": 200}}}
        files = {"project/canvas.json": json.dumps(canvas).encode(), "project/A one.dc.html": b'<p>board</p><script src="support.js"></script>',
                 "project/support.js": b"window.S=1"}
        e, _ = self.store.save_item("c", files, agent="claude-code", title="W")
        item = self.home / "items" / e["dir"]
        from artikeep.viewers import make_canvas_viewer
        make_canvas_viewer(item)  # the viewer as an older release wrote it: no board slot
        (item / "index.html").write_text((item / "index.html").read_text().replace("const INLINE = {};  // artikeep export puts the boards here, so the file stands alone", ""))
        text = export.build(self.store, e["dir"], "html")[1].decode()
        self.assertIn("window.S=1", text)  # the board's own script
        self.assertIn("<p>board<\\/p>", text)  # inside a script, so its closing tags are escaped
        self.assertIn('const INLINE = {"project/A%20one.dc.html"', text)

    def test_cli(self):
        d = self.make()
        env = dict(os.environ, ARTIKEEP_HOME=str(self.home))
        run = lambda *a, cwd=self.work: subprocess.run(["/usr/bin/env", "python3", str(ENTRY), "export", *a], capture_output=True, text=True, env=env, cwd=str(cwd))
        r = run(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.work / ("%s.html" % d)).exists())
        again = run(d)  # never overwrites without -o
        self.assertEqual(again.returncode, 1)
        self.assertIn("-o", again.stderr)
        out = self.work / "send.zip"
        self.assertEqual(run(d, "--format", "zip", "--version", "1", "-o", str(out)).returncode, 0)
        self.assertTrue(zipfile.is_zipfile(out))
        self.assertEqual(run("nope").returncode, 1)

    @unittest.skipUnless(subprocess.run(["python3", "-c", "import playwright"], capture_output=True).returncode == 0, "no Playwright")
    def test_pdf(self):
        from artikeep import export
        name, data, _ = export.build(self.store, self.make(), "pdf")
        self.assertTrue(name.endswith(".pdf"))
        self.assertTrue(data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
