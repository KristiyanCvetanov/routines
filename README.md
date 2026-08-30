# eBag.bg offers

Feeds ebag.bg promotions into the grocery-deal offer store, alongside the
Lidl / Billa / Kaufland brochure data.

## Why it works this way

ebag.bg renders entirely client-side, so fetching the search page returns an
empty shell. The catalogue behind it is **Algolia** (app `JMJMDQ9HHX`, index
`products`, ~22 500 products); the public search key is read from the site's own
JS bundle, which is what the browser does too.

**We do not keyword-search at collection time.** Algolia is typo-tolerant and
relevance-ranked, so a query for `олио` returns tanning oil, hair serum and
stretch-mark cream above the cooking oil. Instead the collector takes the entire
`is_promo:true` set — about 1 700 rows — and all filtering happens locally
against stored data. Full recall, and adding a search criterion never means
re-scraping.

Algolia caps paging at 1 000 hits and refuses `/browse` for this key, so the
sweep is partitioned by `category_name_bg_lvl1` (16 values, largest ~580).

## Layout

    schema.sql    offer schema (Neon / Postgres)
    collect.py    sweep + normalise -> data/
    data/
      snapshots/YYYY-MM-DD.jsonl.gz   raw Algolia records, append-only (~185 KB/day)
      current.json                    normalised rows, overwritten each run

Raw snapshots stay **out of Postgres**. They are the audit trail and the source
for any later backfill, but at ~1 700 records a day they would dominate a small
database while being read approximately never.

## Run

    python collect.py
    python collect.py --out /tmp/ebag --date 2026-08-30

## Currency — read this before joining to the brochure tables

**Every monetary column is EUR.** ebag publishes both, but its `base_unit_price`
is EUR-denominated while `current_price` is лв, and mixing them silently breaks
every per-kg comparison by a factor of ~1.96. Measured on 298 sampled promo
products: 298/298 agree with EUR ÷ pack weight, 0/298 with лв ÷ pack weight.

The collector therefore stores `price_eur` / `current_price_eur` throughout.
If the existing brochure tables are in лв, convert at 1.95583 on the join.

## Schema notes

18 columns, all of them displayed, filtered on, or needed to judge an offer.
Dropped after checking fill rates against live data:

| field | why |
|---|---|
| `bundle_discount_data` | 0% populated |
| `units_in_pack` | 2% populated |
| EUR/лв duplicate columns | one currency only (above) |
| `product_code` | ebag-internal, not an EAN — useless for cross-retailer matching |
| `available_quantity`, `country_of_origin`, `times_sold_1m` | not needed to decide on a deal |

`base_unit_price` (EUR per кг/л/бр) is the cross-retailer comparison key —
brochure pack sizes never line up, so headline prices are not comparable.
Null for 388 rows, all in `Аптека`, where per-piece pricing applies.

`expiry_date` is the best-before of the batch actually in stock, populated for
1 163 of 1 692 (69%). It is not decoration: 35 current promos expire within 30
days, and they are mostly fresh meat and fish at 10–18% off. That is a distinct
kind of deal — worth its own rule, and worth excluding from others.

Bulgarian has no Postgres stemmer, so `search_text` is indexed twice:
`to_tsvector('simple', …)` for exact tokens and `pg_trgm` for inflection
(мляко / млека / млякото). `unaccent` is not used — Bulgarian Cyrillic has no
diacritics worth folding. The EN name and brand are folded into `search_text`
rather than stored as columns, because brands appear in both scripts
(Верея / Vereia).

## Judging an offer

`discount_percent` is arithmetically honest — checked against
`(price_regular - current_price) / price_regular` across all 1 692 current
promos, none disagreed by more than a percentage point, and none was
promo-flagged without a real reduction. What it cannot tell you is whether
`price_regular` was inflated before the promo began. Only `offer_price_points`
can, which is why the collector appends one whenever a price moves.

Alerts should rank on, in order:

1. `base_unit_price` vs the product's own median in `offer_price_points`
2. `base_unit_price` percentile among its category peers
3. `discount_percent`, as a tie-breaker only

Note `category_path` starting with `Био` is an attribute bucket, not a food
category — it contains cosmetics and hygiene. The current top "food" discount by
that filter is hypoallergenic tampons. Scope rules on real food categories.

## Not done yet

- Neon project + `psql -f schema.sql`
- upsert step (`current.json` -> `offers` + `offer_price_points`)
- `deal_rules` rows — waiting on the actual criteria
- alerting + Gmail delivery, deduped via `offer_alerts (rule, product, promo window)`
- scheduled cloud routine to run the above daily
