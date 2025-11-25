import os
import random

def random_ua(path="templates/files/user_agents.txt"):
    """Генератор бесконечно выдаёт user-agent'ы."""
    with open(os.path.join(os.getcwd(), path), "r", encoding="utf-8") as f:
        user_agents = [line.strip() for line in f if line.strip()]

    while True:
        random.shuffle(user_agents)

        for ua in user_agents:
            yield ua

def random_viewport():
    return {"width": random.randint(1200, 1366), "height": random.randint(720, 900)}
