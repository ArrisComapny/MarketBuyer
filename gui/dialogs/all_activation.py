from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget,
)
from PySide6.QtCore import Qt, QTimer


class AllActivationDialog(QDialog):
    """
    Диалог массового запуска.
    Внутри живёт очередь, воркеры, отмена, повтор постановки в очередь при rotate-ошибке.

    ВАЖНО:
    - Сам запуск одного аккаунта делается через self._run_one_for_queue(...) (передаём из MainWindow).
    - Все состояния браузеров/тасков/прокси мы чистим здесь, но хранятся они в MainWindow (передаём dict-ы по ссылке).
    """

    def __init__(
        self,
        parent=None,
        counts: dict[str, int] | None = None,
        *,
        proxy_pool,
        status_to_mode: Callable[[str], str | None],
        load_accounts: Callable[[], Awaitable[None]],
        is_closing: Callable[[], bool],
        run_one_for_queue: Callable[[str, str, "AllActivationDialog"], Awaitable[dict]],
        delete_account_cache_async: Callable[[str], Awaitable[None]],

        # ссылки на состояния MainWindow (используются в stop/cleanup)
        browser_controllers: dict,
        browser_tasks: dict,
        account_proxy: dict,
        running_ui: dict,
    ):
        super().__init__(parent)

        # ===== deps =====
        self.proxy_pool = proxy_pool
        self._status_to_mode = status_to_mode
        self._load_accounts = load_accounts
        self._is_closing = is_closing
        self._run_one_for_queue = run_one_for_queue

        self._browser_controllers = browser_controllers
        self._browser_tasks = browser_tasks
        self._account_proxy = account_proxy
        self._running_ui = running_ui

        # ================== DATA ==================
        counts = counts or {}
        total_all = int(counts.get("total_all", 0))
        total_sel = int(counts.get("total_selected", 0))
        disable_n = int(counts.get("disable", 0))
        logout_n = int(counts.get("logout", 0))
        login_n = int(counts.get("login", 0))
        unknown_n = int(counts.get("unknown", 0))

        # ================== STATE ==================
        self._running = False
        self._completed = False
        self._rows: list[dict] = []
        self._row_by_phone: dict[str, int] = {}

        self._mass_task: asyncio.Task | None = None
        self._mass_cancel: bool = False

        # ================== WINDOW ==================
        self.setWindowTitle("Массовая активация аккаунтов")
        self.resize(980, 620)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # ================== ROOT ==================
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # ================== CENTER ==================
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

        self.cb_login = QCheckBox("Авторизовать аккаунты\nсо статусом login")
        self.cb_login.setChecked(False)
        self.cb_login.setStyleSheet("padding-left: 12px;")
        left.addWidget(self.cb_login)
        left.addStretch()
        self._delete_account_cache_async = delete_account_cache_async

        # ---------- RIGHT ----------
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.verticalHeader().setDefaultSectionSize(23)
        self.table.setHorizontalHeaderLabels(["Телефон", "Статус","%", "Выполнение", "Шаг"])

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

        # ================== BOTTOM ==================
        bottom = QHBoxLayout()
        bottom.addStretch()

        self.btn_start = QPushButton("Запустить")
        self.btn_start.setMinimumSize(260, 44)
        self.btn_start.clicked.connect(self.on_start_clicked)

        bottom.addWidget(self.btn_start)
        bottom.addStretch()
        root.addLayout(bottom)

    # ================== UI API ==================
    def set_selected_accounts(self, rows: list[dict]) -> None:
        """
        rows: [{phone10, status, row_index}, ...]
        """
        self._rows = rows[:]  # сохраняем, чтобы потом запускать без сигналов в MainWindow
        self._row_by_phone.clear()
        self.table.setRowCount(len(rows))

        for r, data in enumerate(rows):
            phone = (data.get("phone10") or "").strip()
            status = (data.get("status") or "").strip()

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
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return

        if percent is not None:
            self.table.item(r, 2).setText(f"{max(0, min(100, int(percent)))}%")

        if step:
            self.table.item(r, 4).setText(step)

    def set_row_exec(self, phone10: str, text: str) -> None:
        phone10 = (phone10 or "").strip()
        r = self._row_by_phone.get(phone10)
        if r is None:
            return
        self.table.item(r, 3).setText(text)

    # ================== BUTTON ==================
    def on_start_clicked(self) -> None:
        # если уже всё завершено — просто закрываем окно
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
        """
        Вызывается когда ВСЕ аккаунты закончили выполнение
        """
        self._running = False
        self._completed = True

        self.btn_start.setText("Готово")

    def _start_mass(self) -> None:
        # старт
        if self._mass_task and not self._mass_task.done():
            return

        self._mass_cancel = False
        self._mass_task = asyncio.create_task(self.run_selected_accounts_queue(self._rows))

    def _cancel_mass(self) -> None:
        # отмена
        self._mass_cancel = True

        if self._mass_task and not self._mass_task.done():
            self._mass_task.cancel()

        asyncio.create_task(self._stop_all_mass_running())

    # ================== MASS LOGIC ==================
    async def run_selected_accounts_queue(self, rows: list[dict]) -> None:
        """
        Массовый запуск: параллельность = кол-во прокси (capacity).
        Ошибка в сценарии НЕ сбрасывает очередь.
        """

        if not rows:
            return

        # 0) подготовка (учёт галочки login)
        relogin_login = bool(self.cb_login.isChecked())

        # 1) собираем задания
        q: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        for item in rows:
            if self._is_closing():
                break

            phone10 = (item.get("phone10") or "").strip()
            status = (item.get("status") or "").strip().lower()

            if status == "login" and not relogin_login:
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "skip"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Пропуск: login (галочка выкл.)"))
                continue

                # ✅ login: если галочка включена — чистим кэш, потом в очередь на вход
            if status == "login" and relogin_login:
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Удаляем кэш…"))
                try:
                    await self._delete_account_cache_async(phone10)
                except Exception as e:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "error"))
                    QTimer.singleShot(0, lambda p=phone10, ee=str(e): self.set_row_progress(p, 0,
                                                                                            f"Ошибка удаления кэша: {ee}"))
                    continue

                # после удаления кэша статус становится logout, значит режим = logout-login
                mode = "logout-login"
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
                await q.put((phone10, mode))
                continue

            mode = self._status_to_mode(status)
            if not mode:
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "unknown"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Пропуск: неизвестный статус"))
                continue

            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p,"В очереди"))
            await q.put((phone10, mode))

        if q.empty():
            return

        # 2) параллельность по прокси
        max_parallel = 10  # максимум одновременных аккаунтов
        capacity = await self.proxy_pool.capacity()
        workers_n = min(max_parallel, capacity)

        # 3) воркеры
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

            if not self._is_closing():
                await self._load_accounts()

            QTimer.singleShot(0, self._on_mass_finished)

    async def _mass_worker(self, q: asyncio.Queue[tuple[str, str]]) -> None:
        retries: dict[tuple[str, str], int] = {}

        while True:
            phone10, mode = await q.get()
            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Выполняется"))
            try:
                if self._is_closing() or self._mass_cancel:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Отменено"))
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Отмена"))
                    continue

                result = await self._run_one_for_queue(phone10, mode, self)
                ok = bool(result.get("ok"))
                requeue = bool(result.get("requeue"))
                msg = (result.get("msg") or "").strip()

                if ok:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Готово"))
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 100, "Сценарий Выполнен"))
                    continue

                if requeue:
                    key = (phone10, mode)
                    tries = retries.get(key, 0) + 1
                    retries[key] = tries

                    if tries >= 3:
                        QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
                        QTimer.singleShot(
                            0,
                            lambda p=phone10, m=(msg or "Не удалось сменить IP (лимит попыток)"):
                            self.set_row_progress(p, 0, f"Ошибка: {m}")
                        )
                        continue

                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
                    QTimer.singleShot(
                        0,
                        lambda p=phone10, t=tries, m=msg:
                        self.set_row_progress(p, 0, f"IP не сменился → в конец очереди (попытка {t}/3). {m}")
                    )
                    await q.put((phone10, mode))
                    continue

                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
                if msg:
                    QTimer.singleShot(0, lambda p=phone10, m=msg: self.set_row_progress(p, 0, f"Ошибка: {m}"))

            except Exception as e:
                QTimer.singleShot(0, lambda p=phone10, ee=str(e): self.set_row_progress(p, 0, f"Worker error: {ee}"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
            finally:
                q.task_done()

    async def _stop_all_mass_running(self) -> None:
        # 1) закрываем все браузеры
        for phone10, controller in list(self._browser_controllers.items()):
            try:
                await controller.close()
            except Exception:
                pass

            QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Отменено"))
            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "cancel"))

        # 2) отменяем все browser tasks
        for phone10, task in list(self._browser_tasks.items()):
            try:
                if task and not task.done():
                    task.cancel()
            except Exception:
                pass

        # 3) освобождаем прокси
        for phone10, proxy_id in list(self._account_proxy.items()):
            try:
                await self.proxy_pool.release(proxy_id)
            except Exception:
                pass

        # 4) чистим состояние
        self._browser_tasks.clear()
        self._browser_controllers.clear()
        self._account_proxy.clear()
        self._running_ui.clear()


