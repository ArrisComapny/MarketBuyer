import asyncio
from qasync import QEventLoop
from PySide6.QtWidgets import QApplication

from gui.login_window import LoginWindow
from core.app import init_application, DBConnectionError
from utils.messagebox import CustomMessageBox


login_window: LoginWindow | None = None


if __name__ == "__main__":
    app = QApplication([])
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
