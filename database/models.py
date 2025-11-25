from datetime import datetime

from sqlalchemy import Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


class User(Base):
    __tablename__ = "users"

    login: Mapped[str] = mapped_column(String(20), primary_key=True)
    password: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)

    accounts_link: Mapped[list["UsersAccounts"]] = relationship(back_populates="user_ref", cascade="all, delete-orphan")

    accounts: Mapped[list["Account"]] = relationship(secondary="users_accounts", back_populates="users", viewonly=True)


class Account(Base):
    __tablename__ = "accounts"

    phone: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    male: Mapped[str] = mapped_column(String(20), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(200), nullable=False)

    users_link: Mapped[list["UsersAccounts"]] = relationship(back_populates="account_ref", cascade="all, delete-orphan")

    users: Mapped[list["User"]] = relationship(secondary="users_accounts", back_populates="accounts", viewonly=True)


class UsersAccounts(Base):
    __tablename__ = "users_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String(20), ForeignKey("users.login", ondelete="CASCADE"), nullable=False)
    phone: Mapped[str] = mapped_column(String(10), ForeignKey("accounts.phone", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(20), nullable=False)

    user_ref: Mapped["User"] = relationship("User", back_populates="accounts_link")
    account_ref: Mapped["Account"] = relationship("Account", back_populates="users_link")


class PhoneMessage(Base):
    __tablename__ = "phone_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(10), nullable=False)
    event_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sender: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)

class Proxy(Base):
    __tablename__ = "proxies"

    proxy: Mapped[str] = mapped_column(String(100), primary_key=True, nullable=False)
    change_ip_url: Mapped[str] = mapped_column(String(255), nullable=False)
