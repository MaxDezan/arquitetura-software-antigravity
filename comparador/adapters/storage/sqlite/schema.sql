CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    reference_model TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(id),
    site TEXT NOT NULL,
    site_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    seller TEXT,
    image_url TEXT,
    match_score REAL NOT NULL,
    link_status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(site, site_id)
);
CREATE INDEX IF NOT EXISTS idx_listings_product ON listings(product_id);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL REFERENCES listings(id),
    price REAL,
    original_price REAL,
    currency TEXT NOT NULL DEFAULT 'BRL',
    availability TEXT,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_listing ON price_snapshots(listing_id, fetched_at);
