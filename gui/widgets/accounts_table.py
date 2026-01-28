from typing import Sequence

from sqlalchemy import Row
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QTableWidget, QTableWidgetItem
from PySide6.QtWidgets import QHBoxLayout, QCheckBox, QHeaderView, QAbstractItemView

from gui.style import AppStyle
from gui.check_box_header import CheckBoxHeader
from gui.widgets.account_row_actions import AccountRowActions

from utils.phone import format_phone_ru


class AccountsTable(QTableWidget):
    """Таблица аккаунтов."""

    runClicked = Signal(str)
    settingsClicked = Signal(str)
    deleteClicked = Signal(str)
    moreClicked = Signal(str)
    commentChanged = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._filling = False

        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["", "Номер телефона", "Статус", "Комментарий", "Действие"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)

        # Header checkbox
        self.header = CheckBoxHeader(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)
        self.header.clicked.connect(self._on_header_checkbox_clicked)

        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(0, 36)
        self.setColumnWidth(1, 120)
        self.setColumnWidth(2, 110)
        self.setColumnWidth(4, 200)

        self.itemChanged.connect(self._on_item_changed)

    def fill(self,
             rows: Sequence[Row[tuple[str, str | None, str | None]]],
             running_ui: dict[str, str] | None = None) -> None:
        """Заполняет таблицу списком аккаунтов."""
        self._filling = True
        self.blockSignals(True)

        running_ui = running_ui or {}

        self.setRowCount(len(rows))
        for row, (phone, comment, status) in enumerate(rows):
            phone10 = str(phone).strip()
            loading_text = running_ui.get(phone10)  # None если не активен
            self._fill_row(row, phone10, comment, status, loading_text)

        self.blockSignals(False)
        self._filling = False
        self.header.setState(Qt.CheckState.Unchecked)

    def _fill_row(self,
                  row: int,
                  phone10: str,
                  comment: str | None,
                  status: str | None,
                  loading_text: str | None) -> None:
        """Заполняет одну строку таблицы данными аккаунта."""
        # ---- checkbox ----
        checkbox = QCheckBox()
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        lay.addWidget(checkbox)
        lay.addStretch()

        checkbox.stateChanged.connect(lambda _: self._on_row_checkbox_changed())
        self.setCellWidget(row, 0, box)

        # ---- phone ----
        phone_view = format_phone_ru(phone10)
        it_phone = QTableWidgetItem(phone_view)
        it_phone.setData(Qt.ItemDataRole.UserRole, phone10)
        it_phone.setFlags(it_phone.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 1, it_phone)

        # ---- status ----
        it_status = QTableWidgetItem(status or "")
        it_status.setFlags(it_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 2, it_status)

        self._apply_status_color(it_status, status)

        # ---- comment ----
        self.setItem(row, 3, QTableWidgetItem(comment or ""))

        # ---- actions ----
        st = (status or "").strip().lower()
        run_text = {
            "disable": "Активировать",
            "login": "Запуск",
            "logout": "Вход",
        }.get(st, "Запуск")

        actions = AccountRowActions(phone10=phone10, run_text=run_text, parent=self)

        actions.runClicked.connect(self.runClicked)
        actions.settingsClicked.connect(self.settingsClicked)
        actions.deleteClicked.connect(self.deleteClicked)
        actions.moreClicked.connect(self.moreClicked)

        self.setCellWidget(row, 4, actions)

        if loading_text:
            actions.set_run_loading(True, loading_text, AppStyle.qss_run_btn_disabled())
        else:
            actions.set_run_loading(False, run_text, AppStyle.qss_run_btn())

    @staticmethod
    def _apply_status_color(item: QTableWidgetItem, status: str | None) -> None:
        """Применяет цветовую подсветку к ячейке статуса аккаунта."""
        colors = {
            "disable": QColor(255, 0, 0, 35),
            "login": QColor(0, 200, 0, 35),
            "logout": QColor(255, 200, 0, 35),
        }
        st = (status or "").strip().lower()
        if st in colors:
            item.setBackground(colors[st])

    def _on_header_checkbox_clicked(self, state: Qt.CheckState) -> None:
        """Обрабатывает клик по checkbox в заголовке таблицы."""
        checked = state == Qt.CheckState.Checked
        for row in range(self.rowCount()):
            cb = self._row_checkbox(row)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)

        self.header.setState(state)

    def _on_row_checkbox_changed(self) -> None:
        """Обрабатывает изменение состояния checkbox в строке."""
        total = self.rowCount()
        checked = sum(
            1 for r in range(total)
            if (cb := self._row_checkbox(r)) and cb.isChecked()
        )

        if checked == 0:
            self.header.setState(Qt.CheckState.Unchecked)
        elif checked == total:
            self.header.setState(Qt.CheckState.Checked)
        else:
            self.header.setState(Qt.CheckState.PartiallyChecked)

    def _row_checkbox(self, row: int) -> QCheckBox | None:
        """Возвращает checkbox строки по индексу."""
        w = self.cellWidget(row, 0)
        return w.findChild(QCheckBox) if w else None

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Обрабатывает изменение ячейки таблицы."""
        if self._filling:
            return
        if item.column() != 3:
            return

        phone_item = self.item(item.row(), 1)
        if not phone_item:
            return

        phone10 = phone_item.data(Qt.ItemDataRole.UserRole)
        self.commentChanged.emit(phone10, item.text().strip())
