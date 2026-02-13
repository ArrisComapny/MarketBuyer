from enum import Enum

class ScenarioMode(str, Enum):
    ACTIVATE = "activate_account"
    LOGIN = "login_account"
    START = "start_account"
    QRCODE = "qrcode_account"


class AccountStatus(str, Enum):
    DISABLE = "disable"
    LOGIN = "login"
    LOGOUT = "logout"

    def run_text(self) -> str:
        return {
            AccountStatus.DISABLE: "Активировать",
            AccountStatus.LOGIN: "Запуск",
            AccountStatus.LOGOUT: "Вход",
        }.get(self, "Запуск")

    @classmethod
    def from_text(cls, v: str | None) -> "AccountStatus":
        s = (v or "").strip().lower()
        if s == cls.DISABLE.value:
            return cls.DISABLE
        if s == cls.LOGIN.value:
            return cls.LOGIN
        if s == cls.LOGOUT.value:
            return cls.LOGOUT
        return cls.DISABLE
