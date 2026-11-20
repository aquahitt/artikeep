import json
import subprocess
import unittest

from tests.helpers import TempArchive

HAS_PW = subprocess.run(["python3", "-c", "import playwright"], capture_output=True).returncode == 0

BOARD = """<!doctype html><html><head><meta charset="utf-8"><title>B</title><script src="./support.js"></script></head><body>
<x-dc><helmet><style>.hot{color:rgb(1,2,3)}</style></helmet>
<div id="root" class="{{cls}}" style="{{box}}" title="n={{count}} {{label}}">
  <h1>{{title}}</h1>
  <sc-if value="{{show}}"><p id="shown">visible</p></sc-if>
  <sc-if value="{{hide}}"><p id="hidden">invisible</p></sc-if>
  <sc-for list="{{rows}}" as="r"><i class="row">{{$index}}:{{r.name}}:{{r.deep.v}}</i></sc-for>
  <button id="b" onClick="{{bump}}">go {{count}}</button><input id="i" value="{{label}}">
  <svg viewBox="0 0 10 10"><path d="{{d}}"/></svg>
  <dc-import name="Card" hint-size="100%,40px"></dc-import>
</div></x-dc>
<script type="text/x-dc" data-dc-script data-props='{"title":{"editor":"text","default":"Hello &amp; bye"},"$preview":{"width":100,"height":100}}'>
class Component extends DCLogic {
  renderVals() {
    const n = this.state.n || 0;
    return { title: this.props.title, cls: 'hot', box: { backgroundColor: 'red', width: 50 + 'px' }, count: n, label: 'L', show: true, hide: false,
      rows: [{ name: 'a', deep: { v: 1 } }, { name: 'b', deep: { v: 2 } }], d: 'M0 0L5 5', bump: () => this.setState({ n: n + 1 }) };
  }
}
</script></body></html>"""


class RuntimeTest(TempArchive):
    def make(self, support=None):
        d = self.work / "proj"
        d.mkdir()
        (d / "Main.dc.html").write_text(BOARD, encoding="utf-8")
        from artikeep.viewers import RUNTIME
        (d / "support.js").write_text(RUNTIME if support is None else support, encoding="utf-8")
        return d

    @unittest.skipUnless(HAS_PW, "no Playwright")
    def test_a_board_renders_with_holes_state_loops_and_events(self):
        from playwright.sync_api import sync_playwright
        d = self.make()
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto("file://%s" % (d / "Main.dc.html"))
            pg.wait_for_timeout(300)
            ev = pg.evaluate
            self.assertEqual(ev("document.querySelector('h1').textContent"), "Hello & bye")  # data-props default, entities decoded
            self.assertEqual(ev("[...document.querySelectorAll('.row')].map(e => e.textContent)"), ["0:a:1", "1:b:2"])
            self.assertTrue(ev("!!document.getElementById('shown')"))
            self.assertFalse(ev("!!document.getElementById('hidden')"))
            self.assertEqual(ev("document.getElementById('root').getAttribute('title')"), "n=0 L")
            self.assertEqual(ev("getComputedStyle(document.getElementById('root')).backgroundColor"), "rgb(255, 0, 0)")  # a style object
            self.assertEqual(ev("getComputedStyle(document.querySelector('h1')).color"), "rgb(1, 2, 3)")  # <helmet> reached the head
            self.assertEqual(ev("document.querySelector('path').getAttribute('d')"), "M0 0L5 5")  # inside svg
            self.assertEqual(ev("document.querySelector('[data-dc-import]').style.height"), "40px")
            pg.click("#b")
            pg.wait_for_timeout(100)
            self.assertEqual(ev("document.getElementById('b').textContent"), "go 1")  # setState re-renders
            self.assertEqual(ev("document.body.innerHTML.includes('{{')"), False)
            b.close()

    def test_support_js_is_upgraded_but_a_real_one_is_left_alone(self):
        from artikeep import viewers
        d = self.work / "p"
        d.mkdir()
        self.assertEqual(viewers.ensure_support(d), "own")  # missing
        self.assertEqual((d / "support.js").read_text(), viewers.RUNTIME)
        (d / "support.js").write_text("// stub: the Design runtime lives on claude.ai; static artboards render without it.\nwindow.DCLogic = class {};\n")
        self.assertEqual(viewers.ensure_support(d), "own")  # an old stub
        self.assertEqual((d / "support.js").read_text(), viewers.RUNTIME)
        (d / "support.js").write_text("/* the real runtime */ window.DCLogic = class Real {};")
        self.assertEqual(viewers.ensure_support(d), "other")
        self.assertIn("the real runtime", (d / "support.js").read_text())
        (d / "support.js").write_text(viewers.RUNTIME_MARK + " (an older revision)\nold();")
        self.assertEqual(viewers.ensure_support(d), "own")  # our own, older: refreshed
        self.assertEqual((d / "support.js").read_text(), viewers.RUNTIME)

    def test_the_viewer_is_regenerated_when_the_runtime_arrives(self):
        from artikeep import viewers
        item = self.work / "item"
        (item / "project").mkdir(parents=True)
        (item / "project" / "canvas.json").write_text(json.dumps({"title": "W", "boards": {"Main.dc.html": {"x": 0, "y": 0, "w": 100, "h": 100}}}))
        (item / "project" / "Main.dc.html").write_text(BOARD)
        (item / "project" / "support.js").write_text("// stub: old\n")
        (item / "index.html").write_text("<!-- artikeep canvas viewer -->\n<script>const C = {}, STATIC = true;</script>")  # an old viewer
        viewers.make_canvas_viewer(item)
        page = (item / "index.html").read_text()
        self.assertIn("OWN = true", page)
        self.assertEqual((item / "project" / "support.js").read_text(), viewers.RUNTIME)
        mtime = (item / "index.html").stat().st_mtime_ns
        viewers.make_canvas_viewer(item)  # nothing changed: left alone
        self.assertEqual((item / "index.html").stat().st_mtime_ns, mtime)

    def test_export_carries_the_runtime(self):
        from artikeep import export
        canvas = {"title": "W", "pages": [], "boards": {"Main.dc.html": {"x": 0, "y": 0, "w": 300, "h": 200}}}
        e, _ = self.store.save_item("c", {"project/canvas.json": json.dumps(canvas).encode(), "project/Main.dc.html": BOARD.encode()},
                                    agent="claude-code", title="W")
        text = export.build(self.store, e["dir"], "html")[1].decode()
        self.assertIn("a small Design component runtime", text)  # the board's support.js is inlined


if __name__ == "__main__":
    unittest.main()
