"""Collect today's cheapest in-stock price per component class from regard.ru.

Regard renders the product listing into the page as JSON (__NEXT_DATA__),
so we read that instead of parsing HTML.

Usage:
    python src/collect_regard.py            # writes data/raw/regard_<date>.csv
"""

import base64
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from components import PSU_BRANDS

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SORT_PRICE_ASC = {"sort": ["orderByPrice", "asc"]}
MAX_PAGES = 3

# build -> component -> (search queries, filter on "title | brief", units needed)
CLASSES = {
    "budget_am4": {
        "cpu": (["Ryzen 5 5600"], r"ryzen 5 5600 (oem|box)", 1),
        "gpu": (["RTX 5050"], r"rtx 5050 .*8gb", 1),
        "ram_kit": (["DDR4 3200 16Gb 2x8 KIT"], r"^16gb ddr4 3200.*2x8gb kit(?!.*so-dimm)", 1),
        "ram_single": (["DDR4 3200 8Gb"], r"^8gb ddr4 3200(?!.*so-dimm)", 2),
        "ssd": (["SSD 1Tb SATA", "SSD 1Tb M.2"], r"(ssd|nvme|m\.2|sata)(?!.*внешний)", 1),
        "motherboard": (["A520M"], r"a520m", 1),
        "cooler": (["SE-902-SD"], r"se-902-sd", 1),
        "psu": (["блок питания 450W", "блок питания 500W"], rf"^(450|500)w .*({PSU_BRANDS})", 1),
        "case": (["корпус mATX"], r"^(?!.*\d{3,}w).*", 1),
    },
    "budget_am5": {
        "cpu": (["Ryzen 5 7500F"], r"ryzen 5 7500f", 1),
        "gpu": (["RTX 5060"], r"rtx 5060 (?!ti).*8gb", 1),
        "ram": (["DDR5 6000 16Gb 2x8 KIT"], r"^16gb ddr5 6000.*2x8gb kit", 1),
        "ssd": (["SSD 1Tb M.2"], r"^1tb.*внутренний ssd, m\.2", 1),
        "motherboard": (["материнская плата B650M"], r"matx, сокет am5, чипсет amd b650", 1),
        "cooler": (["SE-902-SD"], r"se-902-sd", 1),
        "psu": (["блок питания 650W"], rf"^(600|650)w .*({PSU_BRANDS})", 1),
        "case": (["корпус mATX"], r"^(?!.*\d{3,}w).*", 1),
    },
    "mid": {
        "cpu": (["Ryzen 5 9600X"], r"ryzen 5 9600x", 1),
        "gpu": (["RTX 5070"], r"rtx 5070 (?!ti).*12gb", 1),
        "ram": (["DDR5 6000 32Gb 2x16 KIT"], r"^32gb ddr5 6000.*2x16gb kit", 1),
        "ssd": (["SSD 2Tb M.2"], r"^2tb.*внутренний ssd, m\.2", 1),
        "motherboard": (["материнская плата B650"], r"\| atx, сокет am5, чипсет amd b650", 1),
        "cooler": (["SE-224-XTS"], r"se-224-xts", 1),
        "psu": (["блок питания 750W"], rf"^750w .*({PSU_BRANDS})", 1),
        "case": (["корпус ATX"], r"поддержка плат atx.*без бп", 1),
    },
    "high": {
        "cpu": (["Ryzen 7 9800X3D"], r"ryzen 7 9800x3d", 1),
        "gpu": (["RTX 5080"], r"rtx 5080 (?!super).*16gb", 1),
        "ram": (["DDR5 6000 32Gb 2x16 KIT CL30"], r"^32gb ddr5 6000.*2x16gb kit.*cl30", 1),
        "ssd": (["Samsung 990 PRO 2Tb"], r"^2tb samsung 990 pro.*внутренний ssd", 1),
        "motherboard": (["материнская плата X870"], r"\| atx, сокет am5, чипсет amd x870", 1),
        "cooler": (["Peerless Assassin 120 SE"], r"peerless assassin 120 se", 1),
        "psu": (["блок питания 850W"], rf"^850w .*({PSU_BRANDS})", 1),
        "case": (["корпус ATX"], r"поддержка плат atx.*без бп", 1),
    },
}


def fetch(search, page=None):
    q = base64.b64encode(json.dumps(SORT_PRICE_ASC).encode()).decode().rstrip("=")
    url = f"https://www.regard.ru/catalog?search={urllib.parse.quote(search)}&q={q}"
    if page:
        url += f"&page={page}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    listing = json.loads(m.group(1))["props"]["initialState"]["listing"]
    items = []
    for group in listing["data"].values():
        for p in group["pages"].values():
            items += p["data"]
    return items


def candidates(queries, pattern):
    seen, out = set(), []
    for query in queries:
        for page in range(1, MAX_PAGES + 1):
            items = fetch(query, page if page > 1 else None)
            if not items:
                break
            for it in items:
                text = f"{it['title']} | {it.get('brief') or ''}".lower()
                text = re.sub(r"<[^>]+>", "", text)
                if it["id"] in seen or not it.get("show_flag") or not re.search(pattern, text):
                    continue
                seen.add(it["id"])
                out.append(it)
            time.sleep(1)
    return out


def main():
    today = date.today().isoformat()
    rows = []
    for build, comps in CLASSES.items():
        for comp, (queries, pattern, qty) in comps.items():
            found = candidates(queries, pattern)
            if not found:
                print(f"{build}/{comp}: nothing found", file=sys.stderr)
                continue
            best = min(found, key=lambda it: it["price"])
            rows.append({
                "date": today, "market": "RU", "retailer": "Regard",
                "build": build, "component": comp, "sku": best["title"],
                "unit_price": best["price"], "qty": qty,
                "price": best["price"] * qty, "currency": "RUB",
                "candidates": len(found),
            })
            print(f"{build}/{comp}: {best['price']} x{qty}  {best['title']}  ({len(found)} candidates)")

    out = Path(__file__).resolve().parents[1] / "data" / "raw" / f"regard_{today}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
