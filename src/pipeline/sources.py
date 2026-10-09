"""Load raw CSVs into one item shape. Raw files are only ever read.

Each shop's collector wrote its own columns: Regard has unit_price x qty,
Newegg and DNS have one price per line (qty 1), the history file has one row
per product per month. Unknown file names raise, so a new kind of raw file is
handled on purpose rather than silently skipped.
"""

import csv
import re
from decimal import Decimal
from pathlib import Path

from .taxonomy import normalize_build, normalize_component

SNAPSHOT = re.compile(r"^(regard|newegg|dns_build)_(\d{4}-\d{2}-\d{2})\.csv$")
OTHER = {"regard_history.csv", "manual_observations.csv"}


def money(value):
    """Prices as Decimal, so totals do not pick up float noise."""
    return Decimal(str(value).strip())


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _item(row, n, source, *, sku, unit_price, qty, raw_total=None):
    component, variant = normalize_component(row["component"])
    status = row.get("status") or "ok"
    qty = int(qty)
    if status == "ok":
        unit_price = money(unit_price)
        line_total = unit_price * qty
        if raw_total is not None and money(raw_total) != line_total:
            raise ValueError(f"{source}:{n}: price {raw_total} != unit_price {unit_price} x qty {qty}")
    elif status == "not_found":
        # explicit gap written by the collector: no price, never selected
        unit_price = line_total = None
    else:
        raise ValueError(f"{source}:{n}: unknown status {status!r}")
    return {
        "snapshot_date": row["date"],
        "market": row["market"],
        "retailer": row["retailer"],
        "build": normalize_build(row["build"]),
        "component": component,
        "variant": variant,
        "raw_component": row["component"],
        "sku": sku.strip(),
        "unit_price": unit_price,
        "qty": qty,
        "line_total": line_total,
        "currency": row["currency"],
        "status": status,
        "condition": row.get("condition", ""),
        "url": row.get("url", ""),
        "collected_at": row.get("collected_at", ""),
        "rejected": row.get("rejected", ""),
        "source_file": source,
        "source_row": n,
    }


def load_snapshot(path):
    """Build line items from one shop snapshot. Two layouts exist: the original
    one (no status column) and the one written by src/collect_rules.py since
    2026-10-09 (status, url, collected_at, condition; unit_price x qty for every
    shop; "not_found" rows for explicit gaps)."""
    path = Path(path)
    kind = SNAPSHOT.match(path.name).group(1)
    items = []
    # data rows start on line 2 of the file
    for n, row in enumerate(read_csv(path), start=2):
        if "status" in row:
            items.append(_item(row, n, path.name, sku=row["sku"], unit_price=row["unit_price"],
                               qty=row["qty"], raw_total=row["price"]))
        elif kind == "regard":
            items.append(_item(row, n, path.name, sku=row["sku"], unit_price=row["unit_price"],
                               qty=row["qty"], raw_total=row["price"]))
        elif kind == "newegg":
            items.append(_item(row, n, path.name, sku=row["sku"], unit_price=row["price"], qty=1))
        else:  # dns_build
            items.append(_item(row, n, path.name, sku=row["title"], unit_price=row["price"], qty=1))
    return items


def load_history(path):
    rows = []
    for n, row in enumerate(read_csv(path), start=2):
        component, variant = normalize_component(row["component"])
        rows.append({
            "month": row["month"],
            "snapshot": row["snapshot"],
            "product_id": int(row["product_id"]),
            "component": component,
            "variant": variant,
            "sku": row["sku"],
            "price": money(row["price"]),
            "in_stock": row["in_stock"] == "True",
            "currency": row["currency"],
            "source_row": n,
        })
    return rows


_NEEDS = re.compile(r"needs\s+(\d+)")


def load_observations(path):
    """Single shelf prices from screenshots. They belong to no build; qty is
    read from the note when it says how many units a build needs."""
    rows = []
    for n, row in enumerate(read_csv(path), start=2):
        component, variant = normalize_component(row["component"])
        needs = _NEEDS.search(row["note"])
        qty = int(needs.group(1)) if needs else 1
        price = money(row["price"])
        rows.append({
            "date": row["date"],
            "market": row["market"],
            "retailer": row["retailer"],
            "component": component,
            "variant": variant,
            "sku": row["example_sku"],
            "unit_price": price,
            "qty_for_build": qty,
            "build_cost": price * qty,
            "currency": row["currency"],
            "note": row["note"],
            "source_row": n,
        })
    return rows


def load_reference(path):
    """Reference build specs: build -> component -> spec text."""
    spec = {}
    for row in read_csv(path):
        component, _ = normalize_component(row["component"])
        spec.setdefault(normalize_build(row["build"]), {})[component] = row["spec"]
    return spec


def load_fx(path):
    """(date, currency) -> RUB per unit."""
    return {(r["date"], r["currency"]): money(r["rub_per_unit"]) for r in read_csv(path)}


def discover(raw_dir):
    """Snapshot files in raw_dir, sorted; raises on CSVs it does not know."""
    snapshots = []
    for path in sorted(Path(raw_dir).glob("*.csv")):
        if SNAPSHOT.match(path.name):
            snapshots.append(path)
        elif path.name not in OTHER:
            raise ValueError(f"unknown raw file {path.name}: add a loader in src/pipeline/sources.py")
    return snapshots
