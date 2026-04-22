import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from comparador.adapters.sources.crawler.sites.base import BaseScraper
from comparador.domain.models import ListingSnapshot

log = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    name = "amazon"
    domain = "amazon.com.br"

    BASE = "https://www.amazon.com.br"
    SEARCH_URL = BASE + "/s?k={q}"

    async def search(self, query: str, max_results: int = 5) -> list[ListingSnapshot]:
        url = self.SEARCH_URL.format(q=quote_plus(query))
        html = await self.fetcher.fetch_html(
            url,
            self.domain,
            wait_selector="div.s-main-slot, [data-component-type='s-search-result']",
        )
        return self._parse(html, max_results)

    def _parse(self, html: str, max_results: int) -> list[ListingSnapshot]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("div[data-component-type='s-search-result']")
        results: list[ListingSnapshot] = []

        for item in items:
            if len(results) >= max_results:
                break
            asin = (item.get("data-asin") or "").strip()
            if not asin:
                continue
            link_el = item.select_one("h2 a, a.a-link-normal.s-no-outline")
            title_el = item.select_one(
                "h2 a span, h2 span, span.a-text-normal"
            )
            if not link_el or not title_el:
                continue

            href = link_el.get("href", "")
            if href.startswith("/"):
                href = self.BASE + href

            results.append(
                ListingSnapshot(
                    site=self.name,
                    site_id=asin,
                    title=title_el.get_text(strip=True),
                    url=href.split("?")[0],
                    price=self._extract_price(item),
                    original_price=self._extract_original_price(item),
                    image_url=self._extract_image(item),
                    rating=self._extract_rating(item),
                    reviews_count=self._extract_reviews(item),
                )
            )
        return results

    @staticmethod
    def _extract_image(item) -> str | None:
        img = item.select_one("img.s-image")
        if not img:
            img = item.select_one("img")
        return img.get("src") if img else None

    @staticmethod
    def _extract_price(item) -> float | None:
        el = item.select_one(".a-price:not(.a-text-price) .a-offscreen")
        if el:
            return _parse_brl(el.get_text(strip=True))
        whole = item.select_one(".a-price .a-price-whole")
        if not whole:
            return None
        whole_t = whole.get_text(strip=True).replace(".", "").replace(",", "")
        frac_el = item.select_one(".a-price .a-price-fraction")
        frac_t = frac_el.get_text(strip=True) if frac_el else "00"
        try:
            return float(f"{whole_t}.{frac_t}")
        except ValueError:
            return None

    @staticmethod
    def _extract_original_price(item) -> float | None:
        el = item.select_one(".a-price.a-text-price .a-offscreen")
        return _parse_brl(el.get_text(strip=True)) if el else None

    @staticmethod
    def _extract_rating(item) -> float | None:
        el = item.select_one(
            "i.a-icon-star-small span.a-icon-alt, span.a-icon-alt"
        )
        if not el:
            return None
        m = re.search(r"([\d,\.]+)", el.get_text())
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _extract_reviews(item) -> int | None:
        el = item.select_one(
            "span.a-size-base.s-underline-text, a span.a-size-base"
        )
        if not el:
            return None
        t = el.get_text(strip=True).replace(".", "").replace(",", "")
        return int(t) if t.isdigit() else None


def _parse_brl(text: str) -> float | None:
    s = text.replace("R$", "").replace("\xa0", "").strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
