import asyncio
import random
import subprocess
from pathlib import Path
import os
import sys

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False


def ensure_browsers():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


ensure_browsers()


class BrowserController:
    def __init__(self, profile_name: str, user_agent: str = "", proxy=None):
        self.profile_dir = Path(os.getcwd()) / "profiles" / profile_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.context = None
        self.user_agent = user_agent
        self.proxy = proxy
        self.account = None


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

            pages = self.context.pages
            page = pages[0] if pages else await self.context.new_page()

            self.page = page

            if HAS_STEALTH:
                await stealth_async(page)

            try:
                # Проверка IP через прокси
                await page.goto("https://api.ipify.org", wait_until="domcontentloaded", timeout=90000)
                ip = await page.text_content("body")
                print("IP через прокси:", (ip or "").strip())

                # Стартовая страница
                await page.goto("https://www.wildberries.ru", wait_until="domcontentloaded", timeout=90000)

                if mode == "activate":
                    await self._scenario_activate(page)
                elif mode == "start_process":
                    await self._scenario_start_process(page)
                elif mode == "login":
                    await self._scenario_login(page)
                else:
                    print(f"[WARN] Неизвестный mode={mode}, сценарий не запущен")

                await page.wait_for_event("close", timeout=0)

            except Exception as e:
                print("ОШИБКА:", repr(e))
                await page.set_content(
                    f"<h2>Ошибка</h2><pre>{repr(e)}</pre>"
                    f"<p>Окно не закрываю — закрой вручную.</p>"
                )
                await page.wait_for_event("close", timeout=0)
            finally:
                await self.close()

    async def humanize(self, min_ms=300, max_ms=600):
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))
        await self.page.mouse.move(random.randint(200, 600), random.randint(200, 500))
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))
        await self.page.mouse.wheel(0, random.randint(300, 800))
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))

    async def human_click(self, element):
        await element.scroll_into_view_if_needed()
        await asyncio.sleep(random.uniform(0.15, 0.4))

        box = await element.bounding_box()
        if not box:
            return

        x = box["x"] + random.uniform(5, box["width"] - 5)
        y = box["y"] + random.uniform(5, box["height"] - 5)

        await self.page.mouse.move(x, y, steps=random.randint(8, 15))

        await asyncio.sleep(random.uniform(0.08, 0.25))

        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.03, 0.12))
        await self.page.mouse.up()
        await asyncio.sleep(random.uniform(0.15, 0.35))

    async def human_wait(self, min_ms=2000, max_ms=5000):
        await self.page.wait_for_timeout(random.uniform(min_ms, max_ms))

    async def human_type(self, element, text, min_delay_ms=50, max_delay_ms=150):
        for char in text:
            await element.type(char)
            await self.page.wait_for_timeout(random.randint(min_delay_ms, max_delay_ms))

    async def wait_full_load(self, timeout: int = 30000):
        await self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

        await self.page.wait_for_timeout(2000)

        try:
            await self.page.wait_for_selector(
                "header",
                timeout=timeout,
                state="visible"
            )
        except PlaywrightTimeoutError:
            pass

    async def close_modal(self):
        try:
            btn = await self.page.wait_for_selector(
                "button.close",
                timeout=5000,
                state="visible"
            )
            await self.human_wait()
            await btn.click()
        except PlaywrightTimeoutError:
            pass

        return False

    async def accept_cookie(self, page):
        # 3) cookies — если есть, кликаем
        btn = await page.query_selector("button.cookies__btn")
        if not btn:
            try:
                await page.wait_for_selector("button.cookies__btn", timeout=3000)
                btn = await page.query_selector("button.cookies__btn")
            except PlaywrightTimeoutError:
                btn = None

        if btn:
            await btn.hover()
            await asyncio.sleep(0.3)
            await btn.click()
        else:
            print("Cookies уже приняты или баннера нет")

    async def login_btn(self, page):
        account = self.account or {}
        phone = (account.get("phone10") or "").strip()
        if not phone:
            print("self.account.phone10 не задан (не передали account в BrowserController)")
            return False

        # 1) клик "Войти"
        try:
            btn = await page.wait_for_selector('[data-testid="login"]', timeout=3000)
        except PlaywrightTimeoutError:
            print("Кнопка 'Войти' не найдена")
            return False

        await btn.hover()
        await asyncio.sleep(0.3)
        await btn.click()

        # 2) ввод телефона
        try:
            inp = await page.wait_for_selector('input[data-testid="phoneInput"]', timeout=5000)
        except PlaywrightTimeoutError:
            print("Поле телефона не найдено")
            return False

        await inp.hover()
        await asyncio.sleep(0.2)
        await inp.click()
        await asyncio.sleep(0.1)

        await inp.fill("")  # важно для маски

        await self.human_type(inp, phone)
        return True

    async def _scenario_activate(self, page):
        print("[SCENARIO] activate")

        # 1) ждём загрузку страницы
        await self.wait_full_load(timeout=30000)
        await self.humanize()
        await self.close_modal()
        await self.humanize()
        await self.accept_cookie(page)
        await self.humanize()
        await self.login_btn(page)



    async def _scenario_start_process(self, page):
        print("[SCENARIO] start_process")
        return

    async def _scenario_login(self, page):
        print("[SCENARIO] login")
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
