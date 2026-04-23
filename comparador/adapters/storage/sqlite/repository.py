import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from comparador.domain.identity import (
    canonical_product_name,
    link_status_for_score,
)
from comparador.domain.models import (
    Listing,
    ListingSnapshot,
    Product,
    ProductQuery,
)
from comparador.ports.repository import ProductRepository


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class SqliteProductRepository(ProductRepository):
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text()
        with self._conn() as conn:
            conn.executescript(sql)
            # Forward migrations for DBs created before the column existed.
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(listings)").fetchall()
            }
            if "image_url" not in cols:
                conn.execute("ALTER TABLE listings ADD COLUMN image_url TEXT")

    # ---------- commands ----------
    def upsert_product(self, query: ProductQuery) -> Product:
        name = canonical_product_name(query.name)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return _row_to_product(row)
            pid = uuid4()
            now = datetime.utcnow().isoformat()
            conn.execute(
                """INSERT INTO products
                   (id, name, display_name, reference_model, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(pid), name, query.name,
                    query.reference_model, query.notes, now,
                ),
            )
            return Product(
                id=pid,
                name=name,
                display_name=query.name,
                reference_model=query.reference_model,
                notes=query.notes,
                created_at=datetime.fromisoformat(now),
            )

    def upsert_listing(
        self, product: Product, snap: ListingSnapshot
    ) -> Listing:
        status = link_status_for_score(snap.match_score) or "rejected"
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM listings WHERE site = ? AND site_id = ?",
                (snap.site, snap.site_id),
            ).fetchone()
            if row:
                # Update mutable-ish fields but preserve link_status (user may have
                # set it via dashboard) and never downgrade match_score.
                conn.execute(
                    """UPDATE listings
                       SET title = ?, seller = ?,
                           image_url = COALESCE(?, image_url),
                           match_score = MAX(match_score, ?),
                           last_seen_at = ?
                       WHERE id = ?""",
                    (
                        snap.title, snap.seller, snap.image_url,
                        snap.match_score, now, row["id"],
                    ),
                )
                updated = conn.execute(
                    "SELECT * FROM listings WHERE id = ?", (row["id"],)
                ).fetchone()
                return _row_to_listing(updated)

            lid = uuid4()
            conn.execute(
                """INSERT INTO listings
                   (id, product_id, site, site_id, title, url, seller,
                    image_url, match_score, link_status,
                    first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(lid), str(product.id), snap.site, snap.site_id,
                    snap.title, snap.url, snap.seller, snap.image_url,
                    snap.match_score, status, now, now,
                ),
            )
            return Listing(
                id=lid,
                product_id=product.id,
                site=snap.site,
                site_id=snap.site_id,
                title=snap.title,
                url=snap.url,
                seller=snap.seller,
                image_url=snap.image_url,
                match_score=snap.match_score,
                link_status=status,
                first_seen_at=datetime.fromisoformat(now),
                last_seen_at=datetime.fromisoformat(now),
            )

    def add_price_snapshot(
        self, listing: Listing, snap: ListingSnapshot
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO price_snapshots
                   (listing_id, price, original_price, currency,
                    availability, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(listing.id), snap.price, snap.original_price,
                    snap.currency, snap.availability,
                    snap.fetched_at.isoformat(),
                ),
            )

    def set_listing_status(self, listing_id: UUID, status: str) -> None:
        if status not in {"auto", "pending", "confirmed", "rejected"}:
            raise ValueError(f"invalid status: {status}")
        with self._conn() as conn:
            conn.execute(
                "UPDATE listings SET link_status = ? WHERE id = ?",
                (status, str(listing_id)),
            )

    # ---------- queries (admin) ----------
    def list_products_summary(self) -> list[dict]:
        sql = """
        WITH latest AS (
            SELECT listing_id, MAX(fetched_at) AS max_at
            FROM price_snapshots
            GROUP BY listing_id
        ),
        current AS (
            SELECT l.product_id, l.site, ps.price, ps.fetched_at
            FROM listings l
            JOIN latest lt ON lt.listing_id = l.id
            JOIN price_snapshots ps
                 ON ps.listing_id = l.id AND ps.fetched_at = lt.max_at
            WHERE l.link_status IN ('auto', 'confirmed')
              AND ps.price IS NOT NULL
        )
        SELECT
            p.id,
            p.display_name,
            (SELECT COUNT(*) FROM listings WHERE product_id = p.id AND link_status IN ('auto', 'confirmed')) AS listing_count,
            (SELECT MIN(c.price) FROM current c WHERE c.product_id = p.id) AS best_price,
            (SELECT c.site FROM current c
                 WHERE c.product_id = p.id ORDER BY c.price ASC LIMIT 1) AS best_site,
            (SELECT MAX(c.fetched_at) FROM current c
                 WHERE c.product_id = p.id) AS last_updated
        FROM products p
        WHERE EXISTS (
            SELECT 1 FROM listings l
            WHERE l.product_id = p.id
              AND l.link_status != 'rejected'
        )
        ORDER BY p.display_name
        """
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def get_product(self, product_id: UUID) -> Optional[Product]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (str(product_id),)
            ).fetchone()
            return _row_to_product(row) if row else None

    def get_listings_with_current_price(
        self, product_id: UUID
    ) -> list[dict]:
        sql = """
        SELECT
            l.id, l.site, l.site_id, l.title, l.url, l.seller, l.image_url,
            l.match_score, l.link_status,
            l.first_seen_at, l.last_seen_at,
            (SELECT price FROM price_snapshots
                 WHERE listing_id = l.id
                 ORDER BY fetched_at DESC LIMIT 1) AS current_price,
            (SELECT original_price FROM price_snapshots
                 WHERE listing_id = l.id
                 ORDER BY fetched_at DESC LIMIT 1) AS original_price,
            (SELECT fetched_at FROM price_snapshots
                 WHERE listing_id = l.id
                 ORDER BY fetched_at DESC LIMIT 1) AS last_fetched_at
        FROM listings l
        WHERE l.product_id = ?
        ORDER BY
          CASE l.link_status
               WHEN 'confirmed' THEN 0
               WHEN 'auto' THEN 1
               WHEN 'pending' THEN 2
               ELSE 3 END,
          CASE WHEN current_price IS NULL THEN 1 ELSE 0 END,
          current_price ASC
        """
        with self._conn() as conn:
            return [
                dict(r)
                for r in conn.execute(sql, (str(product_id),)).fetchall()
            ]

    def get_price_history(
        self, product_id: UUID
    ) -> dict[str, list[dict]]:
        sql = """
        SELECT l.id as listing_id, substr(ps.fetched_at, 1, 10) as fetch_date, ps.price
        FROM listings l
        JOIN price_snapshots ps ON ps.listing_id = l.id
        WHERE l.product_id = ?
          AND l.link_status IN ('auto', 'confirmed')
          AND ps.price IS NOT NULL
        ORDER BY ps.fetched_at ASC
        """
        
        current_prices: dict[str, float] = {}
        daily_best: dict[str, float] = {}
        
        with self._conn() as conn:
            for r in conn.execute(sql, (str(product_id),)).fetchall():
                listing_id = str(r["listing_id"])
                fetch_date = r["fetch_date"]
                price = r["price"]
                
                # Update this specific store's last known price
                current_prices[listing_id] = price
                
                # The real lowest price available right now across all known stores
                best_now = min(current_prices.values())
                
                # Register the final lowest price of the day
                daily_best[fetch_date] = best_now
                
        out_list = [{"x": f"{d}T12:00:00", "y": p} for d, p in daily_best.items()]
        return {"Melhor Preço": out_list}

    # ---------- queries (public) ----------
    def list_products_public_view(self) -> list[dict]:
        """Products with at least one priced, observed listing. Includes a
        best-guess image (highest match_score among linked listings)."""
        sql = """
        WITH latest AS (
            SELECT listing_id, MAX(fetched_at) AS max_at
            FROM price_snapshots
            GROUP BY listing_id
        ),
        current AS (
            SELECT l.product_id, l.site, l.image_url, l.match_score,
                   ps.price, ps.fetched_at
            FROM listings l
            JOIN latest lt ON lt.listing_id = l.id
            JOIN price_snapshots ps
                 ON ps.listing_id = l.id AND ps.fetched_at = lt.max_at
            WHERE l.link_status IN ('auto', 'confirmed')
              AND ps.price IS NOT NULL
        )
        SELECT
            p.id, p.display_name,
            (SELECT MIN(c.price) FROM current c WHERE c.product_id = p.id) AS best_price,
            (SELECT c.site FROM current c
                 WHERE c.product_id = p.id ORDER BY c.price ASC LIMIT 1) AS best_site,
            (SELECT COUNT(*) FROM listings l2
                 WHERE l2.product_id = p.id
                   AND l2.link_status IN ('auto', 'confirmed')) AS store_count,
            (SELECT c.image_url FROM current c
                 WHERE c.product_id = p.id AND c.image_url IS NOT NULL
                 ORDER BY c.match_score DESC LIMIT 1) AS image_url
        FROM products p
        WHERE EXISTS (SELECT 1 FROM current c WHERE c.product_id = p.id)
        ORDER BY p.display_name
        """
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def get_listings_for_comparison(
        self, product_id: UUID
    ) -> list[dict]:
        """Only auto/confirmed listings with a current price, cheapest first."""
        sql = """
        WITH latest AS (
            SELECT listing_id, MAX(fetched_at) AS max_at
            FROM price_snapshots
            GROUP BY listing_id
        )
        SELECT l.id, l.site, l.site_id, l.title, l.url, l.seller, l.image_url,
               l.match_score,
               ps.price AS current_price,
               ps.original_price,
               ps.fetched_at AS last_fetched_at
        FROM listings l
        JOIN latest lt ON lt.listing_id = l.id
        JOIN price_snapshots ps
             ON ps.listing_id = l.id AND ps.fetched_at = lt.max_at
        WHERE l.product_id = ?
          AND l.link_status IN ('auto', 'confirmed')
          AND ps.price IS NOT NULL
        ORDER BY ps.price ASC
        """
        with self._conn() as conn:
            return [
                dict(r)
                for r in conn.execute(sql, (str(product_id),)).fetchall()
            ]


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=UUID(row["id"]),
        name=row["name"],
        display_name=row["display_name"],
        reference_model=row["reference_model"],
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_listing(row: sqlite3.Row) -> Listing:
    return Listing(
        id=UUID(row["id"]),
        product_id=UUID(row["product_id"]),
        site=row["site"],
        site_id=row["site_id"],
        title=row["title"],
        url=row["url"],
        seller=row["seller"],
        image_url=row["image_url"] if "image_url" in row.keys() else None,
        match_score=row["match_score"],
        link_status=row["link_status"],
        first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
    )
