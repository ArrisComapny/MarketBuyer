import os
import stat
import shutil
import asyncio

import core.app as app_core

from collections import Counter
from types import TracebackType
from typing import Callable, Type

from qasync import asyncSlot
from PySide6.QtGui import QAction
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMenu, QCheckBox, QTabWidget

from config import PROFILE_DIR

from core.proxy_pool import ProxyPool
from core.browser import BrowserController

from domain.dtos import SelectedCounts
from domain.enums import ScenarioMode, AccountStatus

from gui.style import AppStyle
from gui.dialogs.open_qr import OpenQrDialog
from gui.widgets.account_row_actions import AccountRowActions
from gui.widgets.filter_panel import FilterPanel
from gui.widgets.accounts_table import AccountsTable
from gui.dialogs.all_activation import AllActivationDialog
from gui.dialogs.import_menu_bar import ImportMenuBarDialog
from gui.dialogs.setting_menu_bar import ProxyManagerDialog
from gui.dialogs.add_personal_account import AddAccountDialog

from utils.phone import format_phone_ru
from utils.messagebox import CustomMessageBox

from database.repositories import AccountRepo, UsersAccountsRepo

from core.permissions import Perm, calc_user_permissions


class MainWindow(QMainWindow):
    def __init__(self, user) -> None:
        """Главное окно приложения."""
        super().__init__()
        self.setWindowIcon(AppStyle.icon("app"))
        self.user = user

        #  Права пользователя (deny-list в JSONB)
        self.perms = calc_user_permissions(
            self.user.role,
            self.user.permissions
        )

        self.setWindowTitle(f"MarketBuyer – {user.login}")
        self.resize(1300, 700)
        self.create_menu_bar()

        # ---------------- State ----------------
        self.closing = False
        self.browser_tasks: dict[str, asyncio.Task] = {}
        self.browser_controllers: dict[str, BrowserController] = {}
        self.account_proxy: dict[str, int] = {}
        self.running_ui: dict[str, tuple[int | None, str]] = {}

        # ================= Массовый запуск =================
        self.proxy_pool = ProxyPool()
        self._more_menu = None

        # Debounce reload
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.timeout.connect(self.load_accounts)

        # ---------------- UI ----------------
        tabs = QTabWidget(self)
        self.setCentralWidget(tabs)

        # ============ TAB 1 (твой текущий интерфейс) ============
        tab_accounts = QWidget()
        tabs.addTab(tab_accounts, "Аккаунты")  # название вкладки

        main_layout = QVBoxLayout(tab_accounts)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        self.filter = FilterPanel(self)
        self.filter.changed.connect(self.apply_filters)

        self.btn_add = QPushButton("Добавить ЛК")
        self.btn_activate = QPushButton("Массовая активация")
        self.btn_qr = QPushButton("Получить QR")
        self.btn_delete_selected = QPushButton("Удалить выбранные")

        self.btn_delete_selected.setMinimumHeight(35)
        self.btn_qr.setMinimumHeight(35)

        self.btn_add.clicked.connect(self.add_personal_account)
        self.btn_activate.clicked.connect(self.open_all_activation)
        self.btn_qr.clicked.connect(self.open_qr_dialog)
        self.btn_delete_selected.clicked.connect(self.delete_selected_accounts)

        # # ============ TAB 2 (второе пространство) ============
        tab_second = QWidget()
        tabs.addTab(tab_second, "Нагул")

        second_layout = QVBoxLayout(tab_second)
        second_layout.setContentsMargins(10, 10, 10, 10)
        second_layout.setSpacing(8)

        for b in (self.btn_add, self.btn_activate):
            b.setMinimumHeight(35)

        # ✅ Запрет "Удалить выбранные" (скрываем кнопку)
        # if Perm.DELETE_SELECTED not in self.perms:
        #     self.btn_delete_selected.hide()

        top_row.addWidget(self.filter)
        top_row.addStretch()
        top_row.addWidget(self.btn_add)
        top_row.addWidget(self.btn_activate)
        top_row.addWidget(self.btn_qr)
        top_row.addWidget(self.btn_delete_selected)
        main_layout.addLayout(top_row)

        self.table = AccountsTable(self)
        main_layout.addWidget(self.table, stretch=1)

        # ---------------- Signals from table ----------------
        self.table.runClicked.connect(self.on_run_clicked_phone)
        self.table.cancelClicked.connect(self.on_cancel_clicked_phone)
        self.table.settingsClicked.connect(self.on_settings_clicked_phone)
        self.table.deleteClicked.connect(self.on_delete_clicked_phone)
        self.table.moreClicked.connect(self.on_more_clicked_phone)
        self.table.commentChanged.connect(self.on_comment_changed)

        # ---------------- Styles ----------------
        self.style_run_btn = AppStyle.qss_run_btn()
        self.style_run_btn_loading = AppStyle.qss_run_btn_disabled()

        QTimer.singleShot(0, self.load_accounts)

    @staticmethod
    def _mode_to_loading_text(mode: ScenarioMode) -> str:
        """Возвращает текст кнопки для состояния загрузки в зависимости от режима запуска сценария."""
        return {
            ScenarioMode.ACTIVATE: "Активируется…",
            ScenarioMode.START: "Запускается…",
            ScenarioMode.LOGIN: "Входит…",
        }.get(mode, "Запускается…")

    @staticmethod
    def status_to_mode(status: AccountStatus) -> ScenarioMode | None:
        """Преобразует статус аккаунта из таблицы в режим запуска сценария."""
        return {
            AccountStatus.DISABLE: ScenarioMode.ACTIVATE,
            AccountStatus.LOGIN: ScenarioMode.START,
            AccountStatus.LOGOUT: ScenarioMode.LOGIN,
        }.get(status)

    @staticmethod
    def _status_to_run_text(status: AccountStatus) -> str:
        """Возвращает базовый текст кнопки "Запуск" в зависимости от текущего статуса аккаунта."""
        return {
            AccountStatus.DISABLE: "Активировать",
            AccountStatus.LOGIN: "Запуск",
            AccountStatus.LOGOUT: "Вход",
        }.get(status, "Запуск")

    def _find_row_by_phone10(self, phone10: str) -> int:
        """Находит индекс строки в таблице по phone10."""
        for r in range(self.table.rowCount()):
            phone_item = self.table.item(r, 1)
            if phone_item and phone_item.data(Qt.ItemDataRole.UserRole) == phone10:
                return r
        return -1

    def _set_row_loading(self, phone10: str, loading: bool, loading_text: str | None = None) -> None:
        """Устанавливает состояние кнопки запуска в строке аккаунта."""
        row = self._find_row_by_phone10(phone10)
        if row < 0:
            return

        actions = self.table.cellWidget(row, 4)

        if not isinstance(actions, AccountRowActions):
            return

        if loading:
            actions.set_run_loading(True, loading_text or "Запускается…", self.style_run_btn_loading)
            return

        status_item = self.table.item(row, 2)
        st = AccountStatus.from_text(status_item.text())
        actions.set_run_loading(False, self._status_to_run_text(st), self.style_run_btn)

    def _schedule_reload(self, ms: int = 300) -> None:
        """Планирует отложенное обновление таблицы аккаунтов, чтобы избежать частых перерисовок UI."""
        if self.closing:
            return
        self._reload_timer.start(ms)

    @asyncSlot()
    async def load_accounts(self) -> None:
        """Загружает список аккаунтов из БД и обновляет таблицу."""
        async with app_core.db.get_session() as session:
            rows = await AccountRepo.get_list_accounts(
                session,
                user_login=self.user.login,
                is_admin=(self.user.role == "admin")
            )

        running_ui_text: dict[str, str] = {}
        for phone10, task in self.browser_tasks.items():
            if not task or task.done():
                continue
            ui = self.running_ui.get(phone10)
            if not ui:
                running_ui_text[phone10] = "Запускается…"
                continue

            percent, text = ui
            if text == "BROWSER_STARTED":
                running_ui_text[phone10] = "Запущено"
            else:
                running_ui_text[phone10] = f"{percent}% • {text}" if percent is not None else text

        self.table.fill(rows, running_ui_text)
        self.apply_filters()

    def apply_filters(self) -> None:
        """Применяет фильтры по статусу и текстовому поиску к строкам таблицы аккаунтов."""
        allowed = self.filter.allowed_statuses()
        status_show_all = (len(allowed) == 0)

        text = self.filter.search_text()
        digits = self.filter.search_digits()

        for row in range(self.table.rowCount()):
            st_item = self.table.item(row, 2)
            st = AccountStatus.from_text(st_item.text())
            status_ok = status_show_all or (st in allowed)

            if not text:
                search_ok = True
            else:
                phone_item = self.table.item(row, 1)
                comment_item = self.table.item(row, 3)

                phone = phone_item.text().lower()
                comment = comment_item.text().lower()

                phone_digits = "".join(ch for ch in phone if ch.isdigit())
                match_phone = (text in phone) or (digits and digits in phone_digits)
                match_comment = text in comment
                search_ok = match_phone or match_comment

            self.table.setRowHidden(row, not (status_ok and search_ok))
            self.table._on_row_checkbox_changed()

    def on_comment_changed(self, phone10: str, comment: str) -> None:
        """Сохраняет изменённый комментарий аккаунта в БД."""
        asyncio.create_task(self._save_comment_async(phone10, comment))

    def on_run_clicked_phone(self, phone10: str) -> None:
        """Обрабатывает нажатие кнопки запуска сценария в строке аккаунта."""
        row = self._find_row_by_phone10(phone10)
        if row < 0:
            return

        status_item = self.table.item(row, 2)
        status = AccountStatus.from_text(status_item.text())
        mode = self.status_to_mode(status)

        self._set_row_loading(phone10, True, self._mode_to_loading_text(mode))
        asyncio.create_task(self.run_account_with_proxy(phone10, mode=mode))

    def on_cancel_clicked_phone(self, phone10: str) -> None:
        """Отмена запущенного сценария: закрываем браузер и отменяем task."""
        task = self.browser_tasks.get(phone10)
        controller = self.browser_controllers.get(phone10)

        async def _stop():
            if controller:
                try:
                    await controller.close()
                except Exception:
                    pass

            if task and not task.done():
                task.cancel()

            proxy_id = self.account_proxy.pop(phone10, None)
            if proxy_id is not None:
                await self.proxy_pool.release(proxy_id)

            if phone10 in self.browser_tasks:
                self.browser_tasks.pop(phone10)

            self.browser_controllers.pop(phone10, None)
            self.running_ui.pop(phone10, None)

            self._set_row_loading(phone10, False)
            self._schedule_reload(100)

        asyncio.create_task(_stop())

    def on_settings_clicked_phone(self, phone10: str) -> None:
        """Открывает окно редактирования аккаунта."""
        asyncio.create_task(self._open_account_editor(phone10))

    def on_delete_clicked_phone(self, phone10: str) -> None:
        if Perm.DELETE_ACCOUNT not in self.perms:
            return self._deny()
        """Запрашивает подтверждение и удаляет аккаунт из БД."""
        reply = CustomMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранный аккаунт? Аккаунт будет удален из базы данных без возможности восстановления",
            CustomMessageBox.StandardButton.Yes | CustomMessageBox.StandardButton.No,
            CustomMessageBox.StandardButton.No
        )
        if reply == CustomMessageBox.StandardButton.Yes:
            asyncio.create_task(self.delete_account_async(phone10))

    def on_more_clicked_phone(self, phone10: str) -> None:
        """Открывает контекстное меню дополнительных действий для аккаунта."""
        row = self._find_row_by_phone10(phone10)
        if row < 0:
            return

        actions = self.table.cellWidget(row, 4)
        if isinstance(actions, AccountRowActions):
            self.show_more_settings_menu(actions.btn_more, phone10)

    def add_personal_account(self) -> None:
        """Открывает диалог добавления нового аккаунта. После сохранения аккаунта обновляет таблицу."""
        dlg = AddAccountDialog(self)
        dlg.account_saved.connect(self.load_accounts)
        dlg.exec()

    def open_all_activation(self) -> None:
        counts = self._selected_status_counts()
        dlg = AllActivationDialog(self, counts)

        rows = self.table.selected_accounts_rows()
        dlg.set_selected_accounts(rows)
        dlg.open()

    def _deny(self) -> None:
        CustomMessageBox.warning(self, "Доступ запрещён", "Недостаточно прав.")

    def delete_selected_accounts(self) -> None:
        if Perm.DELETE_SELECTED not in self.perms:
            return self._deny()
        rows = self.table.selected_accounts_rows()
        if not rows:
            CustomMessageBox.information(self, "Удаление", "Не выбрано ни одного аккаунта.")
            return

        phones = [r.phone10 for r in rows]
        n = len(phones)

        reply = CustomMessageBox.question(
            self,
            "Удаление",
            f"Удалить выбранные аккаунты: {n} шт?\n"
            f"Аккаунты будут удалены из базы данных без возможности восстановления.",
            CustomMessageBox.StandardButton.Yes | CustomMessageBox.StandardButton.No,
            CustomMessageBox.StandardButton.No
        )
        if reply != CustomMessageBox.StandardButton.Yes:
            return

        asyncio.create_task(self._delete_selected_async(phones))

    def open_qr_dialog(self):
        rows = self.table.selected_accounts_rows()
        if not rows:
            CustomMessageBox.information(self, "QR", "Не выбрано ни одного аккаунта.")
            return

        counts = self._selected_status_counts()
        dlg = OpenQrDialog(parent=self, counts=counts)
        dlg.set_selected_accounts(rows)
        dlg.open()

    async def _delete_selected_async(self, phones: list[str]) -> None:
        try:
            async with app_core.db.get_session() as session:
                await AccountRepo.delete_selected_accounts(session, phones)

        except Exception as e:
            CustomMessageBox.critical(self, "Ошибка", f"Не удалось удалить аккаунты:\n{e}")
            return

        await self.load_accounts()

    async def _save_comment_async(self, phone10: str, comment: str) -> None:
        """Асинхронно сохраняет комментарий аккаунта в БД. Вызывается при изменении ячейки комментария в таблице."""
        try:
            async with app_core.db.get_session() as session:
                await AccountRepo.set_comment(session, phone10, comment)
        except Exception as e:
            self._show_warning("Комментарий", f"Не удалось сохранить комментарий:\n{e}")

    async def _open_account_editor(self, phone10: str) -> None:
        """ Открывает диалог редактирования аккаунта. На время открытия блокирует таблицу аккаунтов."""
        self.table.setDisabled(True)
        try:
            account_data = await self._get_account_by_phone(phone10)
            if not account_data:
                CustomMessageBox.warning(self, "Ошибка", "Аккаунт не найден в БД.")
                return

            dlg = AddAccountDialog(self, account=account_data)
            dlg.account_saved.connect(self.load_accounts)
            dlg.setWindowModality(Qt.WindowModality.ApplicationModal)

            dlg.open()
        finally:
            self.table.setDisabled(False)


    def open_settings(self) -> None:
        """Открывает окно управления прокси."""
        dlg = ProxyManagerDialog(self, proxy_pool=self.proxy_pool)
        dlg.exec()

    async def delete_account_async(self, phone10: str) -> None:
        """Удаляет аккаунт из базы данных пользователя. После удаления обновляет таблицу аккаунтов. """
        try:
            await self.delete_account_cache_async(phone10)
            async with app_core.db.get_session() as session:
                await AccountRepo.delete_account_by_phone(session, phone10)
        except Exception as e:
            CustomMessageBox.critical(self, "Ошибка", f"Не удалось удалить аккаунт:\n{e}")
        finally:
            await self.load_accounts()

    def show_more_settings_menu(self, btn_more: QPushButton, phone10: str) -> None:
        """Показывает контекстное меню действий аккаунта."""
        self._more_menu = QMenu(btn_more)

        act_relogin = QAction("Авторизовать заново", self._more_menu)
        act_delete_cache = QAction("Удалить с компьютера", self._more_menu)

        def _do_relogin():
            async def _flow():
                await self.delete_account_cache_async(phone10)
                self._set_row_loading(phone10, True, "Входит…")
                await self.run_account_with_proxy(phone10, mode=ScenarioMode.LOGIN)

            asyncio.create_task(_flow())

        act_relogin.triggered.connect(_do_relogin)
        act_delete_cache.triggered.connect(lambda: asyncio.create_task(self.delete_account_cache_async(phone10)))

        self._more_menu.addAction(act_relogin)
        self._more_menu.addSeparator()
        self._more_menu.addAction(act_delete_cache)

        self._more_menu.exec(btn_more.mapToGlobal(btn_more.rect().bottomLeft()))

    async def run_account_with_proxy(self, phone10: str, mode: ScenarioMode) -> None:
        """Запускает браузерный сценарий для аккаунта с выделением прокси и контролем жизненного цикла."""
        old_task = self.browser_tasks.get(phone10)
        if old_task and not old_task.done():
            self._show_warning("Запуск", f"Аккаунт {phone10} уже запущен")
            ui = self.running_ui.get(phone10)
            loading_text = f"{ui[0]}% • {ui[1]}" if ui and ui[0] is not None else (ui[1] if ui else "Запускается…")
            self._set_row_loading(phone10, True, loading_text)
            return

        account = await self._get_account_by_phone(phone10)
        if not account:
            self.running_ui.pop(phone10, None)
            self._set_row_loading(phone10, False)
            self._show_warning("Ошибка", "Аккаунт не найден в БД.")
            return

        ua = account.get("user_agent", "")

        proxy, msg = await self.proxy_pool.acquire(
            user_login=self.user.login,
            is_admin=(self.user.role == "admin"),
        )
        if not proxy:
            if not self.closing:
                self._show_warning("Прокси", msg)

            self.running_ui.pop(phone10, None)
            self._set_row_loading(phone10, False)
            return

        self.account_proxy[phone10] = proxy.id

        def _on_progress(p: int, t: str) -> None:
            QTimer.singleShot(0, lambda: self._update_progress_ui(phone10, p, t))

        controller = BrowserController(
            profile_name=phone10,
            user_agent=ua,
            proxy=proxy,
            user=self.user,
            on_progress=_on_progress
        )
        controller.account = account
        self.browser_controllers[phone10] = controller

        task = asyncio.create_task(controller.run(mode=mode))
        self.browser_tasks[phone10] = task

        self.running_ui[phone10] = (None, self._mode_to_loading_text(mode))

        def _cleanup(t: asyncio.Task) -> None:
            """Callback, вызываемый после завершения браузерного сценария."""
            async def _async_cleanup() -> None:
                err_text: str | None = None
                try:
                    t.result()
                except Exception as e:
                    err_text = str(e)

                proxy_id = self.account_proxy.pop(phone10, None)
                if proxy_id is not None:
                    await self.proxy_pool.release(proxy_id)

                if phone10 in self.browser_tasks:
                    del self.browser_tasks[phone10]

                self.browser_controllers.pop(phone10, None)
                self.running_ui.pop(phone10, None)

                self._set_row_loading(phone10, False)

                if err_text and not self.closing:
                    self._show_warning("Сценарий", f"Ошибка для {phone10}:\n{err_text}")

                self._schedule_reload(250)

            asyncio.create_task(_async_cleanup())

        task.add_done_callback(_cleanup)

    def _show_warning(self, title: str, text: str) -> None:
        """Показывает предупреждающее сообщение пользователю из безопасного Qt-контекста."""
        QTimer.singleShot(0, lambda: CustomMessageBox.warning(self, title, text))

    @staticmethod
    async def _get_account_by_phone(phone10: str) -> dict | None:
        """Загружает данные аккаунта из БД по phone10."""
        async with app_core.db.get_session() as session:
            data = await AccountRepo.get_account_dict(session, phone10)

        if not data:
            return None

        data["phone_view"] = format_phone_ru(data["phone10"])
        return data

    @staticmethod
    def _rm_readonly(func: Callable[[str], None],
                     path: str,
                     _: tuple[Type[BaseException], BaseException, TracebackType]) -> None:
        """Снимает флаг read-only с файла или директории и повторно вызывает функцию удаления."""
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            func(path)
        except OSError:
            pass

    async def delete_account_cache_async(self, phone10: str) -> None:
        phone10 = str(phone10).strip()
        profile_path = PROFILE_DIR / phone10

        async with app_core.db.get_session() as session:
            await AccountRepo.set_status(session, phone10, AccountStatus.LOGOUT)

        def _rm_folder():
            if profile_path.exists():
                shutil.rmtree(profile_path, onerror=self._rm_readonly)

        await asyncio.to_thread(_rm_folder)

        await self.load_accounts()

        def _rm_folder():
            """Callback для shutil.rmtree, снимающий флаг read-only с файлов перед удалением."""
            if profile_path.exists():
                shutil.rmtree(profile_path, onerror=self._rm_readonly)

        await asyncio.to_thread(_rm_folder)

        await self.load_accounts()

    def create_menu_bar(self) -> None:
        """Создаёт и настраивает верхнее меню приложения."""
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Файл")
        settings_menu = menu_bar.addMenu("Настройки")
        help_menu = menu_bar.addMenu("Справка")

        self.menuBar().setStyleSheet(AppStyle.qss_menu_bar())

        open_action = QAction("Открыть", self)
        save_action = QAction("Сохранить", self)
        import_action = QAction("Импортировать", self)
        exit_action = QAction("Выход", self)

        settings_action = QAction("ProxyManager", self)
        about_action = QAction("О программе", self)

        exit_action.triggered.connect(self.close)
        settings_action.triggered.connect(self.open_settings)
        import_action.triggered.connect(self.open_import_excel)  # ✅ ВАЖНО

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(import_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        settings_menu.addAction(settings_action)
        help_menu.addAction(about_action)

    def open_import_excel(self) -> None:
        """открытие диалогового окна импортирования."""
        dlg = ImportMenuBarDialog(self)
        dlg.exec()

    def _update_progress_ui(self, phone10: str, percent: int, text: str) -> None:
        """Обновление информации о прогрессе сценария."""
        percent = max(0, min(100, int(percent)))

        self.running_ui[phone10] = (percent, text)

        if text == "BROWSER_STARTED":
            self._set_row_loading(phone10, True, "Запущено")
            return

        if text:
            self._set_row_loading(phone10, True, f"{percent}%")
        else:
            self._set_row_loading(phone10, True, f"{percent}%")

    def _selected_status_counts(self) -> SelectedCounts:
        """Получение количества аккаунтов разных статусов"""
        counts = Counter()

        total_all = self.table.rowCount()

        for row in range(total_all):
            w = self.table.cellWidget(row, 0)
            cb = w.findChild(QCheckBox)
            if not cb.isChecked():
                continue

            st_item = self.table.item(row, 2)
            st = st_item.text()
            counts[st] += 1

        total_selected = sum(counts.values())

        return SelectedCounts(
            disable=counts.get(AccountStatus.DISABLE, 0),
            login=counts.get(AccountStatus.LOGIN, 0),
            logout=counts.get(AccountStatus.LOGOUT, 0),
            total_selected=total_selected,
            total_all=total_all
        )

    async def run_one_account_for_queue(self, phone10: str, mode: ScenarioMode, dlg) -> dict:
        """Запуск выполнения сценария для одного аккаунта."""
        proxy_id: int | None = None
        controller = None

        try:
            account = await self._get_account_by_phone(phone10)
            if not account:
                QTimer.singleShot(0, lambda: dlg.set_row_progress(phone10, 0, "Аккаунт не найден в БД"))
                QTimer.singleShot(0, lambda: self._set_row_loading(phone10, False))
                return {"ok": False, "requeue": False, "msg": "Аккаунт не найден"}

            ua = account.get("user_agent", "")

            QTimer.singleShot(0, lambda: self._set_row_loading(phone10, True, "Запуск…"))

            proxy, msg = await self.proxy_pool.acquire_mass(
                user_login=self.user.login,
                is_admin=(self.user.role == "admin"),
                rotate_total_wait_sec=130,
                rotate_interval_sec=20,
                rotate_wait_after_ok_sec=10,
                require_rotate=True,
            )

            if not proxy:
                msg = (msg or "").strip()

                low = msg.lower()
                rotate_failed = ("смена ip" in low) or ("не удалось сменить ip" in low) or (
                            "ip" in low and "смен" in low)

                if rotate_failed:
                    QTimer.singleShot(0, lambda: dlg.set_row_progress(phone10, 0, f"Прокси: {msg}"))
                    QTimer.singleShot(0, lambda: self._set_row_loading(phone10, False))
                    return {"ok": False, "requeue": True, "msg": msg}

                QTimer.singleShot(0, lambda: dlg.set_row_progress(phone10, 0, f"Прокси: {msg}"))
                QTimer.singleShot(0, lambda: self._set_row_loading(phone10, False))
                return {"ok": False, "requeue": False, "msg": msg}

            proxy_id = proxy.id
            self.account_proxy[phone10] = proxy_id

            def on_progress(p: int, text: str) -> None:
                QTimer.singleShot(0, lambda: dlg.set_row_progress(phone10, p, text))
                QTimer.singleShot(0, lambda: self._update_progress_ui(phone10, p, text))

            controller = BrowserController(
                profile_name=phone10,
                user_agent=ua,
                proxy=proxy,
                user=self.user,
                on_progress=on_progress
            )
            controller.account = account
            self.browser_controllers[phone10] = controller

            data = await controller.run(mode=mode)
            return {"ok": True, "data": data}

        except Exception as e:
            err = str(e)
            QTimer.singleShot(0, lambda p=phone10, msg=err: dlg.set_row_progress(p, 0, f"Ошибка: {msg}"))
            return {"ok": False, "requeue": False, "msg": err}

        finally:
            try:
                if controller:
                    await controller.close()
            except Exception:
                pass

            try:
                if proxy_id is not None:
                    await self.proxy_pool.release(proxy_id)
            except Exception:
                pass

            self.account_proxy.pop(phone10, None)
            self.browser_controllers.pop(phone10, None)
            self.running_ui.pop(phone10, None)

            QTimer.singleShot(0, lambda: self._set_row_loading(phone10, False))



