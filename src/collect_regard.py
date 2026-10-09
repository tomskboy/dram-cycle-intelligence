"""Collect today's cheapest new in-stock price per component from regard.ru.

Regard renders the product listing into the page as JSON (__NEXT_DATA__), so
we read that instead of parsing HTML. Each listing is checked against the
rules in CLASSES (shop category, condition, model, characteristics); see
src/collect_rules.py. A component with no acceptable listing is written as an
explicit "not_found" row.

Usage:
    python src/collect_regard.py            # writes data/raw/regard_<UTC date>.csv
"""

import base64
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from collect_rules import NOT_NEW_TEXT, Listing, Rule, pick, row, write
from components import PSU_BRANDS

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SORT_PRICE_ASC = {"sort": ["orderByPrice", "asc"]}
MAX_PAGES = 3
SITE = "https://www.regard.ru"

# Regard category ids (category_id_char in the listing JSON).
CPU, GPU, RAM, SSD, MB, COOLER, PSU, CASE = "1001", "1013", "1010", "1015", "1000", "5162", "1225", "1032"
# Items "из ремонта" sit in their own category (1798) under the same search, so
# the category check alone rejects them; the title check is a second guard.
REPAIRED = "1798"

NO_SODIMM = r"so-?dimm"
PSU_BRAND = rf"({PSU_BRANDS})"

# build -> list of rules. Patterns run on "title | characteristics", lowercased.
CLASSES = {
    "budget_am4": [
        Rule("cpu", ["Ryzen 5 5600"], (CPU,), r"ryzen 5 5600 (oem|box)"),
        Rule("gpu", ["RTX 5050"], (GPU,), r"rtx 5050\b", specs=(r"\b8gb\b",)),
        Rule("ram_kit", ["DDR4 3200 16Gb 2x8 KIT"], (RAM,), r"^16gb ddr4 3200",
             specs=(r"16 гб, 2 модуля ddr4",), exclude=NO_SODIMM),
        Rule("ram_single", ["DDR4 3200 8Gb"], (RAM,), r"^8gb ddr4 3200",
             specs=(r"\| 8 гб, ddr4,",), exclude=NO_SODIMM + r"|модул", qty=2),
        Rule("ssd", ["SSD 1Tb SATA", "SSD 1Tb M.2"], (SSD,), r"^1tb",
             specs=(r"внутренний ssd", r"\b1000 гб|\b1024 гб")),
        Rule("motherboard", ["A520M"], (MB,), r"\ba520m", specs=(r"matx, сокет am4, чипсет amd a520",)),
        Rule("cooler", ["SE-902-SD"], (COOLER,), r"se-902-sd"),
        Rule("psu", ["блок питания 450W", "блок питания 500W"], (PSU,), rf"^(450|500)w .*{PSU_BRAND}",
             specs=(r"мощность (450|500) вт",)),
        Rule("case", ["корпус mATX"], (CASE,), r"корпус", specs=(r"поддержка плат matx", r"без бп")),
    ],
    "budget_am5": [
        Rule("cpu", ["Ryzen 5 7500F"], (CPU,), r"ryzen 5 7500f (oem|box)"),
        Rule("gpu", ["RTX 5060"], (GPU,), r"rtx 5060 (?!ti)", specs=(r"\b8gb\b",)),
        Rule("ram", ["DDR5 6000 16Gb 2x8 KIT"], (RAM,), r"^16gb ddr5 6000",
             specs=(r"16 гб, 2 модуля ddr5",), exclude=NO_SODIMM),
        Rule("ssd", ["SSD 1Tb M.2"], (SSD,), r"^1tb", specs=(r"внутренний ssd, m\.2", r"\b1000 гб|\b1024 гб")),
        Rule("motherboard", ["материнская плата B650M"], (MB,), r"b650m",
             specs=(r"matx, сокет am5, чипсет amd b650\b",)),
        Rule("cooler", ["SE-902-SD"], (COOLER,), r"se-902-sd"),
        Rule("psu", ["блок питания 650W"], (PSU,), rf"^(600|650)w .*{PSU_BRAND}", specs=(r"мощность (600|650) вт",)),
        Rule("case", ["корпус mATX"], (CASE,), r"корпус", specs=(r"поддержка плат matx", r"без бп")),
    ],
    "mid": [
        Rule("cpu", ["Ryzen 5 9600X"], (CPU,), r"ryzen 5 9600x (oem|box)"),
        Rule("gpu", ["RTX 5070"], (GPU,), r"rtx 5070 (?!ti)", specs=(r"\b12gb\b",)),
        Rule("ram", ["DDR5 6000 32Gb 2x16 KIT"], (RAM,), r"^32gb ddr5 6000",
             specs=(r"32 гб, 2 модуля ddr5",), exclude=NO_SODIMM),
        Rule("ssd", ["SSD 2Tb M.2"], (SSD,), r"^2tb", specs=(r"внутренний ssd, m\.2", r"\b2000 гб|\b2048 гб")),
        Rule("motherboard", ["материнская плата B650"], (MB,), r"b650",
             specs=(r"\| atx, сокет am5, чипсет amd b650\b",)),
        Rule("cooler", ["SE-224-XTS"], (COOLER,), r"se-224-xts"),
        Rule("psu", ["блок питания 750W"], (PSU,), rf"^750w .*{PSU_BRAND}", specs=(r"мощность 750 вт",)),
        Rule("case", ["корпус ATX"], (CASE,), r"корпус", specs=(r"поддержка плат (e-)?atx", r"без бп")),
    ],
    "high": [
        Rule("cpu", ["Ryzen 7 9800X3D"], (CPU,), r"ryzen 7 9800x3d (oem|box)"),
        Rule("gpu", ["RTX 5080"], (GPU,), r"rtx 5080 (?!super)", specs=(r"\b16gb\b",)),
        Rule("ram", ["DDR5 6000 32Gb 2x16 KIT CL30"], (RAM,), r"^32gb ddr5 6000",
             specs=(r"32 гб, 2 модуля ddr5", r"\bcl30\b"), exclude=NO_SODIMM),
        Rule("ssd", ["Samsung 990 PRO 2Tb"], (SSD,), r"^2tb samsung 990 pro\b",
             specs=(r"внутренний ssd, m\.2",), exclude=r"heatsink|радиатор"),
        Rule("motherboard", ["материнская плата X870"], (MB,), r"x870",
             specs=(r"\| atx, сокет am5, чипсет amd x870\b",)),
        Rule("cooler", ["Peerless Assassin 120 SE"], (COOLER,), r"peerless assassin 120 se\b"),
        Rule("psu", ["блок питания 850W"], (PSU,), rf"^850w .*{PSU_BRAND}", specs=(r"мощность 850 вт",)),
        Rule("case", ["корпус ATX"], (CASE,), r"корпус", specs=(r"поддержка плат (e-)?atx", r"без бп")),
    ],
}


