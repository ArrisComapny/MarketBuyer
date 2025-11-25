from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import DB_URL


class Base(DeclarativeBase):
    """Базовый класс моделей ORM"""
    pass


class Database:
    """
    Класс для работы с асинхронным подключением к PostgreSQL через SQLAlchemy.
    Используется шаблон Singleton, чтобы во всём приложении был один engine/sessionmaker.
    """

    _instance: Optional["Database"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, echo: bool = False):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self.engine = create_async_engine(DB_URL, echo=echo, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession )

    async def init_models(self, base: type[Base]):
        """Создать таблицы, если их ещё нет"""
        async with self.engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self):
        async with self.session_factory() as session:
            yield session

    async def test_connection(self) -> bool:
        """Проверка соединения к БД."""
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
