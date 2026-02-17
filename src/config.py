"""
Configuration management.

Loads, validates, and provides typed access to config.json.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("stock-checker")

# ---------------------------------------------------------------------------
# Paths (all relative to the /config mount)
# ---------------------------------------------------------------------------
CONFIG_DIR = Path("/config")
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = CONFIG_DIR / "state.json"
COOKIES_PATH = CONFIG_DIR / "cookies.json"
DEBUG_DIR = CONFIG_DIR / "debug"


# ---------------------------------------------------------------------------
# Product model
# ---------------------------------------------------------------------------
@dataclass
class Product:
    asin: str
    label: str = ""
    priority: str = "normal"  # "high" | "normal"

    def __post_init__(self):
        if not self.label:
            self.label = self.asin
        if self.priority not in ("high", "normal"):
            log.warning("Unknown priority '%s' for %s — defaulting to 'normal'", self.priority, self.asin)
            self.priority = "normal"

    @property
    def is_high_priority(self) -> bool:
        return self.priority == "high"

    @classmethod
    def from_dict(cls, d: dict) -> Product:
        return cls(
            asin=d["asin"],
            label=d.get("label", ""),
            priority=d.get("priority", "normal"),
        )


# ---------------------------------------------------------------------------
# Main config
# ---------------------------------------------------------------------------
@dataclass
class Config:
    # Notification
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""  # TODO: Discord notifier support

    # Amazon
    amazon_domain: str = "amazon.ca"

    # Polling intervals (seconds)
    poll_high_priority_min_seconds: int = 25
    poll_high_priority_max_seconds: int = 35
    poll_interval_min_seconds: int = 45
    poll_interval_max_seconds: int = 60

    # Session
    warmup_every_n_cycles: int = 20

    # Products
    products: list[Product] = field(default_factory=list)

    # Proxy
    proxy_url: Optional[str] = None  # TODO: proxy rotation support

    @classmethod
    def from_file(cls, path: Path = CONFIG_PATH) -> Config:
        """Load config from JSON file, validate, and return typed Config."""
        if not path.exists():
            log.error("Config file not found at %s", path)
            sys.exit(1)

        with open(path) as f:
            raw = json.load(f)

        # Validate required fields
        required = ["telegram_bot_token", "telegram_chat_id", "products"]
        for key in required:
            if key not in raw or not raw[key]:
                log.error("Missing required config key: %s", key)
                sys.exit(1)

        products = [Product.from_dict(p) for p in raw.get("products", [])]

        return cls(
            telegram_bot_token=raw["telegram_bot_token"],
            telegram_chat_id=raw["telegram_chat_id"],
            discord_webhook_url=raw.get("discord_webhook_url", ""),
            amazon_domain=raw.get("amazon_domain", "amazon.ca"),
            poll_high_priority_min_seconds=raw.get("poll_high_priority_min_seconds", 25),
            poll_high_priority_max_seconds=raw.get("poll_high_priority_max_seconds", 35),
            poll_interval_min_seconds=raw.get("poll_interval_min_seconds", 45),
            poll_interval_max_seconds=raw.get("poll_interval_max_seconds", 60),
            warmup_every_n_cycles=raw.get("warmup_every_n_cycles", 20),
            products=products,
            proxy_url=raw.get("proxy_url"),
        )

    @property
    def sorted_products(self) -> list[Product]:
        """Products sorted with high-priority first."""
        return sorted(self.products, key=lambda p: not p.is_high_priority)

    @property
    def has_high_priority(self) -> bool:
        return any(p.is_high_priority for p in self.products)
