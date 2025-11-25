import asyncio
import subprocess
from pathlib import Path
import os, sys

from playwright.async_api import async_playwright
from core.humanize import humanize
from utils.random_tools import random_ua, random_viewport

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except:
    HAS_STEALTH = False


def ensure_browsers():
    subprocess.run([sys.executable, "-m", "playwright", "install", "--help"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


ensure_browsers()


class BrowserController:
    def __init__(self):
        self.profile_dir = Path(os.getcwd()) / "profiles" / "default"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    async def run(self):
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel="chrome",
                headless=False,
                user_agent=random_ua(),
                viewport=random_viewport(),
                locale="ru-RU",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )

            page = await context.new_page()
            if HAS_STEALTH:
                await stealth_async(page)

            await page.goto("https://www.wildberries.ru")
            await humanize(page)

            await asyncio.sleep(30)
            await context.close()
