"""artikeep command line.

  artikeep init [PATH]                  create an archive (git repo) and remember it
  artikeep install [--agents …]         wire hooks + MCP into Claude Code, Codex, Claude Desktop
  artikeep doctor                       check that capture works on this machine
  artikeep open                         open the gallery in the browser (static file)
  artikeep serve [--port N] [--open]    the gallery as a local app: full-text search, live, actions
  artikeep search WORDS [--json]        search the archive (--agent, --type, --project)
  artikeep add PATH… [--title T]        keep any file or page folder by hand
  artikeep attach ITEM --pr N           before/after of an item as a pull request comment
  artikeep collection list|show|add|remove|delete|rename   group related items
  artikeep secrets                      what the secret check holds back from the push
  artikeep allow ITEM [--rule R]        mark what it found in ITEM as fine
  artikeep export ID [--version N] [--format html|zip|pdf] [-o FILE]  one file to send
  artikeep restore ID [--version N] [--to DIR]  copy an item's files out to publish them again
  artikeep import chatgpt|claude-ai EXPORT   import canvases / artifacts from a data export
  artikeep scan codex|claude-code|opencode [--days N|--all]  archive what past sessions made
  artikeep rebuild [--no-push]          rebuild gallery and index, commit (and push)
  artikeep mcp [--scope all] [--allow-save]  run the MCP server on stdio
  artikeep hook AGENT EVENT             entry point for agent hooks (reads JSON on stdin)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from artikeep import __version__, config
from artikeep.store import Store


def _project_args(p) -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument("--project", metavar="PATH", help="the project these belong to (default: the git repository "
                                                    "of the file, else of the current folder)")
    g.add_argument("--no-project", action="store_true", help="keep them without a project")


def _project_of(a):
    """(project, error). project is the --project folder, "" for --no-project, else None: the caller
    picks the default."""
    from artikeep.util import project_arg
    if a.no_project:
        return "", None
    if a.project:
        try:
            return project_arg(a.project), None
        except ValueError as ex:
            return None, str(ex)
    return None, None


def _hook(agent: str, event: str) -> int:
    """Never fail the host tool: a hook error must not block the agent's work."""
    store = Store()
    try:
        store.ensure()
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if agent == "claude-code":
            from artikeep.adapters import claude_code as mod
        elif agent == "codex":
            from artikeep.adapters import codex as mod
        elif agent == "opencode":
            from artikeep.adapters import opencode as mod
        else:
            return 0
        fn = mod.COMMANDS.get(event)
        if fn:
            fn(store, payload)
    except Exception:
        store.error("hook %s %s" % (agent, event))
        from artikeep.notify import notify
        notify(store, "hook", "artikeep: the %s %s hook failed, see %s/errors.log" % (agent, event, store.log))
        if agent == "codex" and event == "stop":
            print("{}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"]:
        return _hook(argv[1] if len(argv) > 1 else "", argv[2] if len(argv) > 2 else "")
    if argv[:1] == ["worker"]:
        from artikeep import worker
        worker.run(Store())
        return 0

    ap = argparse.ArgumentParser(prog="artikeep", description="Local, versioned archive of what AI agents make.")
    ap.add_argument("--version", action="version", version="artikeep " + __version__)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="create an archive folder and remember it")
    p.add_argument("path", nargs="?")
    p.add_argument("--remote", help="git remote URL to push to (make it a private repository)")

    p = sub.add_parser("install", help="wire hooks and the MCP server into agents")
    p.add_argument("--agents", default="auto", help="comma list: claude-code,codex,claude-desktop (default: those found)")
    p.add_argument("--mcp-scope", choices=["project", "all"])
    p.add_argument("--mcp-save", action="store_true", help="let agents save through MCP")
    p.add_argument("--no-mcp", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--uninstall", action="store_true")

    sub.add_parser("doctor", help="check that capture works")
    sub.add_parser("open", help="open the gallery")

    p = sub.add_parser("serve", help="run the gallery as a local app on 127.0.0.1")
    p.add_argument("--port", type=int, default=8765, help="app port; archived files are served on port + 1")
    p.add_argument("--open", action="store_true", help="open it in the browser")

    p = sub.add_parser("collection", help="group related items: list, show, add, remove, delete, rename")
    p.add_argument("action", choices=["list", "show", "add", "remove", "delete", "rename"])
    p.add_argument("name", nargs="?", help="collection name")
    p.add_argument("items", nargs="*", help="item folder names (add, remove) or the new name (rename)")

    p = sub.add_parser("search", help="search the archive")
    p.add_argument("--collection", help="only items in this collection")
    p.add_argument("words", nargs="*")
    p.add_argument("--agent")
    p.add_argument("--type", choices=["page", "canvas", "doc", "file"])
    p.add_argument("--project", help="only this project folder (default: all)")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("add", help="keep files or page folders by hand")
    p.add_argument("paths", nargs="+")
    p.add_argument("--title")
    p.add_argument("--label")
    p.add_argument("--collection", metavar="NAME", help="also put what is kept into this collection")
    _project_args(p)

    p = sub.add_parser("attach", help="post a before/after of an item as a pull request comment")
    p.add_argument("item", help="the item folder name (the id `search` and the gallery show)")
    p.add_argument("--pr", type=int, required=True, help="pull request number")
    p.add_argument("--repo", help="owner/name (default: the origin of the item's project)")
    p.add_argument("--from", dest="frm", type=int, help="the 'before' version (default: the one before the newest)")
    p.add_argument("--to", type=int, help="the 'after' version (default: the newest)")
    p.add_argument("--no-images", action="store_true", help="the text part only")
    p.add_argument("--public", action="store_true", help="allow a public repository (publishes the page there)")
    p.add_argument("--with-request", action="store_true", help="quote the request behind the 'after' version")
    p.add_argument("--dry-run", action="store_true", help="print the comment, change nothing")
    sub.add_parser("secrets", help="show what the secret check holds back from the push")
    p = sub.add_parser("allow", help="mark possible secrets found in an item as false alarms")
    p.add_argument("item", help="the item folder name (see `artikeep secrets`)")
    p.add_argument("--rule", help="only findings of this kind, e.g. 'AWS access key'")

    p = sub.add_parser("export", help="one item as a file to send: html (self-contained), zip or pdf")
    p.add_argument("id", help="the item folder name (the id `search` and the gallery show)")
    p.add_argument("--version", type=int, help="version number; default the newest")
    p.add_argument("--format", choices=["html", "zip", "pdf"], default="html")
    p.add_argument("-o", "--output", help="file to write (default: ./<id>.<format>)")

    p = sub.add_parser("restore", help="copy an item's files out so an agent can publish them again")
    p.add_argument("id", help="the item folder name (the id `search` and the gallery show)")
    p.add_argument("--version", type=int, help="version number; default the newest")
    p.add_argument("--to", help="a new or empty folder to write into")

    p = sub.add_parser("import", help="import a chat data export")
    p.add_argument("source", choices=["chatgpt", "claude-ai"])
    p.add_argument("export", help="the export .zip, its folder, or conversations.json")
    _project_args(p)

    p = sub.add_parser("scan", help="archive deliverables from past agent sessions")
    p.add_argument("agent", choices=["codex", "claude-code", "opencode"])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=30)
    g.add_argument("--all", action="store_true")

    p = sub.add_parser("rebuild", help="rebuild gallery and index, commit")
    p.add_argument("--no-push", action="store_true")

    p = sub.add_parser("mcp", help="run the MCP server on stdio")
    p.add_argument("--scope", choices=["project", "all"])
    p.add_argument("--allow-save", action="store_true", default=None)
    p.add_argument("--agent", default="mcp", help="source recorded for saved items (e.g. claude-desktop)")

    a = ap.parse_args(argv)
    store = Store()

    if a.cmd == "init":
        from pathlib import Path
        root = Path(a.path).expanduser().resolve() if a.path else store.root
        st = Store(root).ensure()
        if not (root / ".git").exists():
            subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=False)
        if a.remote:
            subprocess.run(["git", "-C", str(root), "remote", "add", "origin", a.remote], check=False)
        config.set_home(root)
        from artikeep import worker
        worker.run(st, push=False, wait=True)
        print("archive: %s (remembered in %s)" % (root, config.CONFIG_FILE))
        return 0
    if a.cmd == "install":
        from artikeep import install
        return install.run(store, a)
    if a.cmd == "doctor":
        from artikeep import install
        return install.doctor(store)
    if a.cmd == "open":
        page = store.root / "index.html"
        if not page.exists():
            from artikeep import worker
            worker.run(store.ensure(), push=False, wait=True)
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, str(page)], check=False)
        print(page)
        return 0
    if a.cmd == "serve":
        from artikeep.server import serve
        return serve(store, a.port, a.open)
    if a.cmd == "search":
        from artikeep.search import search
        hits = search(store, " ".join(a.words), scope=a.project, agent=a.agent, kind=a.type, limit=a.limit, collection=a.collection)
        if a.json:
            print(json.dumps(hits, ensure_ascii=False, indent=1))
        for h in [] if a.json else hits:
            print("%s  %-11s %-6s %s\n    %s%s" % (h["updated"], h["agent"], h["type"], h["title"],
                                                  store.items / h["id"], ("\n    " + h["snippet"]) if h["snippet"] else ""))
        if not hits and not a.json:
            print("nothing found")
        return 0
    if a.cmd == "add":
        from artikeep.importers.files import add_path
        store.ensure()
        from artikeep.util import git_root
        project, err = _project_of(a)
        if err:
            print("add: " + err, file=sys.stderr)
            return 1
        made = []
        for path in a.paths:
            entry, vdir = add_path(store, path, title=a.title, label=a.label, project=project, fallback=git_root("."))
            made.append(entry["dir"])
            print("%s %s" % ("saved" if vdir else "unchanged", store.item_dir(entry)))
        if a.collection:
            from artikeep import collections
            try:
                collections.add(store, a.collection, made)
            except ValueError as ex:
                print("add: %s" % ex, file=sys.stderr)
                return 1
            print("in collection %s" % a.collection)
        store.kick()
        return 0
    if a.cmd == "collection":
        from artikeep import collections
        colls = collections.load(store)
        titles = {e["dir"]: e.get("title") or e["dir"] for e in store.load()["items"].values()}
        try:
            if a.action == "list":
                for n, items in sorted(colls.items()):
                    print("%-30s %d item(s)" % (n, len(items)))
                if not colls:
                    print("no collections yet: artikeep collection add NAME ITEM...")
            elif not a.name:
                print("collection: %s needs a name" % a.action, file=sys.stderr)
                return 1
            elif a.action == "show":
                if a.name not in colls:
                    raise KeyError(a.name)
                for f in colls[a.name]:
                    print("%s   %s" % (f, titles.get(f, "?")))
            elif a.action in ("add", "remove"):
                if not a.items:
                    print("collection: name the items (folders as `search` shows them)", file=sys.stderr)
                    return 1
                done = (collections.add if a.action == "add" else collections.remove)(store, a.name, a.items)
                print("%s %d item(s) %s %s" % ("added" if a.action == "add" else "removed", len(done), "to" if a.action == "add" else "from", a.name))
            elif a.action == "delete":
                collections.delete(store, a.name)
                print("deleted collection %s (its items stay)" % a.name)
            else:
                if len(a.items) != 1:
                    print("collection: rename NAME NEWNAME", file=sys.stderr)
                    return 1
                collections.rename(store, a.name, a.items[0])
                print("renamed %s to %s" % (a.name, a.items[0]))
        except KeyError as ex:
            print("collection: no such item or collection: %s" % ex.args[0], file=sys.stderr)
            return 1
        except ValueError as ex:
            print("collection: %s" % ex, file=sys.stderr)
            return 1
        store.kick()
        return 0
    if a.cmd == "attach":
        from artikeep import attach
        try:
            r = attach.run(store, a.item, a.pr, repo=a.repo, frm=a.frm, to=a.to, images=not a.no_images, public=a.public,
                           with_request=a.with_request, dry_run=a.dry_run)
        except attach.AttachError as ex:
            print("attach: %s" % ex, file=sys.stderr)
            return 1
        if r.get("note"):
            print("note: " + r["note"], file=sys.stderr)
        print(r["body"] if a.dry_run else "%s the comment: %s" % ("updated" if r["updated"] else "posted", r["url"]))
        return 0
    if a.cmd == "secrets":
        from artikeep import secretscan
        if not (store.root / ".git").exists():
            print("the archive is not a git repository: nothing is pushed")
            return 0
        history, net, base = secretscan.unpushed(store, set(store.settings.get("secret_allow") or []))
        hits = net or history
        if not hits:
            print("no possible secrets in what is not pushed yet (secret_scan: %s)" % store.settings.get("secret_scan", "block"))
            return 0
        print("%d possible secret(s) in what is not pushed yet%s:" % (len(hits), "" if net else " (already removed again: the push will squash them)"))
        for f in hits:
            print("  %s%s" % (secretscan.describe(f), "   item: %s" % f["item"] if f["item"] else ""))
        print("false alarm? artikeep allow ITEM    real? delete the item (its older versions keep the text), the push then goes ahead")
        return 1
    if a.cmd == "allow":
        from artikeep import secretscan
        hits = secretscan.allow(store, a.item, a.rule)
        if not hits:
            print("allow: nothing found for %s%s" % (a.item, " (%s)" % a.rule if a.rule else ""), file=sys.stderr)
            return 1
        print("marked %d finding(s) as fine:" % len(hits))
        for f in hits:
            print("  " + secretscan.describe(f))
        store.kick()
        return 0
    if a.cmd == "export":
        from pathlib import Path
        from artikeep import export
        try:
            name, data, notes = export.build(store, a.id, a.format, a.version)
        except export.ExportError as ex:
            print("export: %s" % ex, file=sys.stderr)
            return 1
        out = Path(a.output or name).expanduser()
        if out.is_dir():
            out = out / name
        if out.exists() and not a.output:
            print("export: %s exists; name the file with -o" % out, file=sys.stderr)
            return 1
        out.write_bytes(data)
        print("%s (%d KB)" % (out.resolve(), max(1, len(data) // 1024)))
        for n in notes:
            print("note: " + n, file=sys.stderr)
        return 0
    if a.cmd == "restore":
        try:
            m = store.load()
            key, e = store.find(m, a.id)
            info = store.restore_files(key, e, a.version, a.to)
        except (KeyError, ValueError) as ex:
            print("restore: %s" % (ex.args[0] if isinstance(ex, ValueError) else "no item %s" % a.id), file=sys.stderr)
            return 1
        print("%s v%d -> %s\n  %s\n  %s" % (info["id"], info["version"], info["folder"], ", ".join(info["files"][:12]), info["publish"]))
        return 0
    if a.cmd == "import":
        store.ensure()
        if a.source == "chatgpt":
            from artikeep.importers.chatgpt import import_export
        else:
            from artikeep.importers.claude_ai import import_export
        project, err = _project_of(a)
        if err:
            print("import: " + err, file=sys.stderr)
            return 1
        from artikeep.util import git_root
        stats = import_export(store, a.export, project=git_root(".") if project is None else project or None)
        print(json.dumps(stats, ensure_ascii=False))
        if stats.get("unparsed_calls"):
            print("note: %d tool calls had an unknown shape and were skipped" % stats["unparsed_calls"], file=sys.stderr)
        store.kick()
        return 0
    if a.cmd == "scan":
        store.ensure()
        days = 100000 if a.all else a.days
        if a.agent == "codex":
            from artikeep.adapters import codex
            n = codex.cmd_check(store, {}, days=days)
            print("codex: %d new item versions" % n)
        elif a.agent == "opencode":
            from artikeep.adapters import opencode
            print("opencode: %d new item versions" % opencode.cmd_check(store, {}, days=days))
        else:
            from artikeep.adapters import claude_code
            claude_code.cmd_check(store, {}, days=days)
        return 0
    if a.cmd == "rebuild":
        from artikeep import worker
        worker.run(store.ensure(), push=not a.no_push, wait=True)
        print(store.root / "index.html")
        return 0
    if a.cmd == "mcp":
        from artikeep.mcp_server import serve
        store.ensure()
        return serve(store, a.scope, a.allow_save, a.agent)
    ap.print_help()
    return 0
