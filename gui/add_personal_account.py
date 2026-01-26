import re
import random
import asyncio

from pathlib import Path

from sqlalchemy import select, update
from PySide6.QtCore import Signal, Qt
from sqlalchemy.exc import IntegrityError
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton
from PySide6.QtWidgets import QLineEdit, QComboBox, QMessageBox, QSizePolicy, QFormLayout


from database.db import Database
from database.models import Account

BASE_DIR = Path(__file__).resolve().parent.parent
UA_FILE_PATH = BASE_DIR / "templates" / "files" / "user_agents.txt"
NAMES_FILE_PATH = BASE_DIR / "templates" / "files" / "russian_names.txt"


class AddAccountDialog(QDialog):
    account_saved = Signal()

    def __init__(self, parent=None, account: dict | None = None):
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
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

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
        self.gender_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumHeight(38)

        self.btn_save.clicked.connect(self.on_save_clicked)
        self.btn_cancel.clicked.connect(self.reject)
        # self.authorization.clicked.connect(self) # подлючение кнопки (подумать нужна ли она здесь)

        if self.account:
            self.fill_from_account()

        main_layout.addWidget(self.btn_save)
        main_layout.addWidget(self.btn_cancel)




    def on_save_clicked(self):
        name = self.name_edit.text().strip()
        phone_raw = self.phone_edit.text().strip()
        user_agent = self.ua_edit.text().strip()
        comment = self.comment_edit.text().strip()
        gender = self.gender_combo.currentData()

        if not phone_raw:
            QMessageBox.warning(self, "Ошибка", "Телефон обязателен.")
            self.phone_edit.setFocus()
            return

        phone10 = self._phone_to_10_digits(phone_raw)
        if not phone10:
            QMessageBox.warning(self,
                                "Ошибка",
                                "Телефон должен содержать только цифры РФ.\n"
                                "Примеры:\n"
                                "9991112233\n"
                                "89991112233\n"
                                "+7 999 111-22-33")
            self.phone_edit.setFocus()
            return

        if self.account:
            asyncio.create_task(self.update_async(name=name,
                                                  gender=gender,
                                                  phone10=phone10,
                                                  user_agent=user_agent,
                                                  comment=comment))
        else:
            asyncio.create_task(self.save_async(name=name,
                                                gender=gender,
                                                phone10=phone10,
                                                user_agent=user_agent,
                                                comment=comment))

    @staticmethod
    def _load_names() -> list[tuple[str, str]]:
        """
        Возвращает список [(name, gender_db), ...]
        gender_db: 'male' / 'female'
        Файл: Имя;Male или Имя;Female
        """
        path_file_name = NAMES_FILE_PATH
        if not path_file_name.exists():
            return []

        out: list[tuple[str, str]] = []
        for line in path_file_name.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or ";" not in line:
                continue
            name, gender = [x.strip() for x in line.split(";", 1)]
            if not name or not gender:
                continue

            out.append((name, gender))

        # убираем дубликаты, сохраняя порядок
        seen = set()
        uniq = []
        for name, gender in out:
            key = (name, gender)
            if key not in seen:
                seen.add(key)
                uniq.append((name, gender))

        return uniq

    @staticmethod
    def _load_user_agents() -> list[str]:
        path_ua_file = UA_FILE_PATH
        if not path_ua_file.exists():
            return []

        agents: list[str] = []
        for line in path_ua_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            ua = line.strip()
            if ua:
                agents.append(ua)

        # убираем дубликаты, сохраняя порядок
        seen = set()
        unique = []
        for ua in agents:
            if ua not in seen:
                seen.add(ua)
                unique.append(ua)

        return unique

    @staticmethod
    def _phone_to_10_digits(text: str) -> str | None:
        #  Удаляем ВСЁ, кроме цифр
        digits = re.sub(r"\D", "", text)

        #  Проверяем варианты
        # 10 цифр: 9991112233
        if re.fullmatch(r"\d{10}", digits):
            return digits

        # 11 цифр с 7 или 8: 79991112233 / 89991112233
        if re.fullmatch(r"[78]\d{10}", digits):
            return digits[1:]

        return None

    def fill_from_account(self):
        self.name_edit.setText(self.account.get("name", ""))
        self.phone_edit.setText(self.account.get("phone_view", ""))
        self.ua_edit.setText(self.account.get("user_agent", ""))
        self.comment_edit.setText(self.account.get("comment", ""))

        gender = self.account.get("gender")
        if gender == "Male":
            self.gender_combo.setCurrentIndex(1)
        elif gender == "Female":
            self.gender_combo.setCurrentIndex(2)
        else:
            self.gender_combo.setCurrentIndex(0)

    async def _pick_user_agent(self, session) -> str:
        """
        preferred:
          - если None/"" -> просто выбираем свободный UA из файла
          - если задан -> если он уже используется в БД, выбираем другой
        Если все из файла заняты -> разрешаем повтор (выбираем из всего списка).
        """
        agents = self._load_user_agents()

        used_rows = await session.execute(select(Account.user_agent).where(Account.user_agent != ""))
        used = {ua for (ua,) in used_rows.all() if ua}
        free = [ua for ua in agents if ua not in used]
        pool = free if free else agents

        return random.choice(pool)

    async def _pick_name_gender(self, session, selected_gender: str | None = None) -> tuple[str, str]:
        pool = self._load_names()

        if selected_gender:
            pool = [(n, g) for (n, g) in pool if g == selected_gender]

        used_rows = await session.execute(select(Account.name).where(Account.name != ""))
        used_names = {n for (n,) in used_rows.all() if n}

        free = [(n, g) for (n, g) in pool if n not in used_names]
        candidates = free if free else pool
        return random.choice(candidates)

    async def save_async(self, name: str, gender: str, phone10: str, user_agent: str, comment: str) -> None:
        self.btn_save.setEnabled(False)

        try:
            async with Database().get_session() as session:
                exists = await session.scalar(select(Account.phone).where(Account.phone == phone10))
                if exists:
                    QMessageBox.warning(self, "Ошибка", "Аккаунт с таким телефоном уже существует.")
                    self.btn_save.setEnabled(True)
                    return

                if not name and not gender:
                    name, gender = await self._pick_name_gender(session)

                if name and not gender:
                    QMessageBox.warning(self, "Ошибка", "Выберите пол.")
                    self.btn_save.setEnabled(True)
                    return

                if gender and not name:
                    picked_name, _ = await self._pick_name_gender(session, selected_gender=gender)
                    name = picked_name

                if not user_agent:
                    user_agent = await self._pick_user_agent(session)

                acc = Account(phone=phone10,
                              name=name,
                              male=gender,
                              user_agent=user_agent,
                              comment=comment)

                session.add(acc)

                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    QMessageBox.warning(self, "Ошибка", "Аккаунт с таким телефоном уже существует.")
                    self.btn_save.setEnabled(True)
                    return

            self.account_saved.emit()
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить аккаунт:\n{e}")
            self.btn_save.setEnabled(True)

    async def update_async(self, name: str, gender: str, phone10: str, user_agent: str, comment: str) -> None:
        self.btn_save.setEnabled(False)

        try:
            old_phone10 = self.account.get("phone10")
            if not old_phone10:
                raise ValueError("В account нет phone10")

            async with Database().get_session() as session:
                # ✅ если телефон изменили — проверяем, что такого ещё нет
                if phone10 != old_phone10:
                    exists = await session.scalar(select(Account.phone).where(Account.phone == phone10))
                    if exists:
                        QMessageBox.warning(self, "Ошибка", "Аккаунт с таким телефоном уже существует.")

                        self.phone_edit.setText(self.account.get("phone_view", ""))

                        self.btn_save.setEnabled(True)
                        return

                if not name and not gender:
                    name, gender = await self._pick_name_gender(session)

                if name and not gender:
                    QMessageBox.warning(self, "Ошибка", "Выберите пол.")
                    self.btn_save.setEnabled(True)
                    return

                if gender and not name:
                    picked_name, _ = await self._pick_name_gender(session, selected_gender=gender)
                    name = picked_name

                if not user_agent:
                    user_agent = await self._pick_user_agent(session)

                await session.execute(update(Account)
                    .where(Account.phone == old_phone10)
                    .values(phone=phone10,
                            name=name,
                            male=gender,
                            user_agent=user_agent,
                            comment=comment))
                await session.commit()

            self.account_saved.emit()
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить аккаунт:\n{e}")
            self.btn_save.setEnabled(True)
