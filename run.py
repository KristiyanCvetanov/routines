# -*- coding: utf-8 -*-
"""Daily ebag.bg offer run: sweep -> score -> watch list -> deals -> alerts.

    python run.py            # sweep live, write to the database
    python run.py --dry-run  # no writes
    python run.py --cached   # reuse data/catalogue.jsonl.gz, for iterating on rules
"""
import argparse
import datetime as dt
import gzip
import json
import os
import pathlib
import re
import sys

import ebag_api as api
import load
import match
import notify
import rules as R

HERE = pathlib.Path(__file__).parent
DATA = HERE / "data"
CACHE = DATA / "catalogue.jsonl.gz"


def dsn():
    env = os.environ.get("DATABASE_URL")
    if env:
        return env
    envfile = HERE / ".env"
    if envfile.exists():
        m = re.search(r"DATABASE_URL=(.+)", envfile.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip()
    raise SystemExit("DATABASE_URL not set (env or .env)")


def catalogue(cached):
    if cached and CACHE.exists():
        return [json.loads(l) for l in gzip.open(CACHE, "rt", encoding="utf-8")]
    hits = list(api.sweep_catalogue().values())
    DATA.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE, "wt", encoding="utf-8") as f:
        for h in hits:
            f.write(json.dumps(h, ensure_ascii=False) + "\n")
    return hits


def cocoa_descriptions(hits):
    """Dark chocolates whose name omits the cocoa share need their description.

    Only ~37 products, so this stays a targeted follow-up rather than pulling
    descriptions for all 20 000.
    """
    need = [h for h in hits if match.needs_description(h)]
    out = {}
    for i in range(0, len(need), 40):
        chunk = need[i:i + 40]
        r = api.query({
            "query": "", "hitsPerPage": len(chunk),
            "filters": " OR ".join("id=%s" % h["id"] for h in chunk),
            "attributesToRetrieve": ["id", "description_bg"],
            "attributesToHighlight": [],
        })
        for h in r["hits"]:
            out[str(h["id"])] = h.get("description_bg")
    return out


def find_offers(hits):
    by_id = {str(h["id"]): h for h in hits}
    descriptions = cocoa_descriptions(hits)
    offers = []
    for hit in hits:
        discount, kind, reference = match.best_discount(hit, by_id)
        if discount <= 0:
            continue
        watchlist = match.match_watchlist(hit, descriptions)
        if not match.qualifies(discount, watchlist):
            continue
        offers.append({"hit": hit, "discount": discount, "kind": kind,
                       "reference": reference, "watchlist": watchlist})
    offers.sort(key=lambda o: -o["discount"])
    return offers


def promo_key(offer):
    """Identifies one promo window, so an email fires once per window."""
    if offer["kind"] == "promo":
        period = offer["hit"].get("promo_period")
        if period:
            return period
    return "multipack"


def pending_alerts(offers, cur):
    """Watch-list offers over the email threshold not yet alerted this window."""
    out = []
    for offer in offers:
        if not offer["watchlist"] or offer["discount"] < R.WATCHLIST_EMAIL_DISCOUNT:
            continue
        for rule in offer["watchlist"]:
            cur.execute(
                """SELECT 1 FROM ebag_alerts
                   WHERE rule_name = %s AND source = %s
                     AND external_id = %s AND promo_key = %s""",
                (rule, load.STORE, str(offer["hit"]["id"]), promo_key(offer)))
            if not cur.fetchone():
                out.append((rule, offer))
    return out


def write(offers, run_date, conn):
    """Replace this store's rows, then email and record any new alerts.

    The alert is recorded only after the mail is actually accepted, so a broken
    SMTP config does not silently burn the one notification this offer gets.
    """
    rows = [load.to_deal(o["hit"], o["discount"], o["kind"], o["reference"], run_date)
            for o in offers]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM deals WHERE store = %s", (load.STORE,))
        cur.executemany(
            """INSERT INTO deals (store, product, normalized_product, price,
                   old_price, discount_percent, valid_from, valid_until,
                   brochure_id, category, image_url, package_value,
                   package_unit, extracted_at)
               VALUES (%(store)s, %(product)s, %(normalized_product)s, %(price)s,
                   %(old_price)s, %(discount_percent)s, %(valid_from)s,
                   %(valid_until)s, %(brochure_id)s, %(category)s, %(image_url)s,
                   %(package_value)s, %(package_unit)s, now())""", rows)

        fresh = pending_alerts(offers, cur)
    conn.commit()

    if fresh and notify.send(fresh):
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO ebag_alerts
                       (rule_name, source, external_id, promo_key, discount)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                [(rule, load.STORE, str(o["hit"]["id"]), promo_key(o), o["discount"])
                 for rule, o in fresh])
        conn.commit()
    return rows, fresh


def report(offers, fresh):
    listed = [o for o in offers if o["watchlist"]]
    print("offers            : %d  (watch list %d, general %d)"
          % (len(offers), len(listed), len(offers) - len(listed)))
    print("new email alerts  : %d" % len(fresh))
    print("\nwatch list:")
    for o in listed:
        flag = "*" if o["discount"] >= R.WATCHLIST_EMAIL_DISCOUNT else " "
        print("  %s -%2d%% %-9s %-46s %6.2f EUR  [%s]"
              % (flag, o["discount"], o["kind"], o["hit"]["name_bg"][:46],
                 o["hit"]["current_price_eur"], o["watchlist"][0][:24]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cached", action="store_true",
                    help="reuse the cached catalogue instead of sweeping")
    args = ap.parse_args()

    run_date = dt.date.today()
    hits = catalogue(args.cached)
    offers = find_offers(hits)

    if args.dry_run:
        report(offers, [])
        return

    import psycopg
    with psycopg.connect(dsn()) as conn:
        rows, fresh = write(offers, run_date, conn)
    print("wrote %d rows to deals (store=%s)" % (len(rows), load.STORE))
    report(offers, fresh)


if __name__ == "__main__":
    sys.exit(main())
