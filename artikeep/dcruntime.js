// artikeep: a small Design component runtime, written from the documented .dc.html format. MIT.
// It renders an artboard from the file alone, so an archived canvas shows its boards without the host.
// Not the original runtime: {{holes}}, <sc-if>, <sc-for>, events, state and data-props work;
// <dc-import> draws its placeholder box. artikeep rewrites this file when it improves (see viewers.py).
(function () {
  "use strict";
  if (window.DCLogic && window.DCLogic.__artikeep) return;

  class DCLogic {
    constructor(props) { this.props = props || {}; this.state = {}; this._queued = false; this._cbs = []; }
    setState(patch, cb) {
      const next = typeof patch === "function" ? patch(this.state, this.props) : patch;
      if (next) this.state = Object.assign({}, this.state, next);
      this._queue(cb);
    }
    forceUpdate(cb) { this._queue(cb); }
    renderVals() { return {}; }
    _queue(cb) {
      if (cb) this._cbs.push(cb);
      if (this._queued) return;
      this._queued = true;
      Promise.resolve().then(() => { this._queued = false; if (this._render) this._render(); });
    }
  }
  DCLogic.__artikeep = true;
  window.DCLogic = DCLogic;

  const HOLE = /\{\{\s*([^{}]*?)\s*\}\}/g;
  const WHOLE = /^\s*\{\{\s*([^{}]*?)\s*\}\}\s*$/;
  const EVENTS = { doubleclick: "dblclick", mouseenter: "mouseenter", mouseleave: "mouseleave", change: "input" };

  function lookup(path, scope) {
    if (path === "true") return true;
    if (path === "false") return false;
    if (path === "null" || path === "undefined") return null;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    const q = path.match(/^(["'])(.*)\1$/);
    if (q) return q[2];
    let v = scope;
    for (const part of path.split(".")) {
      if (v == null) return undefined;
      v = v[part];
    }
    return v;
  }
  const text = (v) => (v == null || typeof v === "boolean" ? "" : typeof v === "object" ? "" : String(v));
  const interpolate = (s, scope) => s.replace(HOLE, (_, p) => text(lookup(p, scope)));
  const camelToCss = (k) => (k.startsWith("--") ? k : k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase()));
  const styleText = (o) => Object.keys(o).filter((k) => o[k] != null && o[k] !== false).map((k) => camelToCss(k) + ":" + o[k]).join(";");

  function attr(el, name, raw, scope) {
    const whole = raw.match(WHOLE);
    if (/^on[a-z]+$/i.test(name) && whole) {  // the HTML parser lowercases onClick to onclick
      const fn = lookup(whole[1], scope);
      if (typeof fn === "function") {
        const ev = name.slice(2).toLowerCase();
        el.addEventListener(EVENTS[ev] || ev, fn);
        if (ev === "change") el.addEventListener("change", fn);
      }
      return;
    }
    if (name === "ref" && whole) {
      const r = lookup(whole[1], scope);
      if (typeof r === "function") r(el); else if (r && typeof r === "object") r.current = el;
      return;
    }
    if (name.startsWith("hint-")) return;
    const key = name === "classname" ? "class" : name === "htmlfor" ? "for" : name;
    let value = whole ? lookup(whole[1], scope) : interpolate(raw, scope);
    if (key === "style" && value && typeof value === "object") value = styleText(value);
    if (typeof value === "function" || value == null || value === false) return;
    el.setAttribute(key, value === true ? "" : String(value));
    if (key === "value" && "value" in el) el.value = String(value);
    if (key === "checked" && "checked" in el) el.checked = true;
  }

  function build(node, scope, into) {
    if (node.nodeType === 3) {
      into.appendChild(document.createTextNode(interpolate(node.nodeValue, scope)));
      return;
    }
    if (node.nodeType !== 1) return;
    const tag = node.localName;
    if (tag === "helmet") return;
    const kids = () => { for (const c of Array.from(node.childNodes)) build(c, scope, into); };
    if (tag === "sc-if") {
      const m = (node.getAttribute("value") || "").match(WHOLE);
      if (m ? lookup(m[1], scope) : node.getAttribute("value")) kids();
      return;
    }
    if (tag === "sc-for") {
      const m = (node.getAttribute("list") || "").match(WHOLE);
      const list = m ? lookup(m[1], scope) : null;
      const as = node.getAttribute("as") || "item";
      if (Array.isArray(list)) {
        list.forEach((item, i) => {
          const inner = Object.create(scope);
          inner[as] = item; inner.$index = i;
          for (const c of Array.from(node.childNodes)) build(c, inner, into);
        });
      }
      return;
    }
    if (tag === "dc-import") {
      const box = document.createElement("div");
      const size = (interpolate(node.getAttribute("hint-size") || "", scope) || "").split(",");
      if (size[0]) box.style.width = size[0].trim();
      if (size[1]) box.style.height = size[1].trim();
      box.setAttribute("data-dc-import", node.getAttribute("name") || "");
      into.appendChild(box);
      return;
    }
    const el = document.createElementNS(node.namespaceURI, node.localName);
    for (const a of Array.from(node.attributes)) attr(el, a.name, a.value, scope);
    into.appendChild(el);
    for (const c of Array.from(node.childNodes)) build(c, scope, el);
  }

  function boot() {
    const root = document.querySelector("x-dc");
    const script = document.querySelector("script[data-dc-script]");
    if (!root || !script) return;
    const head = document.head;
    const fixed = document.createElement("style");
    fixed.textContent = "x-dc{display:block}";
    head.appendChild(fixed);
    const helmet = root.querySelector("helmet");
    if (helmet) {
      for (const c of Array.from(helmet.children)) head.appendChild(c);
      helmet.remove();
    }
    let declared = {};
    try { declared = JSON.parse(script.getAttribute("data-props") || "{}"); } catch (e) { /* no tweaks */ }
    const props = {};
    for (const k of Object.keys(declared)) if (k[0] !== "$" && declared[k] && "default" in declared[k]) props[k] = declared[k].default;

    const template = document.createElement("template");
    for (const c of Array.from(root.childNodes)) template.content.appendChild(c);
    let Component = DCLogic;
    try { Component = new Function("DCLogic", script.textContent + "\n;return typeof Component === 'function' ? Component : DCLogic;")(DCLogic); }
    catch (e) { console.error("artikeep: the artboard script failed:", e); }
    const logic = new Component(props);
    let mounted = false;
    logic._render = function () {
      let vals = {};
      try { vals = logic.renderVals() || {}; } catch (e) { console.error("artikeep: renderVals failed:", e); }
      const out = document.createDocumentFragment();
      const scope = Object.create(vals);
      for (const c of Array.from(template.content.childNodes)) build(c, scope, out);
      root.replaceChildren(out);
      const cbs = logic._cbs.splice(0);
      try {
        if (!mounted) { mounted = true; if (logic.componentDidMount) logic.componentDidMount(); }
        else if (logic.componentDidUpdate) logic.componentDidUpdate();
      } catch (e) { console.error("artikeep: lifecycle failed:", e); }
      cbs.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
    };
    logic._render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
