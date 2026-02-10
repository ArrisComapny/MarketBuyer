from __future__ import annotations
from .base import BaseScenario
from .modes import ScenarioMode


class StartProcessScenario(BaseScenario):
    mode = ScenarioMode.START_PROCESS

    async def run(self) -> None:
        c = self.c
        print("[SCENARIO] start_process — браузер открыт")
        await c.context.wait_for_event("close", timeout=0)
