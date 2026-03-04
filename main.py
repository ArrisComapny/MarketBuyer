import asyncio

from PySide6.QtCore import Qt
from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor

from utils.logger import AppLogger
from gui.login_window import LoginWindow
from utils.messagebox import CustomMessageBox
from core.app import init_application, DBConnectionError


login_window: LoginWindow | None = None

def apply_fixed_theme(application: QApplication) -> None:
    application.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(255, 105, 180))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    application.setPalette(palette)

    application.setStyleSheet("""
    QHeaderView::section {
        background-color: #333;
        color: white;
        padding: 6px;
        border: 1px solid #444;
    }
    QTableWidget {
        gridline-color: #444;
    }
    QPushButton {
        background-color: #3a3a3a;
        border: 1px solid #555;
        padding: 6px 10px;
        border-radius: 6px;
    }
    QPushButton:hover {
        background-color: #4a4a4a;
    }
    QLineEdit, QComboBox {
        background-color: #222;
        border: 1px solid #555;
        padding: 6px;
        border-radius: 6px;
        color: white;
    }
    """)

if __name__ == "__main__":
    AppLogger.setup()
    app = QApplication([])
    apply_fixed_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    async def start() -> None:
        global login_window

        login_window = LoginWindow()
        login_window.set_loading(True, "Подключение к базе данных...")
        login_window.show()

        try:
            await init_application()
        except DBConnectionError as e:
            CustomMessageBox.critical(login_window, "Ошибка БД", str(e))
            app.quit()
            return
        except Exception as e:
            CustomMessageBox.critical(login_window, "Ошибка", repr(e))
            app.quit()
            return

        login_window.set_loading(False)

    loop.create_task(start())

    with loop:
        loop.run_forever()
