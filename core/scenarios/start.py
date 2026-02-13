from __future__ import annotations
from .base import BaseScenario
from domain.enums import ScenarioMode


class StartProcessScenario(BaseScenario):
    """Сценарий запуска браузера"""
    mode = ScenarioMode.START

    async def run(self) -> None:
        """Запуск сценария."""
        c = self.c
        await c.context.wait_for_event("close", timeout=0)
