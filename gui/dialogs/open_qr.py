from __future__ import annotations

import asyncio
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QFileDialog
)
from PySide6.QtCore import Qt

from core.scenarios.modes import ScenarioMode

from pathlib import Path
import zipfile
from core.scenarios.get_qr import save_mass_results_to_excel

class OpenQrDialog(QDialog):
    def __init__(self,parent=None,counts: dict[str, int] | None = None,*,run_one_for_queue,):

        super().__init__(parent)
        self._run_one_for_queue = run_one_for_queue

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

        self._export_dir: str | None = None
        self._all_results: list[dict] = []

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
        export_dir = self._ask_export_directory()
        if not export_dir:
            return

        self._export_dir = export_dir
        self._all_results = []

        asyncio.create_task(self._run_qr_for_selected())

    async def _run_qr_for_selected(self) -> None:
        if not self._export_dir:
            return

        for item in self._rows:
            phone10 = item.get("phone10")
            if not phone10:
                continue

            self.set_row_result(phone10, "Запуск…")

            result = await self._run_one_for_queue(
                phone10,
                ScenarioMode.QRCODE,
                self
            )

            if result.get("ok"):
                # ВАЖНО: _run_one_for_queue должен вернуть данные сценария
                payload = result.get("data")  # <-- если у тебя ключ другой, поменяй
                if payload:
                    self._all_results.append(payload)

                self.set_row_result(phone10, "QR получен")
                self.set_row_progress(phone10, 100, "Готово")
            else:
                msg = result.get("msg", "Ошибка")
                self.set_row_result(phone10, "Ошибка")
                self.set_row_progress(phone10, 0, msg)

        # ===== ПОСЛЕ ЦИКЛА ПО АККАУНТАМ =====

        export_dir = Path(self._export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        xlsx_path = export_dir / "qr_export.xlsx"

        # 1) сохранить Excel + картинки
        save_mass_results_to_excel(str(xlsx_path), self._all_results)

        try:
            zip_path = self._make_zip(export_dir)  # ✅ self обязательно
            print("ZIP создан:", zip_path)
        except Exception as e:
            print("ОШИБКА ZIP:", repr(e))

    def _ask_export_directory(self) -> str | None:
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для сохранения QR",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        return dir_path or None

    def _make_zip(self, export_dir: Path) -> str:
        zip_path = export_dir / "qr_export.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in export_dir.rglob("*"):
                if f.is_file():
                    if f.resolve() == zip_path.resolve():
                        continue  # ✅ не добавляем zip в самого себя
                    zf.write(f, f.relative_to(export_dir))
        return str(zip_path)

