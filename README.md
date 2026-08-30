# eBag.bg offers

Feeds ebag.bg offers into the grocery-deal database, into the same `deals` table
the Lidl / Billa / Metro / Fantastiko brochures already populate.

    python run.py              # sweep, score, write to deals, email new alerts
    python run.py --dry-run    # no writes
    python run.py --cached     # reuse data/catalogue.jsonl.gz, for tuning rules

Configuration is all environment: `DATABASE_URL` (falls back to a local `.env`),
and `SMTP_USER` / `SMTP_PASSWORD` / `ALERT_TO` for mail.

## What the site actually exposes

ebag.bg renders entirely client-side, so its pages return an empty shell. The
catalogue behind it is **Algolia** (app `JMJMDQ9HHX`, index `products`); the
public search key is read from the site's own JS bundle, the same one the
browser uses.

Four things about that index cost real debugging, and are what the code is
shaped around:

**Keyword search is the wrong collection tool.** Algolia is typo-tolerant and
relevance-ranked, so `олио` returns tanning oil, hair serum and stretch-mark
cream above the cooking oil. The sweep takes the whole catalogue and all
filtering happens locally against it.

**`nbHits` is an estimate.** Without facets it reports ~22 450 against a true
20 703 (`exhaustiveNbHits: false`). Any completeness check must request a facet.

**Paging caps at 1000 and `/browse` is refused**, so the catalogue is
partitioned. Partitioning by category leaves holes — some products carry no
lvl3 category, and the index silently ignores a `NOT attr:*` filter, so there
is no way to ask for them. `ebag_api` bisects on the numeric id instead, which
is exhaustive by construction and verifies its own total.

**Not all offers are in `is_promo`.** Multipacks ("6 x 400 г") are separate
products flagged `is_save_money`, disjoint from `is_promo`, carrying no
`discount_percent`. This is ebag's 2-for-1 equivalent, and the saving is only
visible by comparing against the pack the product bundles up from — which is
often *itself* a multipack. A 36 x 85 г box of cat food points at the 12 x 85 г
box, not at one pouch; dividing by 36 produced a bogus 95% saving before both
sides were reduced to a per-unit price.

## Currency

`current_price` is лв, `base_unit_price` is EUR. Measured on 298 sampled promo
products: 298/298 agree with EUR ÷ pack weight, 0/298 with лв ÷ pack weight.
Mixing them breaks every per-kg comparison by a factor of ~1.96.

Everything here uses the `*_eur` fields, which is also what `deals` already
holds — brochure rows have 1 л fresh milk at 1.14 and 400 г yogurt at
0.49–0.65. No conversion on the join.

## The watch list

`rules.py`, with the thresholds: watch-list items count at **≥15%**, anything at
all counts at **≥40%**, and a watch-list item at **≥30%** earns an email.

Every rule leads with a category scope, because ebag's category tree is curated
and exact while its names are not. `телешко` matched on names alone returns 159
products, 21 of them dog food and 22 baby puree; scoped to Месо и риба it
returns beef. Rule terms match **name and brand only** — including the category
path made the `нахут` rule match "Био Леща Bioitalia Консерва", because the
category it sits in is named for chickpeas.

Notes on individual items:

- **Rummo is not stocked.** Zero products in the whole catalogue. The rule is
  kept so it fires if ebag ever lists it.
- **Rabbit** has no fresh category; it exists only jarred and frozen sous-vide.
  Pate, terrine, liver and bouillon are excluded as not being meat.
- **Veal** — ebag files телешко and говеждо in one category, so beef comes with it.
- **Dark chocolate** — only 28 of 65 state the cocoa share in the name. For the
  rest the description is fetched and parsed; where neither states it the product
  is excluded rather than guessed, so 50% bars cannot slip through an ≥80% rule.
- **Free-range eggs** include the `Пасищно отглеждане` category as well.
- **Chicken** is the one item where "от ферма" was specified, so it requires
  ebag's `is_farm_product` flag.

## Writing into `deals`

`load.py` maps onto the existing conventions: `store='ebag'`, category onto the
app's 17 slugs, `package_value`/`package_unit` in g / ml / item, and
`normalized_product` in the same casefolded, size-stripped shape the brochure
rows use — which is what lets ebag rows join `price_baselines`. 20 of them do
today.

Each run replaces every `store='ebag'` row, so it is idempotent.

Multipack savings have no end date; ebag simply prices the bigger pack lower.
They get a rolling 7-day `valid_until`, refreshed every run, rather than an
invented deadline.

One caveat for the app: unlike the brochure stores, which store everything,
ebag rows are already filtered to what clears a threshold. Any per-store average
discount will look higher for ebag as a result.

## Alerts

`ebag_alerts` (schema.sql) keys on rule + product + promo window, so a
four-week promo emails once rather than 28 times. The row is written only after
the mail is accepted, so a broken SMTP config does not silently burn the one
notification an offer gets.
