"""Collect today's cheapest new in-stock price per component from newegg.com (USD).

Same four builds as collect_regard.py, so Russian and US prices can be compared
part by part. Results come from the page's window.__initialState__ JSON, which
is present whether or not the HTML renders product cards. Searches are limited
to the component's Newegg subcategory (N=...), and every listing is checked
against the rules in CLASSES (subcategory, condition, model, characteristics);
see src/collect_rules.py. A component with no acceptable listing is written
as an explicit "not_found" row.

"not_found" is written only when Newegg answered with a readable search
result. A page that fails to load, has no window.__initialState__ JSON (a
block or captcha page), carries JSON that is not a search result, or ends
the result list early raises FetchError, and then no snapshot file is
written at all. A listing counts as new only when all four condition flags
are present and agree (IsNew, not refurbished, not open-box, ProductType 1).

Usage:
    python src/collect_newegg.py            # writes data/raw/newegg_<UTC date>.csv
"""

import json
import os
import re
import sys
import time
import urllib.error
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
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
# Text of Newegg's bot-check and block pages; such pages carry no search state.
BLOCKED_TEXT = re.compile(r"are you a human|captcha|access denied|request blocked|unusual traffic", re.I)
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


class FetchError(Exception):
    """A search page could not be loaded or read; the snapshot must not be saved."""


CONDITION_FLAGS = ("IsNew", "IsRefurbished", "IsOpenBoxed")


def _condition(feature):
    """Item condition from ItemCell.Feature. "new" only when every flag is
    present and they agree; missing data is "unknown", disagreeing flags are
    "conflicting". check() accepts only "new"."""
    if not isinstance(feature, dict):
        return "unknown"
    flags = [feature.get(k) for k in CONDITION_FLAGS]
    product_type = feature.get("ProductType")
    if not all(isinstance(f, bool) for f in flags) or type(product_type) is not int:
        return "unknown"
    is_new, refurbished, open_box = flags
    if is_new and not refurbished and not open_box and product_type == 1:
        return "new"
    if refurbished and not is_new and not open_box and product_type != 1:
        return "refurbished"
    if open_box and not is_new and not refurbished:
        return "open_box"
    return "conflicting"


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
            condition=_condition(cell.get("Feature")),
            in_stock=bool(cell.get("Instock")),
            is_bundle=bool(p.get("IsCombo")),
        ))
    return out


def state_from_html(html):
    """The search state of a results page. Raises FetchError unless the page
    holds a search result: a Products list (possibly empty) and an integer
    TotalItemCount."""
    m = re.search(r"window\.__initialState__\s*=\s*(\{.*?\})\s*;?\s*</script>", html, re.S)
    if not m:
        if BLOCKED_TEXT.search(html):
            raise FetchError("blocked: bot-check or access-denied page instead of search results")
        raise FetchError("no window.__initialState__ JSON on the page")
    try:
        state = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise FetchError(f"window.__initialState__ is not valid JSON: {e}") from None
    if not isinstance(state, dict) or not isinstance(state.get("Products"), list):
        raise FetchError("window.__initialState__ has no Products list")
    if type(state.get("TotalItemCount")) is not int:
        raise FetchError("window.__initialState__ has no TotalItemCount")
    return state


def page_url(query, n, page=1):
    return f"{SITE}/p/pl?" + urllib.parse.urlencode({"N": n, "d": query, "Order": 1, "page": page})


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:  # HTTPError, timeouts, resets
        raise FetchError(f"download failed: {e}") from None


def collect(r, fetch=fetch_html, pause=1.5):
    """All listings from up to MAX_PAGES result pages. An empty result is
    accepted only when Newegg reports it (Products [] and no items left by
    TotalItemCount); any failed or unreadable page raises FetchError."""
    found, seen = [], 0
    for page in range(1, MAX_PAGES + 1):
        url = page_url(r.queries[0], r.params["N"], page)
        try:
            state = state_from_html(fetch(url))
        except FetchError as e:
            raise FetchError(f"page {page} of {url}: {e}") from None
        products, total = state["Products"], state["TotalItemCount"]
        if not products:
            if seen < total:
                raise FetchError(f"page {page} of {url} is empty, but Newegg reports {total} items "
                                 f"and only {seen} were read")
            break
        seen += len(products)
        found += listings_from_state(state)
        if seen >= total:
            break
        time.sleep(pause)
    return found


def main(fetch=fetch_html, raw_dir=RAW, pause=1.5):
    started = datetime.now(timezone.utc)
    day = started.date().isoformat()
    out = Path(raw_dir) / f"newegg_{day}.csv"
    if out.exists():
        sys.exit(f"{out} exists; snapshots are never overwritten")
    rows = []
    for build, rules in CLASSES.items():
        for r in rules:
            try:
                listings = collect(r, fetch=fetch, pause=pause)
            except FetchError as e:
                sys.exit(f"{build}/{r.component}: {e}\nsnapshot not saved")
            best, outcomes, accepted = pick(listings, r)
            rows.append(row(date=day, collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            market="US", retailer="Newegg", currency="USD", build=build, rule=r,
                            best=best, outcomes=outcomes, accepted=accepted,
                            source=page_url(r.queries[0], r.params["N"])))
            label = f"${best.price}  {best.title[:70]}" if best else "NOT FOUND"
            print(f"{build}/{r.component}: {label}  {dict(outcomes)}", file=sys.stderr)

    # Write next to the target and rename, so an interrupted run leaves no partial snapshot.
    tmp = out.with_name(out.name + ".part")
    write(tmp, rows)
    if out.exists():
        tmp.unlink()
        sys.exit(f"{out} exists; snapshots are never overwritten")
    os.replace(tmp, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
