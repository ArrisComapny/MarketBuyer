from __future__ import annotations

from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QProgressBar, QLabel

from gui.style import AppStyle


class AccountRowActions(QWidget):
    """Виджет действий строки (колонка "Действие")."""

    runClicked = Signal(str)
    cancelClicked = Signal(str)
    settingsClicked = Signal(str)
    deleteClicked = Signal(str)
    moreClicked = Signal(str)

    def __init__(self, phone10: str, run_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.phone10 = str(phone10).strip()

        self._loading = False
        self._loading_text = run_text
        self._can_cancel = False


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
        self._loading = bool(loading)

        # СЦЕНАРИЙ ЗАКОНЧИЛСЯ → сбрасываем флаг отмены
        if not loading:
            self._can_cancel = False

        if text:
            self._loading_text = text

        # Браузер реально запущен → разрешаем отмену (и больше НЕ запрещаем)
        if text == "Запущено":
            self._can_cancel = True

        # Кнопка запуска
        self.btn_run.setDisabled(loading)
        self.btn_run.setText(self._loading_text if loading else text)
        self.btn_run.setStyleSheet(qss)

        # Блокируем остальные кнопки строки
        self.btn_settings.setDisabled(loading)
        self.btn_delete.setDisabled(loading)
        self.btn_more.setDisabled(loading)

    def _emit_run(self) -> None:
        if self._loading and not self._can_cancel:
            return

        if self._loading and self.btn_run.text() == "Отмена":
            self.cancelClicked.emit(self.phone10)
            return

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

    def enterEvent(self, event) -> None:
        # Если сценарий запущен (кнопка disabled) — при наведении показываем "Отмена"
        if self._loading and self._can_cancel:
            self._show_cancel()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        # Уходим мышью — возвращаем текст прогресса/загрузки
        if self._loading:
            self._restore_loading_text()
        super().leaveEvent(event)

    def _show_cancel(self) -> None:
        self.btn_run.setEnabled(True)  # временно даём нажать
        self.btn_run.setText("Отмена")

    def _restore_loading_text(self) -> None:
        self.btn_run.setEnabled(False)
        self.btn_run.setText(self._loading_text)

