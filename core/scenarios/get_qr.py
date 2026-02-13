from __future__ import annotations

from domain.dtos import QrItems, QrPVZ, QrResult
from .base import BaseScenario
from domain.enums import ScenarioMode
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from typing import List, Tuple


class QRcodeScenario(BaseScenario):
    """Сценарий сбора данных о заказах."""
    mode = ScenarioMode.QRCODE

    async def run(self) -> QrResult:
        """Запуск сценария."""

        print(f"Start {self.mode}")
        c = self.c
        acc = c.account

        phone10 = acc["phone10"]
        account_name = acc.get("name", "")

        c.on_progress and c.on_progress(5, "Открываю сайт…")

        await c. accept_cookie()
        await c.close_modal()
        await c.wait_full_load()
        await c.humanize()

        await self.click_btn_order()
        c.on_progress and c.on_progress(10, "Кнопка заказы нажата")

        await c.human_wait()
        await c.change_window_size(800, 1200)
        await c.human_wait()

        pvz_list = await self.scan_pvz_with_products()

        try:
            c.on_progress and c.on_progress(15, "Жду QR блок…")
            code, qr_base64 = await self.fetch_qr_code_data()
            c.on_progress and c.on_progress(40, f"QR получен, код: {code}")
        except PlaywrightTimeoutError:
            code, qr_base64 = "", ""

        return QrResult(phone10=phone10, account_name=account_name, pvz_list=pvz_list, code=code, qr_base64=qr_base64)

    async def click_btn_order(self):
        c = self.c
        order_btn = await c.page.wait_for_selector('a[data-wba-header-name="DLV"]', timeout=5000, state="visible")
        await order_btn.hover()
        await c.human_wait()
        await c.human_click(order_btn)

    async def fetch_qr_code_data(self) -> Tuple[str, str]:
        c = self.c
        await c.page.wait_for_selector("section.delivery-qr", timeout=15000, state="visible")

        code_el = await c.page.wait_for_selector(".delivery-qr__main span", timeout=5000, state="visible")
        code = (await code_el.inner_text()).replace(" ", "").strip()

        img = await c.page.wait_for_selector(".delivery-qr__code-wrap img", timeout=5000, state="visible")
        src = await img.get_attribute("src") or ""

        qr_base64 = src.split(",", 1)[1] if "," in src else ""
        return code, qr_base64

    async def scan_pvz_with_products(self) -> List[QrPVZ]:
        c = self.c
        await c.page.wait_for_selector('[data-testid="delivery-page"]', timeout=15000)

        await c.humanize()
        await c.human_wait()

        blocks = c.page.locator("div.delivery-block__content")
        n = await blocks.count()

        out: List[QrPVZ] = []

        for i in range(n):
            block = blocks.nth(i)

            addr_loc = block.locator("p.delivery-address__info")
            if await addr_loc.count() == 0:
                continue

            address = (await addr_loc.first.inner_text()).strip()
            if not address:
                continue

            items = block.locator(".delivery-block__list .custom-slider__item.product")
            m = await items.count()

            products: List[QrItems] = []

            for j in range(m):
                it = items.nth(j)

                status = ""
                st = it.locator("span.product__tracking")
                if await st.count() > 0:
                    status = (await st.first.inner_text()).strip()

                img = it.locator(".product__photo img")
                src = await img.first.get_attribute("src")
                sku = src.split("/part", 1)[1].split("/", 2)[1]

                products.append(QrItems(sku=sku, quantity=1, status=status))

            out.append(QrPVZ(address_pvz=address, products=products))

        return out
