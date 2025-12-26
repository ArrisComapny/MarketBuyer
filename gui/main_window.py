import asyncio

from PySide6.QtGui import QAction, QColor, QIcon, QPainter
from PySide6.QtCore import Qt, QSize, Signal, QRect, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QPushButton, QMainWindow, QWidget, QVBoxLayout,
                               QTableWidgetItem, QTableWidget, QHeaderView, QAbstractItemView, QLineEdit,
                               QStyleOptionButton, QStyle, QCheckBox, QMessageBox, QToolButton, QFrame, QLabel)
from qasync import asyncSlot

from gui.add_personal_account import AddAccountDialog
from gui.setting_menu_bar import  ProxyManagerDialog

from sqlalchemy import select, delete, update

from database.db import Database
from database.models import Account



class CheckBoxHeader(QHeaderView):
    clicked = Signal(Qt.CheckState)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._rect = QRect()
        self._state = Qt.Unchecked
        self.setSectionsClickable(True)

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return

        opt = QStyleOptionButton()
        opt.state = QStyle.State_Enabled

        if self._state == Qt.Checked:
            opt.state |= QStyle.State_On
        elif self._state == Qt.PartiallyChecked:
            opt.state |= QStyle.State_NoChange
        else:
            opt.state |= QStyle.State_Off

        size = self.style().pixelMetric(QStyle.PM_IndicatorWidth)
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        self._rect = QRect(x, y, size, size)
        opt.rect = self._rect

        self.style().drawControl(QStyle.CE_CheckBox, opt, painter)

    def mousePressEvent(self, event):
        if self._rect.contains(event.pos()):
            new_state = Qt.Unchecked if self._state == Qt.Checked else Qt.Checked
            self.clicked.emit(new_state)
            return
        super().mousePressEvent(event)

    def setState(self, state: Qt.CheckState):
        self._state = state
        self.viewport().update()

