"""Monthly price history from Wayback Machine snapshots of regard.ru product pages.

Regard embeds product data as JSON in the page, and the Internet Archive has
kept snapshots of popular product pages since 2023, so we can read back what a
product cost in a given month.

Usage:
    python src/collect_history.py        # writes data/raw/regard_history.csv
"""

import csv
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "regard_history.csv"

# Long-lived SKUs, one or two per component class.
# (regard product id, component, label)
TRACKED = [
    (418665, "cpu", "AMD Ryzen 5 5600 OEM"),
    (379419, "motherboard", "MSI A520M-A PRO"),
    (395207, "ram_ddr4", "Kingston Fury Beast 16GB (2x8) DDR4-3200"),
    (326504, "ram_ddr4", "Kingston ValueRAM 8GB DDR4-3200"),
    (7435, "ram_ddr5", "Kingston Fury Beast 16GB (2x8) DDR5-5600"),
    (458080, "ram_ddr5", "Kingston Fury Beast 32GB (2x16) DDR5-6000"),
    (339527, "ssd_sata", "Crucial BX500 1TB"),
    (384716, "ssd_nvme", "Samsung 980 1TB"),
    (699695, "ssd_nvme", "Kingston NV3 1TB"),
    (10398, "gpu", "ASUS Dual RTX 3050 8GB"),
    (9720, "gpu", "Palit Dual RTX 4060 8GB"),
    (746540, "gpu", "MSI Ventus 2X OC RTX 5050 8GB"),
    (421781, "psu", "DeepCool PF500"),
]


def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "price-history-research"})
            return urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(4 * (i + 1))


def snapshots(product_id):
    """One snapshot per month (collapse on yyyymm)."""
    url = ("https://web.archive.org/cdx/search/cdx?url=www.regard.ru/product/"
           f"{product_id}/*&output=json&fl=timestamp,original&filter=statuscode:200"
           "&collapse=timestamp:6")
    rows = json.loads(get(url) or "[]")
    return rows[1:]


def price_from_snapshot(timestamp, original, product_id):
    html = get(f"https://web.archive.org/web/{timestamp}id_/{original}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    product = json.loads(m.group(1))["props"]["initialState"].get("product", {}).get("data") or {}
    if product.get("id") != product_id or not product.get("price"):
        return None
    return product["price"], bool(product.get("show_flag"))


def main():
    done = set()
    if OUT.exists():  # resume: the archive is slow and drops connections
        with open(OUT, encoding="utf-8") as f:
            done = {(int(r["product_id"]), r["month"]) for r in csv.DictReader(f)}
    new_file = not OUT.exists()
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "snapshot", "product_id", "component",
                                          "sku", "price", "in_stock", "currency"])
        if new_file:
            w.writeheader()
        for pid, comp, label in TRACKED:
            try:
                snaps = snapshots(pid)
            except Exception as e:
                print(f"{label}: cdx error {e}")
                continue
            print(f"{label}: {len(snaps)} monthly snapshots")
            for ts, original in snaps:
                month = f"{ts[:4]}-{ts[4:6]}"
                if (pid, month) in done:
                    continue
                try:
                    got = price_from_snapshot(ts, original, pid)
                except Exception as e:
                    print(f"  {month}: error {e}")
                    continue
                if got:
                    price, in_stock = got
                    w.writerow({"month": month, "snapshot": ts, "product_id": pid,
                                "component": comp, "sku": label, "price": price,
                                "in_stock": in_stock, "currency": "RUB"})
                    f.flush()
                    print(f"  {month}: {price} {'' if in_stock else '(out of stock)'}")
                time.sleep(1.5)


if __name__ == "__main__":
    main()
