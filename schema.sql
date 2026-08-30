-- The only table this collector owns.
--
-- ebag offers themselves go into the grocery-deal app's existing `deals` table,
-- alongside lidl / billa / metro / fantastiko -- see load.py. That table, and
-- the price_observations / price_baselines machinery behind it, already existed
-- and is not touched here.
--
-- Prices are EUR throughout, matching what `deals` already holds.

CREATE TABLE IF NOT EXISTS ebag_alerts (
    rule_name   text NOT NULL,      -- watch-list rule, from rules.py
    source      text NOT NULL,
    external_id text NOT NULL,      -- ebag product id
    promo_key   text NOT NULL,      -- the promo window, or 'multipack'
    discount    smallint,
    alerted_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rule_name, source, external_id, promo_key)
);
