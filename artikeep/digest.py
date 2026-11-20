"""`artikeep digest`: what the agents made over the last days, grouped by project.

For each project, the items that are new in the window and the ones that got new
versions, with a thumbnail, the number of versions saved, and the requests behind them
when the versions carry one (provenance). HTML opens from the archive like the gallery
(links and thumbnails are relative to the file); Markdown pastes into a chat or a report.
"""
from __future__ import annotations

import datetime as dt
import html
import os
from pathlib import Path

from artikeep.gallery import item_type, main_file, project_label
from artikeep.store import Store, agent_of

MAX_ASKS = 3


def collect(store: Store, days: int = 7, project: str | None = None, now: dt.datetime | None = None) -> dict:
    """{"since", "until", "projects": [{"name", "path", "items": [...]}], "new", "updated"}"""
    now = now or dt.datetime.now()
    since = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    groups = {}
    for key, e in store.load()["items"].items():
        if e.get("deleted"):
            continue
        if project and (e.get("project") or "") != project and project_label(e.get("project")) != project:
            continue
        versions = e.get("versions") or []
        fresh = [v for v in versions if (v.get("at") or "") >= since]
        if not versions:
            stamp = (e.get("updated") or e.get("created") or "")[:19]
            if stamp < since:
                continue
        elif not fresh:
            continue
        first = (versions[0].get("at") if versions else (e.get("created") or "")[:19]) or ""
        asks = []
        for v in fresh:
            if v.get("request") and v["request"] not in asks:
                asks.append(v["request"])
        d = store.item_dir(e)
        main = main_file(d, e)
        groups.setdefault(e.get("project") or "", []).append({
            "dir": e["dir"], "title": e.get("title") or e["dir"], "type": item_type(d, e), "agent": agent_of(e),
            "new": first >= since, "versions": len(versions), "added": len(fresh) or 1,
            "at": (fresh[-1].get("at") if fresh else (e.get("updated") or "")[:19]) or "",
            "asks": asks[-MAX_ASKS:], "stars": bool(e.get("star")), "chosen": any(v.get("mark") == "chosen" for v in versions),
            "main": main, "thumb": "_thumb.jpg" if (d / "_thumb.jpg").exists() else None,
        })
    projects = []
    newest = sorted(groups.items(), key=lambda kv: max(i["at"] for i in kv[1]), reverse=True)
    for path, items in sorted(newest, key=lambda kv: kv[0] == ""):  # newest project first, "no project" last
        items.sort(key=lambda i: i["at"], reverse=True)
        projects.append({"name": project_label(path) or "", "path": path, "items": items})
    flat = [i for p in projects for i in p["items"]]
    return {"since": since[:10], "until": now.strftime("%Y-%m-%d"), "days": days, "projects": projects,
            "new": sum(i["new"] for i in flat), "updated": sum(not i["new"] for i in flat),
            "versions": sum(i["added"] for i in flat)}


def to_markdown(d: dict, store: Store) -> str:
    out = ["# What the agents made, %s to %s" % (d["since"], d["until"]), "",
           "%d new item(s), %d updated, %d version(s) saved." % (d["new"], d["updated"], d["versions"]), ""]
    if not d["projects"]:
        out.append("Nothing new in the last %d days." % d["days"])
    for p in d["projects"]:
        out += ["## %s" % (p["name"] or "No project"), ""]
        for i in p["items"]:
            tags = [("new" if i["new"] else "%d new version(s)" % i["added"]), i["type"], i["agent"]]
            if i["stars"]:
                tags.append("starred")
            if i["chosen"]:
                tags.append("has a chosen version")
            out.append("- **%s** (%s), `%s`" % (i["title"].replace("*", "\\*"), ", ".join(tags), i["dir"]))
            for a in i["asks"]:
                out.append("  - asked: %s" % a.replace("\n", " "))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


CSS = """:root{--bg:#f6f5f2;--card:#fff;--fg:#1d1d1b;--muted:#6b6a66;--line:#e2e0da;--accent:#2e5e4e}
@media (prefers-color-scheme:dark){:root{--bg:#171716;--card:#21211f;--fg:#ecebe7;--muted:#9c9a94;--line:#34332f;--accent:#7fc4a8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:1040px;margin:0 auto;padding:28px 16px 64px}h1{font-size:26px;margin:0 0 4px}.sum{color:var(--muted);margin:0 0 28px}
h2{font-size:18px;margin:30px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.c{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.c .th{height:140px;background:var(--line) center top/cover no-repeat}.c .b{padding:10px 12px 12px;display:grid;gap:4px}
.c h3{font-size:15px;margin:0}.c h3 a{color:inherit;text-decoration:none}.c h3 a:hover{color:var(--accent)}
.m{font-size:12px;color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 10px}.tag{color:var(--accent);font-weight:600}
.q{font-size:13px;color:var(--muted);border-left:2px solid var(--line);padding-left:8px;margin:2px 0 0;overflow-wrap:anywhere}
"""


def to_html(d: dict, store: Store, base: Path) -> str:
    """base: the folder the file will sit in; links are relative to it."""
    rel = lambda p: html.escape(os.path.relpath(p, base).replace(os.sep, "/"), quote=True)
    body = ["<h1>What the agents made</h1>",
            '<p class="sum">%s to %s: %d new, %d updated, %d version(s) saved.</p>' % (d["since"], d["until"], d["new"], d["updated"], d["versions"])]
    if not d["projects"]:
        body.append("<p>Nothing new in the last %d days.</p>" % d["days"])
    for p in d["projects"]:
        body.append("<h2>%s</h2><div class=\"grid\">" % html.escape(p["name"] or "No project"))
        for i in p["items"]:
            item = store.items / i["dir"]
            th = '<div class="th" style="background-image:url(\'%s\')"></div>' % rel(item / i["thumb"]) if i["thumb"] else '<div class="th"></div>'
            title = html.escape(i["title"])
            if i["main"]:
                title = '<a href="%s">%s</a>' % (rel(item / i["main"]), title)
            marks = "".join(" · %s" % html.escape(x) for x in (["starred"] if i["stars"] else []) + (["chosen version"] if i["chosen"] else []))
            asks = "".join('<p class="q">%s</p>' % html.escape(a.replace("\n", " ")) for a in i["asks"])
            body.append('<article class="c">%s<div class="b"><h3>%s</h3><div class="m"><span class="tag">%s</span><span>%s</span><span>%s</span></div>%s</div></article>' % (
                th, title, "new" if i["new"] else "%d new version%s" % (i["added"], "" if i["added"] == 1 else "s"),
                html.escape(i["type"]), html.escape(i["agent"] + marks), asks))
        body.append("</div>")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>artikeep digest</title><style>%s</style></head><body><main>%s</main></body></html>\n" % (CSS, "\n".join(body)))
