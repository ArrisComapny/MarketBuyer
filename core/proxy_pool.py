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

    async def _load_proxies(self) -> list[Proxy]:
        async with Database().get_session() as session:
            res = await session.execute(
                select(Proxy).order_by(Proxy.id.asc())
            )
            return res.scalars().all()

    async def _change_ip(self, proxy: Proxy) -> tuple[bool, str]:
        url = (proxy.change_ip_url or "").strip()
        if not url:
            return True, "change_ip_url пустой — смена IP пропущена"

        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    if r.status == 200:
                        return True, "IP сменён"
                    return False, f"Смена IP не удалась (HTTP {r.status})"
        except Exception as e:
            return False, f"Смена IP ошибка: {e}"

    async def release(self, proxy_id: int) -> None:
        async with self._lock:
            self._busy.discard(proxy_id)

    async def acquire(
        self,
        require_rotate: bool = True,
        rotate_wait_sec: int = 5,
        rotate_retries: int = 3,
    ) -> tuple[Proxy | None, str]:
        """
        Возвращает свободный прокси.
        IP не проверяется вообще.
        """

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

                # УСПЕХ — отдаём прокси
                return proxy, f"Proxy {proxy.id} выдан"

            except Exception as e:
                last_err = str(e)
                await self.release(proxy.id)
                continue

        return None, f"Не удалось выдать прокси. Последняя ошибка: {last_err}"








