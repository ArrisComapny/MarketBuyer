import random
import asyncio

import core.app as app_core

from typing import Callable, Optional

from playwright.async_api import async_playwright, ProxySettings
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import PROFILE_DIR

from domain.enums import ScenarioMode

from core.scenarios.activate import ActivateScenario
from core.scenarios.login import LoginScenario
from core.scenarios.start import StartProcessScenario
from core.scenarios.get_qr import QRcodeScenario

from database.models import User
from database.repositories import PhoneCodeRepo

from utils.logger import AppLogger
log = AppLogger.get(__name__)


SCENARIOS = {
    ActivateScenario.mode: ActivateScenario,
    LoginScenario.mode: LoginScenario,
    StartProcessScenario.mode: StartProcessScenario,
    QRcodeScenario.mode: QRcodeScenario,
}

HEADLESS = {
    ActivateScenario.mode:False ,
    LoginScenario.mode: False,
    StartProcessScenario.mode: False,
    QRcodeScenario.mode: True,
}

class BrowserController:
    def __init__(self, user: User, profile_name: str, user_agent: str = "", proxy=None,
                 on_progress: Optional[Callable[[int, str], None]] = None):
        self.profile_dir = PROFILE_DIR / profile_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.page = None
        self.user = user
        self.proxy = proxy
        self.context = None
        self.account = None
        self.user_agent = user_agent
        self.on_progress = on_progress

    def _build_proxy_cfg(self) -> ProxySettings:
        if not self.proxy:
            raise Exception("No proxy configured")

        scheme = (self.proxy.proxy_scheme or "").lower().strip()

        if scheme.startswith("socks"):
            server = f"{scheme}://{self.proxy.host}:{self.proxy.port}"
        else:
            server = f"http://{self.proxy.host}:{self.proxy.port}"

        proxy_cfg = ProxySettings(server=server, username=self.proxy.login, password=self.proxy.password)

        return proxy_cfg

    async def _launch_context(self, p, headless: bool):
        proxy_cfg = self._build_proxy_cfg()

        self.context = await p.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel="chrome",
            headless=headless,
            proxy=proxy_cfg,
            user_agent=self.user_agent or None,
            locale="ru-RU",
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1280,1200",
            ],
        )

        self.context.set_default_timeout(0)
        self.context.set_default_navigation_timeout(0)

        if self.on_progress:
            self.on_progress(0, "BROWSER_STARTED")

    async def change_window_size(self, width: int, height: int):
        if not self.page:
            return

        await self.page.set_viewport_size({"width": width, "height": height})

    async def _prepare_page(self):
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        await self.page.goto("https://www.wildberries.ru")

    async def run(self, mode: ScenarioMode) -> None:
        async with async_playwright() as p:
            headless = HEADLESS.get(mode, False)
            await self._launch_context(p, headless)
            await self._prepare_page()

            scenario_cls = SCENARIOS.get(mode)
            if not scenario_cls:
                raise ValueError(f"Unknown mode: {mode}")

            scenario = scenario_cls(self)
            return await scenario.run()

    async def humanize(self, min_ms=300, max_ms=600):
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))
        await self.page.mouse.move(random.randint(200, 600), random.randint(200, 500))
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))
        await self.page.mouse.wheel(0, random.randint(300, 800))
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))

    async def human_click(self, element,offset_x=5, offset_y=5):
        await element.scroll_into_view_if_needed()
        await asyncio.sleep(random.uniform(0.15, 0.4))

        box = await element.bounding_box()
        if not box:
            return

        x = box["x"] + random.uniform(offset_x, box["width"] - offset_x)
        y = box["y"] + random.uniform(offset_y, box["height"] - offset_y)

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
        await self.page.wait_for_timeout(8000)

    async def close_modal(self):
        phone10 = (self.account or {}).get("phone10", "unknown")

        try:
            btn = await self.page.wait_for_selector(
                "button.close",
                timeout=5000,
                state="visible"
            )
            await self.human_wait()
            await self.human_click(btn)
        except PlaywrightTimeoutError:
            log.debug(f"[BrowserController][{phone10}] Модальное окно не найдено (skip)")
            pass

    async def accept_cookie(self):
        phone10 = (self.account or {}).get("phone10", "unknown")

        try:
            cookie_btn = await self.page.wait_for_selector(
                "button.cookies__btn",
                timeout=5000,
                state="visible"
            )
            await self.human_wait()
            await self.human_click(cookie_btn)
        except PlaywrightTimeoutError:
            log.debug(f"[BrowserController][{phone10}] cookie кнопка не найдена (skip)")
            pass

    async def click_login_btn(self):
        phone10 = (self.account or {}).get("phone10", "unknown")

        log.info(f"[BrowserController][{phone10}] start login flow")

        try:
            login_btn = await self.page.wait_for_selector(
                '[data-testid="login"]',
                timeout=4000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[BrowserController][{phone10}] Кнопка логина / профиля не найдена")
            raise Exception("Кнопка логина / профиля не найдена")

        await self.human_wait()
        await self.human_click(login_btn)
        await self.humanize()

        try:
            phone_inp = await self.page.wait_for_selector(
                "[data-testid='phoneInput']",
                timeout=10000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[BrowserController][{phone10}] Окно 'Ввод' не найдено")
            raise Exception("Окно 'Ввод' не найдено")

        await self.human_wait()
        await self.human_click(phone_inp, offset_x=60)
        await self.human_type(phone_inp, phone10)
        await self.humanize()

        try:
            request_code_btn = await self.page.wait_for_selector(
                "button[data-testid='requestCodeBtn']",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[BrowserController][{phone10}] Кнопка 'получить код' не найдена")
            raise Exception("Кнопка 'получить код' не найдена")

        await self.human_wait()
        await self.human_click(request_code_btn)
        await self.humanize()

        await self.page.wait_for_timeout(300)

        error_text = None

        for _ in range(15):
            loc = self.page.locator("span#phoneInputErrorMessage.error--MakvU")

            if await loc.count() > 0:
                text = (await loc.first.inner_text()).strip()
                if text:
                    error_text = text
                    break

            await self.page.wait_for_timeout(300)

        if error_text:
            log.error(f"[BrowserController][{phone10}] Ошибка запроса кода: {error_text}")
            raise Exception(f"[{phone10}] Ошибка запроса кода: {error_text}")

        async with app_core.db.get_session() as session:
            code = await PhoneCodeRepo.wait_latest_code(session, phone10)

        await self.page.wait_for_selector(
            "input[autocomplete='one-time-code']",
            timeout=15000,
            state="visible"
        )

        inputs = self.page.locator("input[autocomplete='one-time-code']")

        for i, ch in enumerate(code):
            el = inputs.nth(i)
            await self.human_click(el)
            await el.fill(ch)

        try:
            await self.page.wait_for_selector(
                'a[data-testid="profile"]',
                state="visible",
                timeout=10000
            )
            log.info(f"[BrowserController][{phone10}] login success")
            return True
        except PlaywrightTimeoutError:
            log.error(f"[BrowserController][{phone10}] Кнопка 'Профиль' не найдена ни по одному селектору")
            raise Exception("Кнопка 'Профиль' не найдена ни по одному селектору")

    async def close(self):
        if getattr(self, "context", None):
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
