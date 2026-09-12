# eBag.bg offers

Feeds ebag.bg offers into the grocery-deal database, into the same `deals` table
the Lidl / Billa / Metro / Fantastiko brochures already populate.

    python run.py              # sweep, score, write to deals, notify new alerts
    python run.py --dry-run    # no writes
    python run.py --cached     # reuse data/catalogue.jsonl.gz, for tuning rules

Configuration is all environment: `DATABASE_URL` (falls back to a local `.env`),
and `EBAG_PUSH_URL` / `PUSH_DISPATCH_SECRET` for the notification.

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
all counts at **≥40%**, and a watch-list item at **≥30%** earns a notification.

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
- **Psyllium husk** is the one rule with no category scope: ebag files it both
  as a pantry supplement and in the Аптека constipation aisle, and unlike
  `телешко` the word is unambiguous. The Аптека copy arrives only because a
  watch-list rule outranks the blacklist. Capsules are excluded as a supplement
  rather than husk, and `живовляк` — the plant's Bulgarian name — is
  deliberately not a term, matching only a throat spray containing the leaf.
- **Nuts and seeds** — flax, hemp, raw almond / cashew / walnut, and pistachio
  raw or roasted. The "nut, not a product made from it" part is carried by
  scope alone: ebag files "Ядки в шоколад", "Плодове в шоколад" and the nut
  butters as *siblings* of "Сурови ядки", so a leaf scope excludes them without
  a single exclude term. The blended leaves are left out on the same logic — a
  nut mix is a product containing nuts. `орех` needs one exclusion even so,
  being also how Bulgarian names the brazil nut.

## The blacklist

The general ≥40% rule is indiscriminate by design, and dredged up 42% off
кренвирши, 88 household and cosmetics rows out of 161, and the whole Аптека
supplement aisle. `BLOCKED_SCOPE` mutes branches of the tree, `BLOCKED_BRANDS`
mutes the weekly-promo detergent brands. Together they take a run from 161
offers to 46.

Both apply to the general rule **only**. A watch-list rule outranks them:
asking for a product by name is a stronger signal than the category it happens
to sit in, and `заешко месо` deliberately scopes into Замразени храни because
ebag sells no fresh rabbit — a blanket frozen block would have silently killed
that rule.

Two details worth keeping:

- **Beer, wine and spirits live under Напитки**, alongside the juice and fizzy
  drinks that are the actual noise. `BLOCK_EXCEPT` lists the five alcohol
  subtrees rather than the nine blocked siblings, so a soft-drink category ebag
  adds later is muted by default instead of leaking through.
- **Brands match the brand field, never the name.** "finish" in a name also
  catches Bushmills "Rum Cask Finish" whisky and a Wilkinson "Perfect Finish"
  tweezer; `brand_name_en` is exact where the name is not.

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

A watch-list offer over the threshold is a **push notification**, sent by the
grocery-deal app rather than from here: `notify.py` posts the offers to its
`/api/push/ebag`, and the app renders the message, sends it to the subscribed
devices and keeps it in its own notification list. This used to be an email
through Resend. The app already owned the device subscriptions and the VAPID
keys, so the alert now arrives on the phone that does the shopping, and stays
readable in the app afterwards.

What crosses the boundary is offers, not wording -- rule, product, discount,
price and the `deals.id` of the row this run wrote. The app renders them in the
reader's language, and a tap lands on that deal's row. Which means a
notification carries less than the email did: three products rather than all of
them, and no promo period or per-offer link, because that is what fits on a lock
screen. The rest is one tap away.

The deep link is good for the day it is sent. Every run replaces this store's
rows, so tomorrow's sweep gives the same offer a new `deals.id` and yesterday's
link no longer names a row -- the app opens the deals page and highlights
nothing, which is the right way for it to fail. Notifications are acted on the
day they arrive, so this is not worth an external key on `deals`.

`ebag_alerts` (schema.sql) keys on rule + product + promo window, so a four-week
promo notifies once rather than 28 times. The row is written only after the app
has accepted the notification, so an unreachable app does not silently burn the
one notification an offer gets -- the next run announces it again.

A reply of `delivered: 0` is not a failure: the app records the notification
whether or not a device receives it, which is what separates a broken push
configuration from a quiet week.
