import base64
import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QCheckBox, \
    QApplication
from qasync import asyncSlot

import core.app as app_core
from core.settings import save_settings, load_settings
from database.models import User
from sqlalchemy import select
from utils.messagebox import CustomMessageBox


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.main = None
        self.width = 300
        self.height = 130

        self.setWindowTitle("Авторизация")
        self.setWindowIcon(QIcon(os.path.join(os.getcwd(), "templates/icons/login.png")))
        self.setFixedSize(self.width, self.height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        login_row = QHBoxLayout()

        self.login = QLineEdit()
        self.login.returnPressed.connect(self.try_login)
        self.login.setPlaceholderText("Введите логин...")

        login_label = QLabel("Логин")
        login_label.setFixedWidth(50)

        login_row.addWidget(login_label)
        login_row.addWidget(self.login)

        password_row = QHBoxLayout()

        self.password = QLineEdit()
        self.password.returnPressed.connect(self.try_login)
        self.password.setPlaceholderText("Введите пароль...")
        self.password.setEchoMode(QLineEdit.Password)

        password_label = QLabel("Пароль")
        password_label.setFixedWidth(50)

        password_row.addWidget(password_label)
        password_row.addWidget(self.password)

        self.remember_cb = QCheckBox("Запомнить")
        self.remember_cb.setStyleSheet("""
            QCheckBox {
                spacing: 14px;
            }
        """)


        self.btn = QPushButton("Войти")
        self.btn.clicked.connect(self.try_login)
        self.btn.setStyleSheet("""
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #888888;
            }
        """)

        layout.addLayout(login_row)
        layout.addLayout(password_row)
        layout.addWidget(self.remember_cb)
        layout.addWidget(self.btn)

        self._load_saved_credentials()
        self.center_on_screen()

    def _load_saved_credentials(self):
        """Загрузить сохранённый логин/пароль, если включено 'Запомнить'."""
        self.settings = load_settings()

        saved_login = self.settings.get("login")
        saved_password = self.settings.get("password")
        remember = self.settings.get("remember", False)

        if remember:
            if saved_login:
                self.login.setText(saved_login)

            if saved_password:
                try:
                    decoded_pass = base64.b64decode(saved_password).decode()
                    self.password.setText(decoded_pass)
                except Exception:
                    pass

            self.remember_cb.setChecked(True)

        # ставим фокус на логин
        self.login.setFocus()
        self.login.setCursorPosition(len(self.login.text()))

    def center_on_screen(self):
        """Переместить окно в центр экрана."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        screen_geom = screen.availableGeometry()
        x = screen_geom.x() + (screen_geom.width() - self.width) // 2
        y = screen_geom.y() + (screen_geom.height() - self.height) // 2
        self.move(x, y)

    def set_loading(self, loading: bool, message: str = "Войти"):
        """Включает/выключает режим загрузки."""
        if loading:
            self.btn.setText(message)
            self.btn.setEnabled(False)
            self.login.setEnabled(False)
            self.password.setEnabled(False)
            self.remember_cb.setEnabled(False)
        else:
            self.btn.setText(message)
            self.btn.setEnabled(True)
            self.login.setEnabled(True)
            self.password.setEnabled(True)
            self.remember_cb.setEnabled(True)
            self.login.setFocus()



    @asyncSlot()
    async def try_login(self):
        if app_core.db is None:
            CustomMessageBox.warning(self, "База данных", "База данных ещё не готова.")
            return

        login = self.login.text().lower().strip()
        if not login:
            CustomMessageBox.warning(self, "Ошибка авторизации", "Введите логин.")
            return

        password = self.password.text().strip()
        if not password:
            CustomMessageBox.warning(self, "Ошибка авторизации", "Введите пароль.")
            return

        self.set_loading(True, "Проверка пользователя...")

        user = None

        async with app_core.db.get_session() as session:
            stmt = select(User).where(User.login == login, User.password == password, User.status == True)
            res = await session.execute(stmt)
            user = res.scalar_one_or_none()

        self.set_loading(False)

        if user is None:
            CustomMessageBox.warning(self, "Ошибка", "Неверный логин или пароль")
            return

        if self.remember_cb.isChecked():
            encoded_pass = base64.b64encode(password.encode()).decode()

            save_settings({
                "login": login,
                "password": encoded_pass,
                "remember": True,
            })
        else:
            # если галочка снята — очищаем
            save_settings({
                "login": "",
                "password": "",
                "remember": False,
            })

        from gui.main_window import MainWindow
        self.hide()
        self.main = MainWindow(user)
        self.main.show()
