from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton
)

from gui.style import AppStyle
from domain.dtos import SelectedCounts, RowItems
from domain.enums import ScenarioMode, AccountStatus

from utils.logger import AppLogger

log = AppLogger.get(__name__)


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

        log.info("[MASS] AllActivationDialog opened")

    def set_selected_accounts(self, rows: list[RowItems]) -> None:
        """Заполняет таблицу выбранными аккаунтами для массового запуска."""
        self._rows = rows[:]
        self._row_by_phone.clear()
        self.table.setRowCount(len(rows))

        log.info(f"[MASS] set_selected_accounts rows={len(rows)}")

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
        log.info(f"[MASS] click start: running={self._running} completed={self._completed}")

        if self._completed:
            log.info("[MASS] dialog close (completed)")
            self.accept()
            return

        if not self._running:
            self._running = True
            self.btn_start.setText("Отмена")
            log.info(f"[MASS] start (rows={len(self._rows)}) relogin_login={self.cb_login.isChecked()}")
            self._start_mass()
        else:
            self._running = False
            self.btn_start.setText("Запустить")
            log.info("[MASS] cancel requested")
            self._cancel_mass()

    def _on_mass_finished(self) -> None:
        """Вызывается после завершения массового запуска."""
        log.info("[MASS] finished")
        self._running = False
        self._completed = True
        self.btn_start.setText("Готово")

    def _start_mass(self) -> None:
        """Запускает асинхронную очередь массовой обработки аккаунтов."""
        if self._mass_task and not self._mass_task.done():
            log.info("[MASS] start ignored: already running")
            return
        self._mass_cancel = False
        log.info("[MASS] task created")
        self._mass_task = asyncio.create_task(self.run_selected_accounts_queue(self._rows))

    def _cancel_mass(self) -> None:
        """Останавливает массовый запуск и отменяет активные задачи."""
        self._mass_cancel = True
        log.info("[MASS] cancel flag set")
        if self._mass_task and not self._mass_task.done():
            self._mass_task.cancel()
            log.info("[MASS] mass_task cancelled")
        asyncio.create_task(self._stop_all_mass_running())

    async def run_selected_accounts_queue(self, rows: list[RowItems]) -> None:
        """Формирует очередь аккаунтов и запускает их выполнение с учетом параллельности и доступных прокси."""
        if not rows:
            log.info("[MASS] no rows -> exit")
            return

        relogin_login = bool(self.cb_login.isChecked())
        q: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        log.info(f"[MASS] build queue: rows={len(rows)} relogin_login={relogin_login}")

        for item in rows:
            if self.mw.closing:
                log.info("[MASS] mainwindow closing -> break building queue")
                break

            phone10 = item.phone10
            status = item.status

            if status == AccountStatus.LOGIN and not relogin_login:
                log.info(f"[MASS][{phone10}] skip LOGIN (checkbox off)")
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "skip"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(
                    p, 0, f"Пропуск: {AccountStatus.LOGIN} (галочка выкл.)"
                ))
                continue

            if status == AccountStatus.LOGIN and relogin_login:
                log.info(f"[MASS][{phone10}] relogin requested -> delete cache")
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Удаляем кэш…"))
                try:
                    await self.mw.delete_account_cache_async(phone10)
                except Exception as e:
                    log.warning(f"[MASS][{phone10}] cache delete error: {e}")
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
                log.info(f"[MASS][{phone10}] skip unknown status={status}")
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "unknown"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(
                    p, 0, "Пропуск: неизвестный статус"
                ))
                continue

            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
            await q.put((phone10, mode))

        log.info(f"[MASS] queue ready: size={q.qsize()}")

        if q.empty():
            log.info("[MASS] queue empty -> exit")
            return

        max_parallel = 10
        capacity = await self.mw.proxy_pool.capacity(
            user_login=self.mw.user.login,
            is_admin=(self.mw.user.role == "admin"),
        )
        workers_n = min(max_parallel, capacity)
        log.info(f"[MASS] capacity={capacity} -> workers_n={workers_n}")

        if workers_n <= 0:
            log.warning("[MASS] no available proxies (workers_n<=0)")
            QTimer.singleShot(0, lambda: self.setWindowTitle("Нет доступных прокси"))
            self._running = False
            self.btn_start.setText("Запустить")
            return

        workers = [asyncio.create_task(self._mass_worker(q)) for _ in range(workers_n)]
        log.info(f"[MASS] workers started: {workers_n}")

        try:
            try:
                await q.join()
            except asyncio.CancelledError:
                log.info("[MASS] queue join cancelled")
                pass
        finally:
            log.info("[MASS] queue done, stopping workers")
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            if not self.mw.closing:
                await self.mw.load_accounts()
                log.info("[MASS] accounts reloaded")

            QTimer.singleShot(0, self._on_mass_finished)

    async def _mass_worker(self, q: asyncio.Queue[tuple[str, str]]) -> None:
        """Worker-обработчик очереди: выполняет сценарий для одного аккаунта."""
        retries: dict[tuple[str, str], int] = {}

        while True:
            phone10, mode = await q.get()
            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Выполняется"))
            log.info(f"[MASS][{phone10}] start mode={mode}")

            try:
                if self.mw.closing or self._mass_cancel:
                    log.info(f"[MASS][{phone10}] cancelled (closing={self.mw.closing} cancel={self._mass_cancel})")
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Отменено"))
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Отмена"))
                    continue

                result = await self.mw.run_one_account_for_queue(phone10, mode, self)
                ok = bool(result.get("ok"))
                requeue = bool(result.get("requeue"))
                msg = (result.get("msg") or "").strip()

                log.info(f"[MASS][{phone10}] result ok={ok} requeue={requeue} msg={msg}")

                if ok:
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Готово"))
                    QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 100, "Сценарий выполнен"))
                    log.info(f"[MASS][{phone10}] done")
                    continue

                if requeue:
                    key = (phone10, mode)
                    tries = retries.get(key, 0) + 1
                    retries[key] = tries

                    if tries >= 3:
                        QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
                        QTimer.singleShot(0, lambda p=phone10, m=(msg or "Не удалось сменить IP (лимит попыток)")
                                          : self.set_row_progress(p, 0, f"Ошибка: {m}"))
                        log.error(f"[MASS][{phone10}] requeue limit reached (3). msg={msg}")
                        continue

                    QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "В очереди"))
                    QTimer.singleShot(0, lambda p=phone10, t=tries, m=msg: self.set_row_progress(
                        p, 0, f"IP не сменился → в конец очереди (попытка {t}/3). {m}"
                    ))
                    log.warning(f"[MASS][{phone10}] requeue try={tries}/3 msg={msg}")
                    await q.put((phone10, mode))
                    continue

                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))
                if msg:
                    QTimer.singleShot(0, lambda p=phone10, m=msg: self.set_row_progress(p, 0, f"Ошибка: {m}"))
                log.error(f"[MASS][{phone10}] error: {msg}")

            except Exception as e:
                log.exception(f"[MASS][{phone10}] worker exception: {e}")
                QTimer.singleShot(0, lambda p=phone10, ee=str(e): self.set_row_progress(p, 0, f"Worker error: {ee}"))
                QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "Ошибка"))

            finally:
                q.task_done()

    async def _stop_all_mass_running(self) -> None:
        """Принудительно останавливает все запущенные браузеры, отменяет задачи и освобождает прокси."""
        log.info("[MASS] stop_all_mass_running begin")

        for phone10, controller in list(self.mw.browser_controllers.items()):
            try:
                await controller.close()
            except Exception:
                pass
            QTimer.singleShot(0, lambda p=phone10: self.set_row_progress(p, 0, "Отменено"))
            QTimer.singleShot(0, lambda p=phone10: self.set_row_exec(p, "cancel"))
            log.info(f"[MASS][{phone10}] controller closed")

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
            log.info(f"[MASS][{phone10}] proxy released")

        self.mw.browser_tasks.clear()
        self.mw.browser_controllers.clear()
        self.mw.account_proxy.clear()
        self.mw.running_ui.clear()

        log.info("[MASS] stop_all_mass_running done")
