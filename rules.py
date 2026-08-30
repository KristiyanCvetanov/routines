# -*- coding: utf-8 -*-
"""The watch list, and the thresholds that turn a product into an offer.

Every rule leads with a category scope, because ebag's category tree is curated
and exact while its product names are not. Matching "телешко" on names alone
returns 159 products, 21 of them dog food and 22 of them baby puree; scoped to
Месо и риба it returns actual beef.

Rule contract -- a product matches when BLOCK or ALT matches, and no exclusion
fires. A block matches when:

    scope     product's category path starts with one of these  (omit = any)
    terms     casefolded search text contains one of these      (omit = any)
    all_terms search text contains every one of these           (omit = none)

and additionally, for the rule as a whole:

    exclude_terms       any hit disqualifies
    exclude_scope       any prefix hit disqualifies
    require_farm        product must carry ebag's is_farm_product flag
    cocoa_min           cocoa %, read from the name and then the description

Search text is "name_bg + name_en + brand_bg + brand_en + category path",
casefolded. Bulgarian Cyrillic has no diacritics to fold.
"""

# Thresholds are global, not per-rule.
WATCHLIST_MIN_DISCOUNT = 15    # a watch-list item counts as an offer at >= this
GENERAL_MIN_DISCOUNT = 40      # anything at all counts as an offer at >= this
WATCHLIST_EMAIL_DISCOUNT = 30  # a watch-list item earns an email at >= this

MEAT = "Месо и риба"
DAIRY = "Млечни и яйца"
STAPLES = "Основни храни и консерви"
BIO_DAIRY = "Био > Био млечни продукти"
SWEETS = "Сладко и солено > Шоколад и шоколадови изделия"
CANNED_VEG = "%s > Консервирани зеленчуци" % STAPLES
BIO_STAPLES = "Био > Био основни храни"

RULES = [
    {
        "name": "скир",
        "terms": ["скир", "skyr"],
    },
    {
        "name": "гръцко кисело мляко / йогурт",
        # Scoped to dairy: 'гръцк' alone also matches "Хайвер по Гръцки",
        # "Гръцка питка" and "Сирене по Гръцка рецепта".
        "scope": [DAIRY, BIO_DAIRY],
        "terms": ["гръцк", "цеден", "цедено"],
    },
    {
        "name": "Гръцки Цеден Йогурт Обезмаслен Kri Kri 0%",
        "scope": [DAIRY, BIO_DAIRY],
        "terms": ["kri kri"],
        "all_terms": ["цеден"],
    },
    {
        "name": "яйца от свободни кокошки",
        "scope": ["%s > Яйца" % DAIRY, "%s > Био яйца" % BIO_DAIRY],
        "terms": ["свободн", "пасищн"],
    },
    {
        "name": "пуешко месо",
        "scope": [MEAT],
        "terms": ["пуешк", "пуйка"],
    },
    {
        "name": "телешко месо",
        "scope": ["%s > Телешко и говеждо месо" % MEAT,
                  "%s > Кайма > Телешка и говежда кайма" % MEAT],
    },
    {
        "name": "заешко месо",
        # ebag has no fresh-rabbit category; rabbit exists only jarred and
        # frozen sous-vide. Pate, terrine, liver and bouillon are not meat.
        "scope": ["%s > Месни консерви" % STAPLES, "Замразени храни > Замразено месо"],
        "terms": ["заешк"],
        "exclude_terms": ["пастет", "терин", "бульон", "дроб"],
    },
    {
        "name": "прясна риба",
        # Smoked, marinated and roe are excluded by simply not being in scope.
        "scope": ["%s > Риба > Цели риби" % MEAT,
                  "%s > Риба > Филета" % MEAT,
                  "%s > Риба > Котлети" % MEAT,
                  "%s > Риба > Морски дарове" % MEAT],
    },
    {
        "name": "пилешко месо от ферма",
        "scope": ["%s > Пилешко месо" % MEAT],
        "require_farm": True,   # the one item where 'от ферма' was specified
    },
    {
        "name": "паста La Molisana",
        "terms": ["molisana"],
    },
    {
        "name": "паста Rummo",
        # ebag carries none today; kept so the rule fires if it ever stocks it.
        "terms": ["rummo"],
    },
    {
        "name": "леща кафява и червена",
        "scope": ["%s > Варива > Леща" % STAPLES],
        "alt": {"scope": [CANNED_VEG, BIO_STAPLES], "terms": ["леща"]},
        "exclude_terms": ["белуга", "черна леща", "супа", "чорба"],
    },
    {
        "name": "нахут",
        "scope": ["%s > Варива > Нахут" % STAPLES],
        "alt": {"scope": [CANNED_VEG, BIO_STAPLES], "terms": ["нахут"]},
        "exclude_terms": ["брашно", "хумус", "чипс", "снакс", "супа"],
    },
    {
        "name": "черен шоколад >= 80% какао",
        "scope": ["%s > Черен шоколад" % SWEETS, "%s > Шоколад без захар" % SWEETS],
        "cocoa_min": 80,
    },
]
