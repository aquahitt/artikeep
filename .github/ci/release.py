#!/usr/bin/env python3
"""Release helper for artikeep. Standard library only, Python 3.9+.

  release.py version              print the version the files carry
  release.py bump X.Y.Z           set X.Y.Z everywhere; CHANGELOG "## Unreleased" becomes "## X.Y.Z — today"
  release.py check [--tag vX.Y.Z] the files agree, CHANGELOG has a dated entry, the tag matches
  release.py notes [X.Y.Z]        the CHANGELOG entry as GitHub release notes

The version lives in three files that must agree: pyproject.toml (PyPI),
artikeep/__init__.py (artikeep --version) and .claude-plugin/plugin.json (the plugin).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "artikeep" / "__init__.py"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PYPROJECT_RE = re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")')
INIT_RE = re.compile(r'(?m)^(__version__\s*=\s*")([^"]+)(")')
PLUGIN_RE = re.compile(r'("version"\s*:\s*")([^"]+)(")')
ENTRY_RE = re.compile(r"(?m)^## (\S+)(?: — (\d{4}-\d{2}-\d{2}))?\s*$")


def fail(msg: str) -> None:
    print("release: " + msg, file=sys.stderr)
    sys.exit(1)


def versions() -> dict:
    out = {}
    for path, rx in ((PYPROJECT, PYPROJECT_RE), (INIT, INIT_RE), (PLUGIN, PLUGIN_RE)):
        m = rx.search(path.read_text(encoding="utf-8"))
        out[str(path.relative_to(ROOT))] = m.group(2) if m else None
    return out


def current() -> str:
    vs = versions()
    if len(set(vs.values())) != 1 or None in vs.values():
        fail("versions disagree: " + ", ".join("%s=%s" % kv for kv in vs.items()))
    return next(iter(vs.values()))


def key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def entries() -> list:
    """[(heading, date or None, start, end)] for each "## " section of CHANGELOG.md."""
    text = CHANGELOG.read_text(encoding="utf-8")
    ms = list(ENTRY_RE.finditer(text))
    return [(m.group(1), m.group(2), m.end(), ms[i + 1].start() if i + 1 < len(ms) else len(text))
            for i, m in enumerate(ms)]


def cmd_bump(new: str) -> None:
    if not SEMVER.match(new):
        fail("version must look like 1.2.3, got %r" % new)
    old = current()
    if key(new) <= key(old):
        fail("%s is not newer than %s" % (new, old))
    heads = [e[0] for e in entries()]
    text = CHANGELOG.read_text(encoding="utf-8")
    if "Unreleased" in heads:
        today = datetime.date.today().isoformat()
        text = re.sub(r"(?m)^## Unreleased\s*$", "## %s — %s" % (new, today), text, count=1)
    elif new not in heads:
        fail('CHANGELOG.md has neither "## Unreleased" nor "## %s — <date>": write the entry first' % new)
    for path, rx in ((PYPROJECT, PYPROJECT_RE), (INIT, INIT_RE), (PLUGIN, PLUGIN_RE)):
        path.write_text(rx.sub(lambda m: m.group(1) + new + m.group(3), path.read_text(encoding="utf-8"), count=1),
                        encoding="utf-8")
    CHANGELOG.write_text(text, encoding="utf-8")
    json.loads(PLUGIN.read_text(encoding="utf-8"))  # still valid JSON
    print("%s -> %s" % (old, new))


def cmd_check(tag) -> None:
    v = current()
    found = [e for e in entries() if e[0] == v]
    if not found:
        fail('CHANGELOG.md has no "## %s — <date>" entry' % v)
    if not found[0][1]:
        fail('the CHANGELOG.md entry for %s has no date ("## %s — YYYY-MM-DD")' % (v, v))
    if any(e[0] == "Unreleased" for e in entries()):
        fail('CHANGELOG.md still has a "## Unreleased" section')
    if tag is not None and tag != "v" + v:
        fail("tag %s does not match version %s (expected v%s)" % (tag, v, v))
    print("ok %s" % v)


def cmd_notes(v) -> None:
    v = v or current()
    for head, _, start, end in entries():
        if head == v:
            body = CHANGELOG.read_text(encoding="utf-8")[start:end].strip()
            print(body)
            print("\n---\n")
            print("Install or upgrade: `uv tool install --upgrade artikeep` (or `pipx upgrade artikeep`).  ")
            print("Claude Code plugin: `claude plugin update artikeep@artikeep`, then restart Claude Code.")
            return
    fail("CHANGELOG.md has no entry for %s" % v)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    sub.add_parser("bump").add_argument("version")
    sub.add_parser("check").add_argument("--tag")
    sub.add_parser("notes").add_argument("version", nargs="?")
    a = ap.parse_args()
    if a.cmd == "version":
        print(current())
    elif a.cmd == "bump":
        cmd_bump(a.version)
    elif a.cmd == "check":
        cmd_check(a.tag)
    else:
        cmd_notes(a.version)


if __name__ == "__main__":
    main()
