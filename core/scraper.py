"""Playwright wrapper for JavaScript-capable web scraping.

Runs a headless Chromium browser to scrape pages that require JS rendering.
Playwright browsers must be installed first:
    playwright install chromium
"""

import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class ScraperClient:
    """Async Playwright scraper."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless

    async def get_page_text(self, url: str, *, wait_ms: int = 2000) -> str:
        """
        Navigate to a URL and return the visible text content.

        Args:
            url: Page URL to scrape.
            wait_ms: Milliseconds to wait after load for JS rendering.

        Returns:
            Visible text content of the page.
        """
        logger.info("Scraping %s", url)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(wait_ms)
                text = await page.inner_text("body")
                logger.info("Scraped %d chars from %s", len(text), url)
                return text
            finally:
                await browser.close()

    async def get_page_html(self, url: str, *, wait_ms: int = 2000) -> str:
        """
        Navigate to a URL and return the full HTML content.

        Args:
            url: Page URL to scrape.
            wait_ms: Milliseconds to wait after load for JS rendering.

        Returns:
            Full HTML of the page.
        """
        logger.info("Scraping HTML from %s", url)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(wait_ms)
                html = await page.content()
                logger.info("Scraped %d chars HTML from %s", len(html), url)
                return html
            finally:
                await browser.close()

    async def health_check(self) -> bool:
        """Verify Playwright can launch a browser."""
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                await browser.close()
            return True
        except Exception as exc:
            logger.warning("Scraper health check failed: %s", exc)
            return False
