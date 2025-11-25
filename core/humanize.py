import random

async def humanize(page):
    await page.wait_for_timeout(random.randint(300, 800))
    await page.mouse.move(random.randint(200, 600), random.randint(200, 500))
    await page.wait_for_timeout(random.randint(200, 600))
    await page.mouse.wheel(0, random.randint(300, 800))
    await page.wait_for_timeout(random.randint(300, 900))