def listings_from_next_data(data):
    """Listings from the __NEXT_DATA__ JSON of a Regard catalog page."""
    listing = data["props"]["initialState"]["listing"]
    out = []
    for group in listing["data"].values():
        for page in group["pages"].values():
            for it in page["data"]:
                if it.get("price") in (None, "", 0):  # listed without a price: cannot be bought
                    continue
                category = str(it.get("category_id_char"))
                title = it["title"]
                repaired = category == REPAIRED or re.search(NOT_NEW_TEXT, title.lower())
                out.append(Listing(
                    retailer="Regard",
                    product_id=str(it["id"]),
                    title=title,
                    url=f"{SITE}/product/{it['id']}/{it.get('seo_url') or ''}".rstrip("/"),
                    price=Decimal(str(it["price"])),
                    currency="RUB",
                    category=category,
                    condition="repaired" if repaired else "new",
                    in_stock=bool(it.get("show_flag")),
                    specs=re.sub(r"<[^>]+>", "", it.get("brief") or ""),
                ))
    return out


def page_url(search, page=None):
    q = base64.b64encode(json.dumps(SORT_PRICE_ASC).encode()).decode().rstrip("=")
    url = f"{SITE}/catalog?search={urllib.parse.quote(search)}&q={q}"
    return url + (f"&page={page}" if page else "")


def fetch(search, page=None):
    req = urllib.request.Request(page_url(search, page), headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return listings_from_next_data(json.loads(m.group(1)))


def collect(rule):
    found = []
    for query in rule.queries:
        for page in range(1, MAX_PAGES + 1):
            items = fetch(query, page if page > 1 else None)
            if not items:
                break
            found += items
            time.sleep(1)
    return found


def main():
    started = datetime.now(timezone.utc)
    day = started.date().isoformat()
    rows = []
    for build, rules in CLASSES.items():
        for rule in rules:
            best, outcomes, accepted = pick(collect(rule), rule)
            rows.append(row(date=day, collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            market="RU", retailer="Regard", currency="RUB", build=build, rule=rule,
                            best=best, outcomes=outcomes, accepted=accepted,
                            source=page_url(rule.queries[0])))
            label = f"{best.price} x{rule.qty}  {best.title}" if best else "NOT FOUND"
            print(f"{build}/{rule.component}: {label}  {dict(outcomes)}", file=sys.stderr)

    out = Path(__file__).resolve().parents[1] / "data" / "raw" / f"regard_{day}.csv"
    if out.exists():
        sys.exit(f"{out} exists; snapshots are never overwritten")
    write(out, rows)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
