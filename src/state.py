"""
State persistence for stock status and browser cookies.

Saves to JSON files on disk so the checker survives container restarts
without re-alerting on already-known stock states.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext

log = logging.getLogger("stock-checker")


# ---------------------------------------------------------------------------
# Product state
# ---------------------------------------------------------------------------
@dataclass
class ProductState:
    in_stock: Optional[bool] = None
    consecutive_errors: int = 0
    priority: str = "normal"
    last_checked: Optional[str] = None
    last_alert: Optional[str] = None


# ---------------------------------------------------------------------------
# State manager
# ---------------------------------------------------------------------------
class StateManager:
    """Manages per-ASIN state with JSON persistence."""

    def __init__(self, state_path: Path):
        self.path = state_path
        self._data: dict[str, ProductState] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    raw = json.load(f)
                for asin, values in raw.items():
                    self._data[asin] = ProductState(
                        in_stock=values.get("in_stock"),
                        consecutive_errors=values.get("consecutive_errors", 0),
                        priority=values.get("priority", "normal"),
                        last_checked=values.get("last_checked"),
                        last_alert=values.get("last_alert"),
                    )
                log.info("Loaded state for %d product(s)", len(self._data))
            except Exception as e:
                log.warning("Failed to load state: %s", e)

    def save(self):
        try:
            serializable = {}
            for asin, ps in self._data.items():
                serializable[asin] = {
                    "in_stock": ps.in_stock,
                    "consecutive_errors": ps.consecutive_errors,
                    "priority": ps.priority,
                    "last_checked": ps.last_checked,
                    "last_alert": ps.last_alert,
                }
            with open(self.path, "w") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            log.error("Failed to save state: %s", e)

    def get(self, asin: str) -> ProductState:
        if asin not in self._data:
            self._data[asin] = ProductState()
        return self._data[asin]

    def record_success(self, asin: str, in_stock: bool, priority: str) -> ProductState:
        """Record a successful check. Returns the state for transition detection."""
        ps = self.get(asin)
        ps.consecutive_errors = 0
        ps.in_stock = in_stock
        ps.priority = priority
        ps.last_checked = datetime.now(timezone.utc).isoformat()
        self.save()
        return ps

    def record_error(self, asin: str) -> int:
        """Record a check error. Returns the new consecutive error count."""
        ps = self.get(asin)
        ps.consecutive_errors += 1
        self.save()
        return ps.consecutive_errors

    def record_alert(self, asin: str):
        ps = self.get(asin)
        ps.last_alert = datetime.now(timezone.utc).isoformat()
        self.save()


# ---------------------------------------------------------------------------
# Cookie persistence
# ---------------------------------------------------------------------------
class CookieManager:
    """Saves and restores Playwright browser cookies to/from disk."""

    def __init__(self, cookies_path: Path):
        self.path = cookies_path

    def save(self, context: BrowserContext):
        try:
            cookies = context.cookies()
            with open(self.path, "w") as f:
                json.dump(cookies, f, indent=2)
            log.debug("Saved %d cookies", len(cookies))
        except Exception as e:
            log.warning("Failed to save cookies: %s", e)

    def restore(self, context: BrowserContext):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                log.info("Restored %d cookies from disk", len(cookies))
            except Exception as e:
                log.warning("Failed to load cookies: %s", e)
