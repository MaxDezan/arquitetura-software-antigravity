import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from playwright.async_api import Browser, BrowserContext, async_playwright
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from comparador.adapters.sources.crawler.anti_bot import (
    STEALTH_INIT_SCRIPT,
    default_headers,
    human_delay,
    random_user_agent,
)

log = logging.getLogger(__name__)


class RateLimitedFetcher:
    """Playwright fetcher with per-domain serialized access, stealth, retry."""

    def __init__(
        self,
        headless: bool = True,
        min_delay: float = 3.0,
        max_delay: float = 8.0,
    ) -> None:
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        for ctx in self._contexts.values():
            try:
                await ctx.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _get_context(self, domain: str) -> BrowserContext:
        if domain not in self._contexts:
            ua = random_user_agent()
            ctx = await self._browser.new_context(
                user_agent=ua,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1366, "height": 768},
                extra_http_headers=default_headers(ua),
            )
            await ctx.add_init_script(STEALTH_INIT_SCRIPT)
            await ctx.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in {"image", "media", "font"}
                    else route.continue_()
                ),
            )
            self._contexts[domain] = ctx
            self._locks[domain] = asyncio.Lock()
        return self._contexts[domain]

    @asynccontextmanager
    async def page(self, domain: str):
        ctx = await self._get_context(domain)
        lock = self._locks[domain]
        async with lock:
            page = await ctx.new_page()
            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                await human_delay(self.min_delay, self.max_delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def fetch_html(
        self, url: str, domain: str, wait_selector: Optional[str] = None
    ) -> str:
        async with self.page(domain) as page:
            log.info("GET %s", url)
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp and resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} for {url}")
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    log.warning("selector %s not found on %s", wait_selector, url)
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(0.8)
            return await page.content()
