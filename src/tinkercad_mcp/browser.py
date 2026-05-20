"""BrowserManager — async Playwright singleton for tinkercad-mcp."""

import asyncio
import logging
import os
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from tinkercad_mcp.utils import SESSION_DIR, SESSION_FILE, USER_AGENT

logger = logging.getLogger(__name__)


def _headless() -> bool:
    return os.getenv("TINKERCAD_HEADLESS", "true").lower() == "true"


class BrowserManager:
    """Singleton that owns the single Chromium instance per process."""

    _instance: Optional["BrowserManager"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Singleton access ──────────────────────────────────────────────────────

    @classmethod
    async def get_instance(cls) -> "BrowserManager":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Page access ───────────────────────────────────────────────────────────

    async def get_page(self, *, headless: Optional[bool] = None) -> Page:
        """Return the active Page, launching browser if needed."""
        if self._page is None or self._page.is_closed():
            await self._launch(headless=headless)
        return self._page  # type: ignore[return-value]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def _launch(self, *, headless: Optional[bool] = None) -> None:
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        use_headless = headless if headless is not None else _headless()

        if self._browser is None or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(
                headless=use_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            logger.info("Chromium launched (headless=%s)", use_headless)

        storage_state = str(SESSION_FILE) if SESSION_FILE.exists() else None

        self._context = await self._browser.new_context(
            storage_state=storage_state,
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        self._page = await self._context.new_page()

        self._page.set_default_timeout(int(os.getenv("TINKERCAD_TIMEOUT_MS", "30000")))
        logger.info("Browser context ready (session=%s)", "loaded" if storage_state else "fresh")

    async def relaunch_headed(self) -> Page:
        """Close current context and reopen in headed mode (for manual login)."""
        await self._close_context()
        return await self.get_page(headless=False)

    async def save_session(self) -> None:
        if self._context is None:
            return
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(SESSION_FILE))
        logger.info("Session saved to %s", SESSION_FILE)

    async def clear_session(self) -> None:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
            logger.info("Session file removed")
        if self._context:
            await self._context.clear_cookies()

    async def _close_context(self) -> None:
        if self._page and not self._page.is_closed():
            await self._page.close()
        if self._context:
            await self._context.close()
        self._page = None
        self._context = None

    async def close(self) -> None:
        """Fully shut down Playwright. Resets singleton so next call relaunches."""
        await self._close_context()
        if self._browser and self._browser.is_connected():
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        async with self.__class__._lock:
            self.__class__._instance = None
        logger.info("BrowserManager closed")
