from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
)
from PySide6.QtCore import Qt


class AllActivationDialog(QDialog):
    def __init__(self, parent=None, counts: dict[str, int] | None = None):
        super().__init__(parent)

        # ================== DATA ==================
        counts = counts or {}
        total_all = int(counts.get("total_all", 0))
        total_sel = int(counts.get("total_selected", 0))
        disable_n = int(counts.get("disable", 0))
        logout_n = int(counts.get("logout", 0))
        login_n = int(counts.get("login", 0))
        unknown_n = int(counts.get("unknown", 0))

        # ================== STATE ==================
        self._running = False  # 👈 состояние запуска

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

        # ---------- RIGHT (ПУСТАЯ ТАБЛИЦА) ----------
        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setRowCount(12)  # временно, просто сетка
        self.table.setHorizontalHeaderLabels(["Телефон","Статус", "%", "Шаг"])

        self.table.verticalHeader().setVisible(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(True)



        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 90)

        # заполняем пустыми ячейками, чтобы была сетка
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                it = QTableWidgetItem("")
                if c == 1:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                else:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, it)

        mid.addWidget(left_box, 0)
        mid.addWidget(self.table, 1)
        root.addLayout(mid, 1)

        # ================== BOTTOM BUTTON ==================
        bottom = QHBoxLayout()
        bottom.addStretch()

        self.btn_start = QPushButton("Запустить")
        self.btn_start.setMinimumSize(260, 44)
        self.btn_start.clicked.connect(self.on_start_clicked)

        bottom.addWidget(self.btn_start)
        bottom.addStretch()
        root.addLayout(bottom)

    # ================== BUTTON LOGIC (UI ONLY) ==================
    def on_start_clicked(self) -> None:
        if not self._running:
            # Нажали "Запустить"
            self._running = True
            self.btn_start.setText("Отмена")
        else:
            # Нажали "Отмена"
            self._running = False

