from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from PySide6.QtGui import QIcon


@dataclass(frozen=True)
class AppStyle:
    """Централизованные стили (QSS) и иконки проекта."""

    ICON_DIR: Path = Path("templates/icons")

    # --- Карта иконок (ключ -> файл) ---
    ICONS = {
        "filter": "filter.png",
        "find": "find.png",
        "setting": "setting.png",
        "delete": "delete.png",
        "more_setting": "more_setting.png",
        "login": "login.png",
    }

    # ---------------- Icons ----------------

    @classmethod
    def icon_path(cls, key: str) -> str:
        """Возвращает путь к файлу иконки по ключу."""
        filename = cls.ICONS.get(key)
        if not filename:
            raise KeyError(f"Unknown icon key: {key!r}. Add it to AppStyle.ICONS")
        return str(cls.ICON_DIR / filename)

    @classmethod
    def icon(cls, key: str) -> QIcon:
        """Возвращает QIcon по ключу."""
        return QIcon(cls.icon_path(key))

    # ---------------- QSS ----------------

    @staticmethod
    def qss_icon_btn() -> str:
        """QSS для иконок-кнопок (setting/delete/more)."""
        return """
        QPushButton {
            border: none;
            background-color: transparent;
        }
        QPushButton:hover {
            background-color: rgba(0, 120, 215, 40);
            border-radius: 4px;
        }
        """

    @staticmethod
    def qss_run_btn() -> str:
        """QSS для run-кнопки (обычное состояние)."""
        return """
        QPushButton {
            border: 1px solid white;
            background-color: transparent;
        }
        QPushButton:hover {
            background-color: rgba(0, 120, 215, 40);
            border-radius: 4px;
        }
        """

    @staticmethod
    def qss_run_btn_disabled() -> str:
        """QSS для run-кнопки (disabled/processing)."""
        return """
        QPushButton {
            border: 1px solid #888;
            background-color: #d0d0d0;
            color: #777;
        }
        """

    @staticmethod
    def qss_menu_bar() -> str:
        """QSS для меню-бара (линия снизу)."""
        return """
        QMenuBar {
            border-bottom: 1px solid #d0d0d0;
        }
        """

    @staticmethod
    def qss_checkbox_spacing(spacing_px: int = 14) -> str:
        """QSS для чекбокса со spacing."""
        return f"QCheckBox {{ spacing: {spacing_px}px; }}"

    @staticmethod
    def qss_btn_disabled_dark() -> str:
        """QSS: disabled-кнопка (как в LoginWindow)."""
        return """
        QPushButton:disabled {
            background-color: #2d2d2d;
            color: #888888;
        }
        """