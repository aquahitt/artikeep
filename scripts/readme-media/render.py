"""Render social.html (next to this file) to docs/media/social-preview.png. Usage: python3 render.py"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "docs" / "media" / "social-preview.png"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 640})
        await pg.goto((HERE / "social.html").as_uri(), wait_until="networkidle")
        await pg.wait_for_timeout(600)
        await pg.screenshot(path=str(OUT))
        await b.close()


asyncio.run(main())
