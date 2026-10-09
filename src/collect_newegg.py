"""Collect today's cheapest new in-stock price per component from newegg.com (USD).

Same four builds as collect_regard.py, so Russian and US prices can be compared
part by part. Results come from the page's window.__initialState__ JSON, which
is present whether or not the HTML renders product cards. Searches are limited
to the component's Newegg subcategory (N=...), and every listing is checked
against the rules in CLASSES (subcategory, condition, model, characteristics);
see src/collect_rules.py. A component with no acceptable listing is written
as an explicit "not_found" row.

Usage:
    python src/collect_newegg.py            # writes data/raw/newegg_<UTC date>.csv
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from collect_rules import Listing, Rule, pick, row, write

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SITE = "https://www.newegg.com"
MAX_PAGES = 3
PSU_BRANDS = (r"corsair|seasonic|msi|evga|thermaltake|cooler master|be quiet|deepcool|montech|super flower"
              r"|fsp|gigabyte|asus|nzxt|lian li|phanteks|antec|silverstone|segotep|apevia|sama")

# Newegg subcategory: N value for the search URL, and the SubcategoryDescription
# its products carry. Each N was checked against the returned subcategories.
CPU = ("100007671", "Desktop CPU Processor")
GPU = ("100007709", "GPUs / Video Graphics Cards")
RAM = ("100007611", "Desktop Memory")
SSD = ("100011693", "Internal SSDs")
MB = ("100007625", "AMD Motherboards")
COOLER = ("100008000", "CPU Air Coolers")
PSU = ("100007657", "Power Supplies")
CASE = ("100007583", "Computer Cases")

NO_SODIMM = r"so-?dimm|laptop|notebook"
# One listing for several capacities ("500GB 1TB 2TB") is not a drive of the asked size.
SSD_EXCLUDE = r"external|portable|usb|\b\d+\s?(gb|tb)\b.*\b\d+\s?(gb|tb)\b"
# Subcategory "Computer Cases" also holds accessories, open frames and test benches.
CASE_EXCLUDE = r"accessor|aerodeck|bracket|panel kit|open (computer )?case|open[- ]frame|test bench|mining|server|riser"


def rule(component, query, cat, model, specs=(), exclude="", qty=1):
    return Rule(component, [query], (cat[1],), model, specs=specs, exclude=exclude, qty=qty, params={"N": cat[0]})


# build -> list of rules. Patterns run on the lowercased title.
CLASSES = {
    "budget_am4": [
        rule("cpu", "ryzen 5 5600", CPU, r"ryzen 5 5600(?![xgt\d])"),
        rule("gpu", "rtx 5050", GPU, r"rtx 5050\b", specs=(r"\b8\s?gb\b",)),
        rule("ram", "ddr4 3200 16gb", RAM, r"\b16gb \(2 x 8gb\)", specs=(r"ddr4[ -]3200",), exclude=NO_SODIMM),
        rule("ssd", "1tb ssd", SSD, r"\b1tb\b", exclude=SSD_EXCLUDE),
        rule("motherboard", "a520m", MB, r"\ba520", specs=(r"micro ?atx|matx|m-atx|a520m",)),
        rule("cooler", "cpu tower air cooler", COOLER, r"cpu (air )?cooler", specs=(r"tower",), exclude=r"low[- ]profile"),
        rule("psu", "650w power supply", PSU, rf"\b(550|600|650) ?w", specs=(rf"{PSU_BRANDS}",)),
        rule("case", "micro atx case", CASE, r"micro atx|matx|m-atx", exclude=CASE_EXCLUDE),
    ],
    "budget_am5": [
        rule("cpu", "ryzen 5 7600", CPU, r"ryzen 5 7600(?!x)"),
        rule("gpu", "rtx 5060", GPU, r"rtx 5060(?! ti)", specs=(r"\b8\s?gb\b",)),
        rule("ram", "ddr5 6000 16gb", RAM, r"\b16gb \(2 x 8gb\)", specs=(r"ddr5[ -]6000",), exclude=NO_SODIMM),
        rule("ssd", "1tb nvme", SSD, r"\b1tb\b", specs=(r"nvme|m\.2",), exclude=SSD_EXCLUDE),
        rule("motherboard", "b650m", MB, r"\bb650m\b|\bb650 .*(micro ?atx|matx|m-atx)"),
        rule("cooler", "cpu tower air cooler", COOLER, r"cpu (air )?cooler", specs=(r"tower",), exclude=r"low[- ]profile"),
        rule("psu", "650w power supply", PSU, rf"\b(600|650) ?w", specs=(rf"{PSU_BRANDS}",)),
        rule("case", "micro atx case", CASE, r"micro atx|matx|m-atx", exclude=CASE_EXCLUDE),
    ],
    "mid": [
        rule("cpu", "ryzen 5 9600x", CPU, r"ryzen 5 9600x\b"),
        rule("gpu", "rtx 5070", GPU, r"rtx 5070(?! ti)", specs=(r"\b12\s?gb\b",)),
        rule("ram", "ddr5 6000 32gb", RAM, r"\b32gb \(2 x 16gb\)", specs=(r"ddr5[ -]6000",), exclude=NO_SODIMM),
        rule("ssd", "2tb nvme", SSD, r"\b2tb\b", specs=(r"nvme|m\.2",), exclude=SSD_EXCLUDE),
        rule("motherboard", "b650 atx", MB, r"\bb650(?![em])", specs=(r"\batx\b",),
             exclude=r"micro|m-atx|matx|mini-itx|\bitx\b"),
        rule("cooler", "cpu air cooler 120mm", COOLER, r"cpu (air )?cooler", specs=(r"120 ?mm", r"tower"),
             exclude=r"low[- ]profile"),
        rule("psu", "750w power supply", PSU, r"\b750 ?w", specs=(rf"{PSU_BRANDS}",)),
        rule("case", "atx mid tower case", CASE, r"\batx mid[- ]tower", exclude=CASE_EXCLUDE),
    ],
    "high": [
        rule("cpu", "ryzen 7 9800x3d", CPU, r"ryzen 7 9800x3d\b"),
        rule("gpu", "rtx 5080", GPU, r"rtx 5080(?! super)", specs=(r"\b16\s?gb\b",)),
        rule("ram", "ddr5 6000 32gb cl30", RAM, r"\b32gb \(2 x 16gb\)", specs=(r"ddr5[ -]6000",), exclude=NO_SODIMM),
        rule("ssd", "samsung 990 pro 2tb", SSD, r"samsung (ssd )?990 pro\b", specs=(r"\b2tb\b",),
             exclude=r"heatsink|external|portable"),
        rule("motherboard", "x870 atx", MB, r"\bx870(?!e)", specs=(r"\batx\b",),
             exclude=r"micro|m-atx|matx|mini-itx|\bitx\b"),
        rule("cooler", "peerless assassin 120 se", COOLER, r"peerless assassin 120 se\b"),
        rule("psu", "850w power supply", PSU, r"\b850 ?w", specs=(rf"{PSU_BRANDS}",)),
        rule("case", "atx mid tower case", CASE, r"\batx mid[- ]tower", exclude=CASE_EXCLUDE),
    ],
}


def _condition(feature):
    if feature.get("IsRefurbished"):
        return "refurbished"
    if feature.get("IsOpenBoxed"):
        return "open_box"
    if feature.get("ProductType") not in (None, 1):
        return f"product_type_{feature.get('ProductType')}"
    return "new"


def listings_from_state(state):
    """Listings from a search page's window.__initialState__ JSON."""
    out = []
    for p in state.get("Products") or []:
        cell = p.get("ItemCell")
        if not cell:  # combo/group tiles carry no item of their own
            continue
        desc = cell.get("Description") or {}
        sub = cell.get("Subcategory") or {}
        price = cell.get("FinalPrice")
        if price in (None, ""):
            continue
        item, parent = cell.get("Item"), cell.get("ParentItem")
        out.append(Listing(
            retailer="Newegg",
            product_id=str(item),
            title=desc.get("Title") or "",
            url=f"{SITE}/p/{parent}?Item={item}" if parent else f"{SITE}/p/{item}",
            price=Decimal(str(price)),
            currency="USD",
            category=sub.get("SubcategoryDescription") or "",
            condition=_condition(cell.get("Feature") or {}),
            in_stock=bool(cell.get("Instock")),
            is_bundle=bool(p.get("IsCombo")),
        ))
    return out


