from __future__ import annotations

from .activate import ActivateScenario
from .login import LoginScenario
from .start import StartProcessScenario

SCENARIOS = {
    ActivateScenario.mode: ActivateScenario,
    LoginScenario.mode: LoginScenario,
    StartProcessScenario.mode: StartProcessScenario,
}