"""Why a version exists: the request the user made, read from the agent's transcript.

A version records the user message that led to it (`request`) and the session
(`session`), so the history answers "why is it like this" and a session can be
resumed. Switch it off with `"provenance": false` in artikeep.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MAX_CHARS = 500
SHORT_REPLY = 16  # "yes", "go on": say nothing alone, so the ask before it comes along

# Wrappers the agents put in user turns that are not something the user typed.
INTERNAL_TAGS = (
    "command-name", "command-message", "command-args", "local-command-stdout", "local-command-stderr",
    "local-command-caveat", "system-reminder", "task-notification", "bash-input", "bash-stdout",
    "bash-stderr", "send_user_message_question_reply", "environment_context", "user_instructions",
    "turn_aborted", "subagent_notification", "user-prompt-submit-hook",
)
INTERNAL_RE = re.compile(r"^\s*<(%s)\b" % "|".join(INTERNAL_TAGS))
SYSTEM_BLOCK_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
PASTED_RE = re.compile(r"<pasted_content\b[^>]*>.*?</pasted_content\s*>", re.S)
COMMAND_RE = re.compile(r"<command-name>\s*(/?[^<\s]+)\s*</command-name>")
COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def enabled(settings: dict) -> bool:
    return settings.get("provenance", True) is not False


def clean(text: str) -> str:
    """One line, no system blocks, pasted material replaced by a marker, capped."""
    text = SYSTEM_BLOCK_RE.sub(" ", text or "")
    text = PASTED_RE.sub(" [pasted text] ", text)
    text = " ".join(text.split())
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1].rstrip() + "…"


def is_internal(text: str) -> bool:
    return bool(INTERNAL_RE.match(text or ""))


def _text_of(content) -> str | None:
    """Text a user typed in a message's content, or None when it is only tool results or images."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(parts) if parts else None
    return None


def _command(text: str) -> tuple:
    """('/name', 'args') for a slash-command record, else None."""
    m = COMMAND_RE.search(text)
    if not m:
        return None
    a = COMMAND_ARGS_RE.search(text)
    return (m.group(1) if m.group(1).startswith("/") else "/" + m.group(1)), (a.group(1).strip() if a else "")


def claude_code_request(transcript, tool_use_id=None) -> str | None:
    """The last thing the user asked for before a tool call of a Claude Code session.

    Reads the transcript forward and stops at the record that holds `tool_use_id`; without
    one (or when it is not there yet) it is the last request in the file. A slash command
    counts when it has arguments, or when a skill expanded it right after.
    """
    try:
        path = Path(transcript)
        if not path.is_file():
            return None
        request, before, pending, plain = None, None, None, False
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if tool_use_id and tool_use_id in line and '"tool_use"' in line:
                    break
                if '"user"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "user" or rec.get("isSidechain") or rec.get("isCompactSummary"):
                    continue
                text = _text_of((rec.get("message") or {}).get("content"))
                if text is None:
                    continue
                if rec.get("isMeta"):
                    if pending and not is_internal(text):
                        request, before, pending, plain = pending, request, None, False  # a skill expanded the command
                    continue
                cmd = _command(text)
                if cmd:
                    pending = None
                    if cmd[1]:
                        request, before, plain = "%s %s" % cmd, request, False
                    else:
                        pending = cmd[0]
                    continue
                if is_internal(text):
                    continue
                pending = None
                cleaned = clean(text)
                if cleaned:
                    request, before, plain = cleaned, request, True
        if plain and before and len(request) < SHORT_REPLY:
            request = "%s → %s" % (before, request)
        return clean(request) if request else None
    except Exception:
        return None


def for_version(settings: dict, request, session) -> dict:
    """The extra fields a version carries."""
    if not enabled(settings):
        return {}
    out = {}
    if request:
        out["request"] = request
    if session:
        out["session"] = session
    return out
