import asyncio

from sqlalchemy import select, delete, update
from PySide6.QtGui import QAction, QColor, QIcon, QPainter
from PySide6.QtCore import Qt, QSize, Signal, QRect, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtWidgets import QTableWidgetItem, QTableWidget, QHeaderView, QAbstractItemView, QLineEdit
from PySide6.QtWidgets import QStyleOptionButton, QStyle, QCheckBox, QMessageBox, QToolButton, QFrame, QLabel
from qasync import asyncSlot

from database.db import Database
from database.models import Account
from gui.setting_menu_bar import ProxyManagerDialog
from gui.add_personal_account import AddAccountDialog

from core.browser import BrowserController
from database.models import Proxy
from core.proxy_pool import ProxyPool


class CheckBoxHeader(QHeaderView):
    """
    Заголовок таблицы с чекбоксом в первой колонке (Select All).
    Позволяет выделять/снимать выделение со всех строк одним кликом.
    """
    clicked = Signal(Qt.CheckState)

    def __init__(self, orientation, parent=None) -> None:
        """
        Инициализация заголовка:
        - _rect: область чекбокса, чтобы понимать, куда кликнули
        - _state: текущее состояние чекбокса (Unchecked/Checked/PartiallyChecked)
        """
        super().__init__(orientation, parent)
        self._rect = QRect()
        self._state = Qt.Unchecked
        self.setSectionsClickable(True)

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int) -> None:
        """
        Рисуем стандартный заголовок + добавляем чекбокс в первой колонке (logicalIndex == 0).
        """
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return

        opt = QStyleOptionButton()
        opt.state = QStyle.State_Enabled

        # Проставляем визуальное состояние чекбокса
        if self._state == Qt.Checked:
            opt.state |= QStyle.State_On
        elif self._state == Qt.PartiallyChecked:
            opt.state |= QStyle.State_NoChange
        else:
            opt.state |= QStyle.State_Off

        # Центруем чекбокс внутри ячейки заголовка
        size = self.style().pixelMetric(QStyle.PM_IndicatorWidth)
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        self._rect = QRect(x, y, size, size)
        opt.rect = self._rect

        # Рисуем чекбокс
        self.style().drawControl(QStyle.CE_CheckBox, opt, painter)

    def mousePressEvent(self, event) -> None:
        """
        Если клик попал в прямоугольник чекбокса — переключаем состояние и эмитим сигнал.
        Иначе — обычное поведение заголовка.
        """
        if self._rect.contains(event.pos()):
            new_state = Qt.Unchecked if self._state == Qt.Checked else Qt.Checked
            self.clicked.emit(new_state)
            return
        super().mousePressEvent(event)

    def setState(self, state: Qt.CheckState) -> None:
        """
        Принудительно устанавливаем состояние чекбокса в заголовке.
        Используется, когда часть строк выделена (PartiallyChecked) или все/ничего.
        """
        self._state = state
        self.viewport().update()


