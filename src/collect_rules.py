"""Shared selection rules for the shop collectors (Regard, Newegg).

A listing is accepted for a component only if every check passes, in this
order: shop category, condition (new only), in stock, not a bundle, model,
required characteristics, excluded words. The cheapest accepted listing wins.
If nothing passes, the collector writes an explicit "not_found" row with the
reason counts instead of falling back to a near match - a missing part must
stay missing so the build is reported as incomplete.

Parsing of shop pages lives in each collector; everything here is offline and
covered by tests on saved page excerpts (tests/test_collectors.py).
"""

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

# Words that mark a listing as not new, in titles of either shop.
NOT_NEW_TEXT = (r"из ремонта|уценк|б/у|бывш|восстановлен|витрин|некомплект|дефект"
                r"|refurbish|renewed|open[ -]?box|pre-owned|\bused\b")

# A component sold together with something else ("CPU & AIO Combo") is not the component.
BUNDLE_TEXT = r"\bcombo\b|\bbundle\b"

CONDITION_NEW = "new"


@dataclass
class Listing:
    retailer: str
    product_id: str
    title: str
    url: str
    price: Decimal
    currency: str
    category: str          # shop category id or name, as the shop reports it
    condition: str         # "new", "refurbished", "open_box", "repaired", ...
    in_stock: bool
    specs: str = ""        # characteristics text the shop shows with the title
    is_bundle: bool = False

    @property
    def text(self):
        return f"{self.title} | {self.specs}".lower()


@dataclass
class Rule:
    component: str                 # raw component name written to the CSV (ram_kit, cpu, ...)
    queries: list
    categories: tuple              # accepted shop categories
    model: str                     # regex the title+specs must match
    specs: tuple = ()              # regexes that must all match
    exclude: str = ""              # regex that must not match
    qty: int = 1
    params: dict = field(default_factory=dict)   # shop-specific search parameters


def check(listing, rule):
    """Return None if the listing is acceptable, else the first failed check."""
    if str(listing.category) not in {str(c) for c in rule.categories}:
        return "category"
    if listing.condition != CONDITION_NEW or re.search(NOT_NEW_TEXT, listing.title.lower()):
        return "condition"
    if not listing.in_stock:
        return "stock"
    if listing.is_bundle or re.search(BUNDLE_TEXT, listing.title.lower()):
        return "bundle"
    text = listing.text
    if not re.search(rule.model, text):
        return "model"
    if any(not re.search(s, text) for s in rule.specs):
        return "specs"
    if rule.exclude and re.search(rule.exclude, text):
        return "excluded"
    return None


def pick(listings, rule):
    """(cheapest accepted listing or None, Counter of outcomes, accepted count).
    The same product seen on several pages or queries counts once."""
    seen, accepted, outcomes = set(), [], Counter()
    for listing in listings:
        if listing.product_id in seen:
            continue
        seen.add(listing.product_id)
        reason = check(listing, rule)
        outcomes[reason or "accepted"] += 1
        if reason is None:
            accepted.append(listing)
    best = min(accepted, key=lambda x: (x.price, x.product_id)) if accepted else None
    return best, outcomes, len(accepted)


FIELDS = ["date", "collected_at", "market", "retailer", "build", "component", "status", "sku",
          "product_id", "url", "condition", "in_stock", "category", "unit_price", "qty", "price",
          "currency", "candidates", "checked", "rejected", "source"]


def row(*, date, collected_at, market, retailer, currency, build, rule, best, outcomes, accepted, source):
    rejected = ";".join(f"{k}:{v}" for k, v in sorted(outcomes.items()) if k != "accepted")
    base = {"date": date, "collected_at": collected_at, "market": market, "retailer": retailer,
            "build": build, "component": rule.component, "qty": rule.qty, "currency": currency,
            "candidates": accepted, "checked": sum(outcomes.values()), "rejected": rejected,
            "source": source}
    if best is None:
        return {**base, "status": "not_found", "sku": "", "product_id": "", "url": "", "condition": "",
                "in_stock": "", "category": "", "unit_price": "", "price": ""}
    return {**base, "status": "ok", "sku": best.title, "product_id": best.product_id, "url": best.url,
            "condition": best.condition, "in_stock": "true" if best.in_stock else "false",
            "category": best.category, "unit_price": best.price, "price": best.price * rule.qty}


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
