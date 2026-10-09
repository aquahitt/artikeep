"""artikeep command line.

  artikeep init [PATH]                  create an archive (git repo) and remember it
  artikeep install [--agents …]         wire hooks + MCP into Claude Code and/or Codex
  artikeep doctor                       check that capture works on this machine
  artikeep open                         open the gallery in the browser
  artikeep search WORDS [--all]         search the archive
  artikeep add PATH… [--title T]        keep any file or page folder by hand
  artikeep import chatgpt|claude-ai EXPORT   import canvases / artifacts from a data export
  artikeep scan codex [--days N|--all]  archive Codex deliverables from past sessions
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
        else:
            return 0
        fn = mod.COMMANDS.get(event)
        if fn:
            fn(store, payload)
    except Exception:
        store.error("hook %s %s" % (agent, event))
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
    p.add_argument("--agents", default="auto", help="comma list: claude-code,codex (default: those found)")
    p.add_argument("--mcp-scope", choices=["project", "all"])
    p.add_argument("--mcp-save", action="store_true", help="let agents save through MCP")
    p.add_argument("--no-mcp", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--uninstall", action="store_true")

    sub.add_parser("doctor", help="check that capture works")
    sub.add_parser("open", help="open the gallery")

    p = sub.add_parser("search", help="search the archive")
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

    p = sub.add_parser("import", help="import a chat data export")
    p.add_argument("source", choices=["chatgpt", "claude-ai"])
    p.add_argument("export", help="the export .zip, its folder, or conversations.json")

    p = sub.add_parser("scan", help="archive deliverables from past agent sessions")
    p.add_argument("agent", choices=["codex", "claude-code"])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=30)
    g.add_argument("--all", action="store_true")

    p = sub.add_parser("rebuild", help="rebuild gallery and index, commit")
    p.add_argument("--no-push", action="store_true")

    p = sub.add_parser("mcp", help="run the MCP server on stdio")
    p.add_argument("--scope", choices=["project", "all"])
    p.add_argument("--allow-save", action="store_true", default=None)

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
    if a.cmd == "search":
        from artikeep.search import search
        hits = search(store, " ".join(a.words), scope=a.project, agent=a.agent, kind=a.type, limit=a.limit)
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
        for path in a.paths:
            entry, vdir = add_path(store, path, title=a.title, label=a.label)
            print("%s %s" % ("saved" if vdir else "unchanged", store.item_dir(entry)))
        store.kick()
        return 0
    if a.cmd == "import":
        store.ensure()
        if a.source == "chatgpt":
            from artikeep.importers.chatgpt import import_export
        else:
            from artikeep.importers.claude_ai import import_export
        stats = import_export(store, a.export)
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
        return serve(store, a.scope, a.allow_save)
    ap.print_help()
    return 0
