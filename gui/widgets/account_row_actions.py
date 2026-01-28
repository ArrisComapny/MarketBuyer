from __future__ import annotations

from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton

from gui.style import AppStyle


class AccountRowActions(QWidget):
    """Виджет действий строки (колонка "Действие")."""

    runClicked = Signal(str)
    settingsClicked = Signal(str)
    deleteClicked = Signal(str)
    moreClicked = Signal(str)

    def __init__(self, phone10: str, run_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.phone10 = str(phone10).strip()

        self.btn_run = QPushButton(run_text, self)
        self.btn_run.setFixedSize(105, 25)
        self.btn_run.setStyleSheet(AppStyle.qss_run_btn())

        self.btn_settings = QPushButton(self)
        self.btn_settings.setIcon(AppStyle.icon("setting"))
        self.btn_settings.setIconSize(QSize(20, 20))
        self.btn_settings.setFixedSize(25, 25)
        self.btn_settings.setStyleSheet(AppStyle.qss_icon_btn())

        self.btn_delete = QPushButton(self)
        self.btn_delete.setIcon(AppStyle.icon("delete"))
        self.btn_delete.setIconSize(QSize(20, 20))
        self.btn_delete.setFixedSize(25, 25)
        self.btn_delete.setStyleSheet(AppStyle.qss_icon_btn())

        self.btn_more = QPushButton(self)
        self.btn_more.setIcon(AppStyle.icon("more_setting"))
        self.btn_more.setIconSize(QSize(20, 20))
        self.btn_more.setFixedSize(20, 25)
        self.btn_more.setStyleSheet(AppStyle.qss_icon_btn())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.btn_run)
        layout.addWidget(self.btn_settings)
        layout.addWidget(self.btn_delete)
        layout.addWidget(self.btn_more)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.btn_run.clicked.connect(self._emit_run)
        self.btn_settings.clicked.connect(self._emit_settings)
        self.btn_delete.clicked.connect(self._emit_delete)
        self.btn_more.clicked.connect(self._emit_more)

    def set_run_loading(self, loading: bool, text: str, qss: str) -> None:
        """Переводит кнопку Run в состояние загрузки или возвращает её в норму."""
        self.btn_run.setDisabled(loading)
        if text:
            self.btn_run.setText(text)
        self.btn_run.setStyleSheet(qss)

    def _emit_run(self) -> None:
        """Обработчик нажатия кнопки Run."""
        self.runClicked.emit(self.phone10)

    def _emit_settings(self) -> None:
        """Обработчик нажатия кнопки Settings."""
        self.settingsClicked.emit(self.phone10)

    def _emit_delete(self) -> None:
        """Обработчик нажатия кнопки Delete."""
        self.deleteClicked.emit(self.phone10)

    def _emit_more(self) -> None:
        """Обработчик нажатия кнопки More."""
        self.moreClicked.emit(self.phone10)
