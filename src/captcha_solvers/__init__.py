"""
CAPTCHA detection and solving — pluggable strategy pattern.

Each solver implements detect() and solve(). The registry tries each
solver in order until one handles the page.

Adding a new solver:
    1. Create a class with detect(page) -> bool and solve(page) -> bool
    2. Add it to SOLVERS list below
"""

from __future__ import annotations

import logging
import random
import time
from typing import Protocol

from playwright.sync_api import Page

log = logging.getLogger("stock-checker")


# ---------------------------------------------------------------------------
# Solver protocol
# ---------------------------------------------------------------------------
class CaptchaSolver(Protocol):
    """Interface for CAPTCHA solvers."""

    def detect(self, page: Page) -> bool:
        """Return True if this solver recognizes the CAPTCHA on the page."""
        ...

    def solve(self, page: Page) -> bool:
        """Attempt to solve the CAPTCHA. Return True if successful."""
        ...


# ---------------------------------------------------------------------------
# Soft CAPTCHA solver ("Click the button below to continue shopping")
# ---------------------------------------------------------------------------
class SoftCaptchaSolver:
    """
    Handles Amazon's soft CAPTCHA — a simple "Continue shopping" button
    served as HTTP 200 with a form POST to /errors/validateCaptcha.

    No image puzzle, no text input. Just click through.
    """

    def detect(self, page: Page) -> bool:
        try:
            captcha_form = page.query_selector(
                'form[action="/errors/validateCaptcha"]'
            )
            if captcha_form:
                return True

            page_text = page.inner_text("body").lower()
            return "click the button below to continue shopping" in page_text
        except Exception:
            return False

    def solve(self, page: Page) -> bool:
        try:
            log.info("Soft CAPTCHA detected — auto-solving...")
            button = page.query_selector(
                'button.a-button-text'
            ) or page.query_selector('button[type="submit"]')

            if button:
                time.sleep(random.uniform(0.5, 1.5))
                button.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                time.sleep(random.uniform(1.0, 2.0))
                log.info("CAPTCHA solved — redirected to: %s", page.url)
                return True
            else:
                log.warning("CAPTCHA detected but could not find submit button")
                return False
        except Exception as e:
            log.warning("Soft CAPTCHA solve failed: %s", e)
            return False


# ---------------------------------------------------------------------------
# Image CAPTCHA solver (e.g., 2Captcha / CapSolver)
# ---------------------------------------------------------------------------
class ImageCaptchaSolver:
    """
    Handles Amazon's image CAPTCHA — requires an external solving service.

    TODO: Implement using 2Captcha or CapSolver API.
          1. Detect the image CAPTCHA form
          2. Extract the CAPTCHA image URL
          3. Submit to solving service API
          4. Input the solution and submit the form
    """

    def detect(self, page: Page) -> bool:
        # TODO: detect image-based CAPTCHA (look for captcha image element)
        return False

    def solve(self, page: Page) -> bool:
        # TODO: implement external CAPTCHA solving service integration
        log.warning("Image CAPTCHA detected but solver not implemented")
        return False


# ---------------------------------------------------------------------------
# Solver registry
# ---------------------------------------------------------------------------
# Solvers are tried in order — put the most common one first.
SOLVERS: list[CaptchaSolver] = [
    SoftCaptchaSolver(),
    ImageCaptchaSolver(),
]


def solve_if_captcha(page: Page) -> bool:
    """
    Check if the current page is a CAPTCHA and attempt to solve it.

    Tries each registered solver in order.
    Returns True if a CAPTCHA was detected and solved.
    """
    for solver in SOLVERS:
        if solver.detect(page):
            return solver.solve(page)
    return False
