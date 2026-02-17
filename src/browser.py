"""
Browser management — Playwright lifecycle, stealth patches, context rotation, warmup.

Encapsulates all Playwright details so the rest of the app doesn't need
to know about browser internals.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright, Playwright

from .state import CookieManager

if TYPE_CHECKING:
    from .config import Config

log = logging.getLogger("stock-checker")

# ---------------------------------------------------------------------------
# Stealth JS — injected into every page to mask automation signals
# ---------------------------------------------------------------------------
STEALTH_JS = """
// Mask webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Mask automation-related properties
delete navigator.__proto__.webdriver;

// Chrome runtime mock
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {},
};

// Permissions mock
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// Plugin array (real Chrome has plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// WebGL vendor masking
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 2560, "height": 1440},
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
]


class BrowserManager:
    """
    Manages the Playwright browser lifecycle.

    Handles:
    - Browser launch with stealth flags
    - Context creation with fingerprint randomization
    - Cookie persistence across restarts
    - Session warmup (homepage browse)
    - Context rotation on repeated errors
    - Human-like jitter between actions
    """

    def __init__(self, config: Config, cookie_manager: CookieManager):
        self.config = config
        self.cookies = cookie_manager
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def start(self) -> Page:
        """Launch browser, create context, warmup, return page."""
        log.info("Launching Chromium (headless)...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            # TODO: add proxy support via config.proxy_url
            # proxy={"server": self.config.proxy_url} if self.config.proxy_url else None,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--disable-extensions",
            ],
        )
        self._create_context()
        self.warmup()
        self.save_session()
        return self._page

    def stop(self):
        """Clean shutdown."""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            log.warning("Error during browser shutdown: %s", e)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started — call start() first")
        return self._page

    def _create_context(self):
        """Create a new browser context with stealth patches and random fingerprint."""
        viewport = random.choice(VIEWPORTS)
        user_agent = random.choice(USER_AGENTS)

        self._context = self._browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale="en-US",
            timezone_id="America/Toronto",
            color_scheme="light",
            java_script_enabled=True,
            bypass_csp=False,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        self._context.add_init_script(STEALTH_JS)
        self.cookies.restore(self._context)
        self._page = self._context.new_page()

        log.info(
            "New browser context: %s @ %dx%d",
            user_agent[:60] + "...",
            viewport["width"],
            viewport["height"],
        )

    def rotate_context(self):
        """
        Close current context and create a fresh one with a new fingerprint.
        Used when Amazon starts blocking the current session.
        """
        log.info("Rotating browser context...")
        self.save_session()

        try:
            self._page.close()
            self._context.close()
        except Exception:
            pass

        cooldown = random.uniform(30, 60)
        log.info("Cooling down %.0fs before new context...", cooldown)
        time.sleep(cooldown)

        self._create_context()
        self.warmup()
        self.save_session()

    def warmup(self):
        """Navigate to Amazon homepage to establish a natural session."""
        from .captcha_solvers import solve_if_captcha  # avoid circular import

        domain = self.config.amazon_domain
        log.info("Warming up session on %s...", domain)
        try:
            self._page.goto(
                f"https://www.{domain}/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            time.sleep(random.uniform(1.5, 3.0))

            # Solve CAPTCHA if it appears on homepage
            if solve_if_captcha(self._page):
                log.info("Solved CAPTCHA during warmup")
                time.sleep(random.uniform(1.0, 2.0))

            # Human-like behavior
            self._page.mouse.move(
                random.randint(100, 800), random.randint(200, 600)
            )
            time.sleep(random.uniform(0.5, 1.5))
            self._page.mouse.wheel(0, random.randint(200, 500))
            time.sleep(random.uniform(1.0, 2.0))
            log.info("Warmup complete")
        except Exception as e:
            log.warning("Warmup failed (non-fatal): %s", e)

    def save_session(self):
        """Persist cookies to disk."""
        if self._context:
            self.cookies.save(self._context)

    def navigate(self, url: str) -> int | None:
        """Navigate to a URL and return the HTTP status code."""
        resp = self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return resp.status if resp else None

    @staticmethod
    def human_jitter(page: Page):
        """Small random mouse/scroll movements to look less robotic."""
        try:
            action = random.random()
            if action < 0.3:
                page.mouse.move(random.randint(50, 900), random.randint(100, 700))
            elif action < 0.5:
                page.mouse.wheel(0, random.randint(-200, 400))
        except Exception:
            pass
