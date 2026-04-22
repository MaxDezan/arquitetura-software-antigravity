import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from comparador.adapters.sources.crawler.sites.base import BaseScraper
from comparador.domain.models import ListingSnapshot

log = logging.getLogger(__name__)


class MercadoLivreScraper(BaseScraper):
    name = "mercadolivre"
    domain = "mercadolivre.com.br"

    SEARCH_URL = "https://lista.mercadolivre.com.br/{q}"
    MLB_RE = re.compile(r"(MLB-?\d{8,})")

    async def search(self, query: str, max_results: int = 5) -> list[ListingSnapshot]:
        url = self.SEARCH_URL.format(q=quote_plus(query))
        html = await self.fetcher.fetch_html(
            url,
            self.domain,
            wait_selector="ol.ui-search-layout, .ui-search-results, .ui-search-layout__item",
        )
        return self._parse(html, max_results)

    def _parse(self, html: str, max_results: int) -> list[ListingSnapshot]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(
            "li.ui-search-layout__item, div.ui-search-result__wrapper"
        )
        results: list[ListingSnapshot] = []

        for item in items:
            if len(results) >= max_results:
                break
            a = item.select_one(
                "a.poly-component__title, a.ui-search-link, a.ui-search-item__group__element"
            )
            if not a:
                continue
            href = a.get("href", "")
            title_el = (
                item.select_one("h2")
                or item.select_one(".poly-component__title")
                or a
            )
            title = title_el.get_text(strip=True) or a.get("title", "")
            if not title or not href:
                continue

            mlb = self.MLB_RE.search(href)
            site_id = mlb.group(1).replace("-", "") if mlb else href.split("?")[0]

            results.append(
                ListingSnapshot(
                    site=self.name,
                    site_id=site_id,
                    title=title,
                    url=href,
                    price=self._extract_price(item),
                    original_price=self._extract_original_price(item),
                    seller=self._extract_seller(item),
                    image_url=self._extract_image(item),
                )
            )
        return results

    @staticmethod
    def _extract_image(item) -> str | None:
        img = item.select_one(
            "img.poly-component__picture, img.ui-search-result-image__element"
        )
        if not img:
            img = item.select_one("img")
        if not img:
            return None
        # ML lazy-loads — prefer data-src over placeholder src
        return img.get("data-src") or img.get("src")

    @staticmethod
    def _extract_price(item) -> float | None:
        container = item.select_one(
            ".andes-money-amount--cents-superscript, .andes-money-amount"
        )
        if not container:
            return None
        frac_el = container.select_one("span.andes-money-amount__fraction")
        if not frac_el:
            return None
        frac = frac_el.get_text(strip=True).replace(".", "")
        cents_el = container.select_one("span.andes-money-amount__cents")
        cents = cents_el.get_text(strip=True) if cents_el else "00"
        try:
            return float(f"{frac}.{cents}")
        except ValueError:
            return None

    @staticmethod
    def _extract_original_price(item) -> float | None:
        el = item.select_one(
            "s.andes-money-amount--previous span.andes-money-amount__fraction"
        )
        if not el:
            return None
        try:
            return float(el.get_text(strip=True).replace(".", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_seller(item) -> str | None:
        el = item.select_one(
            ".ui-search-official-store-label, .poly-component__seller, "
            ".ui-search-item__brand-discoverability"
        )
        return el.get_text(strip=True) if el else None
