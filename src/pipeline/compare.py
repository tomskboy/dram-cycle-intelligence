"""Russia vs US, component by component and build by build.

Each component pair gets one match type:

* same_sku      - the same product on both sides (product line + capacity, or a
                  shared manufacturer part number; CPUs must also match OEM/box)
* analogous     - different product, same configuration class (same GPU chip,
                  same RAM capacity/type/speed, same PSU wattage, ...)
* different_spec - the two shops' picks differ in spec (e.g. Ryzen 5 7500F vs
                  Ryzen 5 7600, a 500 W vs a 650 W PSU)
* unverified    - one of the titles does not state the spec

A build is "сопоставимо по проверенным параметрам" (comparable on verified
parameters) when no component is different_spec or unverified. That is a
statement about the parameters in CHECKED_PARAMS only, not about full
equivalence: GPU board, SSD interface, cooler and case quality, and taxes are
not checked. The build premium compares the whole build; the same-SKU premium
uses only same_sku components - the cleaner price comparison, on less of the
build.
"""

from decimal import Decimal

from .specs import part_numbers, product_key, spec_key
from .taxonomy import COMPONENTS

MATCH_TYPES = ("same_sku", "analogous", "different_spec", "unverified")

# What spec_key verifies per component; shown next to every comparison.
CHECKED_PARAMS = {
    "cpu": "модель процессора",
    "gpu": "чип видеокарты",
    "ram": "общий объём, тип DDR, частота",
    "ssd": "объём",
    "motherboard": "чипсет",
    "psu": "мощность",
    "cooler": "не проверяется",
    "case": "не проверяется",
}

COMPARABLE = "сопоставимо по проверенным параметрам"
PARTLY = "сопоставимо частично"

# Limits that hold for every RU/US comparison, whatever the match types.
GENERAL_LIMITATIONS = (
    "проверяются только модель процессора, чип видеокарты, объём, тип и частота памяти, объём SSD, чипсет платы и мощность блока питания (колонка checked_params)",
    "видеокарта сравнивается по чипу: модель платы, частоты и охлаждение не проверяются",
    "SSD сравнивается по объёму: интерфейс (SATA или NVMe) и тип памяти не проверяются",
    "кулеры и корпуса не сравниваются по характеристикам",
    "один SKU у процессора требует одинаковой упаковки (OEM или BOX)",
    "цены в России включают НДС 22%, цены Newegg — без налога с продаж",
    "курс ЦБ на дату снимка; в каждом магазине взята самая дешёвая подходящая позиция",
)


def match_type(component, ru_item, us_item):
    ru_title, us_title = ru_item["sku"], us_item["sku"]
    key_ru, key_us = product_key(component, ru_title), product_key(component, us_title)
    if key_ru and key_ru == key_us and ru_item["qty"] == us_item["qty"]:
        return "same_sku"
    if part_numbers(ru_title) & part_numbers(us_title) and ru_item["qty"] == us_item["qty"]:
        return "same_sku"
    spec_ru = spec_key(component, ru_title, ru_item["qty"])
    spec_us = spec_key(component, us_title, us_item["qty"])
    if spec_ru is None or spec_us is None:
        return "unverified"
    return "analogous" if spec_ru == spec_us else "different_spec"


def _pct(a, b):
    return (a / b - 1) if b else None


def compare(builds, fx):
    """Pair every complete RU build with the complete US build of the same
    snapshot date and build id. Returns (component_rows, build_rows)."""
    us = {(b["snapshot_date"], b["build"]): b for b in builds if b["market"] == "US" and b["complete"]}
    components, summary = [], []
    for ru in builds:
        if ru["market"] != "RU" or not ru["complete"]:
            continue
        other = us.get((ru["snapshot_date"], ru["build"]))
        if other is None:
            continue
        rate = fx.get((ru["snapshot_date"], other["currency"]))
        if rate is None:
            raise ValueError(f"no FX rate for {other['currency']} on {ru['snapshot_date']} in data/reference/fx_rates.csv")

        counts = dict.fromkeys(MATCH_TYPES, 0)
        limits = []
        same_ru = same_us = Decimal(0)
        for c in COMPONENTS:
            if c not in ru["parts"] or c not in other["parts"]:
                continue
            r, u = ru["parts"][c], other["parts"][c]
            mt = match_type(c, r, u)
            counts[mt] += 1
            us_rub = u["line_total"] * rate
            ru_spec = spec_key(c, r["sku"], r["qty"]) or ""
            us_spec = spec_key(c, u["sku"], u["qty"]) or ""
            if mt == "different_spec":
                limits.append(f"{c}: разные характеристики ({ru_spec} и {us_spec})")
            elif mt == "unverified":
                side = " и ".join(s for s, v in (("RU", ru_spec), ("US", us_spec)) if not v)
                limits.append(f"{c}: не проверено, в названии {side} нет параметров ({CHECKED_PARAMS[c]})")
            if mt == "same_sku":
                same_ru += r["line_total"]
                same_us += us_rub
            components.append({
                "snapshot_date": ru["snapshot_date"],
                "build": ru["build"],
                "component": c,
                "ru_retailer": ru["retailer"],
                "ru_sku": r["sku"],
                "ru_qty": r["qty"],
                "ru_rub": r["line_total"],
                "us_retailer": other["retailer"],
                "us_sku": u["sku"],
                "us_qty": u["qty"],
                "us_usd": u["line_total"],
                "us_rub": us_rub,
                "match_type": mt,
                "checked_params": CHECKED_PARAMS[c],
                "ru_spec": ru_spec,
                "us_spec": us_spec,
                "ru_premium": _pct(r["line_total"], us_rub),
            })

        us_total_rub = other["total"] * rate
        summary.append({
            "snapshot_date": ru["snapshot_date"],
            "build": ru["build"],
            "ru_retailer": ru["retailer"],
            "us_retailer": other["retailer"],
            "fx_rub_per_usd": rate,
            "ru_total_rub": ru["total"],
            "us_total_usd": other["total"],
            "us_total_rub": us_total_rub,
            "ru_premium": _pct(ru["total"], us_total_rub),
            **{f"n_{m}": counts[m] for m in MATCH_TYPES},
            "same_sku_ru_rub": same_ru,
            "same_sku_us_rub": same_us,
            "same_sku_premium": _pct(same_ru, same_us) if counts["same_sku"] else None,
            "comparable_verified": not limits,
            "comparability": PARTLY if limits else COMPARABLE,
            "limitations": "; ".join(limits),
        })
    return components, summary
