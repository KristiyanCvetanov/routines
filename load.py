# -*- coding: utf-8 -*-
"""Map ebag offers onto the existing grocery-deal `deals` schema.

The brochure app already owns this database: `deals`, plus `price_observations`
and `price_baselines` that compute a median per product. ebag rows therefore go
into `deals` alongside lidl / billa / metro / fantastiko rather than into a
parallel table of their own.

Prices need no conversion: the brochure rows are already EUR (1 л fresh milk at
1.14, 400 г yogurt at 0.49-0.65), which is what ebag's *_eur fields hold.
"""
import datetime as dt
import re

import match

_WEEK = dt.timedelta(days=7)

STORE = "ebag"

# ebag's 16 top-level categories onto the slugs `deals.category` already uses.
_BY_PATH = [
    ("Месо и риба > Риба", "fish"),
    ("Месо и риба", "meat"),
    ("Колбаси и деликатеси", "meat_deli"),
    ("Млечни и яйца", "dairy"),
    ("Био > Био млечни продукти", "dairy"),
    ("Био > Био месо", "meat"),
    ("Био > Био основни храни", "pantry"),
    ("Био > Био сладко и солено", "sweets"),
    ("Био > Био напитки", "beverages"),
    ("Био > Био плодове и зеленчуци", "vegetables"),
    ("Напитки > Кафе", "coffee_tea"),
    ("Напитки > Чай", "coffee_tea"),
    ("Напитки > Алкохол", "alcohol"),
    ("Напитки > Бира", "alcohol"),
    ("Напитки > Вино", "alcohol"),
    ("Напитки", "beverages"),
    ("Сладко и солено > Ядки", "nuts"),
    ("Сладко и солено > Солени", "snacks"),
    ("Сладко и солено > Чипс", "snacks"),
    ("Сладко и солено", "sweets"),
    ("Замразени храни", "frozen"),
    ("Пекарна", "bakery"),
    ("Плодове и зеленчуци > Плодове", "fruits"),
    ("Плодове и зеленчуци", "vegetables"),
    ("Основни храни и консерви", "pantry"),
    ("Специални храни", "pantry"),
    ("За дома и офиса", "household"),
    ("Козметика и лична грижа", "household"),
]


def category_slug(path):
    for prefix, slug in _BY_PATH:
        if path.startswith(prefix):
            return slug
    return "other"


# Mirrors how `deals.normalized_product` already looks: casefolded, punctuation
# dropped, size tokens removed ("CLEVER Колбас Лионер 200 г" -> "clever колбас
# лионер"). Keeping the same shape is what lets ebag rows join the existing
# price_baselines by normalized_product.
_SIZE = re.compile(r"\b\d+[.,]?\d*\s*(?:г|гр|кг|мл|л|бр|g|kg|ml|l|бр\.)\b", re.I)
_PACKX = re.compile(r"\b\d+\s*[xх]\s*\d+[.,]?\d*\s*\S*", re.I)
_PUNCT = re.compile(r"[^\w\s]+", re.U)
_WS = re.compile(r"\s+")


def normalized_product(name):
    s = (name or "").lower()
    s = _PACKX.sub(" ", s)
    s = _SIZE.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


# `deals` stores grams, millilitres or item counts.
_UNIT = {"г": ("g", 1), "гр": ("g", 1), "кг": ("g", 1000),
         "мл": ("ml", 1), "л": ("ml", 1000), "бр": ("item", 1)}
_PACK_TEXT = re.compile(
    r"^\s*(?:(\d+)\s*[xх]\s*)?(\d+[.,]?\d*)\s*(кг|гр|г|мл|л|бр)\.?\s*$", re.I)


def package(pack_text):
    """('400 г') -> (400, 'g');  ('6 x 400 г') -> (2400, 'g')."""
    m = _PACK_TEXT.match(pack_text or "")
    if not m:
        return None, None
    count = int(m.group(1)) if m.group(1) else 1
    value = float(m.group(2).replace(",", "."))
    unit, factor = _UNIT[m.group(3).lower()]
    total = value * factor * count
    return round(total, 3), unit


def to_deal(hit, discount, kind, reference, run_date, path=None):
    """One `deals` row."""
    path = match.category_path(hit) if path is None else path
    name = hit.get("name_bg") or ""
    pack = hit.get("unit_weight_text_value_bg")
    price = hit.get("current_price_eur")

    if kind == "promo":
        old_price = hit.get("price_eur")
        promo_from, promo_to = match.parse_period(hit.get("promo_period"))
    else:
        # A multipack saving has no end date -- ebag simply prices the bigger
        # pack lower per unit. Rolling 7-day window, refreshed on every run, so
        # the app's valid_until filter keeps showing it without inventing a
        # deadline. `old_price` is what the same quantity costs at the
        # reference pack's unit rate.
        old_price = round(price / (1 - discount / 100.0), 2) if discount else None
        promo_from, promo_to = run_date, run_date + _WEEK

    value, unit = package(pack)
    display = "%s, %s" % (name, pack) if pack else name
    return {
        "store": STORE,
        "product": display,
        "normalized_product": normalized_product(name),
        "price": price,
        "old_price": old_price,
        "discount_percent": discount,
        "valid_from": promo_from or run_date,
        "valid_until": promo_to or (run_date + _WEEK),
        "brochure_id": "%s_%s" % (STORE, run_date.isoformat()),
        "category": category_slug(path),
        "image_url": hit.get("product_image_absolute_url"),
        "package_value": value,
        "package_unit": unit,
    }
