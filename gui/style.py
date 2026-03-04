import sys

from pathlib import Path
from dataclasses import dataclass

from PySide6.QtGui import QIcon


def resource_path(rel_path: str) -> Path:
    """Универсальный путь к ресурсам."""
    # PyInstaller
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel_path

    base = Path(sys.argv[0]).resolve().parent
    return base / rel_path


@dataclass(frozen=True)
class AppStyle:
    """Централизованные стили (QSS) и иконки проекта."""
    # --- Карта иконок (ключ -> файл) ---
    ICONS = {
        "filter": "filter.ico",
        "find": "find.ico",
        "setting": "setting.ico",
        "delete": "delete.ico",
        "more_setting": "more_setting.ico",
        "login": "login.ico",
        "app": "app.ico",
    }

    # ---------------- Icons ----------------

    @classmethod
    def icon_path(cls, key: str) -> str:
        """Возвращает абсолютный путь к иконке."""
        filename = cls.ICONS.get(key)
        if not filename:
            raise KeyError(f"Unknown icon key: {key!r}")

        return str(resource_path(f"templates/icons/{filename}"))

    @classmethod
    def icon(cls, key: str) -> QIcon:
        """Возвращает QIcon по ключу."""
        return QIcon(cls.icon_path(key))

    # ---------------- QSS ----------------

    @staticmethod
    def qss_icon_btn() -> str:
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
        return """
        QPushButton {
            border: 1px solid #888;
            background-color: #d0d0d0;
            color: #777;
        }
        """

    @staticmethod
    def qss_menu_bar() -> str:
        return """
        QMenuBar {
            border-bottom: 1px solid #d0d0d0;
        }
        """

    @staticmethod
    def qss_checkbox_spacing(spacing_px: int = 14) -> str:
        return f"QCheckBox {{ spacing: {spacing_px}px; }}"

    @staticmethod
    def qss_btn_disabled_dark() -> str:
        return """
        QPushButton:disabled {
            background-color: #2d2d2d;
            color: #888888;
        }
        """

    @staticmethod
    def qss_toggle(active: bool) -> str:
        return f"""
                QPushButton {{
                    border: 1px solid rgba(0,0,0,0.15);
                    border-radius: 6px;
                    padding: 2px 10px;
                    font-weight: 600;
                    color: white;
                    background: {'#2ecc71' if active else '#e74c3c'};
                }}
                QPushButton:hover {{
                    background: {'#29b765' if active else '#d64535'};
                }}
            """

    @staticmethod
    def qss_label_stats() -> str:
        return """
            QLabel {
                font-size: 13px;
                padding: 12px 18px;
            }
        """