class MainWindow(QMainWindow):

    def __init__(self, user):
        super().__init__()
        self.user = user

        # Заголовок
        self.setWindowTitle(f"MarketBuyer – {user.login}")
        self.resize(1300, 700)
        self.create_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ================== 1) Верхняя строка: поиск слева + кнопки справа ==================
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setFixedHeight(35)
        self.search_input.setFixedWidth(200)
        self.search_input.setPlaceholderText("Поиск по телефону")
        self.search_input.textChanged.connect(self.filter_table)

        icon_action = QAction(QIcon("templates/icons/find.png"), "", self)
        self.search_input.addAction(icon_action, QLineEdit.LeadingPosition)

        self.btn_add = QPushButton("Добавить ЛК")
        self.btn_activate = QPushButton("Активировать")
        self.btn_filter = QToolButton()
        self.btn_filter.setCheckable(True)
        self.btn_filter.setAutoRaise(True)

        self.btn_filter.setToolTip("Фильтр")
        self.btn_filter.setIcon(QIcon("templates/icons/filter.png"))  # если есть
        self.btn_filter.setIconSize(QSize(18, 18))
        self.btn_filter.setFixedSize(35, 35)
        self.btn_add.clicked.connect(self.add_personal_account)

        for b in (self.btn_add, self.btn_activate):
            b.setMinimumHeight(35)

        top_row.addWidget(self.btn_filter)
        top_row.addWidget(self.search_input)
        top_row.addStretch()
        top_row.addWidget(self.btn_add)
        top_row.addWidget(self.btn_activate)
        main_layout.addLayout(top_row)

        # ===== ПАНЕЛЬ ФИЛЬТРА (скрытая, раскрывается плавно) =====
        self.filter_panel = QFrame()
        self.filter_panel.setFrameShape(QFrame.StyledPanel)
        self.filter_panel.setVisible(False)
        self.filter_panel.setMaximumHeight(0)

        self.filter_layout = QVBoxLayout(self.filter_panel)
        self.filter_layout.setContentsMargins(6, 4, 6, 4)
        self.filter_layout.setSpacing(4)

        # ===== строка: надпись + чекбоксы в ОДНУ линию =====
        row = QWidget(self.filter_panel)  # важно: parent задан
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        label = QLabel("Фильтр по статусам:", row)
        row_layout.addWidget(label)

        self.cb_enable = QCheckBox("Enable", row)
        self.cb_disable = QCheckBox("Disable", row)
        self.cb_enable.setChecked(True)
        self.cb_disable.setChecked(True)

        row_layout.addWidget(self.cb_enable)
        row_layout.addWidget(self.cb_disable)
        row_layout.addStretch()  # всё прижать влево

        self.filter_layout.addWidget(row)

        main_layout.addWidget(self.filter_panel)

        # анимация высоты панели
        self.filter_anim = QPropertyAnimation(self.filter_panel, b"maximumHeight", self)
        self.filter_anim.setDuration(180)
        self.filter_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.btn_filter.toggled.connect(self._toggle_filter_panel)

        # ================== 2) Таблица ==================
        self.table = QTableWidget()
        self._filling_table = False
        self.table.itemChanged.connect(self.on_table_item_changed)
        # Запрет на редактирование в таблице
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed
        )


        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["", "Номер телефона", "Статус", "Комментарий", "Действие"])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)

        self.header = CheckBoxHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(self.header)
        self.header.clicked.connect(self.on_header_checkbox_clicked)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 36)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)

        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(4, 200)

        main_layout.addWidget(self.table, stretch=1)

        # ✅ Стили кнопок иконок
        self.style_icon_btn = """
        QPushButton { border: none; background-color: transparent; }
        QPushButton:hover { background-color: rgba(255, 105, 180, 70); border-radius: 4px; }
        """
        self.style_run_btn = """
        QPushButton {
            border: 1px solid #d0d0d0;
            border-radius: 6px;
            background-color: transparent;
            padding: 2px 10px;
        }
        QPushButton:hover { background-color: rgba(255, 105, 180, 70); }
        """

        # ✅ Запускаем загрузку из БД сразу после создания UI
        QTimer.singleShot(0, self.load_accounts)

    # -------------------- DB: достаём phone/comment/status --------------------

    async def get_accounts_for_table(self):
        async with Database().get_session() as session:
            stmt = select(
                Account.phone,
                Account.comment,
                Account.status
            ).order_by(Account.phone.desc())
            res = await session.execute(stmt)
            return res.all()  # [(phone, comment, status), ...]

    # -------------------- UI: загрузка + заполнение --------------------

    @asyncSlot()
    async def load_accounts(self):
        rows = await self.get_accounts_for_table()
        self.fill_table(rows)

    def fill_table(self, rows):
        self._filling_table = True
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))

        for row, (phone, comment, status) in enumerate(rows):
            # ---------- ЧЕКБОКС ----------
            checkbox = QCheckBox()
            box0 = QWidget()
            lay0 = QHBoxLayout(box0)
            lay0.setContentsMargins(0, 0, 0, 0)
            lay0.addStretch()
            lay0.addWidget(checkbox)
            lay0.addStretch()
            self.table.setCellWidget(row, 0, box0)

            checkbox.stateChanged.connect(lambda _s, cb=checkbox: self.on_row_checkbox_changed(cb))
            phone_view = self.format_phone_ru(phone)

            # ---------- ДАННЫЕ ----------
            item_phone = QTableWidgetItem(phone_view)
            item_phone.setData(Qt.UserRole, phone)
            item_phone.setFlags(item_phone.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, item_phone)

            item_status = QTableWidgetItem(status or "")
            item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, item_status)

            item_comment = QTableWidgetItem(comment or "")
            item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, item_comment)


            # ---------- КНОПКИ В ЯЧЕЙКЕ ----------
            btn_run = QPushButton("Запуск")
            btn_run.setFixedSize(105, 25)
            btn_run.setStyleSheet(self.style_run_btn)

            btn_settings = QPushButton()
            btn_settings.setIcon(QIcon("templates/icons/setting.png"))
            btn_settings.setIconSize(QSize(20, 20))
            btn_settings.setFixedSize(35, 25)
            btn_settings.setStyleSheet(self.style_icon_btn)

            btn_delete = QPushButton()
            btn_delete.setIcon(QIcon("templates/icons/delete.png"))
            btn_delete.setIconSize(QSize(20, 20))
            btn_delete.setFixedSize(35, 25)
            btn_delete.setStyleSheet(self.style_icon_btn)

            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.setSpacing(5)
            h_layout.addWidget(btn_run)
            h_layout.addWidget(btn_settings)
            h_layout.addWidget(btn_delete)

            self.table.setCellWidget(row, 4, container)

            # ---------- ЦВЕТ СТАТУСА ----------
            item_status = self.table.item(row, 2)
            if item_status:
                st = (status or "").strip().lower()
                if st == "enable":
                    item_status.setBackground(QColor(0, 200, 0, 35))
                elif st == "disable":
                    item_status.setBackground(QColor(255, 0, 0, 35))

            # ---------- обработчики ----------
            btn_run.clicked.connect(lambda _, r=row: self.on_run_clicked(r))
            btn_settings.clicked.connect(lambda _, r=row: self.on_settings_clicked(r))
            btn_delete.clicked.connect(lambda _, r=row: self.on_delete_clicked(r))

        self.table.blockSignals(False)
        self._filling_table = False
        # header по умолчанию
        self.header.setState(Qt.Unchecked)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)



    def create_menu_bar(self):
        menu_bar = self.menuBar()

        # --- Основные меню ---
        self.file_menu = menu_bar.addMenu("Файл")
        self.settings_menu = menu_bar.addMenu("Настройки")
        self.help_menu = menu_bar.addMenu("Справка")

        # --- Линия под меню баром----
        self.menuBar().setStyleSheet("""QMenuBar {border-bottom: 1px solid #d0d0d0;}""")

        # --- Создаём действия ---
        self.open_action = QAction("Открыть", self)
        self.save_action = QAction("Сохранить", self)
        self.exit_action = QAction("Выход", self)

        self.settings_action = QAction("ProxyManager", self)
        self.about_action = QAction("О программе", self)

        # --- Обработчики ---
        self.exit_action.triggered.connect(self.close)
        self.settings_action.triggered.connect(self.open_settings)

        # --- Заполняем меню ---
        self.file_menu.addAction(self.open_action)
        self.file_menu.addAction(self.save_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)
        self.settings_menu.addAction(self.settings_action)
        self.help_menu.addAction(self.about_action)

    def _toggle_filter_panel(self, opened: bool):
        self.filter_anim.stop()

        # чтобы finished не накапливался
        try:
            self.filter_anim.finished.disconnect()
        except Exception:
            pass

        if opened:
            self.filter_panel.setVisible(True)
            self.filter_panel.setMaximumHeight(0)

            target = self.filter_panel.sizeHint().height()
            if target <= 0:
                target = 120

            self.filter_anim.setStartValue(0)
            self.filter_anim.setEndValue(target)
            self.filter_anim.start()
        else:
            start = self.filter_panel.maximumHeight()
            self.filter_anim.setStartValue(start)
            self.filter_anim.setEndValue(0)

            def _hide():
                self.filter_panel.setVisible(False)

            self.filter_anim.finished.connect(_hide)
            self.filter_anim.start()

    def add_personal_account(self):

        dlg = AddAccountDialog(self)
        dlg.account_saved.connect(self.load_accounts)  # load_accounts у тебя @asyncSlot()
        dlg.exec()

    def open_settings(self):

        dlg = ProxyManagerDialog(self)  # parent = MainWindow
        result = dlg.exec()  # ← ВАЖНО: exec(), не show()

        if result == QDialog.Accepted:
            print("Настройки сохранены")  # здесь можно открыть QDialog

    def on_run_clicked(self, row):

        id_ = self.table.item(row, 1).text()
        print(f"[RUN] Запуск для ID {id_}, row = {row}")

    @asyncSlot()
    async def on_settings_clicked(self, row: int):
        phone_item = self.table.item(row, 1)
        if not phone_item:
            return

        phone10 = phone_item.data(Qt.UserRole)
        if not phone10:
            return

        account_data = await self._get_account_by_phone(phone10)
        if not account_data:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Ошибка")
            msg.setText("Аккаунт не найден в БД.")
            msg.open()
            return

        dlg = AddAccountDialog(self, account=account_data)
        dlg.account_saved.connect(self.load_accounts)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.open()

    async def _delete_account_async(self, phone10: str):
        async with Database().get_session() as session:
            await session.execute(
                delete(Account).where(Account.phone == phone10)
            )
            await session.commit()

        # ✅ после удаления обновляем таблицу
        await self.load_accounts()

    def on_delete_clicked(self, row: int):
        phone_item = self.table.item(row, 1)
        if not phone_item:
            return

        phone10 = phone_item.data(Qt.UserRole)  # ✅ оригинальный телефон из БД
        if not phone10:
            return

        # подтверждение
        reply = QMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранный аккаунт? Аккаунт будет удален из базы данных без возможности восстановления",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            asyncio.create_task(self._delete_account_async(phone10))

    def _row_checkbox(self, row: int) -> QCheckBox | None:
        w = self.table.cellWidget(row, 0)
        return w.findChild(QCheckBox) if w else None

    def on_header_checkbox_clicked(self, state: Qt.CheckState):
        checked = (state == Qt.Checked)

        self.table.setUpdatesEnabled(False)

        bg = QColor(255, 105, 180, 40) if checked else QColor(0, 0, 0, 0)

        for row in range(self.table.rowCount()):
            cb = self._row_checkbox(row)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)

            for col in range(self.table.columnCount()):
                if col == 2:  # ✅ статус НЕ трогаем
                    continue
                it = self.table.item(row, col)
                if it:
                    it.setBackground(bg)

            widget = self.table.cellWidget(row, 4)
            if widget:
                widget.setStyleSheet("background-color: rgba(255, 105, 180, 40);" if checked else "")

        self.table.setUpdatesEnabled(True)
        self.header.setState(Qt.Checked if checked else Qt.Unchecked)

    def on_row_checkbox_changed(self, checkbox: QCheckBox):
        container = checkbox.parentWidget()  # это box0, который стоит в cellWidget(row,0)
        index = self.table.indexAt(container.pos())  # получаем индекс таблицы по позиции контейнера
        row = index.row()
        if row < 0:
            return

        is_checked = checkbox.isChecked()
        bg = QColor(255, 105, 180, 40) if is_checked else QColor(0, 0, 0, 0)

        for col in range(self.table.columnCount()):
            if col == 2:  # статус не трогаем
                continue
            it = self.table.item(row, col)
            if it:
                it.setBackground(bg)

        widget = self.table.cellWidget(row, 4)
        if widget:
            widget.setStyleSheet("background-color: rgba(255, 105, 180, 40);" if is_checked else "")

        # tri-state для header
        total = self.table.rowCount()
        checked_count = 0
        for r in range(total):
            c = self._row_checkbox(r)
            if c and c.isChecked():
                checked_count += 1

        if checked_count == 0:
            self.header.setState(Qt.Unchecked)
        elif checked_count == total:
            self.header.setState(Qt.Checked)
        else:
            self.header.setState(Qt.PartiallyChecked)

    def on_table_item_changed(self, item: QTableWidgetItem):
        if self._filling_table:
            return

        row = item.row()
        col = item.column()

        # нас интересует только колонка "Комментарий" (3)
        if col != 3:
            return

        phone_item = self.table.item(row, 1)
        if not phone_item:
            return

        phone10 = phone_item.data(Qt.UserRole)  # ✅ достаём оригинал для БД
        if not phone10:
            return

        new_comment = item.text().strip()

        # ✅ сохраняем асинхронно
        asyncio.create_task(self._save_comment_async(phone10, new_comment))

    def filter_table(self, text: str):
        text = text.strip().lower()
        clean_text = ''.join(filter(str.isdigit, text))  # только цифры

        for row in range(self.table.rowCount()):
            phone_item = self.table.item(row, 1)
            comment_item = self.table.item(row, 3)

            phone = phone_item.text().lower() if phone_item else ""
            comment = comment_item.text().lower() if comment_item else ""

            # очищенная версия телефона (только цифры)
            clean_phone = ''.join(filter(str.isdigit, phone))

            # если поле поиска пустое — показываем все строки
            if not text:
                self.table.setRowHidden(row, False)
                continue

            # поиск по телефону
            match_phone = (
                    text in phone or  # по отформатированному
                    clean_text in clean_phone  # по "9001111111"
            )

            # поиск по комментарию
            match_comment = text in comment
            match = match_phone or match_comment
            self.table.setRowHidden(row, not match)

    def format_phone_ru(self, phone10: str) -> str:
        digits = ''.join(filter(str.isdigit, phone10))
        if len(digits) != 10:
            return phone10
        return f"+7 {digits[0:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:10]}"

    async def _save_comment_async(self, phone10: str, comment: str):
        async with Database().get_session() as session:
            await session.execute(
                update(Account)
                .where(Account.phone == phone10)
                .values(comment=comment)
            )
            await session.commit()

    async def _get_account_by_phone(self, phone10: str) -> dict | None:
        async with Database().get_session() as session:
            res = await session.execute(
                select(
                    Account.phone,
                    Account.name,
                    Account.male,  # тут у тебя хранится 'male'/'female'
                    Account.user_agent,
                    Account.comment,
                ).where(Account.phone == phone10)
            )
            row = res.first()
            if not row:
                return None

            phone, name, male, user_agent, comment = row

            # phone_view можно собрать из phone10
            return {
                "phone10": phone,
                "phone_view": self.format_phone_ru(phone),
                "name": name or "",
                "gender": male or None,  # 'male' / 'female' / None
                "user_agent": user_agent or "",
                "comment": comment or "",
            }




        # btn = QPushButton("Запуск браузера")
        # btn.clicked.connect(self.run_browser)
        # self.setCentralWidget(btn)


    # @asyncSlot()
    # async def run_browser(self):
    #     browser = BrowserController()
    #     await browser.run()
