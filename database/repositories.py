from __future__ import annotations

import asyncio
import datetime

from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, insert, desc, distinct

from database.models import Account, UsersAccounts, PhoneCode, User, Proxy


class UserRepo:
    @staticmethod
    async def get_active_user(session, login: str, password: str):
        res = await session.execute(
            select(User).where(User.login == login, User.password == password, User.status.is_(True))
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def get_all_managers(session: AsyncSession):
        res = await session.execute(
            select(User)
            .where(User.status.is_(True), User.role != "admin")
            .order_by(User.login.asc())
        )
        return res.scalars().all()


class ProxyRepo:

    @staticmethod
    async def get_proxies(session: AsyncSession, *, user_login: str, is_admin: bool) -> Sequence[Proxy]:
        stmt = select(Proxy).order_by(Proxy.id.desc())

        if not is_admin:
            stmt = (
                select(Proxy)
                .where(Proxy.owner_login == user_login)
                .order_by(Proxy.id.desc())
            )

        res = await session.execute(stmt)
        return res.scalars().all()

    @staticmethod
    async def set_active(session: AsyncSession, proxy_id: int, active: bool) -> None:
        await session.execute(
            update(Proxy).where(Proxy.id == proxy_id).values(active=bool(active))
        )

    @staticmethod
    async def get_proxy_by_id(session: AsyncSession, proxy_id: int) -> Proxy | None:
        return await session.get(Proxy, proxy_id)

    @staticmethod
    async def delete_proxy_by_id(session: AsyncSession, proxy_id: int) -> bool:
        proxy = await session.get(Proxy, proxy_id)
        if not proxy:
            return False
        await session.delete(proxy)
        return True

    @staticmethod
    async def add_proxy(
            session: AsyncSession,
            host: str,
            port: str,
            login: str,
            password: str,
            proxy_scheme: str,
            change_ip_url: str,
            owner_login: str | None = None,  # ✅ добавили
    ) -> None:
        proxy = Proxy(
            host=host,
            port=port,
            login=login,
            password=password,
            proxy_scheme=proxy_scheme,
            change_ip_url=change_ip_url,
            owner_login=owner_login,  # ✅ записали
        )
        session.add(proxy)


class AccountRepo:
    @staticmethod
    async def get_used_user_agents(session: AsyncSession) -> list[str]:
        res = await session.execute(
            select(distinct(Account.user_agent))
            .where(Account.user_agent.isnot(None), Account.user_agent != "")
        )
        return list(res.scalars().all())

    @staticmethod
    async def get_used_names(session: AsyncSession) -> list[str]:
        res = await session.execute(
            select(distinct(Account.name)).where(Account.name.isnot(None), Account.name != "")
        )
        return list(res.scalars().all())

    @staticmethod
    async def get_list_accounts(session, *, user_login: str, is_admin: bool):
        stmt = (
            select(Account.phone, UsersAccounts.user, Account.comment, Account.status)
            .join(UsersAccounts, UsersAccounts.phone == Account.phone)
            .order_by(Account.phone.desc())
        )

        if not is_admin:
            stmt = stmt.where(UsersAccounts.user == user_login)

        res = await session.execute(stmt)
        return res.all()

    @staticmethod
    async def get_account_dict(session: AsyncSession, phone10: str) -> dict | None:
        res = await session.execute(
            select(Account.phone, Account.name, Account.male, Account.user_agent, Account.comment, Account.status)
            .where(Account.phone == phone10)
        )
        row = res.first()
        if not row:
            return None

        phone, name, male, user_agent, comment, status = row
        return {
            "phone10": phone,
            "name": name or "",
            "gender": male or None,
            "user_agent": user_agent or "",
            "comment": comment or "",
            "status": status or "",
        }

    @staticmethod
    async def add_account(session: AsyncSession,
                          phone10: str,
                          name: str,
                          gender: str,
                          user_agent: str,
                          comment: str) -> None:
        acc = Account(phone=phone10, name=name, male=gender, user_agent=user_agent, comment=comment)
        session.add(acc)

    @staticmethod
    async def update_account(session: AsyncSession,
                             old_phone10: str,
                             phone10: str,
                             name: str,
                             gender: str,
                             user_agent: str,
                             comment: str) -> None:
        await session.execute(
            update(Account)
            .where(Account.phone == old_phone10)
            .values(phone=phone10, name=name, male=gender, user_agent=user_agent, comment=comment)
        )

    @staticmethod
    async def update_profile(session: AsyncSession, phone10: str, name: str, gender: str | None) -> None:
        await session.execute(
            update(Account)
            .where(Account.phone == phone10)
            .values(name=name, male=gender.capitalize())
        )

    @staticmethod
    async def set_comment(session: AsyncSession, phone10: str, comment: str) -> None:
        await session.execute(update(Account).where(Account.phone == phone10).values(comment=comment))

    @staticmethod
    async def set_status(session: AsyncSession, phone10: str, status: str) -> None:
        await session.execute(update(Account).where(Account.phone == phone10).values(status=status))

    @staticmethod
    async def delete_account_by_phone(session: AsyncSession, phone10: str) -> None:
        await session.execute(delete(Account).where(Account.phone == phone10))

    @staticmethod
    async def delete_selected_accounts(session: AsyncSession, phones: list[str]) -> None:
        await session.execute(delete(Account).where(Account.phone.in_(phones)))


class UsersAccountsRepo:
    @staticmethod
    async def set_users_accounts(session: AsyncSession, phone10: str, login: str) -> None:
        res = await session.execute(select(UsersAccounts).where(UsersAccounts.phone == phone10))
        row = res.scalars().first()

        if row is None:
            await session.execute(insert(UsersAccounts).values(phone=phone10, user=login))
        else:
            await session.execute(update(UsersAccounts).where(UsersAccounts.phone == phone10).values(user=login))

    @staticmethod
    async def delete_link(session: AsyncSession, phone10: str, user_login: str) -> None:
        await session.execute(
            delete(UsersAccounts).where(UsersAccounts.phone == phone10, UsersAccounts.user == user_login)
        )


class PhoneCodeRepo:
    @staticmethod
    async def wait_latest_code(session: AsyncSession,
                               phone10: str,
                               not_older_than_sec: int = 60,
                               retries: int = 20,
                               sleep_sec: int = 5,
                               tz_offset_hours: int = 3) -> str:
        msk = datetime.timezone(datetime.timedelta(hours=tz_offset_hours))
        time_request_aware = datetime.datetime.now(msk) - datetime.timedelta(seconds=not_older_than_sec)
        time_request = time_request_aware.replace(tzinfo=None)

        for _ in range(retries):
            result = await session.execute(
                select(PhoneCode.code)
                .where(PhoneCode.phone == phone10, PhoneCode.time_response >= time_request)
                .order_by(desc(PhoneCode.time_response))
                .limit(1)
            )
            code = result.scalars().first()
            if code:
                return code
            await asyncio.sleep(sleep_sec)

        raise Exception("Код не пришел")
