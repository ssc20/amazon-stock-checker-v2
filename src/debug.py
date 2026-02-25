"""
Debug utilities — screenshot and HTML capture on errors.

Saves diagnostic files to /config/debug/ with automatic cleanup
to avoid filling disk.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page

log = logging.getLogger("stock-checker")

MAX_DEBUG_FILES = 40  # 20 screenshots + 20 HTML files


def ensure_debug_dir(debug_dir: Path):
    """Create debug directory and clean old files."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(debug_dir.iterdir(), key=lambda f: f.stat().st_mtime)
    while len(files) > MAX_DEBUG_FILES:
        files.pop(0).unlink()


def capture(page: Page, asin: str, error_msg: str, debug_dir: Path):
    """
    Save a screenshot and page HTML for debugging.

    Files are named with timestamp + ASIN for easy correlation:
        20260217_190900_B0FH795GZ8.png
        20260217_190900_B0FH795GZ8.html
    """
    try:
        ensure_debug_dir(debug_dir)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = f"{timestamp}_{asin}"

        # Screenshot
        screenshot_path = debug_dir / f"{prefix}.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
        log.info("Debug screenshot saved: %s", screenshot_path)

        # Full page HTML
        html_path = debug_dir / f"{prefix}.html"
        html_content = page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        log.info("Debug HTML saved: %s", html_path)

        # Log context for quick triage
        try:
            title = page.title()
            current_url = page.url
            log.info(
                "Debug context — URL: %s | Title: %s | Error: %s",
                current_url, title, error_msg,
            )
        except Exception:
            pass

    except Exception as e:
        log.warning("Failed to capture debug info: %s", e)
