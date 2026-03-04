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
        self._proxies_cache: list[Proxy] | None = None

    # =========================
    # КЭШ
    # =========================

    def invalidate_cache(self) -> None:
        """Сбросить кэш активных прокси (вызывать после изменений в БД)."""
        self._proxies_cache = None

    async def _load_proxies(self) -> list[Proxy]:
        """
        Загружает ТОЛЬКО активные прокси.
        Использует кэш, чтобы не дёргать БД постоянно.
        """
        if self._proxies_cache is not None:
            return self._proxies_cache

        async with Database().get_session() as session:
            res = await session.execute(
                select(Proxy)
                .where(Proxy.active.is_(True))
                .order_by(Proxy.id.asc())
            )
            proxies = res.scalars().all()

        self._proxies_cache = proxies
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
            proxies = await self._load_proxies()

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
        require_rotate: bool = True,
        rotate_wait_sec: int = 5,
        rotate_retries: int = 3,
    ) -> tuple[Proxy | None, str]:

        proxies = await self._load_proxies()
        last_err = "Неизвестная ошибка"

        async with self._lock:
            free = [p for p in proxies if p.id not in self._busy]
            if not free:
                return None, "Все прокси заняты"

            random.shuffle(free)

        for proxy in free:
            async with self._lock:
                if proxy.id in self._busy:
                    continue
                self._busy.add(proxy.id)

            try:
                if require_rotate:
                    for _ in range(rotate_retries):
                        ok, msg = await self._change_ip(proxy)
                        if ok:
                            if rotate_wait_sec > 0:
                                await asyncio.sleep(rotate_wait_sec)
                            break
                        last_err = msg
                    else:
                        await self.release(proxy.id)
                        continue

                return proxy, f"Proxy {proxy.id} выдан"

            except Exception as e:
                last_err = str(e)
                await self.release(proxy.id)

        return None, f"Не удалось выдать прокси. Последняя ошибка: {last_err}"

    # =========================
    # CAPACITY
    # =========================

    async def capacity(self) -> int:
        """Сколько активных прокси доступно."""
        proxies = await self._load_proxies()
        return len(proxies)

