import os
import random

from pathlib import Path
from typing import Generator



BASE_DIR = Path(__file__).resolve().parents[1]  # корень проекта


def random_ua(path="templates/files/user_agents.txt") -> Generator[str, None, None]:
    """Генератор бесконечно выдаёт user-agent'ы."""
    ua_path = BASE_DIR / path

    with open(ua_path, "r", encoding="utf-8") as f:
        user_agents = [line.strip() for line in f if line.strip()]

    while True:
        random.shuffle(user_agents)
        for ua in user_agents:
            yield ua


def random_viewport() -> dict[str, int]:
    return {"width": random.randint(1200, 1366), "height": random.randint(720, 900)}
