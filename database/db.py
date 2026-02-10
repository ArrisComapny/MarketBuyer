from __future__ import annotations

from typing import Optional, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine

from config import DB_URL


class Base(DeclarativeBase):
    """Базовый класс для ORM-моделей SQLAlchemy."""
    pass


class Database:
    _instance: Optional["Database"] = None

    def __new__(cls, *args, **kwargs) -> "Database":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, echo: bool = False) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.engine: AsyncEngine = create_async_engine(
            DB_URL,
            echo=echo,
            pool_pre_ping=True,
        )

        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def init_models(self, base: type[Base]) -> None:
        """Создаёт таблицы (base.metadata.create_all), если их ещё нет."""
        async with self.engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Контекст-менеджер для безопасной работы с сессией."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def test_connection(self) -> bool:
        """Проверка соединения с БД."""
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False
