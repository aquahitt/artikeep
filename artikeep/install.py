"""Wire artikeep into agents on this machine, and check that it works. Safe to repeat.

Claude Code: hooks in ~/.claude/settings.json (PostToolUse Artifact and Claude Docs,
Stop, SessionStart), cleanupPeriodDays raised so transcripts stay recoverable, the
MCP server registered with `claude mcp add --scope user`, a rules block in
~/.claude/CLAUDE.md.
Codex: hooks in ~/.codex/hooks.json (Stop, SessionStart), the MCP server registered
with `codex mcp add`, a rules block in ~/.codex/AGENTS.md.
Every edited file is backed up next to itself first (*.bak.artikeep.<time>).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from artikeep import config
from artikeep.store import Store, agent_of

HOME = Path.home()
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
CODEX_HOOKS = HOME / ".codex" / "hooks.json"
CODEX_CONFIG = HOME / ".codex" / "config.toml"
CODEX_AGENTS_MD = HOME / ".codex" / "AGENTS.md"
ENTRY = Path(__file__).resolve().parent.parent / "bin" / "artikeep"
MARK_BEGIN, MARK_END = "<!-- artikeep:begin -->", "<!-- artikeep:end -->"
OLD_MARKS = ("<!-- claude-artifacts:begin -->", "<!-- claude-artifacts:end -->")
OLD_HOOK = "artifact_archive.py"  # the single-script predecessor; replaced on install

CLAUDE_HOOKS = [
    ("PostToolUse", "Artifact", "publish", 30),
    ("PostToolUse", "mcp__claude_ai_Claude_Docs__.*", "docs", 30),
    ("Stop", "", "stop", 20),
    ("SessionStart", "", "check", 30),
]
CODEX_HOOK_EVENTS = [("Stop", "stop", 30), ("SessionStart", "check", 60)]


def _py() -> str:
    exe = sys.executable or "python3"
    # macOS system python resolves into Xcode or the Command Line Tools, a path that moves on updates.
    if ("/Xcode.app/" in exe or "/CommandLineTools/" in exe) and Path("/usr/bin/python3").exists():
        return "/usr/bin/python3"
    return exe


def launcher() -> list:
    """How agents start artikeep: the clone's bin/artikeep, or the installed package."""
    return [_py(), str(ENTRY)] if ENTRY.exists() else [_py(), "-m", "artikeep"]


def hook_command(agent: str, event: str) -> str:
    # Guarded: a moved or deleted clone must never break the agent. Exit 2 from a
    # Claude Code hook is a blocking error, and a Codex Stop hook must print JSON.
    fallback = "echo '{}'" if (agent, event) == ("codex", "stop") else "true"
    run = " ".join('"%s"' % x if " " in x or "/" in x else x for x in launcher())
    guard = 'test -f "%s" && ' % ENTRY if ENTRY.exists() else ""
    return "%s%s hook %s %s || %s" % (guard, run, agent, event, fallback)


def _ours(h: dict) -> bool:
    cmd = h.get("command", "")
    return "artikeep" in cmd and " hook " in cmd or OLD_HOOK in cmd


class Plan:
    def __init__(self, dry: bool):
        self.dry = dry
        self.lines = []

    def say(self, msg: str) -> None:
        line = ("[dry-run] " if self.dry else "") + msg
        self.lines.append(line)
        print(line)

    def write(self, path: Path, text: str) -> None:
        if self.dry:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_text(encoding="utf-8") == text:
                return
            shutil.copy2(path, path.with_name("%s.bak.artikeep.%d" % (path.name, int(time.time()))))
        path.write_text(text, encoding="utf-8")

    def run(self, cmd: list) -> subprocess.CompletedProcess | None:
        if self.dry:
            return None
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


# ---------------------------------------------------------------- hooks


def merge_hooks(hooks: dict, wanted: list, uninstall: bool) -> dict:
    """Drop our previous entries, keep everyone else's, add ours (wanted: [(event, matcher, command, timeout)])."""
    for event in list(hooks):
        groups = []
        for g in hooks[event] or []:
            g["hooks"] = [h for h in g.get("hooks", []) if not _ours(h)]
            if g["hooks"]:
                groups.append(g)
        hooks[event] = groups
    if not uninstall:
        for event, matcher, command, timeout in wanted:
            g = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
            if matcher:
                g["matcher"] = matcher
            hooks.setdefault(event, []).append(g)
    for event in [e for e, gs in hooks.items() if not gs]:
        del hooks[event]
    return hooks


