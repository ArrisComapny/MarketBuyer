import asyncio
import random
import subprocess
from pathlib import Path
import os
import sys
import datetime

import core.app as app_core


from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from typing import Callable, Optional


from sqlalchemy import select, desc, update, insert


from database.models import PhoneCode, Account, UsersAccounts, User



def ensure_browsers():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
ensure_browsers()


class BrowserController:
    def __init__(self, user: User, profile_name: str, user_agent: str = "", proxy=None,
                 on_progress: Optional[Callable[[int, str], None]] = None):

        self.profile_dir = Path(os.getcwd()) / "profiles" / profile_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.on_progress = on_progress

        self.context = None
        self.user_agent = user_agent
        self.proxy = proxy
        self.account = None
        self.page = None
        self.user = user

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
                headless = False if mode == "scenario_start_process" else True,
                proxy=proxy_cfg,
                user_agent=self.user_agent or None,
                locale="ru-RU",
                no_viewport=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1280,800"

                ],
            )
            if self.on_progress:
                self.on_progress(0, "BROWSER_STARTED")

            self.context.set_default_timeout(0)
            self.context.set_default_navigation_timeout(0)
            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()

            await self.page.goto("https://www.wildberries.ru")

            print(mode)

            if mode == "logout-login":
                await self.scenario_logout(self.account.get("phone10"))
                print("[INFO] logout - login завершён")


            elif mode == "scenario_start_process":
                print("[INFO] start_process — браузер открыт")
                await self.scenario_start_process()

            elif mode == "activate":
                await self.scenario_activate()
                print("[INFO] scenario activate завершён")



    @staticmethod
    async def _update_account(phone10: str, name: str, gender: str | None) -> None:

        async with app_core.db.get_session() as session:
            await session.execute(
                update(Account)
                .where(Account.phone == phone10)
                .values(
                    name=name,
                    male=gender.capitalize(),
                )
            )
            await session.commit()

    @staticmethod
    async def _update_account_status(phone10: str, status: str) -> None:
        async with app_core.db.get_session() as session:
            await session.execute(
                update(Account)
                .where(Account.phone == phone10)
                .values(status=status)
            )
            await session.commit()

    async def users_accounts(self, phone10: str) -> None:
        async with app_core.db.get_session() as session:

            # 1️⃣ Проверяем — есть ли уже запись
            res = await session.execute(
                select(UsersAccounts).where(UsersAccounts.phone == phone10)
            )
            row = res.scalars().first()

            if row is None:
                # 2️⃣ Если НЕТ — INSERT
                stmt = insert(UsersAccounts).values(
                    phone=phone10,
                    user=self.user.login
                )
                await session.execute(stmt)
                print("INSERT users_accounts", phone10, self.user.login)
            else:
                # 3️⃣ Если ЕСТЬ — UPDATE
                stmt = (
                    update(UsersAccounts)
                    .where(UsersAccounts.phone == phone10)
                    .values(user=self.user.login)
                )
                await session.execute(stmt)
                print("UPDATE users_accounts", phone10, self.user.login)

            await session.commit()

    @staticmethod
    async def _get_code(phone10):

        msk = datetime.timezone(datetime.timedelta(hours=3))
        time_request_aware = datetime.datetime.now(msk) - datetime.timedelta(minutes=1)
        time_request = time_request_aware.replace(tzinfo=None)

        async with app_core.db.get_session() as session:
            for _ in range(20):
                stmt = (select(PhoneCode.code)
                    .where(PhoneCode.phone == phone10, PhoneCode.time_response >= time_request)
                    .order_by(desc(PhoneCode.time_response))
                    .limit(1))
                result = await session.execute(stmt)
                code = result.scalars().first()
                if code:
                    break
                await asyncio.sleep(3)
            else:
                raise Exception("Код не пришел")
            return code

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
        try:
            btn = await self.page.wait_for_selector(
                "button.close",
                timeout=5000,
                state="visible"
            )
            await self.human_wait()
            await self.human_click(btn)
        except PlaywrightTimeoutError:
            print(f"реклама закрыта")
            pass


    async def accept_cookie(self):
        try:
            cookie_btn = await self.page.wait_for_selector(
                "button.cookies__btn",
                timeout=5000,
                state="visible"
            )
            await self.human_wait()
            await self.human_click(cookie_btn)
        except PlaywrightTimeoutError:
            print("cookie уже были приняты или кнопка не появилась")
            pass

    async def click_login_btn(self):
        phone = self.account.get("phone10")
        # 1) клик "Войти"
        try:
            login_btn = await self.page.wait_for_selector('[data-testid="login"]', timeout=5000)
        except PlaywrightTimeoutError:
            raise Exception("Кнопка 'Войти' не найдена")

        await self.human_wait()
        await self.human_click(login_btn)
        await self.humanize()

        # 2) ввод телефона
        try:
            phone_inp = await self.page.wait_for_selector(
                "[data-testid='phoneInput']",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            raise Exception("Окно 'Ввод' не найдено")

        await self.human_wait()
        await self.human_click(phone_inp, offset_x=60)
        await self.human_type(phone_inp, phone)
        await self.humanize()

        # 3) Нажимаем на кнопку получить код
        try:
            request_code_btn = await self.page.wait_for_selector(
                "button[data-testid='requestCodeBtn']",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            raise Exception("Кнопка 'получить код' не найдена")
        await self.human_wait()
        await self.human_click(request_code_btn)
        await self.humanize()
        # после клика "Получить код"
        await self.page.wait_for_timeout(300)

        error_text = None

        # ждём до 15 секунд, проверяя каждые 300мс
        for _ in range(15):  # 20 * 300ms = 4.5 сек
            loc = self.page.locator("span#phoneInputErrorMessage.error--MakvU")

            if await loc.count() > 0:
                text = (await loc.first.inner_text()).strip()
                if text:
                    error_text = text
                    break

            await self.page.wait_for_timeout(300)

        if error_text:
            print(f"[{phone}] Ошибка запроса кода: {error_text}")
            raise Exception(f"[{phone}] Ошибка запроса кода: {error_text}")

        code = await self._get_code(phone)
        # ждём, что появится хотя бы первое поле
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
            print( f"{phone} вход в аккаунт выполнен")
        except PlaywrightTimeoutError:
            raise Exception("Кнопка 'Профиль' не появилась — логин не выполнен")

        return True



    async def get_profile_gender(self) -> str | None:

        male = await self.page.wait_for_selector(
            "input[data-testid='genderInputMale']",
            timeout=5000
        )
        if await male.is_checked():
            return "Male"

        female = await self.page.wait_for_selector(
            "input[data-testid='genderInputFemale']",
            timeout=5000
        )
        if await female.is_checked():
            return "Female"

        return None

    async def changing_name_and_gender(self):
        # 1 наводим на иконку кабинета и профиля и нажимаем
        try:
            profile_btn = await self.page.wait_for_selector(
                "span.navbar-pc__icon--profile",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            print(f"Кнопка 'Кабинета' не найдена")
            raise Exception("Кнопка 'Кабинета' не найдена")

        await profile_btn.hover()
        await self.human_wait()
        await self.human_click(profile_btn)

        try:
            user_profile_btn = await self.page.wait_for_selector(
                "h3.user-name--StaCq",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            print(f"Кнопка 'Профиля' не найдена")
            raise Exception("Кнопка 'Профиля' не найдена")
        await self.human_wait()
        await self.human_click(user_profile_btn)

        # 2. Наводим на имя в личном кабинете для смены имени и гендера
        try:
            first_name_input = await self.page.wait_for_selector(
                "input[data-testid='firstNameInput']",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            raise Exception("Поле ввода имени не найдено")

        # --- читаем данные из профиля ---
        profile_name = (await first_name_input.input_value()).strip()
        profile_gender = await self.get_profile_gender()  # "male" / "female" / None

        phone10 = self.account.get("phone10")
        if not phone10:
            print(f"В self.account нет phone10")
            raise Exception("В self.account нет phone10")

        # СЦЕНАРИЙ 1: имя и пол уже есть → сохраняем в БД
        if profile_name and profile_gender in ("Male", "Female"):
            await self._update_account(phone10, profile_name, profile_gender)
        else:
            # СЦЕНАРИЙ 2: нет имени ИЛИ нет пола → вводим И имя, И пол (мои)

            my_name = (self.account.get("name") or "").strip()
            my_gender = self.account.get("gender")  # "male"/"female"/None

            # имя
            if my_name:
                await self.human_wait()
                await self.human_click(first_name_input)
                await first_name_input.fill("")
                await self.human_type(first_name_input, my_name)

            # пол
            print(f"мой гендер {my_gender}")
            if my_gender not in ("Male", "Female"):
                my_gender = None  # просто не будем ставить пол

            label_selector = (
                "label[data-testid='genderOptionMale']"
                if my_gender == "Male"
                else "label[data-testid='genderOptionFemale']"
            )

            label_el = await self.page.wait_for_selector(
                label_selector,
                timeout=5000,
                state="visible"
            )

            await self.human_wait()
            await self.humanize()
            await self.human_click(label_el)

        save_btn = await self.page.wait_for_selector(
            "span:has-text('Сохранить')",
            timeout=5000,
            state="visible"
        )

        await self.humanize()
        await self.human_wait()
        await self.human_click(save_btn)
        print(f"{phone10} вход в аккаунт выполнен")
        await self._update_account_status(phone10, "login")
        await self.users_accounts(phone10)

    async def scenario_activate(self):
        print("[SCENARIO] activate")
        self.on_progress(5, "Открываю сайт…")
        await self.wait_full_load()
        await self.humanize()
        self.on_progress(15, "Закрываю модалки…")
        await self.close_modal()
        await self.humanize()
        self.on_progress(25, "Принимаю cookies…")
        await self.accept_cookie()
        await self.humanize()
        self.on_progress(40, "Запрашиваю код…")
        await self.click_login_btn()
        await self.humanize()
        self.on_progress(75, "Заполняю профиль…")
        await self.changing_name_and_gender()
        await self.human_wait()
        await self.humanize()
        self.on_progress(95, "Завершаю…")
        await self.close()
        self.on_progress(100, "Готово")

    async def scenario_start_process(self):
        print("[SCENARIO] start_process- работа с аккаунтом")
        await self.context.wait_for_event("close", timeout=0)


    async def scenario_logout(self,phone10):
        print("[SCENARIO] login - Авторизация")
        self.on_progress(5, "Открываю сайт…")
        await self.wait_full_load()
        await self.humanize()
        self.on_progress(15, "Закрываю модалки…")
        await self.close_modal()
        await self.humanize()
        self.on_progress(25, "Принимаю cookies…")
        await self.accept_cookie()
        await self.humanize()
        self.on_progress(40, "Запрашиваю код…")
        await self.click_login_btn()
        self.on_progress(80, "Меняю статус на Login")
        await self._update_account_status(phone10, "login")
        await self.close()
        self.on_progress(100, "Готово")


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
