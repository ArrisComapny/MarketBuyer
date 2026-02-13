import time
import random
import asyncio
import aiohttp

from sqlalchemy import select

from database.db import Database
from database.models import Proxy


class ProxyPool:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._busy: set[int] = set()
        self._capacity_cache: int | None = None

    @staticmethod
    async def _load_proxies() -> list[Proxy]:
        async with Database().get_session() as session:
            res = await session.execute(
                select(Proxy).order_by(Proxy.id.asc())
            )
            return res.scalars().all()

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

    async def release(self, proxy_id: int) -> None:
        async with self._lock:
            self._busy.discard(proxy_id)

    async def acquire_mass(
            self,
            rotate_total_wait_sec: int = 120,  # общее ожидание смены IP (на один прокси)
            rotate_interval_sec: int = 20,  # интервал повторов смены IP
            rotate_wait_after_ok_sec: int = 5,  # пауза после успешной смены IP
            require_rotate: bool = True,
            wait_free_total_sec: int = 120,  # ✅ ждать свободный прокси до N секунд
            wait_free_interval_sec: int = 20,  # ✅ проверка каждые N секунд
    ) -> tuple[Proxy | None, str]:
        """Выдача прокси только для массовой очереди."""

        last_err = "Неизвестная ошибка"

        deadline_free = time.monotonic() + max(0, int(wait_free_total_sec))

        free: list[Proxy] = []
        while True:
            proxies = await self._load_proxies()

            async with self._lock:
                free = [p for p in proxies if p.id not in self._busy]
                if free:
                    random.shuffle(free)
                    break

            if time.monotonic() >= deadline_free:
                return None, "Все прокси заняты (таймаут ожидания)"

            await asyncio.sleep(max(0.2, float(wait_free_interval_sec)))

        for proxy in free:
            async with self._lock:
                if proxy.id in self._busy:
                    continue
                self._busy.add(proxy.id)

            try:
                if not require_rotate:
                    return proxy, f"Proxy {proxy.id} выдан"

                deadline_rotate = time.monotonic() + max(0, int(rotate_total_wait_sec))

                while True:
                    ok, msg = await self._change_ip(proxy)

                    if ok:
                        if rotate_wait_after_ok_sec > 0:
                            await asyncio.sleep(rotate_wait_after_ok_sec)
                        return proxy, f"Proxy {proxy.id} выдан ({msg})"

                    last_err = msg

                    now = time.monotonic()
                    if now >= deadline_rotate:
                        await self.release(proxy.id)
                        break

                    await asyncio.sleep(min(float(rotate_interval_sec), deadline_rotate - now))
            except asyncio.CancelledError:
                try:
                    await self.release(proxy.id)
                except Exception:
                    pass
                raise

            except Exception as e:
                last_err = str(e)
                await self.release(proxy.id)

        return None, f"Не удалось выдать прокси. Последняя ошибка: {last_err}"

    async def acquire(
        self,
        require_rotate: bool = True,
        rotate_wait_sec: int = 5,
        rotate_retries: int = 3,
    ) -> tuple[Proxy | None, str]:
        """Возвращает свободный прокси."""

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
                continue

        return None, f"Не удалось выдать прокси. Последняя ошибка: {last_err}"

    async def capacity(self) -> int:
        """Сколько всего прокси доступно."""
        if self._capacity_cache is None:
            proxies = await self._load_proxies()
            self._capacity_cache = len(proxies)
        return self._capacity_cache
