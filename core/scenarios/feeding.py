from __future__ import annotations
from .base import BaseScenario
from domain.enums import ScenarioMode
import random

class FeedingScenario(BaseScenario):
    mode = ScenarioMode.FEEDING

    async def run(self):
        c = self.c
        acc = c.account

        day = acc.get("feeding_day", 1)

        c.on_progress and c.on_progress(5, f"Feeding Day {day}")

        if day == 1:
            await self.day_1()
        elif day == 2:
            await self.day_2()
        elif day == 3:
            await self.day_3()
        elif day == 4:
            await self.day_4()
        elif day == 5:
            await self.day_5()
        elif day == 6:
            await self.day_6()
        elif day == 7:
            await self.day_7()
        else:
            return  # цикл завершён

        await self._increment_day()

    # ============================
    # ЗАГОТОВКИ ДНЕЙ
    # ============================

    async def day_1(self):
        c = self.c
        await c.human_wait()
        await c.humanize()

    async def day_2(self):
        c = self.c
        await c.human_wait()

    async def day_3(self):
        pass

    async def day_4(self):
        pass

    async def day_5(self):
        pass

    async def day_6(self):
        pass

    async def day_7(self):
        pass

    async def _increment_day(self):
        from database.repositories import AccountRepo
        from core.app import db

        phone10 = self.c.account["phone10"]

        async with db.get_session() as session:
            await session.execute(
                update(Account)
                .where(Account.phone == phone10)
                .values(feeding_day=Account.feeding_day + 1)
            )