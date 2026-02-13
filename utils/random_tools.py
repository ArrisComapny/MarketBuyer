import random

from sqlalchemy.ext.asyncio import AsyncSession

from config import UA_FILE_PATH, NAMES_FILE_PATH
from database.repositories import AccountRepo


def load_names() -> list[tuple[str, str]]:
    """
    Загружает список русских имён из файла.

    Формат строки: "Имя;Gender", например: "Алексей;Male".
    Пустые/битые строки игнорируются. Дубликаты удаляются с сохранением порядка.

    Returns:
        Список кортежей (name, gender). Если файла нет — пустой список.
    """
    path_file_name = NAMES_FILE_PATH
    if not path_file_name.exists():
        return []

    out: list[tuple[str, str]] = []
    for line in path_file_name.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or ";" not in line:
            continue
        name, gender = [x.strip() for x in line.split(";", 1)]
        if not name or not gender:
            continue

        out.append((name, gender))

    # убираем дубликаты, сохраняя порядок
    seen = set()
    uniq = []
    for name, gender in out:
        key = (name, gender)
        if key not in seen:
            seen.add(key)
            uniq.append((name, gender))

    return uniq

def load_user_agents() -> list[str]:
    """
    Загружает список user-agent строк из файла.

    Пустые строки игнорируются. Дубликаты удаляются с сохранением порядка.

    Returns:
        Список user-agent строк. Если файла нет — пустой список.
    """
    path_ua_file = UA_FILE_PATH
    if not path_ua_file.exists():
        return []

    agents: list[str] = []
    for line in path_ua_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        ua = line.strip()
        if ua:
            agents.append(ua)

    # убираем дубликаты, сохраняя порядок
    seen = set()
    unique = []
    for ua in agents:
        if ua not in seen:
            seen.add(ua)
            unique.append(ua)

    return unique

async def pick_user_agent(session: AsyncSession) -> str:
    """Возвращает user-agent для нового аккаунта."""
    agents = load_user_agents()
    if not agents:
        raise ValueError("Список user-agent пуст или файл не найден")

    used_agents = set(await AccountRepo.get_used_user_agents(session))

    free = [ua for ua in agents if ua not in used_agents]
    pool = free if free else agents

    return random.choice(pool)

async def pick_name_gender(session: AsyncSession, selected_gender: str | None = None) -> tuple[str, str]:
    """Возвращает пару (имя, пол) для нового аккаунта."""
    pool = load_names()
    if not pool:
        raise ValueError("Список имён пуст или файл не найден")

    if selected_gender:
        pool = [(n, g) for (n, g) in pool if g == selected_gender]

    used_names = set(await AccountRepo.get_used_names(session))

    free = [(n, g) for (n, g) in pool if n not in used_names]
    candidates = free if free else pool

    return random.choice(candidates)
