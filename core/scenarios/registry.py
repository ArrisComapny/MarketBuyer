from __future__ import annotations

from .activate import ActivateScenario
from .logout_login import LogoutLoginScenario
from .start_process import StartProcessScenario

SCENARIOS = {
    ActivateScenario.mode: ActivateScenario,
    LogoutLoginScenario.mode: LogoutLoginScenario,
    StartProcessScenario.mode: StartProcessScenario,
}