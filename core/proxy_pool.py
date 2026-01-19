import asyncio
import time
import aiohttp
from sqlalchemy import select

from database.db import Database
from database.models import Proxy


class ProxyPool:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        # занятые прокси (proxy_id) которые выданы активным браузерам
        self._busy: set[int] = set()

        # ip -> proxy_id (чтобы активные прокси не делили один IP)
        self._used_ips: dict[str, int] = {}

        # proxy_id -> time.time() когда окно с этим прокси ЗАКРЫЛИ (старт кулдауна)
        self._last_free: dict[int, float] = {}

    async def _load_proxies(self) -> list[Proxy]:
        async with Database().get_session() as session:
            res = await session.execute(select(Proxy).order_by(Proxy.id.asc()))
            return res.scalars().all()

    def _proxy_url(self, p: Proxy) -> str:
        scheme = (p.proxy_scheme or "http").lower().strip()
        login = (p.login or "").strip()
        password = (p.password or "").strip()
        if login and password:
            return f"{scheme}://{login}:{password}@{p.host}:{p.port}"
        return f"{scheme}://{p.host}:{p.port}"

    async def get_proxy_ip(self, proxy: Proxy) -> str | None:
        proxy_url = self._proxy_url(proxy)
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get("https://api.ipify.org", proxy=proxy_url, timeout=20) as r:
                    if r.status != 200:
                        return None
                    return (await r.text()).strip()
        except Exception:
            return None

    async def release(self, proxy_id: int) -> None:
        """
        Освободить прокси. Кулдаун стартует с момента закрытия окна.
        """
        async with self._lock:
            self._busy.discard(proxy_id)

            #  старт кулдауна от закрытия окна
            self._last_free[proxy_id] = time.time()

            # освободить закреплённый IP
            for ip, pid in list(self._used_ips.items()):
                if pid == proxy_id:
                    self._used_ips.pop(ip, None)

    def _remain_sec_unlocked(self, proxy_id: int, cooldown_sec: int, now: float) -> int:
        """
        Считать оставшееся время кулдауна (в секундах) для proxy_id.
        ВАЖНО: вызывай только когда держишь self._lock (или внутри acquire_unique под локом).
        """
        last_free = self._last_free.get(proxy_id, 0.0)
        if last_free <= 0:
            return 0
        remain = int(cooldown_sec - (now - last_free))
        return remain if remain > 0 else 0

    async def _change_ip(self, proxy: Proxy) -> tuple[bool, str]:
        """
        Реальный вызов change_ip_url (без проверки кулдауна).
        """
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(proxy.change_ip_url, timeout=30) as r:
                    if r.status == 200:
                        return True, "IP сменён"
                    return False, f"Смена IP не удалась (HTTP {r.status})"
        except Exception as e:
            return False, f"Смена IP ошибка: {e}"

    async def acquire_unique(
        self,
        cooldown_sec: int = 120,
        rotate_wait_sec: int = 5,
    ) -> tuple[Proxy | None, str | None, str]:
        """
        ТВОЁ ТРЕБОВАНИЕ:
        - таймер идет по первому закрытому окну (это _last_free для каждого proxy)
        - если закрылось второе окно во время отката, сообщение должно показывать
          МИНИМАЛЬНОЕ время ожидания среди всех свободных прокси.
        """
        proxies = await self._load_proxies()
        now = time.time()

        # 1) под локом выбираем лучший прокси (готовый) или минимальный remain
        async with self._lock:
            free = [p for p in proxies if p.id not in self._busy]
            if not free:
                return None, None, "Все прокси заняты"

            ready: list[Proxy] = []
            remains: list[int] = []

            for p in free:
                remain = self._remain_sec_unlocked(p.id, cooldown_sec, now)
                if remain == 0:
                    ready.append(p)
                else:
                    remains.append(remain)

            # никто не готов -> вернуть минимальный таймер (по первому закрытому окну)
            if not ready:
                min_wait = min(remains) if remains else cooldown_sec
                return None, None, f"Смена IP пока недоступна, подождите {min_wait} секунд для смены"

            # берём первого готового (можно усложнить стратегию, но этого достаточно)
            proxy = ready[0]
            self._busy.add(proxy.id)

        # 2) вне лока пробуем сменить IP (если у тебя это обязательно перед стартом)
        ok, msg = await self._change_ip(proxy)
        if not ok:
            await self.release(proxy.id)
            return None, None, msg

        # ждём, чтобы провайдер реально успел сменить IP
        await asyncio.sleep(rotate_wait_sec)

        # 3) получаем IP
        ip = await self.get_proxy_ip(proxy)
        if not ip:
            await self.release(proxy.id)
            return None, None, "Не удалось определить IP через прокси"

        # 4) проверяем уникальность IP среди активных
        async with self._lock:
            if ip in self._used_ips:
                await self.release(proxy.id)
                return None, None, f"IP {ip} уже используется другим активным прокси"
            self._used_ips[ip] = proxy.id

        return proxy, ip, f"Proxy {proxy.id} получил IP {ip}"





