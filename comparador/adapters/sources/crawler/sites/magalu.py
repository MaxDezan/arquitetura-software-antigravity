import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from comparador.adapters.sources.crawler.sites.base import BaseScraper
from comparador.domain.models import ListingSnapshot

log = logging.getLogger(__name__)


class MagaluScraper(BaseScraper):
    name = "magalu"
    domain = "magazineluiza.com.br"

    BASE = "https://www.magazineluiza.com.br"
    SEARCH_URL = BASE + "/busca/{q}/"
    SKU_RE = re.compile(r"/p/([a-z0-9]+)/", re.I)

    async def search(self, query: str, max_results: int = 5) -> list[ListingSnapshot]:
        url = self.SEARCH_URL.format(q=quote_plus(query))
        html = await self.fetcher.fetch_html(
            url,
            self.domain,
            wait_selector="[data-testid='product-list'], [data-testid='product-card'], a[href*='/p/']",
        )
        return self._parse(html, max_results)

    def _parse(self, html: str, max_results: int) -> list[ListingSnapshot]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("[data-testid='product-card']")
        if not items:
            items = soup.select(
                "li a[href*='/p/'], a[data-testid='product-card-container']"
            )

        results: list[ListingSnapshot] = []
        seen: set[str] = set()

        for item in items:
            if len(results) >= max_results:
                break
            a = item if item.name == "a" else item.select_one("a[href*='/p/']")
            if not a:
                continue
            href = a.get("href", "")
            if href.startswith("/"):
                href = self.BASE + href

            sku_match = self.SKU_RE.search(href)
            site_id = sku_match.group(1) if sku_match else href.split("?")[0]
            if site_id in seen:
                continue
            seen.add(site_id)

            title_el = item.select_one(
                "[data-testid='product-title'], h2, h3, [data-testid='title']"
            )
            title = (title_el.get_text(strip=True) if title_el else "") or a.get(
                "title", ""
            )
            if not title:
                continue

            results.append(
                ListingSnapshot(
                    site=self.name,
                    site_id=site_id,
                    title=title,
                    url=href.split("?")[0],
                    price=self._extract_price(item),
                    original_price=self._extract_original_price(item),
                    image_url=self._extract_image(item),
                )
            )
        return results

    @staticmethod
    def _extract_image(item) -> str | None:
        img = item.select_one("img[data-testid='image']")
        if not img:
            # fallback: any img that isn't a badge/selo
            for candidate in item.select("img"):
                tid = candidate.get("data-testid", "")
                if tid != "badge":
                    img = candidate
                    break
        return img.get("src") if img else None

    @staticmethod
    def _extract_price(item) -> float | None:
        # price-value = highlighted current price (usually Pix). When there's
        # no discount Magalu omits price-value and keeps only price-original.
        el = item.select_one("[data-testid='price-value']")
        if el is None:
            el = item.select_one("[data-testid='price-original']")
        return _parse_brl(el.get_text(" ", strip=True)) if el else None

    @staticmethod
    def _extract_original_price(item) -> float | None:
        # Only meaningful as "de" price when a discounted price-value also exists.
        if item.select_one("[data-testid='price-value']") is None:
            return None
        el = item.select_one("[data-testid='price-original']")
        return _parse_brl(el.get_text(" ", strip=True)) if el else None


_BRL_RE = re.compile(r"R\$\s*([\d\.]+,\d{2})")


def _parse_brl(text: str) -> float | None:
    m = _BRL_RE.search(text or "")
    if not m:
        return None
    s = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
