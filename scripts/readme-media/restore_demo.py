"""The restore demo GIF: a terminal session with the real output of `artikeep search` and `artikeep restore`
on the synthetic archive. Usage: python3 restore_demo.py OUT.gif   (ARTIKEEP_HOME must hold the demo archive)
Paths are shortened to ~ for display; nothing else in the output is edited."""
import asyncio
import html
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

OUT = Path(sys.argv[1])
REPO = Path(__file__).resolve().parents[2]
HOME = os.environ["ARTIKEEP_HOME"]
ITEM = "2026-10-08-pricing-page-redesign"
W, H = 920, 470


def run(*args):
    r = subprocess.run(["python3", str(REPO / "bin" / "artikeep"), *args], capture_output=True, text=True, env=os.environ)
    return r.stdout.strip("\n")


def short(text, mapping):
    for old, new in mapping:
        text = text.replace(old, new)
    return text


def frame_html(lines, caption=None, cursor=True):
    body = "\n".join(lines)
    cap = '<div class="cap">%s</div>' % html.escape(caption) if caption else ""
    return """<!doctype html><meta charset="utf-8"><style>
body{margin:0;width:%dpx;height:%dpx;background:#1B2420;font:15px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:#ECEFEA;overflow:hidden}
.bar{height:34px;background:#26322C;display:flex;align-items:center;gap:8px;padding:0 14px}.bar i{width:11px;height:11px;border-radius:50%%;background:#4A5851}
.bar b{margin-left:10px;font:500 13px -apple-system,system-ui,sans-serif;color:#A9B4AE}
pre{margin:0;padding:18px 22px;white-space:pre-wrap;overflow-wrap:anywhere;height:%dpx;box-sizing:border-box;overflow:hidden}
.p{color:#7FC4A8}.d{color:#8A968F}.k{color:#E9B872}
.cap{position:absolute;left:0;right:0;bottom:0;padding:14px 22px;background:#2E5E4E;color:#fff;font:600 17px -apple-system,system-ui,sans-serif}
</style><div class="bar"><i></i><i></i><i></i><b>artikeep</b></div><pre>%s%s</pre>%s""" % (W, H, H - 34, body, '<span class="p">▌</span>' if cursor else "", cap)


def colored(cmd=None, text=None):
    if cmd is not None:
        return '<span class="p">$</span> ' + html.escape(cmd)
    out = []
    for ln in text.split("\n"):
        e = html.escape(ln)
        out.append('<span class="d">%s</span>' % e if ln.startswith("    ") else e)
    return "\n".join(out)


async def main():
    home = Path(HOME)
    mapping = [(str(home.resolve()), "~/artikeep"), (str(home), "~/artikeep"), ("/private" + str(home.resolve().parent) , "~/tmp")]
    restore_to = home.parent / "restored"
    cmd1, cmd2, cmd3 = "artikeep search pricing", "artikeep restore %s --to ~/restored" % ITEM, "ls ~/restored"
    out1 = short(run("search", "pricing"), mapping)
    out2 = short(run("restore", ITEM, "--to", str(restore_to)), [(str(restore_to.resolve()), "~/restored"), (str(restore_to), "~/restored")] + mapping)
    out3 = "\n".join(sorted(p.name for p in restore_to.iterdir() if not p.name.startswith(".")))
    # out2: keep the first line and the instruction, the instruction wrapped for the frame
    steps = [
        (None, "The hosted link died after the Claude account changed. The copy is on your disk.", 2600),
        (cmd1, out1, 2200),
        (cmd2, out2, 3600),
        (cmd3, out3, 3600, "The agent publishes it again; artikeep keeps it as a new version of the same item."),
    ]
    frames, shown = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": W, "height": H})

        async def snap(lines, caption=None, cursor=True):
            await pg.set_content(frame_html(lines, caption, cursor))
            return Image.open(io.BytesIO(await pg.screenshot())).convert("RGB")

        out = []  # (image, ms)
        out.append((await snap([], steps[0][1], cursor=False), steps[0][2]))
        for step in steps[1:]:
            cmd, text, hold = step[:3]
            note = step[3] if len(step) > 3 else None
            for n in range(0, len(cmd) + 1, 3):  # typing
                out.append((await snap(shown + [colored(cmd=cmd[:n])]), 70))
            shown.append(colored(cmd=cmd))
            out.append((await snap(shown), 350))
            shown.append(colored(text=text))
            out.append((await snap(shown + [""], note, cursor=not note), hold))
        await b.close()
    # one shared palette keeps the file small
    first = out[-1][0].quantize(colors=48, method=Image.Quantize.MEDIANCUT)
    imgs = [im.quantize(palette=first, dither=Image.Dither.NONE) for im, _ in out]
    imgs[0].save(OUT, save_all=True, append_images=imgs[1:], duration=[ms for _, ms in out], loop=0, optimize=True, disposal=1)
    print(OUT, OUT.stat().st_size // 1024, "KB,", len(imgs), "frames")


asyncio.run(main())
