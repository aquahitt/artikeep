"""Small helpers shared by the store, adapters and importers."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import subprocess
from pathlib import Path

TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch  y  e yu ya".split(" "),
    )
)
CHARSET_RE = re.compile(rb"<meta[^>]+charset", re.I)
DOCTYPE_RE = re.compile(rb"^\s*<!doctype[^>]*>", re.I)
HTML_EXT = (".html", ".htm")


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(text: str | None) -> str:
    text = (text or "").strip().lower()
    out = []
    for ch in text:
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug[:60].strip("-") or "artifact"


def html_title(path) -> str | None:
    try:
        head = Path(path).read_text(encoding="utf-8", errors="ignore")[:20000]
    except Exception:
        return None
    m = re.search(r"<title[^>]*>(.*?)</title>", head, re.S | re.I)
    return html.unescape(m.group(1)).strip() or None if m else None


def md_title(text: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def title_of(path, data: bytes | None = None) -> str:
    """Best human title for a file: <title>, first Markdown heading, or the file name."""
    p = Path(path)
    if data is None:
        try:
            data = p.read_bytes()[:40000]
        except Exception:
            data = b""
    text = data[:40000].decode("utf-8", errors="ignore")
    if p.suffix.lower() in HTML_EXT:
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        if m and m.group(1).strip():
            return html.unescape(m.group(1)).strip()
    if p.suffix.lower() == ".md":
        t = md_title(text)
        if t:
            return t
    return p.stem.replace("_", " ").replace("-", " ").strip() or p.name


def with_charset(data: bytes) -> bytes:
    """Pages may omit <meta charset>: hosts wrap them in their own skeleton. Opened
    locally over file:// they would decode as Windows-1252 and break non-Latin text."""
    if CHARSET_RE.search(data[:1024]):
        return data
    meta = b'<meta charset="utf-8">'
    m = DOCTYPE_RE.match(data)
    if m:
        return data[: m.end()] + b"\n" + meta + data[m.end():]
    return meta + b"\n" + data


def write_bytes(dst, data: bytes) -> bool:
    """Write if different. HTML gets a charset. Returns True when the file now holds data."""
    dst = Path(dst)
    if dst.suffix.lower() in HTML_EXT:
        data = with_charset(data)
    if dst.exists() and dst.read_bytes() == data:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return True


def copy_file(src, dst) -> bool:
    src = Path(src)
    if not src.is_file():
        return False
    return write_bytes(dst, src.read_bytes())


def resolve(path, base) -> Path:
    p = Path(os.path.expanduser(str(path)))
    return p if p.is_absolute() else Path(base) / p


def project_root(cwd) -> str | None:
    """The repository a session works in: worktrees and subfolders map to the main checkout."""
    if not cwd:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            common = Path(r.stdout.strip())
            return str(common.parent if common.name == ".git" else common)
    except Exception:
        pass
    s = str(cwd)
    for marker in ("/.claude/worktrees/", "/.codex/worktrees/"):
        if marker in s:
            return s.split(marker)[0]
    return s


REF_RES = (
    re.compile(r"""(?:src|href|poster)\s*=\s*["']([^"'#?]+)"""),          # HTML
    re.compile(r"""url\(\s*["']?([^"')#?]+)"""),                          # CSS
    re.compile(r"""!?\[[^\]]*\]\(\s*<?([^)\s>#?]+)"""),                    # Markdown links and images
)
REF_MAX_BYTES = 20 * 1024 * 1024


def local_refs(path, data: bytes, limit: int = 200) -> dict:
    """Local files a page or document points to (images, styles, scripts), keyed by the
    relative path it uses. Only files inside the document's own folder tree: a reference
    that climbs out ("../x") or is absolute or remote would need rewriting, so it is left."""
    base = Path(path).resolve().parent
    text = data[:2_000_000].decode("utf-8", errors="ignore")
    out = {}
    for rx in REF_RES:
        for ref in rx.findall(text):
            ref = ref.strip()
            if not ref or ref.startswith(("/", "data:", "mailto:", "javascript:")) or "://" in ref or ".." in Path(ref).parts:
                continue
            target = (base / ref).resolve()
            if base not in target.parents or not target.is_file() or target.stat().st_size > REF_MAX_BYTES:
                continue
            rel = str(target.relative_to(base))
            if rel not in out and target != Path(path).resolve():
                out[rel] = target.read_bytes()
                if len(out) >= limit:
                    return out
    return out


def git_root(path) -> str | None:
    """Main checkout of the repository holding path, or None outside git."""
    p = Path(path)
    p = p if p.is_dir() else p.parent
    try:
        r = subprocess.run(["git", "-C", str(p), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    return project_root(p) if r.returncode == 0 else None


def git_tracked(path) -> bool:
    """True when git already keeps this file: no need to archive a second copy."""
    p = Path(path)
    try:
        r = subprocess.run(
            ["git", "-C", str(p.parent), "ls-files", "--error-unmatch", p.name],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def text_blob(x) -> str:
    """Everything a tool response says, flattened to one string."""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(text_blob(i) for i in x)
    if isinstance(x, dict):
        if x.get("type") == "text" and "text" in x:
            return x["text"]
        return json.dumps(x, ensure_ascii=False)
    return str(x)
