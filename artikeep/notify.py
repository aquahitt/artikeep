"""Desktop notification when capture fails: a line in a log is not a signal anyone sees.

macOS: osascript (text passed as arguments, never spliced into the script); Linux:
notify-send if installed. One notification per kind per interval, so a broken hook
does not flood the screen. Off with "notify": false in artikeep.json.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time

from artikeep.store import Store

SCRIPT = ["-e", "on run argv", "-e", "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run"]


def notify(store: Store, kind: str, message: str, title: str = "artikeep", every: int = 3600) -> bool:
    if not store.settings.get("notify", True):
        return False
    stamp = store.log / ("notify-%s.stamp" % kind)
    try:
        if stamp.exists() and time.time() - stamp.stat().st_mtime < every:
            return False
        if sys.platform == "darwin" and shutil.which("osascript"):
            cmd = ["osascript"] + SCRIPT + [message[:240], title]
        elif shutil.which("notify-send"):
            cmd = ["notify-send", title, message[:240]]
        else:
            return False
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
        return True
    except Exception:
        store.error("notify")
        return False
