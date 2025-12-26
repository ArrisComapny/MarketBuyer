import asyncio
import re
import ipaddress
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QWidget, QHeaderView,
    QAbstractItemView, QLineEdit, QComboBox, QMessageBox, QSizePolicy)
from sqlalchemy import select


from database.db import Database
from database.models import Proxy


class ProxyEditDialog(QDialog):
    def __init__(self, proxy: Proxy | None = None, parent=None):
        super().__init__(parent)
        self.proxy = proxy  # None => новый прокси
        self.setWindowTitle("Добавить прокси" if proxy is None else "Редактировать прокси")
        self.setMinimumWidth(420)


        layout = QFormLayout(self)

        self.host_edit = QLineEdit(proxy.host if proxy else "")
        self.port_edit = QLineEdit(proxy.port if proxy else "")
        self.login_edit = QLineEdit(proxy.login if proxy else "")
        self.password_edit = QLineEdit(proxy.password if proxy else "")

        self.scheme_combo = QComboBox()
        self.scheme_combo.addItems(["http"])
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

        # делаем на всю ширину
        btn_save.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_cancel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        btn_save.setMinimumHeight(36)
        btn_cancel.setMinimumHeight(36)

        # вертикальный layout
        buttons_layout = QVBoxLayout()
        buttons_layout.addWidget(btn_save)
        buttons_layout.addWidget(btn_cancel)

        layout.addRow(buttons_layout)

        self.adjustSize()

    def on_save_clicked(self):
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        password = self.password_edit.text().strip()

        # Host обязателен
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

        # Port обязателен
        if not port:
            QMessageBox.warning(self, "Ошибка", "Port обязателен.")
            self.port_edit.setFocus()
            return

        port_value = int(port)

        # Диапазон 0–65535
        if not (0 <= port_value <= 65535):
            QMessageBox.warning(
                self,
                "Ошибка",
                "Port должен быть в диапазоне от 0 до 65535."
            )
            self.port_edit.setFocus()
            return

        # Пароль без русских букв
        if re.search(r"[А-Яа-яЁё]", password):
            QMessageBox.warning(self, "Ошибка", "Пароль не должен содержать русские буквы.")
            self.password_edit.setFocus()
            return

        self.accept()  # ✅ только если всё валидно


class ProxyManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proxy Manager")
        self.resize(720, 420)

        main_layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Прокси", "Действия"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
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

    def _proxy_title(self, p: Proxy) -> str:
        return f"{p.proxy_scheme}://{p.host}:{p.port}"

    async def load_proxies(self):
        async with Database().get_session() as session:
            res = await session.execute(select(Proxy).order_by(Proxy.id.desc()))
            proxies = res.scalars().all()

        self.table.setRowCount(0)

        for row, proxy in enumerate(proxies):
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(self._proxy_title(proxy)))

            btn_edit = QPushButton("⚙")
            btn_delete = QPushButton("🗑")

            btn_edit.setFixedWidth(40)
            btn_delete.setFixedWidth(40)

            btn_edit.clicked.connect(lambda _, pid=proxy.id: self.open_edit_dialog(pid))
            btn_delete.clicked.connect(lambda _, pid=proxy.id: self.ask_delete(pid))

            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            h.addWidget(btn_edit)
            h.addWidget(btn_delete)

            self.table.setCellWidget(row, 1, box)

    def open_edit_dialog(self, proxy_id: int):
        asyncio.create_task(self._open_edit_async(proxy_id))

    async def _open_edit_async(self, proxy_id: int):
        async with Database().get_session() as session:
            proxy = await session.get(Proxy, proxy_id)

        if not proxy:
            QMessageBox.warning(self, "Не найдено", "Прокси не найден в базе.")
            return

        dlg = ProxyEditDialog(proxy, self)
        if dlg.exec() != QDialog.Accepted:
            return

        # Простая валидация
        if not dlg.host_edit.text().strip() or not dlg.port_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Host и Port обязательны.")
            return

        async with Database().get_session() as session:
            db_proxy = await session.get(Proxy, proxy_id)
            if not db_proxy:
                QMessageBox.warning(self, "Не найдено", "Прокси не найден в базе.")
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
                return

        await self.load_proxies()

    def ask_delete(self, proxy_id: int):
        btn = QMessageBox.question(
            self,
            "Удалить прокси?",
            "Точно удалить этот прокси?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if btn == QMessageBox.Yes:
            asyncio.create_task(self._delete_async(proxy_id))

    async def _delete_async(self, proxy_id: int):
        async with Database().get_session() as session:
            proxy = await session.get(Proxy, proxy_id)
            if not proxy:
                return
            await session.delete(proxy)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить:\n{e}")
                return

        await self.load_proxies()

    def on_add_proxy(self):
        dlg = ProxyEditDialog(None, self)  # None = новый прокси
        if dlg.exec() == QDialog.Accepted:
            asyncio.create_task(self._add_proxy_async(dlg))

    async def _add_proxy_async(self, dlg: ProxyEditDialog):
        new_proxy = Proxy(
            host=dlg.host_edit.text().strip(),
            port=dlg.port_edit.text().strip(),
            login=dlg.login_edit.text().strip(),
            password=dlg.password_edit.text().strip(),
            proxy_scheme=dlg.scheme_combo.currentText(),
            change_ip_url=dlg.change_ip_edit.text().strip(),
        )

        async with Database().get_session() as session:
            session.add(new_proxy)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить прокси:\n{e}")
                return


        await self.load_proxies()




