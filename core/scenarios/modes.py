from enum import Enum

class ScenarioMode(str, Enum):
    ACTIVATE = "activate"
    LOGOUT_LOGIN = "logout-login"
    START_PROCESS = "scenario_start_process"
