from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget,
)
from PySide6.QtCore import Qt


class OpenQrDialog(QDialog):
    def __init__(self, parent=None, counts: dict[str, int] | None = None):
        super().__init__(parent)

        counts = counts or {}
        total_all = int(counts.get("total_all", 0))
        total_sel = int(counts.get("total_selected", 0))
        disable_n = int(counts.get("disable", 0))
        logout_n = int(counts.get("logout", 0))
        login_n = int(counts.get("login", 0))
        unknown_n = int(counts.get("unknown", 0))

        self._rows: list[dict] = []
        self._row_by_phone: dict[str, int] = {}

        self.setWindowTitle("Забрать QR")
        self.resize(980, 620)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        mid = QHBoxLayout()
        mid.setSpacing(18)

        # ---------- LEFT ----------
        left_box = QWidget(self)
        left = QVBoxLayout(left_box)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        stats = QLabel(
            f"Выбрано {total_sel}/{total_all}\n\n"
            f"disable: {disable_n}\n"
            f"logout: {logout_n}\n"
            f"login: {login_n}\n"
            + (f"unknown: {unknown_n}\n" if unknown_n else "")
        )
        stats.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        stats.setStyleSheet("""
            QLabel {
                font-size: 13px;
                padding: 12px 18px;
            }
        """)
        left.addWidget(stats)
        left.addStretch()

        # ---------- RIGHT (TABLE) ----------
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.verticalHeader().setDefaultSectionSize(23)
        self.table.setHorizontalHeaderLabels(["Телефон", "Статус", "%", "Результат", "Шаг"])

        self.table.verticalHeader().setVisible(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 40)
        self.table.setColumnWidth(3, 180)

        self.table.setRowCount(0)

        mid.addWidget(left_box, 0)
        mid.addWidget(self.table, 1)
        root.addLayout(mid, 1)

        # ---------- BOTTOM ----------
        bottom = QHBoxLayout()
        bottom.addStretch()

        self.btn_start = QPushButton("Забрать QR")
        self.btn_start.setMinimumSize(260, 44)
        self.btn_start.clicked.connect(self.on_start_clicked)

        bottom.addWidget(self.btn_start)
        bottom.addStretch()
        root.addLayout(bottom)

    # ===== API как в AllActivationDialog =====
    def set_selected_accounts(self, rows: list[dict]) -> None:
        """
        rows: [{phone10, status, row_index}, ...]
        """
        self._rows = rows[:]
        self._row_by_phone.clear()

        self.table.setRowCount(len(rows))
        for r, data in enumerate(rows):
            phone = (data.get("phone10") or "").strip()
            status = (data.get("status") or "").strip()

            self._row_by_phone[phone] = r

            it_phone = QTableWidgetItem(phone)
            it_status = QTableWidgetItem(status)
            it_percent = QTableWidgetItem("0%")
            it_res = QTableWidgetItem("")
            it_step = QTableWidgetItem("")

            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            it_percent.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(r, 0, it_phone)
            self.table.setItem(r, 1, it_status)
            self.table.setItem(r, 2, it_percent)
            self.table.setItem(r, 3, it_res)
            self.table.setItem(r, 4, it_step)

    def set_row_progress(self, phone10: str, percent: int | None, step: str = "") -> None:
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return

        if percent is not None:
            self.table.item(r, 2).setText(f"{max(0, min(100, int(percent)))}%")

        if step:
            self.table.item(r, 4).setText(step)

    def set_row_result(self, phone10: str, text: str) -> None:
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return
        self.table.item(r, 3).setText(text)

    # ===== button =====
    def on_start_clicked(self) -> None:
        # тут позже будет логика “забрать QR”
        # сейчас просто закрываем окно как заглушку
        self.accept()
