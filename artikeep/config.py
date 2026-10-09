"""Where the archive lives and how it behaves.

The archive folder is chosen, in order, by $ARTIKEEP_HOME, then the "home" key of
~/.config/artikeep/config.json, then ~/artikeep. Behaviour settings live inside
the archive itself (artikeep.json), so they travel with it to another machine.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "artikeep" / "config.json"

DEFAULTS = {
    # Push to the git remote after each commit, if the archive has one.
    "git_push": True,
    # Thumbnails need Playwright in some `python3` on PATH: "auto" tries and stays quiet.
    "thumbnails": "auto",
    # Look up GitHub issues that link to archived items (needs the gh CLI). Once a day.
    "issue_links": True,
    # Gallery language: "auto" follows the browser, or "en" / "ru".
    "lang": "auto",
    # MCP server: "project" shows only items made in the repository the agent works in;
    # "all" shows everything. Writing through MCP is off unless enabled.
    "mcp_scope": "project",
    "mcp_save": False,
    # Codex: which files a session made count as deliverables worth keeping.
    "codex_extensions": [".html", ".htm", ".svg", ".md", ".pdf", ".docx", ".pptx", ".xlsx", ".csv"],
}


def home() -> Path:
    env = os.environ.get("ARTIKEEP_HOME")
    if env:
        return Path(env).expanduser()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if data.get("home"):
            return Path(data["home"]).expanduser()
    except Exception:
        pass
    return Path.home() / "artikeep"


def set_home(path: Path) -> None:
    data = {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    data["home"] = str(path)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lang(conf: dict) -> str:
    """Language for hook messages: the setting, else the locale."""
    if conf.get("lang") in ("ru", "en"):
        return conf["lang"]
    loc = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    return "ru" if loc.lower().startswith("ru") else "en"


def settings(root: Path) -> dict:
    out = dict(DEFAULTS)
    try:
        out.update(json.loads((root / "artikeep.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    return out
