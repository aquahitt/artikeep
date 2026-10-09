"""Claude Code: the Artifact tool, the Claude Docs connector, scratchpad drafts.

Hooks (installed by `artikeep install`, or by the Claude Code plugin):
  publish   PostToolUse on Artifact: copy the page and its files, snapshot a version.
  docs      PostToolUse on mcp__claude_ai_Claude_Docs__*: log writes; decode `export`
            results into doc-<tab>.<ext>; remember which docs are unexported.
  stop      Stop: mirror scratchpad pages into drafts/; once per edit series, ask
            Claude to export docs it changed (Docs has no other way to get the text).
  check     SessionStart: archive recent publishes the hook missed, from transcripts.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path

from artikeep import config
from artikeep.store import Store
from artikeep.util import (
    copy_file, html_title, now_iso, project_root, resolve, text_blob, with_charset,
)

URL_RE = re.compile(r"https://claude\.ai/(?:code/)?artifact/[0-9A-Za-z-]+")
ABS_PATH_RE = re.compile(r"(/(?:private/)?(?:tmp|var|Users|home)/[^\s\"'`<>|]+)")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
DOC_WRITE_TOOLS = ("__batch", "__update", "__create", "__delete")
EXPORT_EXT = {"markdown": "md", "notion": "notion.md", "text": "txt", "html": "html", "docx": "docx", "pdf": "pdf"}
TMP_ROOT = Path("/private/tmp") if Path("/private/tmp").exists() else Path("/tmp")
TRANSCRIPTS = Path.home() / ".claude" / "projects"
DRAFT_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".svg", ".json"}
DRAFT_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "Default", "GPUPersistentCache"}
DRAFT_MAX_BYTES = 5 * 1024 * 1024
DRAFT_MAX_DEPTH = 3  # page sources sit shallow; deeper trees are tool output


def _t(store: Store, ru: str, en: str) -> str:
    return ru if config.lang(store.settings) == "ru" else en


def _say(msg: str) -> None:
    print(json.dumps({"systemMessage": msg}, ensure_ascii=False))


# ---------------------------------------------------------------- Artifact tool


def handle_artifact(store: Store, payload: dict):
    ti = payload.get("tool_input") or {}
    action = ti.get("action") or "publish"
    if action not in ("publish", "read", "delete"):
        return None
    resp_text = json.dumps(payload.get("tool_response"), ensure_ascii=False, default=str)
    resp_urls = URL_RE.findall(resp_text)
    url = ti.get("url") or (resp_urls[0] if resp_urls else None)
    cwd = payload.get("cwd") or os.getcwd()
    root = resolve(ti["root"], cwd) if ti.get("root") else Path(cwd)
    when = payload.get("timestamp") or now_iso()

    with store.lock("manifest"):
        m = store.load()
        if action == "delete":
            if url and url in m["items"] and not ti.get("path"):
                m["items"][url]["deleted"] = now_iso()
                store.save(m)
            return "deleted"
        if action == "read":
            # A read of our own artifact saves the server's page to a file: keep it as a snapshot.
            if not url or ti.get("path") or ti.get("paths"):
                return None
            saved = [p for p in ABS_PATH_RE.findall(resp_text) if p.endswith((".html", ".htm")) and Path(p).is_file()]
            if not saved:
                return None
            entry = store.entry_for(m, url, ti.get("title") or html_title(saved[0]))
            entry.setdefault("url", url)
            entry.setdefault("agent", "claude-code")
            copy_file(saved[0], store.item_dir(entry) / "server" / "index.html")
            entry["server_snapshot"] = now_iso()
            store.save(m)
            return "read"

        key = url or ("local:" + str(ti.get("file_path") or ti.get("type_url") or now_iso()))
        source = resolve(ti["file_path"], cwd) if ti.get("file_path") and not ti.get("asset") else None
        title_guess = ti.get("title") or (html_title(source) if source else None) or (source.stem if source else None)
        entry = store.entry_for(m, key, title_guess, when)
        entry["agent"] = "claude-code"
        if url:
            entry["url"] = url
        d = store.item_dir(entry)
        d.mkdir(parents=True, exist_ok=True)
        copied, missing = [], []
        if ti.get("type_url"):
            entry["type_url"] = ti["type_url"]
        typed = bool(entry.get("type_url"))

        def take(src, rel):
            (copied if copy_file(src, d / rel) else missing).append(str(src))

        if ti.get("asset"):
            for p in ti.get("file_paths") or ([ti["file_path"]] if ti.get("file_path") else []):
                take(resolve(p, cwd), Path("assets") / Path(p).name)
        elif ti.get("file_path"):
            src = resolve(ti["file_path"], root if ti.get("root") else cwd)
            rel = os.path.relpath(src, root) if ti.get("root") else Path(src).name
            if typed:
                take(src, Path("data") / rel)
            elif Path(src).suffix.lower() in (".html", ".htm"):
                take(src, "index.html")
                entry["source_name"] = Path(src).name
            else:
                # e.g. a Design canvas: canvas.json is the entry; the viewer becomes index.html
                take(src, rel)
                entry["source_name"] = str(rel)
        files = ti.get("files")
        if isinstance(files, dict):
            for pub, spec in files.items():
                if spec is None:
                    continue
                if isinstance(spec, dict) and "artifact" in spec:
                    entry.setdefault("foreign_files", {})[pub] = spec
                    continue
                src = spec["from"] if isinstance(spec, dict) else spec
                take(resolve(src, root), pub)
        elif isinstance(files, list):
            for spec in files:
                take(resolve(spec["path"], root), spec["path"])

        title = ti.get("title") or html_title(d / "index.html") or entry.get("title") or title_guess
        if title:
            entry["title"] = title
        if ti.get("description"):
            entry["description"] = ti["description"]
        entry["project"] = project_root(cwd)
        if when >= entry.get("updated", ""):
            entry["updated"] = when
        entry["publishes"].append({
            "at": when, "session": payload.get("session_id"), "tool_use_id": payload.get("tool_use_id"),
            "source": ti.get("file_path"), "asset": bool(ti.get("asset")), "copied": len(copied), "missing": missing,
        })
        if not url:
            entry["url_unknown"] = True
        if copied and not ti.get("asset"):
            store.snapshot(d, entry, when, ti.get("label"))
        store.save(m)
    if missing or not url:
        return "partial: missing=%s url=%s" % (missing, url)
    return "ok"


def cmd_publish(store: Store, payload: dict) -> None:
    store.log_payload("publish", payload)
    if payload.get("tool_name") != "Artifact":
        return
    try:
        result = handle_artifact(store, payload)
    except Exception:
        store.error("publish")
        _say(_t(store, "artikeep: копия не сохранена, см. %s/errors.log", "artikeep: copy not saved, see %s/errors.log") % store.log)
        return
    if result is None:
        return
    store.kick()
    if result.startswith("partial"):
        _say(_t(store, "artikeep: сохранено не всё (%s)", "artikeep: not everything was saved (%s)") % result)


# ---------------------------------------------------------------- Claude Docs


def doc_id_of(ti: dict, resp: str):
    c = ti.get("container") or {}
    if c.get("kind") == "project" and c.get("id"):
        return c["id"]
    ref = ti.get("ref") or {}
    if ref.get("object") == "project" and ref.get("id"):
        return ref["id"]
    m = re.search(r"claude\.ai/(?:code/)?artifact/(?:[^/\s\"]*-)?(%s)" % UUID_RE.pattern, resp)
    if m:
        return m.group(1)
    m = re.search(r'"project"\s*:\s*\{[^}]*"id"\s*:\s*"(%s)"' % UUID_RE.pattern, resp)
    return m.group(1) if m else None


def decode_export(resp_obj, resp: str):
    """The export tool returns the tab inline as base64; find and decode it."""
    import base64

    cands = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and (k.lower() in ("base64", "bytes_b64", "b64")
                                           or (k.lower() in ("data", "content", "bytes", "file") and len(v) > 16)):
                    cands.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and o.lstrip().startswith("{"):
            try:
                walk(json.loads(o))
            except Exception:
                pass

    walk(resp_obj)
    cands += sorted(re.findall(r"[A-Za-z0-9+/=\r\n]{200,}", resp), key=len, reverse=True)[:3]
    for c in cands:
        s = re.sub(r"\s+", "", c.split(",", 1)[1] if c.startswith("data:") else c)
        try:
            data = base64.b64decode(s, validate=True)
        except Exception:
            continue
        if data:
            return data
    return None


def _docs_state_path(store: Store) -> Path:
    return store.log / "docs_state.json"


def _load_docs_state(store: Store) -> dict:
    try:
        return json.loads(_docs_state_path(store).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_docs_state(store: Store, st: dict) -> None:
    p = _docs_state_path(store)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def cmd_docs(store: Store, payload: dict) -> None:
    name = payload.get("tool_name") or ""
    if "Claude_Docs__" not in name:
        return
    is_write = name.endswith(DOC_WRITE_TOOLS)
    is_export = name.endswith("__export")
    if not (is_write or is_export):
        return
    ti = payload.get("tool_input") or {}
    resp_obj = payload.get("tool_response")
    resp = text_blob(resp_obj)
    doc = doc_id_of(ti, resp)
    if not doc:
        store.log_payload("docs-unknown", payload)
        return
    url = "https://claude.ai/code/artifact/" + doc
    now = now_iso()
    with store.lock("manifest"):
        m = store.load()
        # A doc made from the Docs artifact type may already be filed under its short artifact url.
        key = next((k for k, e in m["items"].items() if doc in k or doc in " ".join(e.get("aliases", []))), url)
        create = (ti.get("container") or {}).get("create") or {}
        title = create.get("name")
        entry = store.entry_for(m, key, title or ("doc " + doc[:8]))
        entry.setdefault("url", url)
        entry["kind"] = "claude-doc"
        entry["agent"] = "claude-code"
        entry.setdefault("project", project_root(payload.get("cwd") or os.getcwd()))
        if title:
            entry["title"] = title
        d = store.item_dir(entry)
        d.mkdir(parents=True, exist_ok=True)
        rec = {"at": now, "session": payload.get("session_id"), "tool": name.split("__")[-1], "input": ti, "response": resp[:20000]}
        with open(d / "docs-ops.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        saved = None
        if is_export:
            data = decode_export(resp_obj, resp)
            fmt = ti.get("format") or "markdown"
            if data:
                saved = "doc-%s.%s" % (re.sub(r"[^\w-]", "_", ti.get("file") or "tab"), EXPORT_EXT.get(fmt, fmt))
                (d / saved).write_bytes(with_charset(data) if fmt == "html" else data)
                entry["exported"] = now
                store.snapshot(d, entry, now)
            else:
                store.log_payload("docs-export-undecoded", payload)
        entry["updated"] = now
        store.save(m)
    with store.lock("docs"):
        st = _load_docs_state(store)
        s = st.setdefault(doc, {"tabs": []})
        s["title"] = entry.get("title")
        tabs = set(s.get("tabs", []))
        tabs |= set(re.findall(r'"f\d*"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4})"', resp))
        for t in re.findall(r'"files"\s*:\s*\[(.*?)\]', resp, re.S):
            tabs |= set(re.findall(r'"id"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4})"', t))
        if ti.get("file"):
            tabs.add(ti["file"])
        s["tabs"] = sorted(tabs)
        tick = time.time()
        if is_write:
            s["last_write"] = tick
            s["session"] = payload.get("session_id")
        if is_export and saved:
            s.setdefault("exported_tabs", {})[ti.get("file") or "tab"] = now
            s["last_export"] = tick
        _save_docs_state(store, st)
    store.kick()
    if is_export and not saved:
        _say(_t(store, "artikeep: экспорт документа не удалось раскодировать, см. .hooklog/payloads.jsonl",
                "artikeep: could not decode the document export, see .hooklog/payloads.jsonl"))


def docs_reminder(store: Store, payload: dict):
    """Block the stop once per edit series if a doc changed after its last export."""
    sess = payload.get("session_id")
    with store.lock("docs"):
        st = _load_docs_state(store)
        due = []
        for doc, s in st.items():
            if s.get("session") != sess or not s.get("last_write"):
                continue
            if s.get("last_export", 0) >= s["last_write"] or s.get("reminded_for") == s["last_write"]:
                continue
            s["reminded_for"] = s["last_write"]
            due.append((doc, s))
        if due:
            _save_docs_state(store, st)
    if not due:
        return None
    ru = config.lang(store.settings) == "ru"
    lines = []
    for doc, s in due:
        tabs = ", ".join(s.get("tabs") or []) or ("id вкладок возьми из read документа" if ru else "take tab ids from a read of the doc")
        lines.append(("«%s» (doc %s; вкладки: %s)" if ru else "\"%s\" (doc %s; tabs: %s)") % (s.get("title") or doc, doc, tabs))
    if ru:
        return ("artikeep: документы Claude Docs правились после последнего экспорта — " + "; ".join(lines)
                + '. Экспортируй каждую вкладку: mcp__claude_ai_Claude_Docs__export с container {"kind":"project","id":"<doc>"}, '
                'file = id вкладки, format = "markdown" — hook сохранит копию в %s. '
                "Если экспорт недоступен, скажи об этом пользователю одной строкой и заканчивай." % store.root)
    return ("artikeep: Claude Docs documents changed after their last export — " + "; ".join(lines)
            + '. Export every tab: mcp__claude_ai_Claude_Docs__export with container {"kind":"project","id":"<doc>"}, '
            'file = the tab id, format = "markdown"; the hook keeps a copy in %s. '
            "If export is unavailable, tell the user in one line and finish." % store.root)


# ---------------------------------------------------------------- drafts


def scratchpads(session_id):
    if not session_id:
        return []
    return [p for p in TMP_ROOT.glob("claude-*/*/%s/scratchpad" % session_id) if p.is_dir()]


def mirror_drafts(store: Store, session_id, cwd=None) -> int:
    changed = 0
    droot = store.root / "drafts"
    for sp in scratchpads(session_id):
        html_dirs = set()
        for dirpath, dirnames, filenames in os.walk(sp):
            depth = len(Path(dirpath).relative_to(sp).parts)
            dirnames[:] = [] if depth >= DRAFT_MAX_DEPTH else [
                x for x in dirnames if x not in DRAFT_SKIP_DIRS and not x.endswith((".xcarchive", ".app"))]
            if any(f.endswith((".html", ".htm")) for f in filenames):
                html_dirs.add(Path(dirpath))
        if not html_dirs:
            continue
        existing = list(droot.glob("*-%s" % session_id[:8])) if droot.exists() else []
        stamp = dt.datetime.fromtimestamp(sp.stat().st_mtime).date().isoformat()
        dest_root = existing[0] if existing else droot / ("%s-%s" % (stamp, session_id[:8]))
        meta = dest_root / "_meta.json"
        if not meta.exists():
            dest_root.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({"session": session_id, "agent": "claude-code", "project": project_root(cwd)},
                                       ensure_ascii=False), encoding="utf-8")
        for hd in html_dirs:
            for f in hd.iterdir():
                if not f.is_file() or f.suffix.lower() not in DRAFT_EXT or f.stat().st_size > DRAFT_MAX_BYTES:
                    continue
                dst = dest_root / f.relative_to(sp)
                if dst.exists() and dst.stat().st_mtime >= f.stat().st_mtime:
                    continue
                copy_file(f, dst)
                changed += 1
    return changed


def cmd_stop(store: Store, payload: dict) -> None:
    try:
        if mirror_drafts(store, payload.get("session_id"), payload.get("cwd")):
            store.kick()
    except Exception:
        store.error("drafts")
    try:
        reason = docs_reminder(store, payload)
        if reason:
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    except Exception:
        store.error("docs reminder")


# ---------------------------------------------------------------- self-check


def recent_publishes(store: Store, days: int) -> list:
    cutoff = time.time() - days * 86400
    found = []
    for f in TRANSCRIPTS.rglob("*.jsonl") if TRANSCRIPTS.exists() else []:
        try:
            if f.stat().st_mtime < cutoff:
                continue
            results, uses = {}, []
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"Artifact"' not in line and "tool_result" not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    content = (rec.get("message") or {}).get("content")
                    if not isinstance(content, list):
                        continue
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") == "tool_use" and c.get("name") == "Artifact":
                            uses.append((c, rec))
                        elif c.get("type") == "tool_result":
                            results[c.get("tool_use_id")] = c
            for c, rec in uses:
                inp = c.get("input") or {}
                if (inp.get("action") or "publish") != "publish":
                    continue
                r = results.get(c["id"])
                if r is None or r.get("is_error"):
                    continue
                if "refused" in json.dumps(r.get("content"), ensure_ascii=False)[:300].lower():
                    continue
                found.append({
                    "tool_use_id": c["id"], "tool_name": "Artifact", "tool_input": inp,
                    "tool_response": r.get("content"), "session_id": rec.get("sessionId") or f.stem,
                    "cwd": rec.get("cwd"), "timestamp": rec.get("timestamp"),
                })
        except Exception:
            store.error("recent_publishes %s" % f)
    return found


def cmd_check(store: Store, payload: dict, days: int = 3) -> None:
    m = store.load()
    known = {p.get("tool_use_id") for e in m["items"].values() for p in e.get("publishes", [])}
    lost, backfilled = [], 0
    for p in recent_publishes(store, days):
        if p["tool_use_id"] in known:
            continue
        r = handle_artifact(store, p)
        if r and r.startswith("partial"):
            lost.append(p["tool_input"].get("file_path") or p["tool_use_id"])
        backfilled += 1
    store.kick()  # also pulls what other machines pushed
    if backfilled or lost:
        msg = _t(store, "artikeep: hook пропустил %d публикаций, дописаны задним числом.",
                 "artikeep: the hook missed %d publishes; archived them now.") % backfilled
        if lost:
            msg += _t(store, " Без исходника: %s.", " Source gone: %s.") % ", ".join(lost[:5])
        msg += _t(store, " Проверьте, что hook artikeep подключён (artikeep doctor).",
                  " Check that the artikeep hook is installed (artikeep doctor).")
        _say(msg)


COMMANDS = {"publish": cmd_publish, "docs": cmd_docs, "stop": cmd_stop, "drafts": cmd_stop, "check": cmd_check}
