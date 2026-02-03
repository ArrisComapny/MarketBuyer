import asyncio

from PySide6.QtCore import Signal, Qt
from sqlalchemy.exc import IntegrityError
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton
from PySide6.QtWidgets import QLineEdit, QComboBox, QSizePolicy, QFormLayout

import core.app as app_core

from utils.phone import phone_to_10_digits
from database.repositories import AccountRepo
from utils.messagebox import CustomMessageBox
from utils.random_tools import pick_name_gender, pick_user_agent


class AddAccountDialog(QDialog):
    account_saved = Signal()

    def __init__(self, parent=None, account: dict | None = None) -> None:
        super().__init__(parent)

        self.account = account
        self.setWindowTitle("Добавить личный кабинет")
        self.resize(520, 330)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # --- Телефон ---
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("Например: +7 900 111-22-33 или 89001112233")
        self.phone_edit.setMinimumHeight(30)
        form.addRow("Телефон", self.phone_edit)

        # --- Имя ---
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Если пусто — выберется автоматически из списка")
        self.name_edit.setMinimumHeight(30)
        form.addRow("Имя", self.name_edit)

        # --- Пол ---
        self.gender_combo = QComboBox()
        self.gender_combo.addItem("Сгенерировать автоматически", None)
        self.gender_combo.addItem("Мужской", "Male")
        self.gender_combo.addItem("Женский", "Female")
        self.gender_combo.setMinimumHeight(30)
        self.gender_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Пол", self.gender_combo)

        # --- User-Agent ---
        self.ua_edit = QLineEdit()
        self.ua_edit.setPlaceholderText("Если пусто — выберется автоматически из списка")
        self.ua_edit.setMinimumHeight(30)
        form.addRow("User-Agent", self.ua_edit)

        # --- Комментарий ---
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("Например: основной аккаунт / заметка")
        self.comment_edit.setMinimumHeight(30)
        form.addRow("Комментарий", self.comment_edit)

        main_layout.addLayout(form)
        main_layout.addStretch()

        self.btn_save = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")

        for b in (self.btn_save, self.btn_cancel):
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(38)

        self.btn_save.clicked.connect(self.on_save_clicked)
        self.btn_cancel.clicked.connect(self.reject)

        if self.account:
            self.fill_from_account()

        main_layout.addWidget(self.btn_save)
        main_layout.addWidget(self.btn_cancel)

    from sqlalchemy.ext.asyncio import AsyncSession

    @staticmethod
    async def _normalize_fields(session: AsyncSession,
                                name: str,
                                gender: str | None,
                                user_agent: str) -> tuple[str, str, str]:
        """Нормализует поля аккаунта."""
        if not name and not gender:
            name, gender = await pick_name_gender(session)

        if name and not gender:
            raise ValueError("Выберите пол.")

        if gender and not name:
            name, _ = await pick_name_gender(session, selected_gender=gender)

        if not user_agent:
            user_agent = await pick_user_agent(session)

        return name, gender, user_agent

    def on_save_clicked(self) -> None:
        """Обрабатывает нажатие кнопки «Сохранить»."""
        name = self.name_edit.text().strip()
        user_agent = self.ua_edit.text().strip()
        gender = self.gender_combo.currentData()
        phone_raw = self.phone_edit.text().strip()
        comment = self.comment_edit.text().strip()

        if not phone_raw:
            CustomMessageBox.warning(self, "Ошибка", "Телефон обязателен.")
            self.phone_edit.setFocus()
            return

        phone10 = phone_to_10_digits(phone_raw)
        if not phone10:
            CustomMessageBox.warning(
                self,
                "Ошибка",
                "Телефон должен содержать только цифры РФ.\n"
                "Примеры:\n"
                "9991112233\n"
                "89991112233\n"
                "+7 999 111-22-33"
            )
            self.phone_edit.setFocus()
            return

        if self.account:
            asyncio.create_task(self.update_account(name=name,
                                                    gender=gender,
                                                    phone10=phone10,
                                                    user_agent=user_agent,
                                                    comment=comment))
        else:
            asyncio.create_task(self.save_account(name=name,
                                                  gender=gender,
                                                  phone10=phone10,
                                                  user_agent=user_agent,
                                                  comment=comment))

    def fill_from_account(self) -> None:
        """Заполняет поля формы данными существующего аккаунта при открытии диалога в режиме редактирования."""
        self.name_edit.setText(self.account.get("name", ""))
        self.ua_edit.setText(self.account.get("user_agent", ""))
        self.comment_edit.setText(self.account.get("comment", ""))
        self.phone_edit.setText(self.account.get("phone_view", ""))

        gender = self.account.get("gender")
        index = self.gender_combo.findData(gender)
        if index == -1:
            index = 0

        self.gender_combo.setCurrentIndex(index)

    async def save_account(self, name: str, gender: str | None, phone10: str, user_agent: str, comment: str) -> None:
        """Асинхронно создаёт новый аккаунт в базе данных."""
        self.btn_save.setEnabled(False)

        try:
            async with app_core.db.get_session() as session:
                name, gender, user_agent = await self._normalize_fields(
                    session,
                    name=name,
                    gender=gender,
                    user_agent=user_agent,
                )

                await AccountRepo.add_account(
                    session,
                    phone10=phone10,
                    name=name,
                    gender=gender,
                    user_agent=user_agent,
                    comment=comment,
                )

            self.account_saved.emit()
            self.accept()

        except IntegrityError:
            CustomMessageBox.warning(self, "Ошибка", "Аккаунт с таким телефоном уже существует.")

        except Exception as e:
            CustomMessageBox.critical(self, "Ошибка", f"Не удалось сохранить аккаунт:\n{e}")

        finally:
            self.btn_save.setEnabled(True)

    async def update_account(self, name: str, gender: str | None, phone10: str, user_agent: str, comment: str) -> None:
        """Асинхронно обновляет существующий аккаунт в базе данных."""
        self.btn_save.setEnabled(False)

        try:
            old_phone10 = self.account.get("phone10")
            if not old_phone10:
                raise ValueError("В account нет phone10")

            async with app_core.db.get_session() as session:
                name, gender, user_agent = await self._normalize_fields(
                    session,
                    name=name,
                    gender=gender,
                    user_agent=user_agent,
                )

                await AccountRepo.update_account(
                    session,
                    old_phone10=old_phone10,
                    phone10=phone10,
                    name=name,
                    gender=gender,
                    user_agent=user_agent,
                    comment=comment,
                )

            self.account_saved.emit()
            self.accept()

        except IntegrityError:
            CustomMessageBox.warning(self, "Ошибка", "Аккаунт с таким телефоном уже существует.")
            self.phone_edit.setText(self.account.get("phone_view", ""))

        except Exception as e:
            CustomMessageBox.critical(self, "Ошибка", f"Не удалось обновить аккаунт:\n{e}")

        finally:
            self.btn_save.setEnabled(True)
