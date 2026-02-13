import json

from typing import Any

from config import CONFIG_PATH


def load_settings() -> dict[str, Any]:
    """Загружает настройки из JSON-файла. Возвращает пустой словарь при ошибке."""
    if not CONFIG_PATH.exists():
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict[str, Any]) -> None:
    """Сохраняет настройки в JSON-файл (перезаписывает полностью)."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

