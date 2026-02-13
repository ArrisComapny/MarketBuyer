from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QWidget
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton

from gui.style import AppStyle

from domain.dtos import SelectedCounts, RowItems
from domain.enums import ScenarioMode, AccountStatus


class AllActivationDialog(QDialog):
    """Диалог массового запуска активации аккаунтов."""

    def __init__(self, parent: "MainWindow", counts: SelectedCounts) -> None:
        super().__init__(parent)

        self.mw = parent

        self._running = False
        self._completed = False
        self._rows: list[RowItems] = []
        self._row_by_phone: dict[str, int] = {}

        self._mass_task: asyncio.Task | None = None
        self._mass_cancel: bool = False

        self.setWindowTitle("Массовая активация аккаунтов")
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

        self.cb_login = QCheckBox(f"Авторизовать аккаунты\nсо статусом {AccountStatus.LOGIN}")
        self.cb_login.setChecked(False)
        self.cb_login.setStyleSheet("padding-left: 12px;")
        left.addWidget(self.cb_login)
        left.addStretch()

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.verticalHeader().setDefaultSectionSize(23)
        self.table.setHorizontalHeaderLabels(["Телефон", "Статус", "%", "Выполнение", "Шаг"])

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
        self.table.setColumnWidth(3, 85)

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

    def set_selected_accounts(self, rows: list[RowItems]) -> None:
        """Заполняет таблицу выбранными аккаунтами для массового запуска."""
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
            it_exec = QTableWidgetItem("")
            it_step = QTableWidgetItem("")

            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            it_percent.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(r, 0, it_phone)
            self.table.setItem(r, 1, it_status)
            self.table.setItem(r, 2, it_percent)
            self.table.setItem(r, 3, it_exec)
            self.table.setItem(r, 4, it_step)

    def set_row_progress(self, phone10: str, percent: int | None, step: str = "") -> None:
        """Обновляет процент выполнения и текущий шаг для строки аккаунта."""
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return

        if percent is not None:
            self.table.item(r, 2).setText(f"{max(0, min(100, int(percent)))}%")
        if step:
            self.table.item(r, 4).setText(step)

    def set_row_exec(self, phone10: str, text: str) -> None:
        """Обновляет колонку 'Выполнение' для указанного аккаунта."""
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return
        self.table.item(r, 3).setText(text)

    def on_start_clicked(self) -> None:
        """Обрабатывает нажатие кнопки 'Запустить/Отмена/Готово'."""
        if self._completed:
            self.accept()
            return

        if not self._running:
            self._running = True
            self.btn_start.setText("Отмена")
            self._start_mass()
        else:
            self._running = False
            self.btn_start.setText("Запустить")
            self._cancel_mass()

    def _on_mass_finished(self) -> None:
        """Вызывается после завершения массового запуска."""
        self._running = False
        self._completed = True
        self.btn_start.setText("Готово")

    def _start_mass(self) -> None:
        """Запускает асинхронную очередь массовой обработки аккаунтов."""
        if self._mass_task and not self._mass_task.done():
            return
        self._mass_cancel = False
        self._mass_task = asyncio.create_task(self.run_selected_accounts_queue(self._rows))

    def _cancel_mass(self) -> None:
        """Останавливает массовый запуск и отменяет активные задачи."""
        self._mass_cancel = True
        if self._mass_task and not self._mass_task.done():
            self._mass_task.cancel()
        asyncio.create_task(self._stop_all_mass_running())

    async def run_selected_accounts_queue(self, rows: list[RowItems]) -> None:
        """Формирует очередь аккаунтов и запускает их выполнение с учетом параллельности и доступных прокси."""
        if not rows:
            return

        relogin_login = bool(self.cb_login.isChecked())
        q: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        for item in rows:
            if self.mw.closing:
                break

            phone10 = item.phone10
            status = item.status

            if status == AccountStatus.LOGIN and not relogin_login:
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "skip"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(
                    p, 0, f"Пропуск: {AccountStatus.LOGIN} (галочка выкл.)"
                ))
                continue

            if status == AccountStatus.LOGIN and relogin_login:
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Удаляем кэш…"))
                try:
                    await self.mw.delete_account_cache_async(phone10)
                except Exception as e:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "error"))
                    QTimer.singleShot(0, lambda p=phone10, ee=str(e): self.set_row_progress(
                        p, 0, f"Ошибка удаления кэша: {ee}"
                    ))
                    continue

                mode = ScenarioMode.LOGIN
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
                await q.put((phone10, mode))
                continue

            mode = self.mw.status_to_mode(status)
            if not mode:
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "unknown"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(
                    p, 0, "Пропуск: неизвестный статус"
                ))
                continue

            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
            await q.put((phone10, mode))

        if q.empty():
            return

        max_parallel = 10
        capacity = await self.mw.proxy_pool.capacity()
        workers_n = min(max_parallel, capacity)

        if workers_n <= 0:
            QTimer.singleShot(0, lambda: self.setWindowTitle("Нет доступных прокси"))
            self._running = False
            self.btn_start.setText("Запустить")
            return

        workers = [asyncio.create_task(self._mass_worker(q)) for _ in range(workers_n)]

        try:
            try:
                await q.join()
            except asyncio.CancelledError:
                pass
        finally:
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            if not self.mw.closing:
                await self.mw.load_accounts()

            QTimer.singleShot(0, self._on_mass_finished)

    async def _mass_worker(self, q: asyncio.Queue[tuple[str, str]]) -> None:
        """Worker-обработчик очереди: выполняет сценарий для одного аккаунта."""
        retries: dict[tuple[str, str], int] = {}

        while True:
            phone10, mode = await q.get()
            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Выполняется"))
            try:
                if self.mw.closing or self._mass_cancel:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Отменено"))
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Отмена"))
                    continue

                result = await self.mw.run_one_account_for_queue(phone10, mode, self)
                ok = bool(result.get("ok"))
                requeue = bool(result.get("requeue"))
                msg = (result.get("msg") or "").strip()

                if ok:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Готово"))
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(
                        p, 100, "Сценарий выполнен"
                    ))
                    continue

                if requeue:
                    key = (phone10, mode)
                    tries = retries.get(key, 0) + 1
                    retries[key] = tries

                    if tries >= 3:
                        QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
                        QTimer.singleShot(0, lambda p=phone10, m=(
                                msg or "Не удалось сменить IP (лимит попыток)"
                        ): self.set_row_progress( p, 0, f"Ошибка: {m}"))
                        continue

                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
                    QTimer.singleShot(0, lambda p=phone10, t=tries, m=msg: self.set_row_progress(
                        p, 0, f"IP не сменился → в конец очереди (попытка {t}/3). {m}"
                    ))
                    await q.put((phone10, mode))
                    continue

                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
                if msg:
                    QTimer.singleShot(0, lambda p=phone10, m=msg: self.set_row_progress(
                        p, 0, f"Ошибка: {m}"
                    ))

            except Exception as e:
                QTimer.singleShot(0, lambda p=phone10, ee=str(e): self.set_row_progress(
                    p, 0, f"Worker error: {ee}"
                ))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
            finally:
                q.task_done()

    async def _stop_all_mass_running(self) -> None:
        """Принудительно останавливает все запущенные браузеры, отменяет задачи и освобождает прокси."""
        for phone10, controller in list(self.mw.browser_controllers.items()):
            try:
                await controller.close()
            except Exception:
                pass
            QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Отменено"))
            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "cancel"))

        for phone10, task in list(self.mw.browser_tasks.items()):
            try:
                if task and not task.done():
                    task.cancel()
            except Exception:
                pass

        for phone10, proxy_id in list(self.mw.account_proxy.items()):
            try:
                await self.mw.proxy_pool.release(proxy_id)
            except Exception:
                pass

        self.mw.browser_tasks.clear()
        self.mw.browser_controllers.clear()
        self.mw.account_proxy.clear()
        self.mw.running_ui.clear()
