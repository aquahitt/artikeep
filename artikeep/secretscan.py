"""Look for secrets in what the archive is about to push.

Agents put real data into artifacts: a key in a debugging page, a token in a log table.
Before each push the lines the unpushed commits add are checked against well-known
secret shapes, plus a generic `key = "..."` rule that needs a random-looking value.
A hit keeps everything on disk but stops the push (setting `secret_scan`: "block", the
default; "warn" pushes and tells you; "off" skips the check).

Ways out of a block, none of which loses anything:
  * the text was a false alarm: `artikeep allow ITEM` marks what is found now as fine;
  * the secret was removed again (edit, delete): the unpushed commits are squashed, so
    the old text is never pushed, and the push goes ahead.

Only a small list of patterns, no dependency: it catches the common, loud leaks, not
every secret.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess

from artikeep.store import Store

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SKIP_PARTS = ("/_vendor/",)
SKIP_SUFFIX = (".min.js", ".map", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".woff", ".woff2", ".ttf", ".zip")
PLACEHOLDER = re.compile(r"example|your[_-]|xxxx|changeme|placeholder|dummy|sample|fake|test[_-]?key|<[a-z_ -]+>|\$\{|\{\{", re.I)

RULES = [
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("Anthropic or OpenAI key", re.compile(r"\bsk-(?:ant-|proj-)[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY")),
]
GENERIC = re.compile(r"""(?i)\b[\w-]*(?:api[_-]?key|secret|token|passwd|password)[\w-]*["']?\s*[:=]\s*["']([A-Za-z0-9/+=_.-]{20,})["']""")


def entropy(s: str) -> float:
    return -sum(s.count(c) / len(s) * math.log2(s.count(c) / len(s)) for c in set(s))


def fingerprint(rule: str, text: str) -> str:
    return hashlib.sha256((rule + "\0" + text).encode()).hexdigest()[:16]


def scan_line(line: str) -> list:
    """[(rule, fingerprint)] for one line of text."""
    if len(line) > 100_000:
        return []
    out = []
    for rule, rx in RULES:
        for m in rx.finditer(line):
            if "EXAMPLE" not in m.group(0).upper():
                out.append((rule, fingerprint(rule, m.group(0))))
    for m in GENERIC.finditer(line):
        value = m.group(1)
        if not PLACEHOLDER.search(value) and entropy(value) >= 3.5 and not value.startswith(("http", "/")):
            out.append(("secret-looking value", fingerprint("generic", value)))
    return out


def scan_diff(diff: str, allow=()) -> list:
    """Findings in the added lines of a unified diff: [{file, line, rule, fp, item}], once per fingerprint and file."""
    found, seen = [], set()
    path, new = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
            new = int(m.group(1)) if m else 0
        elif raw.startswith("+") and path:
            if not (path.endswith(SKIP_SUFFIX) or any(p in "/" + path for p in SKIP_PARTS)):
                for rule, fp in scan_line(raw[1:]):
                    if fp not in allow and (fp, path) not in seen:
                        seen.add((fp, path))
                        parts = path.split("/")
                        found.append({"file": path, "line": new, "rule": rule, "fp": fp,
                                      "item": parts[1] if parts[0] == "items" and len(parts) > 2 else None})
            new += 1
        elif not raw.startswith("-"):
            new += 1
    return found


def _git(store: Store, *args):
    return subprocess.run(["git", "-C", str(store.root)] + list(args), capture_output=True, text=True, errors="replace")


def remote_base(store: Store):
    """The remote-tracking commit this branch pushes onto, or None before the first push."""
    branch = _git(store, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
    r = _git(store, "rev-parse", "--verify", "-q", "refs/remotes/origin/%s" % branch)
    return r.stdout.strip() if r.returncode == 0 else None


def unpushed(store: Store, allow=()) -> tuple:
    """(findings in every unpushed commit, findings still present in the net change, base)."""
    base = remote_base(store)
    rng = "%s..HEAD" % base if base else "HEAD"
    log = _git(store, "log", "-p", "--no-color", "--format=", "-U0", rng).stdout
    net = _git(store, "diff", "--no-color", "-U0", base or EMPTY_TREE, "HEAD").stdout
    return scan_diff(log, allow), scan_diff(net, allow), base


def describe(f: dict) -> str:
    return "%s:%d (%s)" % (f["file"], f["line"], f["rule"])


def check_before_push(store: Store) -> tuple:
    """(ok to push, findings). Squashes the unpushed commits when the secret is gone again."""
    mode = store.settings.get("secret_scan", "block")
    if mode in ("off", False):
        return True, []
    allow = set(store.settings.get("secret_allow") or [])
    history, net, base = unpushed(store, allow)
    save_findings(store, net or history)
    if not history:
        return True, []
    if not net and base:
        _git(store, "reset", "--soft", base)
        _git(store, "commit", "-q", "-m", "archive: squashed (a secret that was removed again is not pushed)")
        save_findings(store, [])
        return True, []
    return mode == "warn", net or history


def findings_path(store: Store):
    return store.log / "secrets.json"


def save_findings(store: Store, findings: list) -> None:
    p = findings_path(store)
    try:
        if findings:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding="utf-8")
        elif p.exists():
            p.unlink()
    except Exception:
        store.error("secrets.json")


def load_findings(store: Store) -> list:
    try:
        return json.loads(findings_path(store).read_text(encoding="utf-8"))
    except Exception:
        return []


def allow(store: Store, item: str | None = None, rule: str | None = None) -> list:
    """Mark the current findings (of one item and rule, when given) as fine. Returns them."""
    history, net, _ = unpushed(store, set(store.settings.get("secret_allow") or []))
    hits = [f for f in history + net if (not item or f["item"] == item) and (not rule or f["rule"].lower() == rule.lower())]
    if not hits:
        return []
    conf_path = store.root / "artikeep.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.exists() else {}
    conf["secret_allow"] = sorted(set(conf.get("secret_allow") or []) | {f["fp"] for f in hits})
    conf_path.write_text(json.dumps(conf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    store.settings["secret_allow"] = conf["secret_allow"]
    return hits
