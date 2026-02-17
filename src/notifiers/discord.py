"""
Discord webhook notification implementation.

TODO: Implement Discord notifications.
      1. Accept webhook_url in __init__
      2. Format messages as Discord embeds for rich display
      3. Send via POST to webhook URL
      4. Add to build_notifiers() in __init__.py
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Product
    from . import CheckResult

log = logging.getLogger("stock-checker")


class DiscordNotifier:
    """Sends notifications via Discord webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        # TODO: POST to self.webhook_url with {"content": message}
        raise NotImplementedError("Discord notifier not yet implemented")

    def send_startup(self, products: list[Product], domain: str) -> bool:
        # TODO: format as Discord embed with product list
        raise NotImplementedError

    def send_restock(self, product: Product, result: CheckResult) -> bool:
        # TODO: format as rich embed with title, price, buy link
        raise NotImplementedError

    def send_error(self, product: Product, error: str, error_count: int) -> bool:
        # TODO: format as warning embed
        raise NotImplementedError
