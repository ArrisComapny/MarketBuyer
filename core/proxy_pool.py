import asyncio
import aiohttp
import random
from sqlalchemy import select

from database.db import Database
from database.models import Proxy


class ProxyPool:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._busy: set[int] = set()

        # ✅ Кэш активных прокси
        self._proxies_cache: dict[tuple[str, bool], list[Proxy]] = {}

    # =========================
    # КЭШ
    # =========================

    def invalidate_cache(self, user_login: str | None = None) -> None:
        """
        Сбросить кэш.
        user_login=None -> сбросить весь кэш
        user_login='vasya' -> сбросить кэш только этого пользователя (и admin/не-admin ключи)
        """
        if user_login is None:
            self._proxies_cache.clear()
            return

        for key in list(self._proxies_cache.keys()):
            if key[0] == user_login:
                self._proxies_cache.pop(key, None)

    async def _load_proxies(self, *, user_login: str, is_admin: bool) -> list[Proxy]:
        """
        Загружает ТОЛЬКО активные прокси.
        Для user -> только owner_login == user_login
        Для admin -> все активные
        Кэшируется по (user_login, is_admin)
        """
        key = (user_login, is_admin)
        if key in self._proxies_cache:
            return self._proxies_cache[key]

        async with Database().get_session() as session:
            stmt = (
                select(Proxy)
                .where(Proxy.active.is_(True))
            )

            if not is_admin:
                stmt = stmt.where(Proxy.owner_login == user_login)

            stmt = stmt.order_by(Proxy.id.asc())

            res = await session.execute(stmt)
            proxies = res.scalars().all()

        self._proxies_cache[key] = proxies
        return proxies

    # =========================
    # IP ROTATION
    # =========================

    @staticmethod
    async def _change_ip(proxy: Proxy) -> tuple[bool, str]:
        url = (proxy.change_ip_url or "").strip()
        if not url:
            return True, "change_ip_url пустой — смена IP пропущена"

        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False,
                ) as r:
                    if r.status != 400:
                        return True, "IP сменён"
                    return False, f"Смена IP не удалась (HTTP {r.status})"
        except Exception as e:
            return False, f"Смена IP ошибка: {e}"

    # =========================
    # ОСВОБОЖДЕНИЕ
    # =========================

    async def release(self, proxy_id: int) -> None:
        async with self._lock:
            self._busy.discard(proxy_id)

    # =========================
    # MASS ACQUIRE
    # =========================

    async def acquire_mass(
            self,
            *,
            user_login: str,
            is_admin: bool,
            rotate_total_wait_sec: int = 120,
            rotate_interval_sec: int = 20,
            rotate_wait_after_ok_sec: int = 5,
            require_rotate: bool = True,
            wait_free_total_sec: int = 120,
            wait_free_interval_sec: int = 20,
    ) -> tuple[Proxy | None, str]:

        last_err = "Неизвестная ошибка"

        # Ждём свободный прокси
        deadline_free = asyncio.get_event_loop().time() + wait_free_total_sec

        while True:
            proxies = await self._load_proxies(user_login=user_login, is_admin=is_admin)

            async with self._lock:
                free = [p for p in proxies if p.id not in self._busy]
                if free:
                    random.shuffle(free)
                    break

            if asyncio.get_event_loop().time() >= deadline_free:
                return None, "Все прокси заняты (таймаут ожидания)"

            await asyncio.sleep(wait_free_interval_sec)

        # Пытаемся выдать один
        for proxy in free:
            async with self._lock:
                if proxy.id in self._busy:
                    continue
                self._busy.add(proxy.id)

            try:
                if not require_rotate:
                    return proxy, f"Proxy {proxy.id} выдан"

                deadline_rotate = asyncio.get_event_loop().time() + rotate_total_wait_sec

                while True:
                    ok, msg = await self._change_ip(proxy)

                    if ok:
                        if rotate_wait_after_ok_sec > 0:
                            await asyncio.sleep(rotate_wait_after_ok_sec)
                        return proxy, f"Proxy {proxy.id} выдан ({msg})"

                    last_err = msg

                    if asyncio.get_event_loop().time() >= deadline_rotate:
                        await self.release(proxy.id)
                        break

                    await asyncio.sleep(rotate_interval_sec)

            except asyncio.CancelledError:
                await self.release(proxy.id)
                raise

            except Exception as e:
                last_err = str(e)
                await self.release(proxy.id)

        return None, f"Не удалось выдать прокси. Последняя ошибка: {last_err}"

    # =========================
    # SINGLE ACQUIRE
    # =========================

    async def acquire(
            self,
            user_login: str,
            is_admin: bool,
            require_rotate: bool = True,
            rotate_wait_sec: int = 5,
            rotate_retries: int = 3,
    ) -> tuple[Proxy | None, str]:

        proxies = await self._load_proxies(user_login=user_login, is_admin=is_admin)
        last_err = "Неизвестная ошибка"

        async with self._lock:
            free = [p for p in proxies if p.id not in self._busy]
            if not free:
                return None, "Все прокси заняты"

            random.shuffle(free)

        # Делаем несколько кругов по всем свободным прокси
        for _ in range(rotate_retries):
            for proxy in free:
                async with self._lock:
                    if proxy.id in self._busy:
                        continue
                    self._busy.add(proxy.id)

                try:
                    if not require_rotate:
                        return proxy, f"Proxy {proxy.id} выдан"

                    ok, msg = await self._change_ip(proxy)
                    if ok:
                        if rotate_wait_sec > 0:
                            await asyncio.sleep(rotate_wait_sec)
                        return proxy, f"Proxy {proxy.id} выдан ({msg})"

                    last_err = msg
                    await self.release(proxy.id)

                except asyncio.CancelledError:
                    await self.release(proxy.id)
                    raise

                except Exception as e:
                    last_err = str(e)
                    await self.release(proxy.id)

        return None, f"Не удалось выдать прокси. Последняя ошибка: {last_err}"

    # =========================
    # CAPACITY
    # =========================

    async def capacity(self, *, user_login: str, is_admin: bool) -> int:
        proxies = await self._load_proxies(user_login=user_login, is_admin=is_admin)
        return len(proxies)

