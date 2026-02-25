"""
Notification system — pluggable notifiers with a common protocol.

Adding a new notifier:
    1. Create a module in this package (e.g., discord.py)
    2. Implement the Notifier protocol
    3. Add a build function to build_notifiers() below
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..config import Config, Product

log = logging.getLogger("stock-checker")


# ---------------------------------------------------------------------------
# Check result (passed to notifiers)
# ---------------------------------------------------------------------------
class CheckResult:
    """Result of a single product stock check."""

    def __init__(
        self,
        asin: str,
        url: str,
        in_stock: bool | None = None,
        title: str | None = None,
        price: str | None = None,
        error: str | None = None,
        sold_by: str | None = None,
    ):
        self.asin = asin
        self.url = url
        self.in_stock = in_stock
        self.title = title
        self.price = price
        self.error = error
        self.sold_by = sold_by

    @property
    def ok(self) -> bool:
        return self.error is None


# ---------------------------------------------------------------------------
# Notifier protocol
# ---------------------------------------------------------------------------
class Notifier(Protocol):
    """Interface that all notifiers implement."""

    def send(self, message: str) -> bool:
        """Send a raw message. Returns True on success."""
        ...

    def send_startup(self, products: list[Product], domain: str) -> bool:
        """Send startup notification."""
        ...

    def send_restock(self, product: Product, result: CheckResult) -> bool:
        """Send restock alert."""
        ...

    def send_error(self, product: Product, error: str, error_count: int) -> bool:
        """Send error alert (typically after N consecutive errors)."""
        ...


# ---------------------------------------------------------------------------
# Registry — build notifiers from config
# ---------------------------------------------------------------------------
def build_notifiers(config: Config) -> list[Notifier]:
    """Instantiate all configured notifiers."""
    notifiers: list[Notifier] = []

    # Telegram (required)
    if config.telegram_bot_token and config.telegram_chat_id:
        from .telegram import TelegramNotifier
        notifiers.append(
            TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
        )

    # Discord (optional)
    if config.discord_webhook_url:
        # TODO: import and instantiate DiscordNotifier
        log.warning("Discord notifier configured but not yet implemented")

    if not notifiers:
        log.error("No notifiers configured — alerts will not be sent!")

    return notifiers


def notify_all(notifiers: list[Notifier], method: str, *args, **kwargs):
    """Call a method on all notifiers, catching errors."""
    for notifier in notifiers:
        try:
            getattr(notifier, method)(*args, **kwargs)
        except Exception as e:
            log.error("Notifier %s.%s failed: %s", type(notifier).__name__, method, e)
