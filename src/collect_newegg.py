"""Collect today's cheapest new in-stock price per component class from newegg.com (USD).

Same four builds as collect_regard.py, so Russian and US prices can be compared
part by part. Open-box, refurbished and used listings are skipped.

Usage:
    python src/collect_newegg.py            # writes data/raw/newegg_<date>.csv
"""

import csv
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
PSU = r"corsair|seasonic|msi|evga|thermaltake|cooler master|be quiet|deepcool|montech|super flower|fsp|gigabyte|asus|nzxt|lian li|phanteks|antec|silverstone|segotep|apevia"
NOT_NEW = r"open box|refurbished|renewed|used|pre-owned|bundle|combo|gaming pc|desktop pc|prebuilt|laptop|notebook|riser|cable|bracket|backplate|water block|waterblock"

# build -> component -> (search query, title pattern, min price $)
CLASSES = {
    "budget_am4": {
        "cpu": ("AMD Ryzen 5 5600 processor", r"ryzen 5 5600(?![xgt\d])", 60),
        "gpu": ("geforce rtx 5050", r"geforce rtx 5050", 150),
        "ram": ("DDR4 3200 16GB 2 x 8GB desktop memory", r"16gb \(2 x 8gb\).*ddr4[ -]3200(?!.*so-?dimm)", 20),
        "ssd": ("1TB internal SSD", r"\b1tb\b.*(ssd|nvme|solid state)(?!.*(external|portable|usb))", 30),
        "motherboard": ("A520M motherboard AM4", r"a520", 40),
        "cooler": ("CPU air cooler tower", r"cpu (air )?cooler", 12),
        "psu": ("650W power supply", rf"(550|600|650) ?w.*({PSU})|({PSU}).*(550|600|650) ?w", 35),
        "case": ("micro ATX case", r"micro atx|matx|m-atx", 30),
    },
    "budget_am5": {
        "cpu": ("AMD Ryzen 5 7600 processor", r"ryzen 5 7600(?!x)", 100),
        "gpu": ("geforce rtx 5060", r"geforce rtx 5060(?! ti)", 200),
        "ram": ("DDR5 6000 16GB 2 x 8GB desktop memory", r"16gb \(2 x 8gb\).*ddr5[ -]6000(?!.*so-?dimm)", 30),
        "ssd": ("1TB NVMe M.2 SSD", r"\b1tb\b.*(nvme|m\.2)(?!.*(external|portable|usb))", 30),
        "motherboard": ("B650M motherboard AM5", r"b650m", 80),
        "cooler": ("CPU air cooler tower", r"cpu (air )?cooler", 12),
        "psu": ("650W power supply", rf"(600|650) ?w.*({PSU})|({PSU}).*(600|650) ?w", 40),
        "case": ("micro ATX case", r"micro atx|matx|m-atx", 30),
    },
    "mid": {
        "cpu": ("AMD Ryzen 5 9600X processor", r"ryzen 5 9600x", 150),
        "gpu": ("geforce rtx 5070", r"geforce rtx 5070(?! ti)", 400),
        "ram": ("DDR5 6000 32GB 2 x 16GB desktop memory", r"32gb \(2 x 16gb\).*ddr5[ -]6000(?!.*so-?dimm)", 50),
        "ssd": ("2TB NVMe M.2 SSD", r"\b2tb\b.*(nvme|m\.2)(?!.*(external|portable|usb))", 60),
        "motherboard": ("B650 ATX motherboard AM5", r"b650(?!m)(?!.*(micro|m-atx|matx))", 100),
        "cooler": ("CPU air cooler 120mm tower", r"cpu (air )?cooler", 20),
        "psu": ("750W power supply gold", rf"750 ?w.*({PSU})|({PSU}).*750 ?w", 60),
        "case": ("ATX mid tower case", r"atx mid[- ]tower", 40),
    },
    "high": {
        "cpu": ("AMD Ryzen 7 9800X3D processor", r"ryzen 7 9800x3d", 300),
        "gpu": ("geforce rtx 5080", r"geforce rtx 5080(?! super)", 800),
        "ram": ("DDR5 6000 32GB 2 x 16GB desktop memory", r"32gb \(2 x 16gb\).*ddr5[ -]6000(?!.*so-?dimm)", 50),
        "ssd": ("Samsung 990 PRO 2TB", r"990 pro.*\b2tb\b(?!.*heatsink)", 100),
        "motherboard": ("X870 ATX motherboard", r"x870(?!.*micro)", 150),
        "cooler": ("Thermalright Peerless Assassin 120 SE", r"peerless assassin 120 se", 25),
        "psu": ("850W power supply gold", rf"850 ?w.*({PSU})|({PSU}).*850 ?w", 70),
        "case": ("ATX mid tower case", r"atx mid[- ]tower", 40),
    },
}


def search(query, pages=3):
    items = []
    for page in range(1, pages + 1):
        url = f"https://www.newegg.com/p/pl?d={urllib.parse.quote_plus(query)}&Order=1&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        text = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
        for cell in re.findall(r'<div class="item-cell".*?(?=<div class="item-cell"|$)', text, re.S):
            t = re.search(r'class="item-title"[^>]*>(.*?)</a>', cell, re.S)
            p = re.search(r'price-current[^>]*>.*?<strong>([\d,]+)</strong><sup>(\.\d+)</sup>', cell, re.S)
            if t and p:
                items.append((float(p.group(1).replace(",", "") + p.group(2)),
                              html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()))
        time.sleep(1.5)
    return items


def main():
    today = date.today().isoformat()
    rows = []
    for build, comps in CLASSES.items():
        for comp, (query, pattern, floor) in comps.items():
            try:
                found = [(p, t) for p, t in search(query)
                         if p >= floor and re.search(pattern, t.lower()) and not re.search(NOT_NEW, t.lower())]
            except Exception as e:
                print(f"{build}/{comp}: error {e}", file=sys.stderr)
                continue
            if not found:
                print(f"{build}/{comp}: nothing found", file=sys.stderr)
                continue
            price, title = min(found)
            rows.append({"date": today, "market": "US", "retailer": "Newegg", "build": build,
                         "component": comp, "sku": title, "price": price, "currency": "USD",
                         "candidates": len(found)})
            print(f"{build}/{comp}: ${price:.2f}  {title[:80]}  ({len(found)} candidates)")

    out = Path(__file__).resolve().parents[1] / "data" / "raw" / f"newegg_{today}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
