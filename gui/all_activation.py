from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout)
from PySide6.QtCore import Qt


class AllActivationDialog(QDialog):
    """
    Окно массовой активации аккаунтов.
    Здесь позже будут кнопки и логика.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Активация аккаунтов")
        self.resize(420, 260)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Массовая активация аккаунтов")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")

        layout.addWidget(title)

        info = QLabel(
            "Здесь позже будут кнопки\n"
            "и выбор сценариев активации"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(info)
        layout.addStretch()

        # --- кнопки ---
        btn_row = QHBoxLayout()

        self.btn_start = QPushButton("Запустить")
        self.btn_close = QPushButton("Закрыть")

        self.btn_start.setMinimumHeight(36)
        self.btn_close.setMinimumHeight(36)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

        self.btn_close.clicked.connect(self.reject)