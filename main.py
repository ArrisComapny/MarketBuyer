import sys
import asyncio
from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

from gui.login_window import LoginWindow
from core.app import init_application, DBConnectionError
from utils.messagebox import CustomMessageBox


login_window: LoginWindow | None = None

def apply_fixed_theme(app: QApplication):
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.Highlight, QColor(255, 105, 180))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    app.setStyleSheet("""
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
    app = QApplication([])
    apply_fixed_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    async def start():
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
