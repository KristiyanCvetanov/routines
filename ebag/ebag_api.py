"""Algolia access for ebag.bg, plus a full-catalogue sweep.

The public search credentials are the ones the site's own JS bundle uses.

Two things make a naive sweep wrong:

* Algolia refuses /browse for this key and caps paging at 1000 hits, so the
  catalogue has to be partitioned. Category-based partitioning leaves holes --
  some products carry no lvl3 category, and this index silently ignores a
  `NOT attr:*` filter, so there is no way to ask for them. Bisecting on the
  numeric id has no such blind spot: every product has exactly one id, and the
  ranges are exhaustive by construction.

* nbHits without facets is an ESTIMATE (`exhaustiveNbHits: false`); it reports
  ~22450 against a true 20703. Any completeness check has to request facets to
  get an exact count.
* The offers are NOT all in `is_promo`. Multipacks ("6 x 400 г") are separate
  products flagged `is_save_money`, disjoint from `is_promo`, and that is where
  ebag's equivalent of a 2-for-1 lives. Getting them needs the whole catalogue,
  because the saving is only computable against the single-pack product.
"""
import json
import urllib.request

APP_ID = "JMJMDQ9HHX"
API_KEY = "42ca9458d9354298c7016ce9155d8481"
INDEX = "products"
BASE_URL = "https://www.ebag.bg"

FIELDS = [
    "id", "name_bg", "name_en", "brand_name_bg", "brand_name_en",
    "url_slug_bg", "product_image_absolute_url",
    "price_eur", "current_price_eur", "discount_percent",
    "base_unit_price", "unit_weight_type", "unit_weight_text_value_bg",
    "promo_period", "expiry_date",
    "hierarchical_categories_bg", "category_name_bg_lvl1",
    "is_available", "is_promo", "is_save_money", "is_farm_product",
    "bundle_items",
]


def query(body):
    req = urllib.request.Request(
        "https://%s-dsn.algolia.net/1/indexes/%s/query" % (APP_ID, INDEX),
        data=json.dumps(body).encode(),
        headers={
            "X-Algolia-Application-Id": APP_ID,
            "X-Algolia-API-Key": API_KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def exact_count(filters=None):
    """Exact hit count. Requesting a facet forces Algolia to count exhaustively."""
    body = {"query": "", "hitsPerPage": 0,
            "facets": ["category_name_bg_lvl1"], "maxValuesPerFacet": 1}
    if filters:
        body["filters"] = filters
    r = query(body)
    if not r.get("exhaustiveNbHits", False):
        raise RuntimeError("non-exhaustive count for %r" % filters)
    return r["nbHits"]


def _collect(lo, hi, out, on_page):
    """Page through ids in [lo, hi], bisecting while the range will not fit."""
    filters = "id>=%d AND id<=%d" % (lo, hi)
    total = exact_count(filters)
    if total == 0:
        return
    if total > 1000:
        if lo >= hi:
            raise RuntimeError("%d products share id %d" % (total, lo))
        mid = (lo + hi) // 2
        _collect(lo, mid, out, on_page)
        _collect(mid + 1, hi, out, on_page)
        return
    page = 0
    while True:
        r = query({"query": "", "hitsPerPage": 1000, "page": page,
                   "filters": filters, "attributesToRetrieve": FIELDS,
                   "attributesToHighlight": []})
        for hit in r["hits"]:
            out[str(hit["id"])] = hit
        page += 1
        if on_page:
            on_page(len(out))
        if page >= r["nbPages"]:
            return


def sweep_catalogue(progress=None):
    """Every product in the index, keyed by id."""
    out = {}
    _collect(0, 10 ** 9, out, progress)
    expected = exact_count()
    if len(out) != expected:
        raise RuntimeError("swept %d of %d products" % (len(out), expected))
    return out


def catalogue_size():
    return exact_count()
