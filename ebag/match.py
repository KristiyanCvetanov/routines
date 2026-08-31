# -*- coding: utf-8 -*-
"""Turn a swept catalogue into offers: apply the watch list and score discounts.

Two kinds of discount exist on ebag and they work differently:

* `is_promo` products carry `discount_percent` off a reference price.
* Multipacks ("6 x 400 г") are SEPARATE products flagged `is_save_money`,
  disjoint from is_promo, with no discount_percent at all. This is ebag's
  2-for-1 equivalent, and the saving is only visible by comparing the pack's
  per-item price against the single product it bundles.
"""
import datetime as dt
import re

import rules as R

_PACK = re.compile(r"^\s*(\d+)\s*[xх]\s*", re.I)
_NAME_PCT = re.compile(r"(\d{2,3})\s*%")
_DESC_PCT = re.compile(r"(\d{2,3})\s*%\s*какао|какао[^.]{0,40}?(\d{2,3})\s*%", re.I)
_TAGS = re.compile(r"<[^>]+>")


def category_path(hit):
    h = hit.get("hierarchical_categories_bg") or {}
    return (h.get("lv5") or h.get("lv4") or h.get("lv3")
            or h.get("lv2") or h.get("lv1") or hit.get("category_name_bg_lvl1") or "")


def search_text(hit, path=None):
    """Full text for storage and free-text search -- includes the category."""
    path = category_path(hit) if path is None else path
    return " ".join(str(x) for x in [
        hit.get("name_bg"), hit.get("name_en"),
        hit.get("brand_name_bg"), hit.get("brand_name_en"), path,
    ] if x).lower()


def rule_text(hit):
    """Text a rule's `terms` match against: name and brand only.

    The category path is deliberately left out. Including it made the 'нахут'
    rule match "Био Леща Bioitalia Консерва", because the category it sits in
    is named for chickpeas. Categories are the job of `scope`.
    """
    return " ".join(str(x) for x in [
        hit.get("name_bg"), hit.get("name_en"),
        hit.get("brand_name_bg"), hit.get("brand_name_en"),
    ] if x).lower()


