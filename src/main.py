#!/usr/bin/env python3
"""
Amazon Stock Checker v2 — main entry point.

Orchestrates the poll loop:
    1. Load config
    2. Launch browser
    3. Loop: check products → detect transitions → notify → sleep
"""

import logging
import random
import sys
import time

from src.browser import BrowserManager
from src.checker import check_product
from src.config import Config, DEBUG_DIR, COOKIES_PATH, STATE_PATH
from src.notifiers import build_notifiers, notify_all
from src.state import CookieManager, StateManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("stock-checker")


# ---------------------------------------------------------------------------
# Polling interval logic
# ---------------------------------------------------------------------------
def get_cycle_interval(config: Config) -> float:
    """
    Calculate sleep time after a full poll cycle.

    Uses tighter intervals if any high-priority products exist.
    Adds ±15s jitter so timing never looks robotic.
    """
    if config.has_high_priority:
        base_min = config.poll_high_priority_min_seconds
        base_max = config.poll_high_priority_max_seconds
    else:
        base_min = config.poll_interval_min_seconds
        base_max = config.poll_interval_max_seconds

    jitter = random.uniform(-15, 15)
    interval = random.uniform(base_min, base_max) + jitter
    return max(10, interval)  # floor at 10s safety minimum


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    config = Config.from_file()
    state = StateManager(STATE_PATH)
    cookies = CookieManager(COOKIES_PATH)
    notifiers = build_notifiers(config)
    browser = BrowserManager(config, cookies)

    log.info("=" * 50)
    log.info("Amazon Stock Checker v2 (Playwright)")
    log.info("=" * 50)

    page = browser.start()
    products = config.sorted_products
    log.info("Monitoring %d product(s) on %s", len(products), config.amazon_domain)

    # Startup notification
    notify_all(notifiers, "send_startup", products, config.amazon_domain)

    cycle_count = 0

    try:
        while True:
            cycle_count += 1

            # Hot-reload config each cycle
            try:
                config = Config.from_file()
                products = config.sorted_products
                # Rebuild notifiers in case credentials changed
                notifiers = build_notifiers(config)
            except Exception as e:
                log.error("Config reload failed: %s", e)

            # Periodic warmup to refresh session
            if cycle_count % config.warmup_every_n_cycles == 0:
                browser.warmup()
                browser.save_session()

            log.info("--- Cycle %d (%d products) ---", cycle_count, len(products))

            for product in products:
                result = check_product(
                    page=browser.page,
                    product=product,
                    domain=config.amazon_domain,
                    debug_dir=DEBUG_DIR,
                )

                prev = state.get(product.asin)
                prev_in_stock = prev.in_stock

                if not result.ok:
                    # --- Error path ---
                    log.warning("[%s] %s — %s", product.asin, product.label, result.error)
                    error_count = state.record_error(product.asin)

                    if error_count == 5:
                        notify_all(
                            notifiers, "send_error",
                            product, result.error, error_count,
                        )

                    # Rotate context on repeated errors
                    if error_count >= 3 and error_count % 3 == 0:
                        browser.rotate_context()

                else:
                    # --- Success path ---
                    state.record_success(
                        product.asin, result.in_stock, product.priority,
                    )

                    if result.in_stock:
                        log.info("[%s] %s — IN STOCK ✓", product.asin, product.label)

                        # Alert on out → in transition (or first check)
                        if prev_in_stock is not True:
                            notify_all(notifiers, "send_restock", product, result)
                            state.record_alert(product.asin)
                    else:
                        log.info("[%s] %s — out of stock", product.asin, product.label)

                # Human-like pause between products
                BrowserManager.human_jitter(browser.page)
                time.sleep(random.uniform(2, 6))

            # Save session after each full cycle
            browser.save_session()

            # Sleep before next cycle
            sleep_time = get_cycle_interval(config)
            log.info("Sleeping %.0fs until next cycle...", sleep_time)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        browser.stop()


if __name__ == "__main__":
    main()
