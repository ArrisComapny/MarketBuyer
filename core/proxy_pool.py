import asyncio
import aiohttp
import random
from sqlalchemy import select

from database.db import Database
from database.models import Proxy


class ProxyPool:
    def __init__(self):
        # Лок для синхронизации доступа между корутинами
        self._lock = asyncio.Lock()

        # Множество ID прокси, которые сейчас используются
        self._busy: set[int] = set()

    async def _load_proxies(self) -> list[Proxy]:
        """
        Загружает все прокси из базы данных, отсортированные по id
        """
        async with Database().get_session() as session:
            res = await session.execute(
                select(Proxy).order_by(Proxy.id.asc())
            )
            return res.scalars().all()

    def _proxy_url(self, p: Proxy) -> str:
        """
        Формирует proxy URL для aiohttp:
        scheme://login:password@host:port
        """
        scheme = (p.proxy_scheme or "http").lower().strip()
        login = (p.login or "").strip()
        password = (p.password or "").strip()

        if login and password:
            return f"{scheme}://{login}:{password}@{p.host}:{p.port}"

        return f"{scheme}://{p.host}:{p.port}"

    async def get_proxy_ip(self, proxy: Proxy) -> str | None:
        """
        Определяет внешний IP прокси через api.ipify.org
        """
        proxy_url = self._proxy_url(proxy)

        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    "https://api.ipify.org",
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    if r.status != 200:
                        return None

                    return (await r.text()).strip()

        except Exception:
            # Любая ошибка = IP определить не удалось
            return None

    async def _change_ip(self, proxy: Proxy) -> tuple[bool, str]:
        """
        Вызывает URL смены IP у прокси-провайдера
        """
        url = (proxy.change_ip_url or "").strip()

        # Если URL не задан — считаем, что прокси без ротации
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

                    return (
                        False,
                        f"Смена IP не удалась (HTTP {r.status}), "
                        f"попробуйте повторить через 60-120 сек"
                    )

        except Exception as e:
            return False, f"Смена IP ошибка: {e}"

    async def release(self, proxy_id: int) -> None:
        """
        Освобождает прокси (делает его доступным для других задач)
        """
        async with self._lock:
            self._busy.discard(proxy_id)

    async def acquire_unique(
        self,
        rotate_wait_sec: int = 5,
        require_rotate: bool = True,
        ip_retries: int = 3,
        rotate_retries: int = 3,
    ) -> tuple[Proxy | None, str | None, str]:
        """
        Получает свободный прокси и гарантирует,
        что IP успешно определился.

        ❗ УНИКАЛЬНОСТЬ IP НЕ ПРОВЕРЯЕТСЯ
        """

        proxies = await self._load_proxies()
        last_err = "Неизвестная ошибка"

        # Получаем список свободных прокси
        async with self._lock:
            free = [p for p in proxies if p.id not in self._busy]
            if not free:
                return None, None, "Все прокси заняты"

            # Перемешиваем для равномерного использования
            random.shuffle(free)

        # Перебираем свободные прокси
        for candidate in free:
            async with self._lock:
                if candidate.id in self._busy:
                    continue

                # Помечаем прокси как занятый
                proxy = candidate
                self._busy.add(proxy.id)

            try:
                # Пытаемся сменить IP несколько раз
                for _ in range(rotate_retries):

                    if require_rotate:
                        ok, msg = await self._change_ip(proxy)
                        if not ok:
                            last_err = msg
                            continue

                        # Ждём, пока IP реально сменится
                        if rotate_wait_sec > 0:
                            await asyncio.sleep(rotate_wait_sec)

                    # Пытаемся получить IP несколько раз
                    ip = None
                    for _ in range(ip_retries):
                        ip = await self.get_proxy_ip(proxy)
                        if ip:
                            break
                        await asyncio.sleep(1)

                    if not ip:
                        last_err = "Не удалось определить IP через прокси"
                        continue

                    # УСПЕХ
                    print(f"[PROXY IP] proxy_id={proxy.id}, ip={ip}")
                    return proxy, ip, f"Proxy {proxy.id} получил IP {ip}"

                # Если не получилось — освобождаем прокси
                await self.release(proxy.id)
                continue

            except Exception as e:
                last_err = str(e)
                await self.release(proxy.id)
                continue

        return (None,None,f"Не удалось получить IP через прокси. Последняя ошибка: {last_err}"
                )







