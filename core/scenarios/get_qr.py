from __future__ import annotations

import re
from typing import List, Tuple

from utils.exceptions import NoProductsWarning
from domain.dtos import QrItems, QrPVZ, QrResult
from .base import BaseScenario
from domain.enums import ScenarioMode
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utils.logger import AppLogger

log = AppLogger.get(__name__)


class QRcodeScenario(BaseScenario):
    """Сценарий сбора данных о заказах."""
    mode = ScenarioMode.QRCODE

    async def run(self) -> QrResult:
        c = self.c
        acc = c.account or {}

        phone10 = acc.get("phone10", "unknown")
        account_name = acc.get("name", "")

        log.info(f"[QR][{phone10}] START QRcodeScenario")

        try:
            c.on_progress and c.on_progress(5, "Открываю сайт…")
            log.info(f"[QR][{phone10}] Открываю сайт…")

            await c.accept_cookie()
            await c.close_modal()
            await c.wait_full_load()
            await c.humanize()

            log.info(f"[QR][{phone10}] Переход в заказы")
            await self.click_btn_order()

            await self.check_empty_delivery_page()
            c.on_progress and c.on_progress(10, "Кнопка заказы нажата")
            log.info(f"[QR][{phone10}] Кнопка 'Заказы' нажата")

            await c.human_wait()
            await c.change_window_size(800, 1200)
            await c.human_wait()

            c.on_progress and c.on_progress(15, "Сканирую на наличие товара")
            log.info(f"[QR][{phone10}] Сканирую ПВЗ/товары")

            pvz_list = await self.scan_pvz_with_products()
            log.info(f"[QR][{phone10}] ПВЗ найдено: {len(pvz_list)}")

            c.on_progress and c.on_progress(50, "Жду QR блок…")
            log.info(f"[QR][{phone10}] Жду QR блок…")

            code, qr_base64 = await self.fetch_qr_code_data()

            c.on_progress and c.on_progress(60, f"QR получен, код: {code}")
            log.info(f"[QR][{phone10}] QR получен, code={code}, b64_len={len(qr_base64)}")

            log.info(f"[QR][{phone10}] DONE QRcodeScenario")

            return QrResult(
                phone10=phone10,
                account_name=account_name,
                pvz_list=pvz_list,
                code=code,
                qr_base64=qr_base64
            )

        except NoProductsWarning as e:
            log.warning(f"[QR][{phone10}] {e}")

            c.on_progress and c.on_progress(100, "Нет товаров")

            return QrResult(
                phone10=phone10,
                account_name=account_name,
                pvz_list=[],
                code="",
                qr_base64=""
            )

        except Exception as e:
            log.exception(f"[QR][{phone10}] ERROR QRcodeScenario: {e}")
            raise

    # =========================================
    # КНОПКА ЗАКАЗОВ
    # =========================================

    async def click_btn_order(self) -> None:
        c = self.c
        phone10 = (c.account or {}).get("phone10", "unknown")

        try:
            order_btn = await c.page.wait_for_selector(
                'a[data-wba-header-name="DLV"]',
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[QR][{phone10}] Кнопка 'Заказы' не найдена")
            raise Exception("Кнопка 'Заказы' не найдена")

        await order_btn.hover()
        await c.human_wait()
        await c.human_click(order_btn)

    async def fetch_qr_code_data(self) -> Tuple[str, str]:
        c = self.c
        phone10 = (c.account or {}).get("phone10", "unknown")

        try:
            await c.page.wait_for_selector("section.delivery-qr", timeout=15000, state="visible")
        except PlaywrightTimeoutError:
            log.error(f"[QR][{phone10}] Секция QR не появилась")
            raise Exception("Секция QR не появилась")

        try:
            code_el = await c.page.wait_for_selector(
                ".delivery-qr__main span",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[QR][{phone10}] Текст QR-кода не найден")
            raise Exception("Текст QR-кода не найден")

        code = (await code_el.inner_text()).replace(" ", "").strip()

        try:
            img = await c.page.wait_for_selector(
                ".delivery-qr__code-wrap img",
                timeout=5000,
                state="visible"
            )
        except PlaywrightTimeoutError:
            log.error(f"[QR][{phone10}] Изображение QR не найдено")
            raise Exception("Изображение QR не найдено")

        src = await img.get_attribute("src") or ""
        if not src:
            log.error(f"[QR][{phone10}] QR изображение без src")
            raise Exception("QR изображение без src")

        qr_base64 = src.split(",", 1)[1] if "," in src else ""
        if not qr_base64:
            log.warning(f"[QR][{phone10}] QR base64 пустой")

        return code, qr_base64

    # =========================================
    # СКАН ПВЗ
    # =========================================

    async def scan_pvz_with_products(self) -> List[QrPVZ]:
        c = self.c
        phone10 = (c.account or {}).get("phone10", "unknown")

        c.on_progress and c.on_progress(20, "Ждём страницу доставок")
        log.info(f"[QR][{phone10}] Ждём страницу доставок")

        try:
            await c.page.wait_for_selector('[data-testid="delivery-page"]', timeout=15000, state="visible")
        except PlaywrightTimeoutError:
            log.error(f"[QR][{phone10}] Страница заказов не загрузилась")
            raise Exception("Страница заказов не загрузилась")

        await self.check_empty_delivery_page()
        await c.humanize()
        await c.human_wait()

        c.on_progress and c.on_progress(25, "Ждём, что появятся блоки")
        log.info(f"[QR][{phone10}] Ждём блоки ПВЗ")

        try:
            await c.page.wait_for_selector("div.delivery-block__content", timeout=15000, state="visible")
        except PlaywrightTimeoutError:
            log.error(f"[QR][{phone10}] Блоки ПВЗ не появились (delivery-block__content)")
            raise Exception("Блоки ПВЗ не появились (delivery-block__content)")

        blocks = await c.page.query_selector_all(
            "div.delivery-block.delivery-block--delivery div.delivery-block__content"
        )
        if not blocks:
            log.error(f"[QR][{phone10}] Блоки ПВЗ не найдены (query_selector_all пусто)")
            raise Exception("Блоки ПВЗ не найдены")

        log.info(f"[QR][{phone10}] Найдено блоков ПВЗ: {len(blocks)}")

        out: List[QrPVZ] = []

        for block in blocks:
            addr_el = None

            try:
                addr_el = await block.wait_for_selector("p.delivery-address__info", timeout=2500, state="visible")
            except PlaywrightTimeoutError:
                pass

            if not addr_el:
                try:
                    addr_el = await block.wait_for_selector("p.delivery-address__info", timeout=2500, state="attached")
                except PlaywrightTimeoutError:
                    pass

            if not addr_el:
                log.warning(f"[QR][{phone10}] Адрес ПВЗ не найден в одном из блоков (skip)")
                continue

            address = (await addr_el.inner_text()).strip()
            if not address:
                continue

            # Прогресс не по каждому блоку, иначе будет дергаться — но можно оставить
            c.on_progress and c.on_progress(30, "Проверяю товары в ПВЗ")
            log.info(f"[QR][{phone10}] ПВЗ: {address}")

            try:
                await block.wait_for_selector(
                    ".delivery-block__list .custom-slider__item.product",
                    timeout=7000,
                    state="attached"
                )
            except PlaywrightTimeoutError:
                log.error(f"[QR][{phone10}] В ПВЗ '{address}' не найдены товары (ожидание product)")
                raise Exception(f"В ПВЗ '{address}' не найдены товары (product)")

            items = await block.query_selector_all(".delivery-block__item.product")
            if not items:
                log.error(f"[QR][{phone10}] В ПВЗ '{address}' не найдены товары (items пусто)")
                raise Exception(f"В ПВЗ '{address}' не найдены товары")

            products: List[QrItems] = []

            for it in items:
                status = ""
                st_el = await it.query_selector(".product__price-status .product__tracking")
                if st_el:
                    status = (await st_el.inner_text()).strip()

                try:
                    img_el = await it.wait_for_selector(".product__photo img", timeout=5000, state="attached")
                except PlaywrightTimeoutError:
                    log.error(f"[QR][{phone10}] Не найдено фото товара в ПВЗ '{address}'")
                    raise Exception(f"Не найдено фото товара в ПВЗ '{address}'")

                src = await img_el.get_attribute("src") or ""
                if not src:
                    log.error(f"[QR][{phone10}] Фото товара без src в ПВЗ '{address}'")
                    raise Exception(f"Фото товара без src в ПВЗ '{address}'")

                sku = ""
                if "/part" in src:
                    try:
                        sku = src.split("/part", 1)[1].split("/", 2)[1]
                    except Exception:
                        log.error(f"[QR][{phone10}] Ошибка парсинга SKU из src: {src}")
                        raise Exception(f"Ошибка парсинга SKU из src: {src}")

                quantity = 1
                qty_el = await it.query_selector("span.product__size")
                if qty_el:
                    qty_text = (await qty_el.inner_text()).strip()
                    m = re.search(r"\d+", qty_text)
                    if m:
                        quantity = int(m.group())

                products.append(QrItems(sku=sku, quantity=quantity, status=status))

            log.info(f"[QR][{phone10}] ПВЗ '{address}': товаров={len(products)}")
            out.append(QrPVZ(address_pvz=address, products=products))

        return out

    async def check_empty_delivery_page(self) -> None:
        c = self.c
        # phone10 = (c.account or {}).get("phone10", "unknown")

        try:
            await c.page.wait_for_selector("h1:has-text('Здесь будут товары')", timeout=1500)
        except PlaywrightTimeoutError:
            return

        # log.info(f"[QR][{phone10}] Товаров нет")
        raise NoProductsWarning("Товаров нет")



