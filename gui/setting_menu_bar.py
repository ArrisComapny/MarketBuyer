import re
import asyncio

from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QPushButton, QWidget, QHeaderView
from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QComboBox, QMessageBox, QSizePolicy

import core.app as app_core

from database.models import Proxy
from utils.proxy import proxy_title
from database.repositories import ProxyRepo


class ProxyEditDialog(QDialog):
    def __init__(self, proxy: Proxy | None = None, parent=None) -> None:
        """Диалог добавления или редактирования прокси."""

        super().__init__(parent)

        self.proxy = proxy
        self.setWindowTitle("Добавить прокси" if proxy is None else "Редактировать прокси")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.host_edit = QLineEdit(proxy.host if proxy else "")
        self.port_edit = QLineEdit(proxy.port if proxy else "")
        self.login_edit = QLineEdit(proxy.login if proxy else "")
        self.password_edit = QLineEdit(proxy.password if proxy else "")

        self.scheme_combo = QComboBox()
        self.scheme_combo.addItems(["http", "https", "socks5"])
        if proxy:
            self.scheme_combo.setCurrentText(proxy.proxy_scheme)

        self.change_ip_edit = QLineEdit(proxy.change_ip_url if proxy else "")

        layout.addRow("Host", self.host_edit)
        layout.addRow("Port", self.port_edit)
        layout.addRow("Login", self.login_edit)
        layout.addRow("Password", self.password_edit)
        layout.addRow("Scheme", self.scheme_combo)
        layout.addRow("Change IP URL", self.change_ip_edit)

        btn_save = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")

        btn_save.clicked.connect(self.on_save_clicked)
        btn_cancel.clicked.connect(self.reject)

        btn_save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_cancel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        btn_save.setMinimumHeight(36)
        btn_cancel.setMinimumHeight(36)

        buttons_layout = QVBoxLayout()
        buttons_layout.addWidget(btn_save)
        buttons_layout.addWidget(btn_cancel)

        layout.addRow(buttons_layout)

        self.adjustSize()

    def on_save_clicked(self) -> None:
        """Валидирует введённые данные прокси и закрывает диалог с Accept при успешной проверке."""

        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        login = self.login_edit.text().strip()
        password = self.password_edit.text().strip()
        change_url = self.change_ip_edit.text().strip()

        if not host:
            QMessageBox.warning(self, "Ошибка", "Host обязателен.")
            self.host_edit.setFocus()
            return

        # 🔹 ПРОВЕРКА IP ПО REGEX (IPv4)
        ip_regex = (
            r"^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
            r"(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$"
        )

        if not re.fullmatch(ip_regex, host):
            QMessageBox.warning(
                self,
                "Ошибка",
                "Host должен быть корректным IPv4-адресом (например 192.168.1.1)."
            )
            self.host_edit.setFocus()
            return

        if not port:
            QMessageBox.warning(self, "Ошибка", "Port обязателен.")
            self.port_edit.setFocus()
            return
        elif not port.isdigit() or not (1 <= int(port) <= 65535):
            QMessageBox.warning( self, "Ошибка", "Port должен быть в диапазоне от 0 до 65535.")
            self.port_edit.setFocus()
            return

        if not login:
            QMessageBox.warning(self, "Ошибка", "Login обязателен.")
            self.login_edit.setFocus()
            return

        if not password:
            QMessageBox.warning(self, "Ошибка", "Password обязателен.")
            self.password_edit.setFocus()
            return

        # Пароль без русских букв
        if re.search(r"[А-Яа-яЁё]", password):
            QMessageBox.warning(self, "Ошибка", "Пароль не должен содержать русские буквы.")
            self.password_edit.setFocus()
            return

        if not change_url:
            QMessageBox.warning(self, "Ошибка", "Change IP URL обязателен.")
            self.change_ip_edit.setFocus()
            return
        elif not change_url.startswith("http"):
            QMessageBox.warning(self, "Ошибка", "Change IP URL должен начинаться с http")
            self.change_ip_edit.setFocus()
            return

        self.accept()


class ProxyManagerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        """Окно управления списком прокси."""

        super().__init__(parent)

        self.setWindowTitle("Proxy Manager")
        self.resize(720, 420)

        main_layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Прокси", "Действия"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 120)

        main_layout.addWidget(self.table)

        self.add_button = QPushButton("+ Добавить прокси")
        self.add_button.clicked.connect(self.on_add_proxy)
        self.add_button.setMinimumHeight(40)
        main_layout.addWidget(self.add_button)

        bottom = QHBoxLayout()
        bottom.addStretch()
        main_layout.addLayout(bottom)

        asyncio.create_task(self.load_proxies())

    async def load_proxies(self) -> None:
        """Загружает список прокси из базы данных и обновляет таблицу."""
        try:
            async with app_core.db.get_session() as session:
                proxies = await ProxyRepo.get_proxies(session)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить прокси:\n{e}")
            return

        self.table.setRowCount(0)

        for row, proxy in enumerate(proxies):
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(proxy_title(proxy)))

            style_btn = """
            QPushButton {
                border: none; 
                background-color: transparent; 
            }
            QPushButton:hover {
                background-color: rgba(0, 120, 215, 40);
                border-radius: 4px;
            }
            """

            btn_edit = QPushButton()
            btn_edit.setIcon(QIcon("templates/icons/setting.png"))
            btn_edit.setIconSize(QSize(20, 20))
            btn_edit.setFixedSize(35, 25)
            btn_edit.setStyleSheet(style_btn)

            btn_delete = QPushButton()
            btn_delete.setIcon(QIcon("templates/icons/delete.png"))
            btn_delete.setIconSize(QSize(20, 20))
            btn_delete.setFixedSize(35, 25)
            btn_delete.setStyleSheet(style_btn)

            btn_edit.clicked.connect(lambda _, pid=proxy.id: self.open_edit_dialog(pid))
            btn_delete.clicked.connect(lambda _, pid=proxy.id: self.ask_delete(pid))

            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            h.addWidget(btn_edit)
            h.addWidget(btn_delete)

            self.table.setCellWidget(row, 1, box)

    def open_edit_dialog(self, proxy_id: int) -> None:
        """Открывает диалог редактирования прокси по его ID."""

        self.table.setDisabled(True)
        asyncio.create_task(self.open_edit_async(proxy_id))

    async def open_edit_async(self, proxy_id: int) -> None:
        """
        Асинхронно загружает прокси из базы, отображает диалог редактирования
        и сохраняет изменения при подтверждении.
        """
        async with app_core.db.get_session() as session:
            proxy = await ProxyRepo.get_proxy_by_id(session, proxy_id)

        if not proxy:
            QMessageBox.warning(self, "Не найдено", "Прокси не найден в базе.")
            self.table.setDisabled(False)
            return

        dlg = ProxyEditDialog(proxy, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.table.setDisabled(False)
            return

        async with app_core.db.get_session() as session:
            db_proxy = await ProxyRepo.get_proxy_by_id(session, proxy_id)
            if not db_proxy:
                QMessageBox.warning(self, "Не найдено", "Прокси не найден в базе.")
                self.table.setDisabled(False)
                return

            db_proxy.host = dlg.host_edit.text().strip()
            db_proxy.port = dlg.port_edit.text().strip()
            db_proxy.login = dlg.login_edit.text().strip()
            db_proxy.password = dlg.password_edit.text().strip()
            db_proxy.proxy_scheme = dlg.scheme_combo.currentText().strip()
            db_proxy.change_ip_url = dlg.change_ip_edit.text().strip()

            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить:\n{e}")
                self.table.setDisabled(False)
                return

        await self.load_proxies()
        self.table.setDisabled(False)

    def ask_delete(self, proxy_id: int) -> None:
        """Запрашивает подтверждение удаления прокси у пользователя."""

        btn = QMessageBox.question(self,
                                   "Удалить прокси?",
                                   "Точно удалить этот прокси?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
        if btn == QMessageBox.StandardButton.Yes:
            asyncio.create_task(self.delete_async(proxy_id))

    async def delete_async(self, proxy_id: int) -> None:
        """Асинхронно удаляет прокси из базы данных по ID и обновляет список прокси."""

        try:
            async with app_core.db.get_session() as session:
                ok = await ProxyRepo.delete_proxy_by_id(session, proxy_id)

            if not ok:
                QMessageBox.information(self, "Удаление", "Прокси не найден.")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить:\n{e}")
        finally:
            await self.load_proxies()

    def on_add_proxy(self) -> None:
        """Открывает диалог добавления нового прокси."""

        dlg = ProxyEditDialog(None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            asyncio.create_task(self._add_proxy_async(dlg))

    async def _add_proxy_async(self, dlg: ProxyEditDialog) -> None:
        """Асинхронно сохраняет новый прокси в базу данных и обновляет список прокси."""

        host = dlg.host_edit.text().strip()
        port = dlg.port_edit.text().strip()
        login = dlg.login_edit.text().strip()
        password = dlg.password_edit.text().strip()
        scheme = dlg.scheme_combo.currentText()
        change_ip_url = dlg.change_ip_edit.text().strip()

        try:
            async with app_core.db.get_session() as session:
                await ProxyRepo.add_proxy(
                    session,
                    host=host,
                    port=port,
                    login=login,
                    password=password,
                    proxy_scheme=scheme,
                    change_ip_url=change_ip_url,
                )

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить прокси:\n{e}")
        finally:
            await self.load_proxies()