class MainWindow(QMainWindow):
    def __init__(self, user) -> None:
        """
        Создаёт UI главного окна:
        - меню
        - панель поиска/кнопок
        - панель фильтра статусов (с анимацией)
        - таблица аккаунтов
        Также инициализирует структуры для управления браузерами/прокси.
        """
        super().__init__()
        self.user = user

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

        # Поле поиска (по телефону / комментарию)
        self.search_input = QLineEdit()
        self.search_input.setFixedHeight(35)
        self.search_input.setFixedWidth(200)
        self.search_input.setPlaceholderText("Поиск по телефону")
        self.search_input.textChanged.connect(lambda _: self.apply_filters())

        # Иконка лупы в поле поиска
        icon_action = QAction(QIcon("templates/icons/find.png"), "", self)
        self.search_input.addAction(icon_action, QLineEdit.LeadingPosition)

        # Кнопки управления
        self.btn_add = QPushButton("Добавить ЛК")
        self.btn_activate = QPushButton("Активировать")

        # Кнопка раскрытия фильтра
        self.btn_filter = QToolButton()
        self.btn_filter.setCheckable(True)
        self.btn_filter.setAutoRaise(True)
        self.btn_filter.setToolTip("Фильтр")
        self.btn_filter.setIcon(QIcon("templates/icons/filter.png"))
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

        # ================== Панель фильтра (скрывается/показывается анимацией) ==================
        self.filter_panel = QFrame()
        self.filter_panel.setFrameShape(QFrame.StyledPanel)
        self.filter_panel.setVisible(False)
        self.filter_panel.setMaximumHeight(0)

        self.filter_layout = QVBoxLayout(self.filter_panel)
        self.filter_layout.setContentsMargins(6, 4, 6, 4)
        self.filter_layout.setSpacing(4)

        # Отображаемые подписи на кнопке "run" в зависимости от статуса
        self.run_btn_text = {
            "disable": "Активировать",
            "login": "Запуск",
            "logout": "Вход",
        }

        self._filter_hide_slot = None

        # Строка чекбоксов статусов
        row = QWidget(self.filter_panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        label = QLabel("Фильтр по статусам:", row)
        row_layout.addWidget(label)

        self.cb_disable = QCheckBox("Disable", row)
        self.cb_login = QCheckBox("login", row)
        self.cb_logout = QCheckBox("logout", row)

        # По умолчанию показываем всё
        self.cb_login.setChecked(True)
        self.cb_disable.setChecked(True)
        self.cb_logout.setChecked(True)

        row_layout.addWidget(self.cb_disable)
        row_layout.addWidget(self.cb_login)
        row_layout.addWidget(self.cb_logout)
        row_layout.addStretch()

        self.filter_layout.addWidget(row)
        main_layout.addWidget(self.filter_panel)

        # Анимация разворачивания/сворачивания фильтра
        self.filter_anim = QPropertyAnimation(self.filter_panel, b"maximumHeight", self)
        self.filter_anim.setDuration(180)
        self.filter_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.btn_filter.toggled.connect(self.toggle_filter_panel)

        # При изменении фильтров — пересчитываем видимость строк
        self.cb_disable.toggled.connect(self.apply_filters)
        self.cb_login.toggled.connect(self.apply_filters)
        self.cb_logout.toggled.connect(self.apply_filters)

        # ================== 2) Таблица ==================
        self.table = QTableWidget()

        # Флаг, чтобы не обрабатывать on_table_item_changed при массовом заполнении
        self._filling_table = False
        self.table.itemChanged.connect(self.on_table_item_changed)

        # Разрешаем редактирование только двойным кликом/Enter
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["", "Номер телефона", "Статус", "Комментарий", "Действие"])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)

        # Заголовок с Select-All чекбоксом
        self.header = CheckBoxHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(self.header)
        self.header.clicked.connect(self.on_header_checkbox_clicked)

        # Настройки ширин колонок
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

        # Стили кнопок (иконок и "run")
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
        style_run_btn = """
                QPushButton {
                    border: 1px solid white; 
                    background-color: transparent; 
                }
                QPushButton:hover {
                    background-color: rgba(0, 120, 215, 40);
                    border-radius: 4px;
                }
                """
        self.style_run_btn_disabled = """
        QPushButton {
            border: 1px solid #888;
            background-color: #d0d0d0;
            color: #777;
        }
        """

        self.style_icon_btn = style_btn
        self.style_run_btn = style_run_btn

        # Загружаем аккаунты после первого цикла событий Qt (чтобы UI успел показаться)
        QTimer.singleShot(0, self.load_accounts)

        # Флаг завершения приложения (важно, чтобы не трогать UI после закрытия)
        self._closing = False

        # phone10 -> asyncio.Task (запущенный browser task)
        self._browser_tasks = {}

        # phone10 -> BrowserController (контроллер браузера)
        self._browser_controllers = {}

        # Пул прокси (выдаёт свободные прокси, меняет IP, возвращает)
        self.proxy_pool = ProxyPool()

        # phone10 -> proxy_id (чтобы потом release прокси)
        self._account_proxy = {}

        # phone10 -> ip (для простой уникальности IP между аккаунтами)
        self._account_ip: dict[str, str] = {}

    @staticmethod
    async def _get_accounts_for_table():
        """
        Читает из БД список аккаунтов для таблицы:
        phone, comment, status.
        Возвращает список строк (tuple).
        """
        async with Database().get_session() as session:
            stmt = select(Account.phone, Account.comment, Account.status).order_by(Account.phone.desc())
            res = await session.execute(stmt)
            return res.all()

    @asyncSlot()
    async def load_accounts(self) -> None:
        """
        Загружает данные из БД и заполняет таблицу.
        asyncSlot позволяет безопасно вызывать из Qt-сигналов.
        """
        rows = await self._get_accounts_for_table()
        self.fill_table(rows)

    def fill_table(self, rows) -> None:
        """
        Полностью перерисовывает таблицу по данным rows:
        - чекбокс в 0-й колонке
        - phone/status/comment
        - кнопки run/settings/delete
        - подсветка статуса цветом
        Также в конце применяет фильтры и сбрасывает чекбокс заголовка.
        """
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

            # При изменении чекбокса строки — обновляем подсветку + состояние header checkbox
            checkbox.stateChanged.connect(lambda _s, cb=checkbox: self.on_row_checkbox_changed(cb))

            # Форматируем телефон для отображения
            phone_view = self._format_phone_ru(phone)

            # ---------- ДАННЫЕ ----------
            item_phone = QTableWidgetItem(phone_view)
            # В UserRole храним оригинальный phone10 (чтобы удобно обращаться к БД/профилю)
            item_phone.setData(Qt.UserRole, phone)
            item_phone.setFlags(item_phone.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, item_phone)

            item_status = QTableWidgetItem(status or "")
            item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, item_status)

            item_comment = QTableWidgetItem(comment or "")
            self.table.setItem(row, 3, item_comment)

            # ---------- КНОПКИ В ЯЧЕЙКЕ ----------
            btn_run = QPushButton()
            btn_run.setFixedSize(105, 25)
            btn_run.setStyleSheet(self.style_run_btn)

            st = (status or "").strip().lower()
            btn_run.setText(self.run_btn_text.get(st, "Запуск"))

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
                status_colors = {
                    "disable": QColor(255, 0, 0, 35),   # красный (не активирован)
                    "login": QColor(0, 200, 0, 35),     # зелёный (готов к запуску)
                    "logout": QColor(255, 200, 0, 35),  # жёлтый (нужно логиниться)
                }
                color = status_colors.get(st)
                if color:
                    item_status.setBackground(color)

            # ---------- обработчики ----------
            # Важно: передаём row и кнопку, чтобы потом восстановить UI
            btn_run.clicked.connect(lambda _, r=row, b=btn_run: self.on_run_clicked_row(r, b))
            btn_settings.clicked.connect(lambda _, r=row: self.on_settings_clicked(r))
            btn_delete.clicked.connect(lambda _, r=row: self.on_delete_clicked(r))

        # Применяем фильтры после заполнения
        self.apply_filters()

        self.table.blockSignals(False)
        self._filling_table = False

        # Сброс header checkbox
        self.header.setState(Qt.Unchecked)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)

    def create_menu_bar(self) -> None:
        """
        Создаёт меню приложения:
        - Файл (Открыть/Сохранить/Выход)
        - Настройки (ProxyManager)
        - Справка (О программе)
        """
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Файл")
        settings_menu = menu_bar.addMenu("Настройки")
        help_menu = menu_bar.addMenu("Справка")

        # Рисуем линию под менюшкой
        self.menuBar().setStyleSheet("""
        QMenuBar {
            border-bottom: 1px solid #d0d0d0;
        }
        """)

        # Actions
        open_action = QAction("Открыть", self)
        save_action = QAction("Сохранить", self)
        exit_action = QAction("Выход", self)

        settings_action = QAction("ProxyManager", self)
        about_action = QAction("О программе", self)

        # Обработчики
        exit_action.triggered.connect(self.close)
        settings_action.triggered.connect(self.open_settings)

        # Заполняем меню
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        settings_menu.addAction(settings_action)
        help_menu.addAction(about_action)

    def toggle_filter_panel(self, opened: bool) -> None:
        """
        Показывает/скрывает панель фильтра с анимацией по maximumHeight.
        opened=True  -> разворачиваем
        opened=False -> сворачиваем и скрываем в конце анимации
        """
        self.filter_anim.stop()

        # Если ранее подключали finished->hide, отключаем, чтобы не копить слоты
        if self._filter_hide_slot:
            self.filter_anim.finished.disconnect(self._filter_hide_slot)
            self._filter_hide_slot = None

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

            self._filter_hide_slot = _hide
            self.filter_anim.finished.connect(_hide)
            self.filter_anim.start()

    def add_personal_account(self) -> None:
        """
        Открывает диалог добавления аккаунта.
        После сохранения — перезагружает таблицу.
        """
        dlg = AddAccountDialog(self)
        dlg.account_saved.connect(self.load_accounts)
        dlg.exec()

    def open_settings(self) -> None:
        """
        Открывает окно настройки прокси (ProxyManagerDialog).
        """
        dlg = ProxyManagerDialog(self)
        result = dlg.exec()

        if result == QDialog.Accepted:
            print("Настройки сохранены")

    def on_run_clicked_row(self, row: int, btn: QPushButton) -> None:
        """
        Обработчик клика по кнопке "run" в строке.
        По статусу решает, какой режим запускать:
        - disable -> activate_account
        - login   -> start_process
        - logout  -> login_account

        В начале:
        - сохраняет старый текст кнопки
        - блокирует кнопки settings/delete в этой строке
        """
        phone_item = self.table.item(row, 1)
        status_item = self.table.item(row, 2)
        if not phone_item or not status_item:
            return

        phone10 = phone_item.data(Qt.UserRole)
        status = (status_item.text() or "").strip().lower()

        # сохраняем исходный текст, чтобы потом вернуть
        btn.setProperty("old_text", btn.text())

        # блокируем settings/delete на время работы
        self._set_actions_container_enabled(btn, False)

        if status == "disable":
            btn.setText("Активируется…")
            btn.setDisabled(True)
            btn.setStyleSheet(self.style_run_btn_disabled)
            self.activate_account(phone10, btn)

        elif status == "login":
            btn.setText("Запускается…")
            btn.setDisabled(True)
            btn.setStyleSheet(self.style_run_btn_disabled)
            self.start_process(phone10, btn)

        elif status == "logout":
            btn.setText("Входит…")
            btn.setDisabled(True)
            btn.setStyleSheet(self.style_run_btn_disabled)
            self.login_account(phone10, btn)

    def closeEvent(self, event):
        """
        Перехватывает закрытие окна.
        Первый раз: отменяет закрытие и запускает асинхронное выключение:
        - отмена browser tasks
        - закрытие браузеров
        Затем повторно вызывает self.close().
        """
        if self._closing:
            event.accept()
            return

        event.ignore()
        self.setEnabled(False)
        asyncio.create_task(self._shutdown_and_close())

    async def _shutdown_and_close(self):
        """
        Асинхронное завершение:
        1) отменяет все таски браузеров
        2) вызывает ctrl.close() у всех контроллеров
        3) ждёт завершения
        4) ставит флаг _closing и закрывает окно повторно
        """
        tasks = list(self._browser_tasks.values())
        for t in tasks:
            if t and not t.done():
                t.cancel()

        close_tasks = [ctrl.close() for ctrl in self._browser_controllers.values()]

        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*close_tasks, return_exceptions=True)

        self._closing = True
        self.setEnabled(True)
        self.close()

    async def _run_account_with_proxy(self, phone10: str, btn: QPushButton, mode: str) -> None:
        """
        Универсальный запуск аккаунта с прокси и контролем уникальности IP:
        - проверяет, не запущен ли уже аккаунт
        - берёт UA из БД
        - берёт прокси из pool + получает IP
        - проверяет уникальность IP относительно других запущенных аккаунтов
        - создаёт BrowserController и asyncio.Task
        - в done_callback делает cleanup: release proxy, очистка ip, восстановление UI
        """
        print(f"{mode.upper()}", phone10)

        # Защита от повторного запуска
        old_task = self._browser_tasks.get(phone10)
        if old_task and not old_task.done():
            self._show_warning("Запуск", f"Аккаунт {phone10} уже запущен")
            return

        # 1) Берём user-agent из БД
        account = await self._get_account_by_phone(phone10)
        ua = (account.get("user_agent") if account else "") or ""

        # 2) Берём прокси и его текущий IP
        proxy, ip, msg = await self.proxy_pool.acquire_unique()
        print(f"[proxy] {msg}")

        # Если прокси не выдали — восстанавливаем UI и выходим
        if not proxy:
            if not self._closing:
                self._show_warning("Прокси", msg)
            self._restore_btn(btn)
            self._set_actions_container_enabled(btn, True)
            return

        # 2.1) Проверяем уникальность IP (простая: среди уже запущенных аккаунтов)
        for other_phone, other_ip in self._account_ip.items():
            if other_ip == ip and other_phone != phone10:
                self._show_warning(
                    "IP не уникален",
                    f"IP {ip} уже используется аккаунтом {other_phone}"
                )

                # Возвращаем прокси обратно в пул
                await self.proxy_pool.release(proxy.id)

                # Восстанавливаем UI
                self._restore_btn(btn)
                self._set_actions_container_enabled(btn, True)
                return

        # 2.2) Сохраняем, что этот аккаунт использует такой IP/прокси
        self._account_ip[phone10] = ip
        self._account_proxy[phone10] = proxy.id

        print(f"[{phone10}] mode={mode}, proxy_id={proxy.id}, ip={ip}")

        # 3) Запускаем браузер через контроллер
        controller = BrowserController(
            profile_name=phone10,
            user_agent=ua,
            proxy=proxy,
        )
        self._browser_controllers[phone10] = controller

        task = asyncio.create_task(controller.run(mode=mode))
        self._browser_tasks[phone10] = task

        # Cleanup после завершения задачи
        def _cleanup(t: asyncio.Task):
            async def _async_cleanup():
                # 1) гасим исключения/отмену (чтобы не падало в callback)
                try:
                    t.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

                # 2) освобождаем прокси
                proxy_id = self._account_proxy.pop(phone10, None)
                if proxy_id is not None:
                    await self.proxy_pool.release(proxy_id)

                # 3) убираем IP аккаунта
                self._account_ip.pop(phone10, None)

                # 4) восстанавливаем UI (если окно не закрывается)
                if not self._closing:
                    old_text = btn.property("old_text") or "Запуск"
                    btn.setText(old_text)
                    btn.setDisabled(False)
                    btn.setStyleSheet(self.style_run_btn)
                    self._set_actions_container_enabled(btn, True)

                # 5) чистим ссылки на таск/контроллер
                self._browser_tasks.pop(phone10, None)
                self._browser_controllers.pop(phone10, None)

            asyncio.create_task(_async_cleanup())

        task.add_done_callback(_cleanup)

    @asyncSlot()
    async def activate_account(self, phone10: str, btn: QPushButton) -> None:
        """
        Запуск аккаунта в режиме "activate".
        """
        await self._run_account_with_proxy(phone10, btn, mode="activate")

    @asyncSlot()
    async def start_process(self, phone10: str, btn: QPushButton) -> None:
        """
        Запуск аккаунта в режиме "start_process".
        """
        await self._run_account_with_proxy(phone10, btn, mode="start_process")

    @asyncSlot()
    async def login_account(self, phone10: str, btn: QPushButton) -> None:
        """
        Запуск аккаунта в режиме "login".
        """
        await self._run_account_with_proxy(phone10, btn, mode="login")

    def _restore_btn(self, btn: QPushButton) -> None:
        """
        Восстанавливает кнопку run в исходное состояние:
        - текст
        - enabled
        - стиль
        + возвращает доступ к settings/delete
        """
        old_text = btn.property("old_text") or "Запуск"
        btn.setText(old_text)
        btn.setDisabled(False)
        btn.setStyleSheet(self.style_run_btn)

        self._set_actions_container_enabled(btn, True)

    @asyncSlot()
    async def on_settings_clicked(self, row: int) -> None:
        """
        Открывает диалог редактирования аккаунта для выбранной строки.
        - на время открытия блокирует таблицу
        - загружает данные аккаунта из БД
        - если аккаунт не найден — показывает предупреждение
        """
        self.table.setDisabled(True)

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

        self.table.setDisabled(False)

    async def delete_account_async(self, phone10: str) -> None:
        """
        Удаляет аккаунт из БД по phone10 и затем обновляет таблицу.
        """
        async with Database().get_session() as session:
            await session.execute(delete(Account).where(Account.phone == phone10))
            await session.commit()

        await self.load_accounts()

    def on_delete_clicked(self, row: int) -> None:
        """
        Показывает подтверждение удаления.
        При подтверждении — запускает async-удаление через asyncio.create_task.
        """
        phone_item = self.table.item(row, 1)
        if not phone_item:
            return

        phone10 = phone_item.data(Qt.UserRole)
        if not phone10:
            return

        reply = QMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранный аккаунт? Аккаунт будет удален из "
            "базы данных без возможности восстановления",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            asyncio.create_task(self.delete_account_async(phone10))

    def _row_checkbox(self, row: int) -> QCheckBox | None:
        """
        Возвращает QCheckBox, который находится в 0-й колонке указанной строки.
        """
        w = self.table.cellWidget(row, 0)
        return w.findChild(QCheckBox) if w else None

    def on_header_checkbox_clicked(self, state: Qt.CheckState) -> None:
        """
        Клик по чекбоксу в заголовке:
        - отмечает/снимает все строки
        - подсвечивает строки
        - выставляет header state (Checked/Unchecked)
        """
        checked = (state == Qt.Checked)

        self.table.setUpdatesEnabled(False)

        bg = QColor(0, 120, 215, 40) if checked else QColor(0, 0, 0, 0)

        for row in range(self.table.rowCount()):
            cb = self._row_checkbox(row)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)

            # Подсветка всех ячеек кроме колонки статуса (2)
            for col in range(self.table.columnCount()):
                if col == 2:
                    continue
                it = self.table.item(row, col)
                if it:
                    it.setBackground(bg)

            # И подсветка контейнера с кнопками
            widget = self.table.cellWidget(row, 4)
            if widget:
                widget.setStyleSheet("background-color: rgba(0, 120, 215, 40);" if checked else "")

        self.table.setUpdatesEnabled(True)
        self.header.setState(Qt.Checked if checked else Qt.Unchecked)

    def _show_warning(self, title: str, text: str) -> None:
        """
        Показывает QMessageBox.warning через QTimer.singleShot,
        чтобы не конфликтовать с потоками/циклами Qt/asyncio.
        """
        QTimer.singleShot(0, lambda: QMessageBox.warning(self, title, text))

    def on_row_checkbox_changed(self, checkbox: QCheckBox) -> None:
        """
        Обработчик изменения чекбокса строки:
        - включает/выключает подсветку строки
        - пересчитывает состояние header чекбокса (unchecked/partial/checked)
        """
        container = checkbox.parentWidget()
        index = self.table.indexAt(container.pos())
        row = index.row()
        if row < 0:
            return

        is_checked = checkbox.isChecked()
        bg = QColor(0, 120, 215, 40) if is_checked else QColor(0, 0, 0, 0)

        # Подсветка ячеек строки (кроме статуса)
        for col in range(self.table.columnCount()):
            if col == 2:
                continue
            it = self.table.item(row, col)
            if it:
                it.setBackground(bg)

        # Подсветка контейнера действий
        widget = self.table.cellWidget(row, 4)
        if widget:
            widget.setStyleSheet("background-color: rgba(0, 120, 215, 40);" if is_checked else "")

        # Пересчёт состояния header checkbox
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

    def on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """
        Срабатывает при изменении ячейки таблицы.
        Здесь сохраняем только колонку комментария (col == 3) в БД.
        """
        if self._filling_table:
            return

        row = item.row()
        col = item.column()

        # Сохраняем только комментарий
        if col != 3:
            return

        phone_item = self.table.item(row, 1)
        if not phone_item:
            return

        phone10 = phone_item.data(Qt.UserRole)
        if not phone10:
            return

        new_comment = item.text().strip()
        asyncio.create_task(self._save_comment_async(phone10, new_comment))

    def _norm_status(self, s: str) -> str:
        """
        Нормализует статус: lower + strip, чтобы сравнения были стабильными.
        """
        return (s or "").strip().lower()

    def apply_filters(self) -> None:
        """
        Применяет фильтрацию таблицы:
        1) по статусам (чекбоксы disable/login/logout)
        2) по тексту поиска (в телефоне и комментарии)
        """
        # --- 1) статусы, которые разрешены ---
        allowed = set()
        if self.cb_disable.isChecked():
            allowed.add("disable")
        if self.cb_login.isChecked():
            allowed.add("login")
        if self.cb_logout.isChecked():
            allowed.add("logout")

        # если ничего не выбрано — показываем всё
        status_show_all = (len(allowed) == 0)

        # --- 2) текст поиска ---
        text = self.search_input.text().strip().lower()
        clean_text = ''.join(filter(str.isdigit, text))

        for row in range(self.table.rowCount()):
            # статус из колонки 2
            st_item = self.table.item(row, 2)
            st = self._norm_status(st_item.text() if st_item else "")
            status_ok = status_show_all or (st in allowed)

            # поиск по телефону и комменту
            if not text:
                search_ok = True
            else:
                phone_item = self.table.item(row, 1)
                comment_item = self.table.item(row, 3)

                phone = phone_item.text().lower() if phone_item else ""
                comment = comment_item.text().lower() if comment_item else ""

                clean_phone = ''.join(filter(str.isdigit, phone))
                match_phone = (text in phone) or (clean_text and clean_text in clean_phone)
                match_comment = text in comment
                search_ok = match_phone or match_comment

            # итог: показываем только если оба условия true
            self.table.setRowHidden(row, not (status_ok and search_ok))

    def filter_table(self, text: str) -> None:
        """
        Совместимость/старый вызов: просто применяет фильтры.
        """
        self.apply_filters()

    def _set_actions_container_enabled(self, run_btn: QPushButton, enabled: bool) -> None:
        """
        Включает/выключает кнопки settings/delete в той же ячейке, где run_btn.
        Сам run_btn не трогаем — он управляется отдельно.
        """
        container = run_btn.parentWidget()
        if not container:
            return

        for b in container.findChildren(QPushButton):
            if b is run_btn:
                continue
            b.setEnabled(enabled)

    @staticmethod
    def _format_phone_ru(phone10: str) -> str:
        """
        Форматирует 10 цифр в вид +7 XXX-XXX-XX-XX.
        Если цифр не 10 — возвращает как есть.
        """
        digits = ''.join(filter(str.isdigit, phone10))
        if len(digits) != 10:
            return phone10
        return f"+7 {digits[0:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:10]}"

    @staticmethod
    async def _save_comment_async(phone10: str, comment: str) -> None:
        """
        Сохраняет комментарий аккаунта в БД по phone10.
        """
        async with Database().get_session() as session:
            await session.execute(
                update(Account).where(Account.phone == phone10).values(comment=comment)
            )
            await session.commit()

    async def _get_account_by_phone(self, phone10: str) -> dict | None:
        """
        Берёт данные аккаунта из БД по phone10.
        Возвращает dict для удобной передачи в диалог/логику.
        """
        async with Database().get_session() as session:
            res = await session.execute(
                select(
                    Account.phone,
                    Account.name,
                    Account.male,
                    Account.user_agent,
                    Account.comment
                ).where(Account.phone == phone10)
            )
            row = res.first()

            if not row:
                return None

            phone, name, male, user_agent, comment = row

            return {
                "phone10": phone,
                "phone_view": self._format_phone_ru(phone),
                "name": name or "",
                "gender": male or None,
                "user_agent": user_agent or "",
                "comment": comment or "",
            }

