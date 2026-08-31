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

Separately, BLOCKED_SCOPE and BLOCKED_BRANDS below mute whole branches of
the tree, and whole brands, for the general discount rule only -- see
match.blocked.

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
NUTS = "Сладко и солено > Ядки и семена"
RAW_NUTS = "%s > Сурови ядки" % NUTS
ROASTED_NUTS = "%s > Печени ядки" % NUTS
SEEDS = "%s > Семена" % NUTS
BIO_RAW_NUTS = "Био > Био ядки и семена > Био сурови ядки"
BIO_ROASTED_NUTS = "Био > Био ядки и семена > Био печени ядки"
BIO_SEEDS = "Био > Био ядки и семена > Био семена"
COSMETICS = "Козметика и лична грижа"


# --------------------------------------------------------------------------
# blacklist
# --------------------------------------------------------------------------
# Branches that never produce an offer on the general discount rule alone,
# however steep the discount. They are what GENERAL_MIN_DISCOUNT dredged up
# that nobody asked for: 42% off кренвирши, 88 household/cosmetics rows out of
# 161, the whole Аптека supplement aisle.
#
# A watch-list rule still overrides this -- `заешко месо` deliberately scopes
# into Замразени храни because ebag sells no fresh rabbit, and muting frozen
# outright would silently kill that rule. See match.qualifies.
BLOCKED_SCOPE = [
    "Колбаси и деликатеси",                 # deli meat, cured and sliced
    "Био > Био месо и колбаси > Био колбаси",
    "Напитки",                              # drinks -- alcohol exempted below
    "Био > Био напитки",
    "Замразени храни",                      # frozen, incl. ice cream
    "Аптека",                               # medicines, supplements, medical
    "%s > Грим" % COSMETICS,                # make-up
    "%s > Грижа за коса" % COSMETICS,       # shampoo, conditioner, styling
    "%s > Професионална грижа за коса" % COSMETICS,
    "%s > Мъжка грижа > Продукти за коса" % COSMETICS,
    "%s > Душ гел, сапуни и продукти за баня" % COSMETICS,
    "%s > Мъжка грижа > Продукти за тяло" % COSMETICS,   # мъжки душ гел
    "Био > Био козметика и лична грижа",
    "За бебето и детето > Детска козметика > Къпане и хигиена",
    "Зоомагазин",                           # pet food, litter, puppy pads
]

# Brands never worth an offer on the general rule -- the detergent and
# dishwasher aisles, which run a deep promo on something every single week.
#
# Matched against ebag's brand field, not the product name: "finish" in a name
# also catches Bushmills "Rum Cask Finish" whisky and a Wilkinson "Perfect
# Finish" tweezer. The field is exact where the name is not.
BLOCKED_BRANDS = [
    "persil",
    "perwoll",
    "somat",
    "finish",
]

# Blocked branches that are nonetheless wanted. ebag files beer, wine and
# spirits under Напитки alongside juice and fizzy drinks; only the soft ones
# are noise. Listing the exceptions rather than the nine blocked siblings keeps
# a newly added soft-drink category muted by default.
BLOCK_EXCEPT = [
    "Напитки > Вино",
    "Напитки > Бира",
    "Напитки > Високоалкохолни напитки",
    "Напитки > Ликьори и аперитиви",
    "Напитки > Сайдер, коктейли и миксове",
]

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

    # Nuts and seeds -- the nut itself, never a product made from it. Scope
    # alone carries that: ebag files "Ядки в шоколад", "Плодове в шоколад" and
    # the nut butters as siblings of "Сурови ядки", so a leaf scope excludes
    # them without a single exclude_term. The blended leaves ("Ядки микс
    # сурови", "Кедрови ядки и салатни миксове") are left out for the same
    # reason -- a mix is a product containing nuts.
    #
    # The Био tree repeats the assortment under its own shallower leaves, which
    # do not name the nut, so each rule reaches it through `alt` on terms.
    {
        "name": "псилиум",
        # No scope: ebag scatters it across pantry supplements and the Аптека
        # constipation aisle, and unlike 'телешко' the word is unambiguous.
        # The Аптека copy arrives only because a watch-list rule outranks
        # BLOCKED_SCOPE. Capsules are a supplement, not husk; and живовляк --
        # the plant's Bulgarian name -- is deliberately not a term, since it
        # matches a propolis throat spray that merely contains the leaf.
        "terms": ["псилиум", "psyllium"],
        "exclude_terms": ["капсул", "таблет", "спрей"],
    },
    {
        "name": "ленено семе",
        "scope": ["%s > Ленено семе" % SEEDS],
        "alt": {"scope": [BIO_SEEDS], "terms": ["ленен", "ленено", "flax"]},
    },
    {
        "name": "конопено семе",
        "scope": ["%s > Конопено семе" % SEEDS],
        "alt": {"scope": [BIO_SEEDS], "terms": ["конопен", "конопено", "hemp"]},
    },
    {
        "name": "сурови бадеми",
        "scope": ["%s > Бадеми сурови" % RAW_NUTS],
        "alt": {"scope": [BIO_RAW_NUTS], "terms": ["бадем", "almond"]},
    },
    {
        "name": "сурово кашу",
        "scope": ["%s > Кашу сурово" % RAW_NUTS],
        "alt": {"scope": [BIO_RAW_NUTS], "terms": ["кашу", "cashew"]},
    },
    {
        "name": "сурови орехи",
        # 'орех' is also how Bulgarian names the brazil nut, which has a leaf of
        # its own here but only the generic Био сурови ядки leaf over in Био.
        "scope": ["%s > Орехи сурови" % RAW_NUTS],
        "alt": {"scope": [BIO_RAW_NUTS], "terms": ["орех", "walnut"]},
        "exclude_terms": ["бразилск"],
    },
    {
        "name": "шамфъстък",
        # The one nut wanted roasted as well as raw.
        "scope": ["%s > Шамфъстък суров" % RAW_NUTS,
                  "%s > Шамфъстък печен" % ROASTED_NUTS],
        "alt": {"scope": [BIO_RAW_NUTS, BIO_ROASTED_NUTS],
                "terms": ["шамфъстък", "шам фъстък", "pistachio"]},
    },
]
