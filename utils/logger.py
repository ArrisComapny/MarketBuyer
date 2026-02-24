import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class AppLogger:
    _initialized = False

    @classmethod
    def setup(cls, level: int = logging.INFO) -> None:
        """
        Инициализация логирования.
        Логи пишутся в /logs/app.log
        С ротацией (5 MB, 5 файлов).
        """
        if cls._initialized:
            return

        project_root = Path(__file__).resolve().parent.parent
        log_dir = project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "app.log"

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # ❗ важно: очищаем старые handlers
        root_logger.handlers.clear()

        # ===== File handler (с ротацией) =====
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # ===== Console handler =====
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        cls._initialized = True

    @staticmethod
    def get(name: str) -> logging.Logger:
        return logging.getLogger(name)
