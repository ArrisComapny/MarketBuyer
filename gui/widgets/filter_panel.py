import re

from PySide6.QtGui import QAction
from PySide6.QtCore import Signal, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QLineEdit, QToolButton

from gui.style import AppStyle


class FilterPanel(QWidget):
    """Виджет: поиск + фильтр по статусам (с анимацией раскрытия панели)."""
    changed = Signal()

    def __init__(self, parent=None) -> None:
        """Создаёт UI фильтра и подключает сигналы, которые emit changed."""
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # ================== Верхняя строка: кнопка фильтра + поиск ==================
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        self.btn_filter = QToolButton(self)
        self.btn_filter.setCheckable(True)
        self.btn_filter.setAutoRaise(True)
        self.btn_filter.setToolTip("Фильтр")
        self.btn_filter.setIcon(AppStyle.icon("filter"))
        self.btn_filter.setIconSize(QSize(18, 18))
        self.btn_filter.setFixedSize(35, 35)

        self.search_input = QLineEdit(self)
        self.search_input.setFixedHeight(35)
        self.search_input.setFixedWidth(200)
        self.search_input.setPlaceholderText("Поиск по телефону")

        icon_action = QAction(AppStyle.icon("find"), "", self)
        self.search_input.addAction(icon_action, QLineEdit.ActionPosition.LeadingPosition)

        top_row.addWidget(self.btn_filter)
        top_row.addWidget(self.search_input)
        top_row.addStretch()

        root.addLayout(top_row)

        # ================== Панель фильтра (скрывается/показывается анимацией) ==================
        self.panel = QFrame(self)
        self.panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.panel.setVisible(False)
        self.panel.setMaximumHeight(0)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(6, 4, 6, 4)
        panel_layout.setSpacing(4)

        row = QWidget(self.panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        label = QLabel("Фильтр по статусам:", row)
        row_layout.addWidget(label)

        self.cb_disable = QCheckBox("Disable", row)
        self.cb_login = QCheckBox("login", row)
        self.cb_logout = QCheckBox("logout", row)

        # По умолчанию показываем всё
        self.cb_disable.setChecked(True)
        self.cb_login.setChecked(True)
        self.cb_logout.setChecked(True)

        row_layout.addWidget(self.cb_disable)
        row_layout.addWidget(self.cb_login)
        row_layout.addWidget(self.cb_logout)
        row_layout.addStretch()

        panel_layout.addWidget(row)
        root.addWidget(self.panel)

        # Анимация
        self.anim = QPropertyAnimation(self.panel, b"maximumHeight", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Сигналы
        self.btn_filter.toggled.connect(self._toggle_panel)
        self.search_input.textChanged.connect(lambda _: self.changed.emit())

        self.cb_disable.toggled.connect(lambda _: self.changed.emit())
        self.cb_login.toggled.connect(lambda _: self.changed.emit())
        self.cb_logout.toggled.connect(lambda _: self.changed.emit())

        self._hide_slot = None

    def allowed_statuses(self) -> set[str]:
        """Возвращает выбранные статусы (пустой set означает «показывать всё»)."""
        allowed: set[str] = set()
        if self.cb_disable.isChecked():
            allowed.add("disable")
        if self.cb_login.isChecked():
            allowed.add("login")
        if self.cb_logout.isChecked():
            allowed.add("logout")
        return allowed

    def search_text(self) -> str:
        """Возвращает текст поиска (strip + lower)."""
        return self.search_input.text().strip().lower()

    def search_digits(self) -> str:
        """Возвращает только цифры из текста поиска (удобно для сравнения телефонов)."""
        return re.sub(r"\D", "", self.search_text())

    def is_panel_open(self) -> bool:
        """True если панель фильтра раскрыта."""
        return self.btn_filter.isChecked()

    def set_panel_open(self, opened: bool) -> None:
        """Программно раскрывает/скрывает панель фильтра."""
        self.btn_filter.setChecked(opened)

    def _toggle_panel(self, opened: bool) -> None:
        """Показывает/скрывает панель фильтра с анимацией и emit changed."""
        self.anim.stop()

        if self._hide_slot:
            try:
                self.anim.finished.disconnect(self._hide_slot)
            except Exception:
                pass
            self._hide_slot = None

        if opened:
            self.panel.setVisible(True)
            self.panel.setMaximumHeight(0)

            target = self.panel.sizeHint().height()
            if target <= 0:
                target = 120

            self.anim.setStartValue(0)
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            start = self.panel.maximumHeight()
            self.anim.setStartValue(start)
            self.anim.setEndValue(0)

            def _hide():
                self.panel.setVisible(False)

            self._hide_slot = _hide
            self.anim.finished.connect(_hide)
            self.anim.start()

        # любое раскрытие/сворачивание тоже влияет на UX — можно считать "changed"
        self.changed.emit()
