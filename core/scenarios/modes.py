from enum import Enum

class ScenarioMode(str, Enum):
    ACTIVATE = "activate_account"
    LOGIN = "login_account"
    START = "start_account"
    QRCODE = "qrcode_account"
