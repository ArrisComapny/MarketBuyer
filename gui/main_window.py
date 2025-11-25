from PySide6.QtWidgets import QMainWindow, QPushButton
from qasync import asyncSlot

from core.browser import BrowserController


class MainWindow(QMainWindow):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.setWindowTitle(f"MarketBuyer – {user.login}")

        btn = QPushButton("Запуск браузера")
        btn.clicked.connect(self.run_browser)
        self.setCentralWidget(btn)

    @asyncSlot()
    async def run_browser(self):
        browser = BrowserController()
        await browser.run()
