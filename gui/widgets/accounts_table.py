from typing import Sequence

from sqlalchemy import Row
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QTableWidget, QTableWidgetItem
from PySide6.QtWidgets import QHBoxLayout, QCheckBox, QHeaderView, QAbstractItemView

from domain.dtos import RowItems
from domain.enums import AccountStatus

from utils.phone import format_phone_ru

from gui.style import AppStyle
from gui.widgets.check_box_header import CheckBoxHeader
from gui.widgets.account_row_actions import AccountRowActions


class AccountsTable(QTableWidget):
    """Таблица аккаунтов."""
    runClicked = Signal(str)
    cancelClicked = Signal(str)
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
            loading_text = running_ui.get(phone10)
            status = AccountStatus.from_text(status)

            self._fill_row(row, phone10, comment, status, loading_text)

        self.blockSignals(False)
        self._filling = False

    def _fill_row(self, row: int, phone10: str, comment: str, status: AccountStatus, loading_text: str) -> None:
        """Заполняет одну строку таблицы данными аккаунта."""
        checkbox = QCheckBox()
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        lay.addWidget(checkbox)
        lay.addStretch()

        checkbox.stateChanged.connect(lambda _: self._on_row_checkbox_changed())
        self.setCellWidget(row, 0, box)

        phone_view = format_phone_ru(phone10)
        it_phone = QTableWidgetItem(phone_view)
        it_phone.setData(Qt.ItemDataRole.UserRole, phone10)
        it_phone.setFlags(it_phone.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 1, it_phone)

        it_status = QTableWidgetItem(status.value)
        it_status.setFlags(it_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 2, it_status)

        self._apply_status_color(it_status, status)

        self.setItem(row, 3, QTableWidgetItem(comment or ""))

        run_text = status.run_text()

        actions = AccountRowActions(phone10=phone10, run_text=run_text, parent=self)

        actions.runClicked.connect(self.runClicked)
        actions.cancelClicked.connect(self.cancelClicked)
        actions.settingsClicked.connect(self.settingsClicked)
        actions.deleteClicked.connect(self.deleteClicked)
        actions.moreClicked.connect(self.moreClicked)

        self.setCellWidget(row, 4, actions)

        if loading_text:
            actions.set_run_loading(True, loading_text, AppStyle.qss_run_btn_disabled())
        else:
            actions.set_run_loading(False, run_text, AppStyle.qss_run_btn())

    @staticmethod
    def _apply_status_color(item: QTableWidgetItem, status: AccountStatus) -> None:
        """Устанавливает цвет фона ячейки статуса в зависимости от состояния аккаунта."""
        item.setBackground({
            AccountStatus.DISABLE: QColor(255, 0, 0, 35),
            AccountStatus.LOGIN: QColor(0, 200, 0, 35),
            AccountStatus.LOGOUT: QColor(255, 200, 0, 35),
        }.get(status))

    def _on_header_checkbox_clicked(self, state: Qt.CheckState) -> None:
        """Отмечает или снимает выбор со всех видимых строк таблицы."""
        checked = state == Qt.CheckState.Checked

        for row in range(self.rowCount()):
            if self.isRowHidden(row):
                continue

            cb = self._row_checkbox(row)
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)

        self.header.setState(state)

    def _on_row_checkbox_changed(self) -> None:
        """Обновляет состояние чекбокса в заголовке."""
        visible_rows = [r for r in range(self.rowCount()) if not self.isRowHidden(r)]
        total = len(visible_rows)
        checked = sum(1 for r in visible_rows if (cb := self._row_checkbox(r)) and cb.isChecked())

        if checked == 0:
            self.header.setState(Qt.CheckState.Unchecked)
        elif checked == total:
            self.header.setState(Qt.CheckState.Checked)
        else:
            self.header.setState(Qt.CheckState.PartiallyChecked)

    def _row_checkbox(self, row: int) -> QCheckBox:
        """Возвращает чекбокс строки по индексу."""
        w = self.cellWidget(row, 0)
        return w.findChild(QCheckBox)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Обрабатывает изменение комментария и отправляет сигнал сохранения."""
        if self._filling:
            return

        phone_item = self.item(item.row(), 1)
        phone10 = phone_item.data(Qt.ItemDataRole.UserRole)

        self.commentChanged.emit(phone10, item.text().strip())

    def selected_accounts_rows(self) -> list[RowItems]:
        """Возвращает список выбранных строк таблицы."""
        out: list[RowItems] = []

        for row in range(self.rowCount()):
            cb = self._row_checkbox(row)
            if not cb.isChecked():
                continue

            phone_item = self.item(row, 1)
            phone10 = phone_item.data(Qt.ItemDataRole.UserRole)

            status_item = self.item(row, 2)
            status = status_item.text()

            out.append(RowItems(row_idx=row, phone10=phone10, status=status))
        return out
