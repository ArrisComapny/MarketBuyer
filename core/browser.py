import asyncio
import subprocess
from pathlib import Path
import os
import sys

from playwright.async_api import async_playwright
from core.humanize import humanize

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False


def ensure_browsers():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--help"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


ensure_browsers()


class BrowserController:
    def __init__(self, profile_name: str, user_agent: str = "", proxy=None):
        self.profile_dir = Path(os.getcwd()) / "profiles" / profile_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.context = None
        self.user_agent = user_agent  # строка из БД
        self.proxy = proxy

    async def run(self, mode: str = "activate"):
        async with async_playwright() as p:
            proxy_cfg = None
            if self.proxy:
                scheme = (self.proxy.proxy_scheme or "").lower().strip()

                # Playwright: для http/https прокси обычно задают http://
                if scheme in ("http", "https", ""):
                    server = f"http://{self.proxy.host}:{self.proxy.port}"
                elif scheme.startswith("socks"):
                    server = f"{scheme}://{self.proxy.host}:{self.proxy.port}"
                else:
                    server = f"http://{self.proxy.host}:{self.proxy.port}"

                proxy_cfg = {"server": server}

                # логин/пароль добавляем только если непустые
                if (self.proxy.login or "").strip() and (self.proxy.password or "").strip():
                    proxy_cfg["username"] = self.proxy.login
                    proxy_cfg["password"] = self.proxy.password

            self.context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel="chrome",
                headless=False,
                proxy=proxy_cfg,
                user_agent=self.user_agent or None,
                locale="ru-RU",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )

            page = await self.context.new_page()

            # логи, чтобы понять, почему не грузит
            page.on("requestfailed", lambda r: print("[requestfailed]", r.url, r.failure))
            page.on("pageerror", lambda e: print("[pageerror]", e))

            if HAS_STEALTH:
                await stealth_async(page)

            try:
                # Проверка IP через прокси
                await page.goto("https://api.ipify.org", wait_until="domcontentloaded", timeout=90000)
                ip = await page.text_content("body")
                print("IP через прокси:", (ip or "").strip())

                # ОДНА И ТА ЖЕ стартовая страница для всех кнопок
                await page.goto("https://www.wildberries.ru", wait_until="domcontentloaded", timeout=90000)
                await humanize(page)

                # ==========================
                # РАЗНЫЕ СЦЕНАРИИ ПО MODE
                # ==========================
                if mode == "activate":
                    await self._scenario_activate(page)
                elif mode == "start_process":
                    await self._scenario_start_process(page)
                elif mode == "login":
                    await self._scenario_login(page)
                else:
                    print(f"[WARN] Неизвестный mode={mode}, сценарий не запущен")

                # чтобы окно не закрывалось само
                await page.wait_for_event("close", timeout=0)

            except Exception as e:
                print("ОШИБКА goto:", repr(e))
                await page.set_content(
                    f"<h2>Ошибка загрузки</h2><pre>{repr(e)}</pre>"
                    f"<p>Окно не закрываю — закрой вручную.</p>"
                )
                await page.wait_for_event("close", timeout=0)
            finally:
                await self.close()

    # ==========================
    # СЦЕНАРИИ (пока заглушки)
    # ==========================
    async def _scenario_activate(self, page):
        print("[SCENARIO] activate")
        # TODO: тут будет сценарий активации
        # например: await page.click("...")
        return

    async def _scenario_start_process(self, page):
        print("[SCENARIO] start_process")
        # TODO: тут будет сценарий "Запуск"
        return

    async def _scenario_login(self, page):
        print("[SCENARIO] login")
        # TODO: тут будет сценарий "Вход"
        return

    async def close(self):
        if getattr(self, "context", None):
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None






# if __name__ == "__main__":
#     controller = BrowserController()
#     asyncio.run(controller.run())
