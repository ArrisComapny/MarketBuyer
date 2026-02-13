from __future__ import annotations

import core.app as app_core

from .base import BaseScenario
from domain.enums import ScenarioMode
from database.repositories import AccountRepo, UsersAccountsRepo
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


class ActivateScenario(BaseScenario):
    mode = ScenarioMode.ACTIVATE

    async def run(self) -> None:

        c = self.c
        print("[SCENARIO] activate")

        c.on_progress and c.on_progress(5, "Открываю сайт…")
        await c.wait_full_load()
        await c.humanize()

        c.on_progress and c.on_progress(15, "Закрываю модалки…")
        await c.close_modal()
        await c.humanize()

        c.on_progress and c.on_progress(25, "Принимаю cookies…")
        await c.accept_cookie()
        await c.humanize()

        c.on_progress and c.on_progress(40, "Запрашиваю код…")
        await c.click_login_btn()
        await c.humanize()

        c.on_progress and c.on_progress(75, "Заполняю профиль…")
        await self.changing_name_and_gender()
        await c.human_wait()

        c.on_progress and c.on_progress(100, "Готово")
        await c.close()

    async def changing_name_and_gender(self):
        c = self.c

        try:
            profile_btn = await c.page.wait_for_selector(
                "span.navbar-pc__icon--profile",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            print(f"Кнопка 'Кабинета' не найдена")
            raise Exception("Кнопка 'Кабинета' не найдена")

        await profile_btn.hover()
        await c.human_wait()
        await c.human_click(profile_btn)

        try:
            user_profile_btn = await c.page.wait_for_selector(
                '[data-testid="displayName"]',
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            print("Кнопка 'Профиля' не найдена")
            raise Exception("Кнопка 'Профиля' не найдена")
        await c.human_wait()
        await c.human_click(user_profile_btn)

        # 2. Наводим на имя в личном кабинете для смены имени и гендера
        try:
            first_name_input = await c.page.wait_for_selector(
                "input[data-testid='firstNameInput']",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            raise Exception("Поле ввода имени не найдено")

        # --- читаем данные из профиля ---
        profile_name = (await first_name_input.input_value()).strip()
        profile_gender = await self.get_profile_gender()

        phone10 = c.account.get("phone10")
        if not phone10:
            print(f"В self.account нет phone10")
            raise Exception("В self.account нет phone10")

        if profile_name and profile_gender in ("Male", "Female"):
            async with app_core.db.get_session() as session:
                await AccountRepo.update_profile(session, phone10, profile_name, profile_gender)
        else:
            my_name = (c.account.get("name") or "").strip()
            my_gender = c.account.get("gender")  # "male"/"female"/None

            # имя
            if my_name:
                await c.human_wait()
                await c.human_click(first_name_input)
                await first_name_input.fill("")
                await c.human_type(first_name_input, my_name)

            # пол
            print(f"мой гендер {my_gender}")
            if my_gender not in ("Male", "Female"):
                my_gender = None  # просто не будем ставить пол

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

        await c.humanize()
        await c.human_wait()
        await c.human_click(save_btn)

        async with app_core.db.get_session() as session:
            await AccountRepo.set_status(session, phone10, "login")
            await UsersAccountsRepo.set_users_accounts(session, phone10, c.user.login)

    async def get_profile_gender(self) -> str | None:
        male = await self.c.page.wait_for_selector(
            "input[data-testid='genderInputMale']",
            timeout=5000
        )
        if await male.is_checked():
            return "Male"

        female = await self.c.page.wait_for_selector(
            "input[data-testid='genderInputFemale']",
            timeout=5000
        )
        if await female.is_checked():
            return "Female"

        return None
