-- Shared offer store for grocery-deal (ebag / lidl / billa / kaufland ...).
-- Target: Neon serverless Postgres. Safe to re-run.
--
-- Deliberately narrow: every column is either displayed, filtered on, or needed
-- to judge whether an offer is genuinely good. Raw scrape payloads are NOT kept
-- here -- they live as gzipped JSONL files outside the database.
--
-- ALL MONETARY COLUMNS ARE EUR. ebag publishes лв as well, but its
-- base_unit_price is EUR-denominated; mixing the two silently corrupts every
-- per-kg comparison. Multiply by 1.95583 for лв.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------
-- Current offers. Only products that clear a threshold land here --
-- the other ~20 500 catalogue products are not offers.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offers (
    source            text NOT NULL,          -- 'ebag', 'lidl', ...
    external_id       text NOT NULL,

    name              text NOT NULL,
    brand             text,
    url               text,
    image_url         text,

    offer_type        text NOT NULL,          -- 'promo' | 'multipack'
    price_regular     numeric(10,2),          -- same quantity at the undiscounted rate
    current_price     numeric(10,2) NOT NULL,
    discount_percent  smallint NOT NULL,      -- recomputed, never taken on trust

    base_unit_price   numeric(10,2),          -- EUR per кг / л / бр
    base_unit         text,
    pack_text         text,                   -- '400 г' / '6 x 400 г', for display

    promo_from        date,
    promo_to          date,
    expiry_date       date,                   -- best-before of the stocked batch

    category_path     text,
    is_available      boolean,

    watchlist         text[],                 -- watch-list rules this matched
    search_text       text NOT NULL,          -- name + EN name + brand + category

    first_seen_at     timestamptz NOT NULL DEFAULT now(),
    last_seen_at      timestamptz NOT NULL DEFAULT now(),
    is_active         boolean NOT NULL DEFAULT true,

    PRIMARY KEY (source, external_id)
);

-- Bulgarian has no Postgres stemmer, so index twice: 'simple' tsvector for
-- exact tokens, trigrams for inflection (мляко / млека / млякото).
CREATE INDEX IF NOT EXISTS offers_search_trgm
    ON offers USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS offers_search_fts
    ON offers USING gin (to_tsvector('simple', search_text));
CREATE INDEX IF NOT EXISTS offers_watchlist
    ON offers USING gin (watchlist);
-- text_pattern_ops so category prefix matching uses the index:
--   WHERE category_path LIKE 'Млечни и яйца > %'
CREATE INDEX IF NOT EXISTS offers_category
    ON offers (category_path text_pattern_ops);
CREATE INDEX IF NOT EXISTS offers_live
    ON offers (is_active, discount_percent DESC);

-- ---------------------------------------------------------------
-- Price history -- one row per observed CHANGE, not per run.
-- The declared discount is arithmetically honest but says nothing about
-- whether the reference price was inflated first; only this can.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offer_price_points (
    source          text NOT NULL,
    external_id     text NOT NULL,
    observed_on     date NOT NULL,
    current_price   numeric(10,2) NOT NULL,
    base_unit_price numeric(10,2),
    PRIMARY KEY (source, external_id, observed_on)
);

-- ---------------------------------------------------------------
-- One email per product per promo window, per rule.
-- The watch list itself lives in rules.py: its scope/alt/cocoa_min structure
-- does not express well as table columns, and it changes rarely.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offer_alerts (
    rule_name   text NOT NULL,
    source      text NOT NULL,
    external_id text NOT NULL,
    promo_key   text NOT NULL,      -- 'promo_from..promo_to', or 'multipack'
    discount    smallint,
    alerted_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rule_name, source, external_id, promo_key)
);
