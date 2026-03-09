from __future__ import annotations

import logging
import core.app as app_core

from .base import BaseScenario
from domain.enums import ScenarioMode
from database.repositories import AccountRepo, UsersAccountsRepo
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

log = logging.getLogger(__name__)


class ActivateScenario(BaseScenario):
    mode = ScenarioMode.ACTIVATE

    async def run(self) -> None:
        c = self.c
        phone10 = (getattr(c, "account", None) or {}).get("phone10", "unknown")

        log.info(f"[{phone10}] START ActivateScenario")

        try:
            c.on_progress and c.on_progress(5, "Открываю сайт…")
            log.info(f"[{phone10}] Открываю сайт…")
            await c.wait_full_load()
            await c.humanize()

            c.on_progress and c.on_progress(15, "Закрываю модалки…")
            log.info(f"[{phone10}] Закрываю модалки…")
            await c.close_modal()
            await c.humanize()

            c.on_progress and c.on_progress(25, "Принимаю cookies…")
            log.info(f"[{phone10}] Принимаю cookies…")
            await c.accept_cookie()
            await c.humanize()

            profile_btn = await c.page.query_selector('[data-testid="profile"]')

            if profile_btn:
                log.info(f"[{phone10}] Профиль уже есть → сразу заполняю")
                c.on_progress and c.on_progress(75, "Заполняю профиль…")
                await self.changing_name_and_gender()
            else:
                log.info(f"[{phone10}] Профиля нет → запускаю логин")
                c.on_progress and c.on_progress(40, "Войти и запросить пароль")
                await c.click_login_btn()
                await c.humanize()

                c.on_progress and c.on_progress(75, "Заполняю профиль…")
                await self.changing_name_and_gender()

        except Exception as e:
            log.exception(f"[{phone10}] ERROR ActivateScenario: {e}")
            raise

        finally:
            try:
                await c.close()
            except Exception:
                pass

    async def changing_name_and_gender(self) -> None:
        c = self.c
        acc = getattr(c, "account", None) or {}
        phone10 = acc.get("phone10", "unknown")

        log.info(f"[{phone10}] Открываю профиль…")

        try:
            profile_btn = await c.page.wait_for_selector(
                '[data-testid="profile"]',
                timeout=8000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[{phone10}] Кнопка 'Кабинета' не найдена")
            raise Exception("Кнопка 'Кабинета' не найдена")

        await profile_btn.hover()
        await c.human_click(profile_btn)



        try:
            user_profile_btn = await c.page.wait_for_selector(
                '[data-testid="notification-bell"]',
                timeout=8000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[{phone10}] Кнопка 'Профиля' не найдена")
            raise Exception("Кнопка 'Профиля' не найдена")

        await c.human_wait()
        await c.human_click(user_profile_btn)
        await c.human_wait()

        try:
            close_btn = await c.page.wait_for_selector(
                '[data-testid="notifications-close"]',
                timeout=10000,
                state="visible"
            )
            await c.human_click(close_btn)

        except PlaywrightTimeoutError:
            log.info(f"[{phone10}] Кнопка закрытия уведомления не появилась")
            pass

        await c.human_wait()
        await c.human_click(user_profile_btn)
        await c.human_wait()

        try:
            profile_btn = await c.page.wait_for_selector(
                '[data-testid="displayName"]',
                timeout=6000,
                state="visible"
            )
            await c.human_click(profile_btn)
            await c.human_wait()
            await c.humanize()

        except PlaywrightTimeoutError:
            log.info(f"[{phone10}] Кнопка профиля для ввода имени не появилась")
            raise Exception("Кнопка профиля для ввода имени не появилась")


        try:
            first_name_input = await c.page.wait_for_selector(
                "input[data-testid='firstNameInput']",
                timeout=10000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[{phone10}] Поле ввода имени не найдено")
            raise Exception("Поле ввода имени не найдено")

        profile_name = (await first_name_input.input_value()).strip()
        profile_gender = await self.get_profile_gender()

        log.info(f"[{phone10}] Профиль: name='{profile_name}', gender='{profile_gender}'")

        if phone10 == "unknown":
            raise Exception("В self.account нет phone10")

        if profile_name and profile_gender in ("Male", "Female"):
            log.info(f"[{phone10}] Уже заполнено в профиле → сохраняю в БД")
            async with app_core.db.get_session() as session:
                await AccountRepo.update_profile(session, phone10, profile_name, profile_gender)
        else:
            my_name = (acc.get("name") or "").strip()
            my_gender = acc.get("gender")

            log.info(f"[{phone10}] Заполняю из аккаунта: name='{my_name}', gender='{my_gender}'")

            if my_name:
                await c.human_wait()
                await c.human_click(first_name_input)
                await first_name_input.fill("")
                await c.human_type(first_name_input, my_name)

            if my_gender not in ("Male", "Female"):
                my_gender = None

            if my_gender:
                label_selector = (
                    "label[data-testid='genderOptionMale']"
                    if my_gender == "Male"
                    else "label[data-testid='genderOptionFemale']"
                )

                label_el = await c.page.wait_for_selector(
                    label_selector,
                    timeout=5000,
                    state="visible"
                )

                await c.human_wait()
                await c.humanize()
                await c.human_click(label_el)

        save_btn = await c.page.wait_for_selector(
            "span:has-text('Сохранить')",
            timeout=5000,
            state="visible"
        )

        log.info(f"[{phone10}] Нажимаю 'Сохранить'")
        await c.humanize()
        await c.human_wait()
        await c.human_click(save_btn)

        user_login = getattr(getattr(c, "user", None), "login", "")
        async with app_core.db.get_session() as session:
            await AccountRepo.set_status(session, phone10, "login")
            await UsersAccountsRepo.set_users_accounts(session, phone10, user_login)

        log.info(f"[{phone10}] Профиль сохранён + статус login")

    async def get_profile_gender(self) -> str | None:
        c = self.c
        phone10 = (getattr(c, "account", None) or {}).get("phone10", "unknown")

        try:
            male = await c.page.wait_for_selector(
                "input[data-testid='genderInputMale']",
                timeout=5000
            )
            if await male.is_checked():
                log.info(f"[{phone10}] gender=Male")
                return "Male"
        except PlaywrightTimeoutError:
            pass

        try:
            female = await c.page.wait_for_selector(
                "input[data-testid='genderInputFemale']",
                timeout=5000
            )
            if await female.is_checked():
                log.info(f"[{phone10}] gender=Female")
                return "Female"
        except PlaywrightTimeoutError:
            pass

        log.info(f"[{phone10}] gender=None")
        return None
