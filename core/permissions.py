# core/permissions.py

from __future__ import annotations


class Perm:
    # Меню
    IMPORT_EXCEL = "import_excel"
    PROXY_MANAGER = "proxy_manager"

    # Верхние кнопки
    ADD_ACCOUNT = "add_account"
    MASS_ACTIVATION = "mass_activation"
    GET_QR = "get_qr"
    DELETE_SELECTED = "delete_selected"

    # Действия в строке таблицы
    EDIT_ACCOUNT = "edit_account"
    DELETE_ACCOUNT = "delete_account"

    # Контекстное меню "More"
    MORE_MENU = "more_menu"
    REAUTH = "reauth"
    REMOVE_FROM_PC = "remove_from_pc"

    DELETE_PROXY = "delete_proxy"
    EDIT_PROXY = "edit_proxy"
    OPEN_PROXY = "open_proxy"


# Все возможные права в системе
ALL_PERMS: set[str] = {
    Perm.IMPORT_EXCEL,
    Perm.PROXY_MANAGER,
    Perm.ADD_ACCOUNT,
    Perm.MASS_ACTIVATION,
    Perm.GET_QR,
    Perm.DELETE_SELECTED,
    Perm.EDIT_ACCOUNT,
    Perm.DELETE_ACCOUNT,
    Perm.MORE_MENU,
    Perm.REAUTH,
    Perm.REMOVE_FROM_PC,
    Perm.DELETE_PROXY,
    Perm.EDIT_PROXY,
    Perm.OPEN_PROXY,
}


def parse_permissions(value) -> set[str]:
    """
    PostgreSQL JSONB возвращает list.
    Поэтому просто превращаем список в set.
    """
    if not value:
        return set()

    if isinstance(value, list):
        return set(map(str, value))

    # на всякий случай (если вдруг придёт строка)
    try:
        import json
        data = json.loads(value)
        if isinstance(data, list):
            return set(map(str, data))
    except Exception:
        pass

    return set()


def calc_user_permissions(role: str | None, denied_permissions) -> set[str]:
    """
    DENY-LIST модель:

    - admin → получает ВСЁ
    - остальные → получают всё, кроме запрещённого
    """

    role = (role or "manager").strip().lower()

    if role == "admin":
        return set(ALL_PERMS)

    denied = parse_permissions(denied_permissions)

    # всем разрешено всё, кроме запрещённого
    return set(ALL_PERMS) - denied