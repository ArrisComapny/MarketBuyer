from __future__ import annotations

import core.app as app_core

from .base import BaseScenario
from domain.enums import ScenarioMode
from database.repositories import AccountRepo
from utils.logger import AppLogger

log = AppLogger.get(__name__)


class LoginScenario(BaseScenario):
    """Сценарий входа в аккаунт WB."""
    mode = ScenarioMode.LOGIN

    async def run(self) -> None:
        c = self.c
        phone10 = (c.account or {}).get("phone10", "unknown")

        log.info(f"[LOGIN][{phone10}] START")

        try:
            c.on_progress and c.on_progress(5, "Открываю сайт…")
            log.info(f"[LOGIN][{phone10}] Открываю сайт")
            await c.wait_full_load()
            await c.humanize()

            c.on_progress and c.on_progress(15, "Закрываю модальные окна…")
            log.info(f"[LOGIN][{phone10}] Закрываю модалки")
            await c.close_modal()
            await c.humanize()

            c.on_progress and c.on_progress(25, "Принимаю cookies…")
            log.info(f"[LOGIN][{phone10}] Принимаю cookies")
            await c.accept_cookie()
            await c.humanize()

            c.on_progress and c.on_progress(40, "Запрашиваю код…")
            log.info(f"[LOGIN][{phone10}] Запрашиваю код")
            await c.click_login_btn()

            c.on_progress and c.on_progress(80, "Меняю статус на Login")
            log.info(f"[LOGIN][{phone10}] Обновляю статус в БД → login")

            async with app_core.db.get_session() as session:
                await AccountRepo.set_status(session, phone10, "login")

            c.on_progress and c.on_progress(100, "Готово")
            log.info(f"[LOGIN][{phone10}] DONE")

        except Exception as e:
            log.exception(f"[LOGIN][{phone10}] ERROR: {e}")
            raise

        finally:
            try:
                await c.close()
                log.info(f"[LOGIN][{phone10}] Browser closed")
            except Exception:
                pass