def state_from_html(html):
    m = re.search(r"window\.__initialState__\s*=\s*(\{.*?\})\s*;?\s*</script>", html, re.S)
    return json.loads(m.group(1)) if m else {}


def page_url(query, n, page=1):
    return f"{SITE}/p/pl?" + urllib.parse.urlencode({"N": n, "d": query, "Order": 1, "page": page})


def collect(r):
    found = []
    for page in range(1, MAX_PAGES + 1):
        req = urllib.request.Request(page_url(r.queries[0], r.params["N"], page), headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
        items = listings_from_state(state_from_html(html))
        if not items:
            break
        found += items
        time.sleep(1.5)
    return found


def main():
    started = datetime.now(timezone.utc)
    day = started.date().isoformat()
    rows = []
    for build, rules in CLASSES.items():
        for r in rules:
            best, outcomes, accepted = pick(collect(r), r)
            rows.append(row(date=day, collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            market="US", retailer="Newegg", currency="USD", build=build, rule=r,
                            best=best, outcomes=outcomes, accepted=accepted,
                            source=page_url(r.queries[0], r.params["N"])))
            label = f"${best.price}  {best.title[:70]}" if best else "NOT FOUND"
            print(f"{build}/{r.component}: {label}  {dict(outcomes)}", file=sys.stderr)

    out = Path(__file__).resolve().parents[1] / "data" / "raw" / f"newegg_{day}.csv"
    if out.exists():
        sys.exit(f"{out} exists; snapshots are never overwritten")
    write(out, rows)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
