from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QTableWidgetItem,QHeaderView,QWidget,QFileDialog,QDialog,
QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,)

from gui.style import AppStyle
from domain.dtos import RowItems, SelectedCounts, QrResult
from domain.enums import ScenarioMode, AccountStatus
from utils.save_qr_info import save_mass_results_to_excel, make_zip


class OpenQrDialog(QDialog):
    """Диалоговое окно сбора QR по выбранным аккаунтам."""

    def __init__(self, parent: "MainWindow", counts: SelectedCounts):
        super().__init__(parent)

        self.mw = parent

        self._rows: list[RowItems] = []
        self._row_by_phone: dict[str, int] = {}

        self.setWindowTitle("Получить QR")
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

        self.btn_start = QPushButton("Запустить")
        self.btn_start.setMinimumSize(260, 44)
        self.btn_start.clicked.connect(self.on_start_clicked)

        bottom.addWidget(self.btn_start)
        bottom.addStretch()
        root.addLayout(bottom)

        self._export_dir: str | None = None
        self._all_results: list[QrResult] = []

        # ===== STATE =====
        self._running: bool = False
        self._completed: bool = False

        self._qr_task: asyncio.Task | None = None
        self._workers: list[asyncio.Task] = []
        self._cancel_requested: bool = False

    # ---------- UI helpers ----------
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

    # ---------- Start / Cancel / Done ----------
    def on_start_clicked(self) -> None:
        """
        Кнопка работает как:
        - "Получить QR" -> старт
        - "Отмена" -> отменить все сценарии
        - "Готово" -> закрыть окно
        """
        # 1) если уже завершили — закрываем
        if self._completed:
            self.accept()
            return

        # 2) если идёт выполнение — это "Отмена"
        if self._running:
            self._cancel_requested = True
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Отмена…")
            asyncio.create_task(self._cancel_all())
            return

        # 3) старт
        export_dir = self._ask_export_directory()
        if not export_dir:
            return

        self._export_dir = export_dir
        self._all_results = []

        self._running = True
        self._completed = False
        self._cancel_requested = False

        self.btn_start.setEnabled(True)
        self.btn_start.setText("Отмена")

        self._qr_task = asyncio.create_task(self._run_qr_for_selected())

    async def _cancel_all(self) -> None:
        """Отменяет воркеры/таски, закрывает браузеры/прокси и сохраняет то, что уже собрано."""
        # 1) просим остановиться
        self._cancel_requested = True

        # 2) отменяем основную задачу
        if self._qr_task and not self._qr_task.done():
            self._qr_task.cancel()

        # 3) отменяем воркеров
        for t in list(self._workers):
            if t and not t.done():
                t.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        # 4) зачистка: браузеры + прокси
        await self._stop_all_running()

        # 5) ✅ экспорт уже собранного
        try:
            await self._export_partial_results(suffix="cancelled")
        except Exception as e:
            # можно показать в UI (например, в первой строке)
            if self._rows:
                phone10 = getattr(self._rows[0], "phone10", "") or ""
                self.set_row_progress(phone10, 0, f"Экспорт: {type(e).__name__}: {e}")

        # 6) вернуть UI в "не запущено"
        self._running = False
        self._completed = False
        self.btn_start.setEnabled(True)
        self.btn_start.setText("Запустить")

    async def _stop_all_running(self) -> None:
        """Закрывает все контроллеры браузеров и освобождает прокси, которые могли остаться заняты."""
        # Эти поля предполагаются такими же, как в mass/all_activation.
        browser_map = getattr(self.mw, "browser_controllers", None)
        proxy_map = getattr(self.mw, "account_proxy", None)
        running_ui = getattr(self.mw, "running_ui", None)

        if isinstance(browser_map, dict):
            for phone10, controller in list(browser_map.items()):
                try:
                    await controller.close()
                except Exception:
                    pass
                self.set_row_result(phone10, "Отменено")
                self.set_row_progress(phone10, 0, "Отменено")
            browser_map.clear()

        if isinstance(proxy_map, dict):
            for phone10, proxy_id in list(proxy_map.items()):
                try:
                    await self.mw.proxy_pool.release(proxy_id)
                except Exception:
                    pass
            proxy_map.clear()

        if isinstance(running_ui, dict):
            running_ui.clear()

    # ---------- Main worker runner ----------
    async def _run_qr_for_selected(self) -> None:
        def reset_btn() -> None:
            self._running = False
            self._completed = False
            self.btn_start.setEnabled(True)
            self.btn_start.setText("Запустить")

        def finish_ok() -> None:
            self._running = False
            self._completed = True
            self.btn_start.setEnabled(True)
            self.btn_start.setText("Готово")

        if not self._export_dir:
            reset_btn()
            return

        self._workers = []
        self._cancel_requested = False
        self._all_results = []

        q: asyncio.Queue[str] = asyncio.Queue()
        for item in self._rows:
            phone10 = getattr(item, "phone10", None)
            if not phone10:
                continue
            await q.put(phone10)
            self.set_row_result(phone10, "В очереди")
            self.set_row_progress(phone10, 0, "")

        if q.empty():
            reset_btn()
            return

        max_parallel = 10
        try:
            capacity = await self.mw.proxy_pool.capacity(
                user_login=self.mw.user.login,
                is_admin=(self.mw.user.role == "admin"),
            )
            workers_n = max(1, min(max_parallel, int(capacity)))
        except Exception:
            workers_n = 3

        results_lock = asyncio.Lock()
        retries: dict[str, int] = {}
        max_retries = 3

        async def worker(_: int) -> None:
            while True:
                phone10 = await q.get()
                try:
                    if self._cancel_requested:
                        self.set_row_result(phone10, "Отменено")
                        self.set_row_progress(phone10, 0, "Отменено")
                        continue

                    self.set_row_result(phone10, "Запуск…")
                    self.set_row_progress(phone10, 0, "Старт")

                    result = await self.mw.run_one_account_for_queue(phone10, ScenarioMode.QRCODE, self)

                    if self._cancel_requested:
                        self.set_row_result(phone10, "Отменено")
                        self.set_row_progress(phone10, 0, "Отменено")
                        continue

                    ok = (result.get("ok") is True)
                    requeue = (result.get("requeue") is True)
                    msg = (result.get("msg") or "Ошибка").strip()

                    if ok:
                        payload = result.get("data")

                        # ✅ если сценарий вернул данные, но товаров нет
                        if payload and not payload.pvz_list:
                            self.set_row_result(phone10, "Внимание")
                            self.set_row_progress(phone10, 100, "Товаров нет")
                            continue

                        # ✅ обычный успех: есть товары → сохраняем
                        if payload:
                            async with results_lock:
                                self._all_results.append(payload)

                        self.set_row_result(phone10, "QR получен")
                        self.set_row_progress(phone10, 100, "Готово")
                        continue

                    if requeue:
                        tries = retries.get(phone10, 0) + 1
                        retries[phone10] = tries

                        if tries >= max_retries:
                            self.set_row_result(phone10, "Ошибка")
                            self.set_row_progress(phone10, 0, f"IP не сменился (лимит {max_retries}). {msg}")
                            continue

                        self.set_row_result(phone10, "В очереди")
                        self.set_row_progress(phone10, 0, f"IP не сменился → повтор {tries}/{max_retries}. {msg}")
                        await q.put(phone10)
                        continue

                    self.set_row_result(phone10, "Ошибка")
                    self.set_row_progress(phone10, 0, msg)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.set_row_result(phone10, "Ошибка")
                    self.set_row_progress(phone10, 0, f"{type(e).__name__}: {e}")
                finally:
                    q.task_done()

        self._workers = [asyncio.create_task(worker(i)) for i in range(workers_n)]
        try:
            await q.join()
        finally:
            for w in self._workers:
                w.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)

        if self._cancel_requested:
            reset_btn()
            return

        try:
            export_dir = Path(self._export_dir)
            export_dir.mkdir(parents=True, exist_ok=True)

            temp_dir = export_dir / f"qr_temp_{asyncio.get_running_loop().time():.0f}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            xlsx_path = temp_dir / "qr_export.xlsx"
            save_mass_results_to_excel(str(xlsx_path), self._all_results)

            make_zip(temp_dir, export_dir)

        except Exception as e:
            if self._rows:
                phone10 = getattr(self._rows[0], "phone10", "") or ""
                self.set_row_progress(phone10, 0, f"ZIP: {type(e).__name__}: {e}")
            reset_btn()
            return

        finish_ok()

    # ---------- Close blocking while running ----------
    def closeEvent(self, event) -> None:
        # нельзя закрыть крестиком пока идёт выполнение
        if self._running:
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        # нельзя закрыть Esc / reject пока идёт выполнение
        if self._running:
            return
        super().reject()

    # ---------- Directory picker ----------
    def _ask_export_directory(self) -> str | None:
        """Открывает диалог выбора папки и возвращает путь."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для сохранения QR",
            "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        return dir_path or None

    async def _export_partial_results(self, *, suffix: str = "partial") -> None:
        """Сохраняет XLSX и ZIP из уже собранных результатов (self._all_results)."""
        if not self._export_dir:
            return
        if not self._all_results:
            return  # нечего сохранять

        export_dir = Path(self._export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        # уникальная папка, чтобы не затирать
        temp_dir = export_dir / f"qr_{suffix}_{asyncio.get_running_loop().time():.0f}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        xlsx_path = temp_dir / "qr_export.xlsx"
        save_mass_results_to_excel(str(xlsx_path), self._all_results)

        make_zip(temp_dir, export_dir)
