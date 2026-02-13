from __future__ import annotations

import asyncio

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem, QHeaderView, QWidget, QFileDialog
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,  QTableWidget

from gui.style import AppStyle

from domain.dtos import RowItems, SelectedCounts, QrResult
from domain.enums import ScenarioMode, AccountStatus
from utils.save_qr_info import save_mass_results_to_excel, make_zip


class OpenQrDialog(QDialog):
    """Диалоговое окно сбора информации о заказах"""
    def __init__(self, parent: "MainWindow", counts: SelectedCounts):
        super().__init__(parent)

        self.mw = parent

        self._rows: list[RowItems] = []
        self._row_by_phone: dict[str, int] = {}

        self.setWindowTitle("Забрать QR")
        self.resize(980, 620)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        mid = QHBoxLayout()
        mid.setSpacing(18)

        left_box = QWidget(self)
        left = QVBoxLayout(left_box)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        stats = QLabel(
            f"Выбрано {counts.total_selected}/{counts.total_all}\n\n"
            f"{AccountStatus.DISABLE}: {counts.disable}\n"
            f"{AccountStatus.LOGOUT}: {counts.logout}\n"
            f"{AccountStatus.LOGIN}: {counts.login}\n"
        )

        stats.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        stats.setStyleSheet(AppStyle.qss_label_stats())
        left.addWidget(stats)
        left.addStretch()

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

        bottom = QHBoxLayout()
        bottom.addStretch()

        self.btn_start = QPushButton("Забрать QR")
        self.btn_start.setMinimumSize(260, 44)
        self.btn_start.clicked.connect(self.on_start_clicked)

        bottom.addWidget(self.btn_start)
        bottom.addStretch()
        root.addLayout(bottom)

        self._export_dir: str | None = None
        self._all_results: list[QrResult] = []

    def set_selected_accounts(self, rows: list[RowItems]) -> None:
        """Заполняет таблицу выбранными аккаунтами, для которых будем забирать QR."""
        self._rows = rows[:]
        self._row_by_phone.clear()

        self.table.setRowCount(len(rows))
        for r, data in enumerate(rows):
            phone = data.phone10
            status = data.status

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
        """Обновляет процент выполнения и текст шага в строке аккаунта."""
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return

        if percent is not None:
            self.table.item(r, 2).setText(f"{max(0, min(100, int(percent)))}%")
        if step:
            self.table.item(r, 4).setText(step)

    def set_row_result(self, phone10: str, text: str) -> None:
        """Обновляет колонку 'Результат'."""
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return
        self.table.item(r, 3).setText(text)

    def on_start_clicked(self) -> None:
        """Запрашивает папку экспорта и запускает асинхронный сбор QR для выбранных аккаунтов."""
        export_dir = self._ask_export_directory()
        if not export_dir:
            return

        self._export_dir = export_dir
        self._all_results = []

        asyncio.create_task(self._run_qr_for_selected())

    async def _run_qr_for_selected(self) -> None:
        """
        Последовательно запускает сценарий получения QR для каждого аккаунта,
        собирает результаты и сохраняет их в Excel + ZIP в выбранную папку.
        """
        if not self._export_dir:
            return

        for item in self._rows:
            phone10 = item.phone10
            if not phone10:
                continue

            self.set_row_result(phone10, "Запуск…")

            result = await self.mw.run_one_account_for_queue(phone10, ScenarioMode.QRCODE, self)

            if result.get("ok"):
                payload = result.get("data")
                if payload:
                    self._all_results.append(payload)

                self.set_row_result(phone10, "QR получен")
                self.set_row_progress(phone10, 100, "Готово")
            else:
                msg = result.get("msg", "Ошибка")
                self.set_row_result(phone10, "Ошибка")
                self.set_row_progress(phone10, 0, msg)

        export_dir = Path(self._export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        xlsx_path = export_dir / "qr_export.xlsx"

        save_mass_results_to_excel(str(xlsx_path), self._all_results)

        try:
            make_zip(export_dir)
        except Exception as e:
            raise  Exception("ОШИБКА ZIP:", repr(e))

    def _ask_export_directory(self) -> str | None:
        """Открывает диалог выбора папки и возвращает путь."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для сохранения QR",
            "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        return dir_path or None
