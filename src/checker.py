"""
Stock checker — product page parsing and stock detection.

Responsible for navigating to a product page, parsing it, and determining
whether the item is in stock. Handles CAPTCHA interception transparently.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

from playwright.sync_api import Page

from .captcha_solvers import solve_if_captcha
from .config import Product
from .debug import capture as capture_debug
from .notifiers import CheckResult

log = logging.getLogger("stock-checker")

# Signals that indicate an item is out of stock
OUT_OF_STOCK_SIGNALS = [
    "currently unavailable",
    "out of stock",
    "sign up for restock",
    "we don't know when or if this item will be back in stock",
    "no featured offers available",
]

# Substrings that identify Amazon itself as the seller (case-insensitive match)
AMAZON_SOLD_BY_PATTERNS = [
    "sold by amazon",
    "ships from and sold by amazon",
]

# TODO: Add retailer-specific parsers (BestBuy, Walmart, etc.)
#       Could subclass or use a strategy pattern:
#
#       class RetailerParser(Protocol):
#           def build_url(self, product_id: str) -> str: ...
#           def parse_stock(self, page: Page) -> CheckResult: ...
#
#       class AmazonParser(RetailerParser): ...
#       class BestBuyParser(RetailerParser): ...


def check_product(
    page: Page,
    product: Product,
    domain: str,
    debug_dir: Path,
) -> CheckResult:
    """
    Navigate to a product page and determine stock status.

    Handles soft CAPTCHA interception — if Amazon serves a CAPTCHA,
    it auto-solves and re-navigates before parsing.
    """
    url = f"https://www.{domain}/dp/{product.asin}"
    result = CheckResult(asin=product.asin, url=url)

    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if resp and resp.status == 503:
            result.error = "CAPTCHA / rate limited (503)"
            capture_debug(page, product.asin, result.error, debug_dir)
            return result
        if resp and resp.status != 200:
            result.error = f"HTTP {resp.status}"
            capture_debug(page, product.asin, result.error, debug_dir)
            return result

        # Wait for the product content block to render
        try:
            page.wait_for_selector("#productTitle", timeout=15000)
        except Exception:
            pass  # Continue — page may still be parseable (e.g. CAPTCHA page)
        time.sleep(random.uniform(0.5, 1.0))

        # --- CAPTCHA interception ---
        if _handle_captcha(page, url, product.asin, result, debug_dir):
            # _handle_captcha sets result.error if it couldn't solve
            if result.error:
                return result

        # --- Parse product page ---
        result.title = _extract_title(page)
        result.price = _extract_price(page)
        result.sold_by = _extract_sold_by(page)
        result.in_stock = _detect_stock(page)

        if result.in_stock is None:
            result.error = "Could not determine stock status (page structure may have changed)"
            capture_debug(page, product.asin, result.error, debug_dir)

        return result

    except Exception as e:
        error_msg = str(e)
        result.error = "Page load timeout" if "timeout" in error_msg.lower() else error_msg
        try:
            capture_debug(page, product.asin, result.error, debug_dir)
        except Exception:
            pass
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _handle_captcha(
    page: Page, url: str, asin: str, result: CheckResult, debug_dir: Path,
) -> bool:
    """
    Detect and solve CAPTCHA, re-navigating to product page after.

    Returns True if a CAPTCHA was encountered (solved or not).
    Sets result.error if it couldn't be solved after 3 attempts.
    """
    if not solve_if_captcha(page):
        return False

    # CAPTCHA solved — re-navigate to product page
    log.info("Re-navigating to product page after CAPTCHA solve...")
    time.sleep(random.uniform(1.0, 3.0))
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(1.0, 2.0))

    # Second CAPTCHA?
    if solve_if_captcha(page):
        log.warning("Double CAPTCHA — solving again...")
        time.sleep(random.uniform(2.0, 4.0))
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(1.0, 2.0))

        # Third CAPTCHA? Give up.
        if solve_if_captcha(page):
            result.error = "Persistent CAPTCHA after 3 solve attempts"
            capture_debug(page, asin, result.error, debug_dir)

    return True


def _extract_title(page: Page) -> str | None:
    try:
        el = page.query_selector("#productTitle")
        return el.inner_text().strip() if el else None
    except Exception:
        return None


def _extract_price(page: Page) -> str | None:
    try:
        whole = page.query_selector("span.a-price-whole")
        if whole:
            fraction = page.query_selector("span.a-price-fraction")
            frac_str = fraction.inner_text().strip() if fraction else ""
            return f"${whole.inner_text().strip()}{frac_str}"
    except Exception:
        pass
    return None


def _extract_sold_by(page: Page) -> str | None:
    """
    Extract seller/fulfillment text from the buy box.

    Tries the classic #merchant-info element first, then falls back to the
    newer tabular buy box container. Returns raw text (e.g. "Sold by Amazon.ca
    and Ships from Amazon") or None if neither element is found.
    """
    try:
        el = page.query_selector("#merchant-info")
        if el:
            return el.inner_text().strip()
        el = page.query_selector("#tabular-buybox-container")
        if el:
            return el.inner_text().strip()
    except Exception:
        pass
    return None


def _detect_stock(page: Page) -> bool | None:
    """
    Determine stock status from the rendered page.

    Returns True (in stock), False (out of stock), or None (unknown).
    """
    # Most reliable: look for the Add to Cart / Buy Now buttons
    add_to_cart = (
        page.query_selector("#add-to-cart-button")
        or page.query_selector("#add-to-cart-button-ubb")
    )
    buy_now = page.query_selector("#buy-now-button")

    if add_to_cart or buy_now:
        return True

    # "Unqualified buy box" means no seller won the Buy Box — treat as out of stock
    if page.query_selector("#unqualifiedBuyBox"):
        return False

    # Fallback: check the #availability section
    try:
        availability_el = page.query_selector("#availability")
        if availability_el:
            avail_text = availability_el.inner_text().lower()
            for signal in OUT_OF_STOCK_SIGNALS:
                if signal in avail_text:
                    return False
    except Exception:
        pass

    # Broader page text scan
    try:
        body_text = page.inner_text("body").lower()
        for signal in OUT_OF_STOCK_SIGNALS:
            if signal in body_text:
                return False
    except Exception:
        pass

    return None