def install_claude_hooks(plan: Plan, uninstall: bool) -> None:
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8")) if CLAUDE_SETTINGS.exists() else {}
    wanted = [(e, mt, hook_command("claude-code", ev), t) for e, mt, ev, t in CLAUDE_HOOKS]
    merge_hooks(data.setdefault("hooks", {}), wanted, uninstall)
    if not data["hooks"]:
        del data["hooks"]
    note = ""
    if not uninstall and (data.get("cleanupPeriodDays") or 30) < 3650:
        data["cleanupPeriodDays"] = 3650
        note = ", cleanupPeriodDays 3650 (transcripts are the recovery source of last resort)"
    plan.write(CLAUDE_SETTINGS, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    plan.say("Claude Code: hooks %s in %s%s" % ("removed" if uninstall else "set", CLAUDE_SETTINGS, note))


def install_codex_hooks(plan: Plan, uninstall: bool) -> None:
    data = json.loads(CODEX_HOOKS.read_text(encoding="utf-8")) if CODEX_HOOKS.exists() else {}
    wanted = [(e, "", hook_command("codex", ev), t) for e, ev, t in CODEX_HOOK_EVENTS]
    merge_hooks(data.setdefault("hooks", {}), wanted, uninstall)
    plan.write(CODEX_HOOKS, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    plan.say("Codex: hooks %s in %s" % ("removed" if uninstall else "set", CODEX_HOOKS))
    if CODEX_CONFIG.exists() and re.search(r"^\s*hooks\s*=\s*false", CODEX_CONFIG.read_text(encoding="utf-8"), re.M):
        plan.say("Codex: WARNING features.hooks = false in %s — hooks will not run until it is true" % CODEX_CONFIG)


# ---------------------------------------------------------------- MCP


def install_mcp(plan: Plan, agent: str, uninstall: bool) -> None:
    cli = "claude" if agent == "claude-code" else "codex"
    if not shutil.which(cli):
        plan.say("%s: `%s` CLI not on PATH; register the MCP server by hand: %s mcp" % (agent, cli, " ".join(launcher())))
        return
    scope = ["--scope", "user"] if cli == "claude" else []
    plan.run([cli, "mcp", "remove"] + scope + ["artikeep"])
    if uninstall:
        plan.say("%s: MCP server removed" % agent)
        return
    r = plan.run([cli, "mcp", "add"] + scope + ["artikeep", "--"] + launcher() + ["mcp"])
    ok = r is None or r.returncode == 0
    plan.say("%s: MCP server %s" % (agent, "registered" if ok else "NOT registered: " + (r.stderr or r.stdout).strip()[:300]))


# ---------------------------------------------------------------- rules for the agents


def rules(store: Store, agent: str) -> str:
    ru = config.lang(store.settings) == "ru"
    root = str(store.root).replace(str(HOME), "~")
    if ru:
        lines = [
            "## Архив артефактов (artikeep)",
            "",
            "Всё, что агенты делают для пользователя, копируется в `%s` автоматически (hook-и artikeep, "
            "git с версиями; галерея — `%s/index.html`)." % (root, root),
            "",
            "- Прежде чем делать заново страницу, отчёт или документ, который мог уже быть, — поискать в архиве: "
            "MCP-инструмент `search_artifacts` / `read_artifact` или `artikeep search <слова>`.",
            "- Ссылка на прошлый артефакт не открывается — искать копию там же.",
        ]
        if agent == "claude-code":
            lines += [
                "- Исходники страниц писать в scratchpad: инструмент `Artifact` принимает файлы оттуда, копию снимет hook.",
                "- Страница с базой артефакта или правками на самой странице: перед правкой прочитать её `Artifact read` — "
                "hook положит снимок сервера в `items/…/server/`.",
                "- Документ Claude Docs: закончив правки, экспортировать каждую вкладку `mcp__claude_ai_Claude_Docs__export` "
                "с `format: \"markdown\"`. Забыл — hook на конце хода напомнит один раз.",
                "- Hook сообщил «сохранено не всё» — сказать пользователю, что именно не попало в архив.",
            ]
        else:
            lines += [
                "- Документы для человека (отчёты, страницы, таблицы), записанные вне git, архивируются в конце хода. "
                "Путь к такому файлу называть в итоговом ответе — так hook найдёт и файлы, созданные скриптом.",
            ]
    else:
        lines = [
            "## Artifact archive (artikeep)",
            "",
            "Everything agents make for the user is copied to `%s` automatically (artikeep hooks, git with "
            "versions; gallery at `%s/index.html`)." % (root, root),
            "",
            "- Before recreating a page, report or document that may already exist, search the archive: MCP tools "
            "`search_artifacts` / `read_artifact`, or `artikeep search <words>`.",
            "- If a link to a past artifact no longer opens, look for its copy there.",
        ]
        if agent == "claude-code":
            lines += [
                "- Write page sources in the scratchpad: the `Artifact` tool takes files from there and the hook keeps a copy.",
                "- For a page with an artifact database or in-page edits, `Artifact read` it before editing: the hook "
                "keeps the server's copy in `items/…/server/`.",
                "- Claude Docs: when done editing, export every tab with `mcp__claude_ai_Claude_Docs__export`, "
                "`format: \"markdown\"`. If you forget, the hook reminds you once at the end of the turn.",
                "- If the hook says not everything was saved, tell the user what is missing from the archive.",
            ]
        else:
            lines += [
                "- Documents for the user (reports, pages, tables) written outside git are archived at the end of the "
                "turn. Name the file's path in your final answer, so files made by scripts are found too.",
            ]
    return MARK_BEGIN + "\n" + "\n".join(lines) + "\n" + MARK_END


def strip_block(text: str, begin: str, end: str) -> str:
    while begin in text:
        head, rest = text.split(begin, 1)
        tail = rest.split(end, 1)[1] if end in rest else ""
        text = head.rstrip("\n") + ("\n" + tail.lstrip("\n") if tail.strip() else "\n")
    return text


def install_rules(plan: Plan, store: Store, path: Path, agent: str, uninstall: bool) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    text = strip_block(strip_block(text, *OLD_MARKS), MARK_BEGIN, MARK_END).rstrip("\n")
    if not uninstall:
        text = (text + "\n\n" if text else "") + rules(store, agent)
    plan.write(path, text + "\n")
    plan.say("%s: rules block %s in %s" % (agent, "removed" if uninstall else "set", path))


# ---------------------------------------------------------------- the command itself


def install_link(plan: Plan, uninstall: bool) -> None:
    """`artikeep` on PATH: a symlink in ~/.local/bin, only if that folder is on PATH and the name is free."""
    if not ENTRY.exists():
        return  # installed with pip: the package already put the command on PATH
    bindir = HOME / ".local" / "bin"
    link = bindir / "artikeep"
    ours = link.is_symlink() and Path(os.readlink(str(link))) == ENTRY
    if uninstall:
        if ours and not plan.dry:
            link.unlink()
        if ours:
            plan.say("command: removed %s" % link)
        return
    if str(bindir) not in os.environ.get("PATH", "").split(os.pathsep):
        plan.say("command: %s is not on PATH; run artikeep as %s" % (bindir, " ".join(launcher())))
        return
    if ours:
        return
    if link.exists() or link.is_symlink():
        plan.say("command: %s exists and is not ours; left as is" % link)
        return
    if not plan.dry:
        bindir.mkdir(parents=True, exist_ok=True)
        link.symlink_to(ENTRY)
    plan.say("command: %s -> %s" % (link, ENTRY))


# ---------------------------------------------------------------- entry points


def detect() -> list:
    found = []
    if (HOME / ".claude").exists() or shutil.which("claude"):
        found.append("claude-code")
    if (HOME / ".codex").exists() or shutil.which("codex"):
        found.append("codex")
    return found


def run(store: Store, a) -> int:
    agents = detect() if a.agents == "auto" else [x.strip() for x in a.agents.split(",") if x.strip()]
    if not agents:
        print("No Claude Code or Codex found on this machine (~/.claude, ~/.codex).")
        return 1
    plan = Plan(a.dry_run)
    if not a.uninstall:
        store.ensure()
        conf_path = store.root / "artikeep.json"
        conf = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.exists() else {}
        if a.mcp_scope:
            conf["mcp_scope"] = a.mcp_scope
        if a.mcp_save:
            conf["mcp_save"] = True
        if a.mcp_scope or a.mcp_save:
            plan.write(conf_path, json.dumps(conf, ensure_ascii=False, indent=2) + "\n")
        if not os.environ.get("ARTIKEEP_HOME"):
            if not a.dry_run:
                config.set_home(store.root)
        plan.say("archive: %s" % store.root)
    install_link(plan, a.uninstall)
    for agent in agents:
        if agent == "claude-code":
            install_claude_hooks(plan, a.uninstall)
            install_rules(plan, store, CLAUDE_MD, agent, a.uninstall)
        elif agent == "codex":
            install_codex_hooks(plan, a.uninstall)
            install_rules(plan, store, CODEX_AGENTS_MD, agent, a.uninstall)
        else:
            plan.say("unknown agent %s (known: claude-code, codex)" % agent)
            continue
        if not a.no_mcp:
            install_mcp(plan, agent, a.uninstall)
    if not a.uninstall and not a.dry_run:
        print("done. New agent sessions pick the hooks up; in a running Claude Code session open /hooks once.")
        print("check with: %s doctor" % " ".join(launcher()))
    return 0


def doctor(store: Store) -> int:
    ok = True

    def line(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(("ok    " if good else "FAIL  ") + msg)

    line(sys.version_info >= (3, 9), "python %s at %s" % (sys.version.split()[0], sys.executable))
    line(store.root.exists(), "archive %s" % store.root)
    if (store.root / ".git").exists():
        remote = subprocess.run(["git", "-C", str(store.root), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
        print("info  git remote: %s" % (remote or "none (local only)"))
    else:
        print("info  archive is not a git repository: no history, no sync (artikeep init makes one)")
    m = store.load()
    last = {}
    for e in m["items"].values():
        a = agent_of(e)
        last[a] = max(last.get(a, ""), e.get("updated") or "")
    for a, ts in sorted(last.items()):
        print("info  %-11s last saved %s" % (a, ts[:16].replace("T", " ")))
    print("info  %d items" % len(m["items"]))
    def hook_cmds(data: dict) -> list:
        return [h.get("command", "") for gs in (data.get("hooks") or {}).values() for g in gs for h in g.get("hooks", [])]

    def mcp_registered(cli: str) -> bool:
        if not shutil.which(cli):
            return False
        return subprocess.run([cli, "mcp", "get", "artikeep"], capture_output=True, text=True, timeout=60).returncode == 0

    if CLAUDE_SETTINGS.exists():
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        cmds = hook_cmds(data)
        mine = [c for c in cmds if "artikeep" in c and " hook claude-code " in c]
        plugin = any(k.startswith("artikeep@") and v for k, v in (data.get("enabledPlugins") or {}).items())
        if plugin and mine:
            line(False, "Claude Code: both the plugin and installer hooks are on, every artifact is saved twice; "
                        "keep one (artikeep install --uninstall --agents claude-code)")
        elif plugin:
            line(True, "Claude Code: hooks and MCP server from the artikeep plugin")
        elif mine or (HOME / ".claude").exists():
            line(len(mine) >= 4, "Claude Code hooks: %d of 4" % len(mine))
            line(mcp_registered("claude"), "Claude Code: MCP server artikeep registered")
        line(not any(OLD_HOOK in c for c in cmds), "Claude Code: no leftover hooks of the old artifact_archive.py")
        days = data.get("cleanupPeriodDays") or 30
        line(days >= 365, "Claude Code keeps transcripts %s days%s" % (
            days, "" if days >= 365 else ' (lost artifacts are recovered from them: set "cleanupPeriodDays": 3650 in %s)' % CLAUDE_SETTINGS))
    if CODEX_HOOKS.exists():
        n = len([c for c in hook_cmds(json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))) if " hook codex " in c])
        if n:
            line(n >= 2, "Codex hooks: %d of 2" % n)
            line(mcp_registered("codex"), "Codex: MCP server artikeep registered")
        else:
            print("info  Codex: not wired (artikeep install --agents codex)")
    errs = store.log / "errors.log"
    if errs.exists():
        recent = [ln for ln in errs.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.startswith("--- ")][-3:]
        print("info  last errors:\n      " + "\n      ".join(recent) if recent else "info  no errors logged")
    return 0 if ok else 1