_PERIOD = re.compile(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")


def parse_date(value):
    """'30/12/2030' -> date. Populated for ~69% of products."""
    if not value:
        return None
    try:
        return dt.datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def parse_period(value):
    """'17/08/2026 - 15/09/2026' -> (date, date)."""
    if not value:
        return None, None
    m = _PERIOD.search(value)
    if not m:
        return None, None
    return parse_date(m.group(1)), parse_date(m.group(2))


def pack_count(hit):
    """6 from '6 x 400 г'. None when the product is not a multipack."""
    m = _PACK.match(hit.get("unit_weight_text_value_bg") or "")
    return int(m.group(1)) if m else None


def cocoa_percent(hit, description=None):
    """Cocoa share from the product name, falling back to its description.

    Returns None when neither states it -- 37 of ebag's 65 dark chocolates do
    not, and guessing would let 50% bars through an '>= 80%' rule.
    """
    m = _NAME_PCT.search(hit.get("name_bg") or "")
    if m:
        return int(m.group(1))
    if description:
        d = _TAGS.sub(" ", description)
        found = [int(a or b) for a, b in _DESC_PCT.findall(d)]
        if found:
            return max(found)
    return None


# --------------------------------------------------------------------------
# discounts
# --------------------------------------------------------------------------

def promo_discount(hit):
    regular, current = hit.get("price_eur"), hit.get("current_price_eur")
    if not hit.get("is_promo") or not regular or not current or regular <= current:
        return 0
    return round((regular - current) / regular * 100)


def multipack_discount(hit, by_id):
    """Saving of a multipack against the pack it bundles up from.

    Returns (percent, reference_hit).

    The reference in `bundle_items` is often ITSELF a multipack -- a 36 x 85 г
    box of cat food points at the 12 x 85 г box, not at one pouch. Dividing the
    box price by 36 and comparing it to the 12-pack price produced a bogus 95%
    saving. Both sides are therefore reduced to a price per single unit.
    """
    items = hit.get("bundle_items") or []
    count = pack_count(hit)
    if not items or not count:
        return 0, None
    reference = by_id.get(str(items[0].get("product_id")))
    if not reference:
        return 0, None
    ref_price = reference.get("current_price_eur")
    pack_price = hit.get("current_price_eur")
    if not ref_price or not pack_price:
        return 0, None
    ref_count = items[0].get("units_in_pack") or pack_count(reference) or 1
    per_unit = pack_price / count
    ref_per_unit = ref_price / ref_count
    if per_unit >= ref_per_unit:
        return 0, reference
    return round((ref_per_unit - per_unit) / ref_per_unit * 100), reference


def best_discount(hit, by_id):
    """(percent, kind, single) -- the better of the two mechanisms."""
    promo = promo_discount(hit)
    pack, single = multipack_discount(hit, by_id)
    if pack > promo:
        return pack, "multipack", single
    return promo, "promo", None


# --------------------------------------------------------------------------
# watch list
# --------------------------------------------------------------------------

def _block_matches(block, text, path):
    scope = block.get("scope")
    if scope and not any(path == s or path.startswith(s + " > ") or path.startswith(s)
                         for s in scope):
        return False
    terms = block.get("terms")
    if terms and not any(t in text for t in terms):
        return False
    all_terms = block.get("all_terms")
    if all_terms and not all(t in text for t in all_terms):
        return False
    return True


def rule_matches(rule, hit, text=None, path=None, description=None):
    path = category_path(hit) if path is None else path
    text = rule_text(hit) if text is None else text

    if not (_block_matches(rule, text, path)
            or (rule.get("alt") and _block_matches(rule["alt"], text, path))):
        return False
    for term in rule.get("exclude_terms") or ():
        if term in text:
            return False
    for prefix in rule.get("exclude_scope") or ():
        if path.startswith(prefix):
            return False
    if rule.get("require_farm") and not hit.get("is_farm_product"):
        return False
    if rule.get("cocoa_min") is not None:
        pct = cocoa_percent(hit, description)
        if pct is None or pct < rule["cocoa_min"]:
            return False
    return True


def match_watchlist(hit, descriptions=None):
    """Names of every watch-list rule this product satisfies."""
    path = category_path(hit)
    text = rule_text(hit)
    desc = (descriptions or {}).get(str(hit.get("id")))
    return [r["name"] for r in R.RULES
            if rule_matches(r, hit, text, path, desc)]


def needs_description(hit):
    """Dark chocolate whose name omits the cocoa share -- fetch its description."""
    path = category_path(hit)
    for rule in R.RULES:
        if rule.get("cocoa_min") is None:
            continue
        if _block_matches(rule, rule_text(hit), path):
            return _NAME_PCT.search(hit.get("name_bg") or "") is None
    return False


def blocked(hit, path=None):
    """Is this product in a branch or brand muted for the general rule?

    Category prefixes match at a path boundary, so "Напитки" mutes the drinks
    tree without also matching "Напитки и ..." should ebag ever add one. Brands
    match the brand field exactly -- see R.BLOCKED_BRANDS for why not the name.
    """
    path = category_path(hit) if path is None else path
    brands = {str(hit.get("brand_name_bg") or "").lower(),
              str(hit.get("brand_name_en") or "").lower()}
    if brands & set(R.BLOCKED_BRANDS):
        return True
    for prefix in R.BLOCK_EXCEPT:
        if path == prefix or path.startswith(prefix + " > "):
            return False
    return any(path == prefix or path.startswith(prefix + " > ")
               for prefix in R.BLOCKED_SCOPE)


def qualifies(discount, watchlist, is_blocked=False):
    """Is this an offer worth storing, per the configured thresholds?

    A watch-list rule outranks the blacklist: asking for a product by name is a
    stronger signal than the category it happens to sit in.
    """
    if watchlist and discount >= R.WATCHLIST_MIN_DISCOUNT:
        return True
    return not is_blocked and discount >= R.GENERAL_MIN_DISCOUNT
