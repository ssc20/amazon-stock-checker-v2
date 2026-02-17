"""
Telegram push notification implementation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from ..config import Product
    from . import CheckResult

log = logging.getLogger("stock-checker")


class TelegramNotifier:
    """Sends notifications via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, message: str) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(self.api_url, json=payload, timeout=10)
            if resp.status_code != 200:
                log.error("Telegram API error: %s %s", resp.status_code, resp.text)
                return False
            return True
        except requests.RequestException as e:
            log.error("Telegram send failed: %s", e)
            return False

    def send_startup(self, products: list[Product], domain: str) -> bool:
        product_list = "\n".join(
            f"  {'🔴' if p.is_high_priority else '⚪'} {p.label}"
            for p in products
        )
        return self.send(
            f"🟢 <b>Stock Checker v2 started</b>\n"
            f"Browser: Chromium (stealth)\n"
            f"Domain: {domain}\n\n"
            f"Monitoring:\n{product_list}"
        )

    def send_restock(self, product: Product, result: CheckResult) -> bool:
        title = result.title or product.label
        price_str = f"\n💰 {result.price}" if result.price else ""
        pri_str = " 🔴 HIGH PRIORITY" if product.is_high_priority else ""
        now = datetime.now(timezone.utc).isoformat()

        return self.send(
            f"🚨🚨🚨 <b>IN STOCK NOW</b>{pri_str} 🚨🚨🚨\n\n"
            f"<b>{title}</b>{price_str}\n\n"
            f"🔗 <a href=\"{result.url}\">BUY NOW →</a>\n\n"
            f"ASIN: <code>{result.asin}</code>\n"
            f"⏰ {now}"
        )

    def send_error(self, product: Product, error: str, error_count: int) -> bool:
        return self.send(
            f"⚠️ <b>Checker issue</b>\n"
            f"<b>{product.label}</b> — {error_count} consecutive errors\n"
            f"Last error: {error}\n"
            f"ASIN: <code>{product.asin}</code>\n"
            f"📸 Screenshots saved to /config/debug/"
        )
