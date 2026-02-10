from __future__ import annotations

from abc import ABC, abstractmethod

from core.scenarios.modes import ScenarioMode


class BaseScenario(ABC):
    mode: ScenarioMode

    def __init__(self, controller: "BrowserController"):
        self.c = controller

    @abstractmethod
    async def run(self) -> None:
        raise NotImplementedError
