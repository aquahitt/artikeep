"""Screenshots and the demo GIF of the gallery served at 127.0.0.1:8790. Usage: python3 capture.py OUTDIR"""
import asyncio
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8790/"
PRICING = '[data-open="2026-10-08-pricing-page-redesign"]'


def save_png(raw: bytes, name: str, width: int = 1600) -> None:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(OUT / name, optimize=True)


async def page(b, scheme="light", w=1440, h=900, dsf=2, mobile=False):
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dsf, color_scheme=scheme,
                              is_mobile=mobile, has_touch=mobile)
    pg = await ctx.new_page()
    await pg.goto(URL, wait_until="networkidle")
    await pg.wait_for_timeout(900)
    return pg


async def calm(pg):
    await pg.mouse.move(5, pg.viewport_size["height"] - 5)
    await pg.evaluate("document.activeElement && document.activeElement.blur()")
    await pg.wait_for_timeout(400)


async def stills(b):
    for scheme in ("light", "dark"):
        pg = await page(b, scheme)
        await calm(pg)
        save_png(await pg.screenshot(), "gallery-%s.png" % scheme)
        await pg.click(PRICING)
        await pg.wait_for_timeout(1200)
        await calm(pg)
        save_png(await pg.screenshot(), "versions-%s.png" % scheme)
        await pg.keyboard.press("c")
        await pg.wait_for_timeout(1800)
        await calm(pg)
        save_png(await pg.screenshot(), "compare-%s.png" % scheme)
        await pg.context.close()
    pg = await page(b)
    await pg.fill("#q", "latency")
    await pg.wait_for_timeout(1500)
    await calm(pg)
    save_png(await pg.screenshot(), "search-light.png")
    await pg.context.close()
    pg = await page(b, w=390, h=844, dsf=3, mobile=True)
    await calm(pg)
    save_png(await pg.screenshot(), "mobile-light.png", width=780)
    await pg.context.close()


async def gif(b):
    pg = await page(b, w=1280, h=780, dsf=1)
    await calm(pg)
    frames = []

    async def shot(ms):
        frames.append((Image.open(io.BytesIO(await pg.screenshot())).convert("RGB"), ms))

    await shot(1600)
    await pg.click("#q")
    for ch in "pricing":
        await pg.keyboard.type(ch)
        await pg.wait_for_timeout(120)
        await shot(110)
    await pg.wait_for_timeout(900)
    await shot(1300)
    await pg.hover(PRICING)
    await pg.wait_for_timeout(300)
    await shot(500)
    await pg.click(PRICING)
    for _ in range(3):
        await pg.wait_for_timeout(150)
        await shot(150)
    await pg.mouse.move(640, 770)
    await pg.wait_for_timeout(800)
    await shot(2200)
    await pg.keyboard.press("c")
    await pg.evaluate("document.activeElement && document.activeElement.blur()")
    for _ in range(3):
        await pg.wait_for_timeout(200)
        await shot(200)
    await pg.wait_for_timeout(1500)
    await calm(pg)
    await shot(3200)
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(500)
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(500)
    await pg.fill("#q", "")
    await pg.wait_for_timeout(900)
    await calm(pg)
    await shot(1200)
    await pg.context.close()

    w = 1120
    imgs = [im.resize((w, round(im.height * w / im.width)), Image.LANCZOS) for im, _ in frames]
    sheet = Image.new("RGB", (w, imgs[0].height * len(imgs)))
    for i, im in enumerate(imgs):
        sheet.paste(im, (0, i * im.height))
    pal = sheet.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
    q[0].save(OUT / "demo.gif", save_all=True, append_images=q[1:], duration=[ms for _, ms in frames], loop=0, optimize=True)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        if "--gif" not in sys.argv:
            await stills(b)
        await gif(b)
        await b.close()


asyncio.run(main())
