from __future__ import annotations

import core.app as app_core

from database.repositories import AccountRepo
from .base import BaseScenario
from .modes import ScenarioMode


class LogoutLoginScenario(BaseScenario):
    mode = ScenarioMode.LOGOUT_LOGIN

    async def run(self) -> None:
        c = self.c
        phone10 = c.account.get("phone10")

        print("[SCENARIO] logout-login")
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

        c.on_progress and c.on_progress(80, "Меняю статус на Login")
        async with app_core.db.get_session() as session:
            await AccountRepo.set_status(session, phone10, "login")

        c.on_progress and c.on_progress(100, "Готово")
        await c.close()
