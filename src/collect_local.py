"""Collect current prices from DNS, Ozon, Wildberries, Yandex Market and Avito.

These sites block non-Russian and datacenter IPs, so this script is meant to be
run on your own machine. It opens a real Chrome window with a saved profile:
the first time, pick your city on DNS and solve any captcha by hand, the
profile remembers it for next runs.

Setup (once):
    pip install playwright
    playwright install chromium

Run:
    python src/collect_local.py                      # all sites
    python src/collect_local.py --sites dns avito    # only some
    python src/collect_local.py --debug              # save screenshots when nothing is found

Output: data/raw/local_<date>.csv with the cheapest matching listings per
site and component, plus a build total per site printed at the end.
"""

import argparse
import csv
import re
import time
import urllib.parse
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from components import CLASSES, USED_EXCLUDE

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / ".browser-profile"
DEBUG_DIR = ROOT / "data" / "raw" / "debug"
KEEP_PER_COMPONENT = 10

# search url (sorted cheapest first where the site supports it) and the
# pattern of a product link, used to find product cards on the page
SITES = {
    "dns": {
        "name": "DNS",
        "url": "https://www.dns-shop.ru/search/?q={q}",
        "link": r"dns-shop\.ru/product/[0-9a-f]+/",
        "condition": "new",
    },
    "ozon": {
        "name": "Ozon",
        "url": "https://www.ozon.ru/search/?text={q}&sorting=price",
        "link": r"ozon\.ru/product/",
        "condition": "new",
    },
    "wb": {
        "name": "Wildberries",
        "url": "https://www.wildberries.ru/catalog/0/search.aspx?search={q}&sort=priceup",
        "link": r"wildberries\.ru/catalog/\d+/detail\.aspx",
        "condition": "new",
    },
    "ym": {
        "name": "Yandex Market",
        "url": "https://market.yandex.ru/search?text={q}&how=aprice",
        "link": r"market\.yandex\.ru/(product--|card/)",
        "condition": "new",
    },
    "avito": {
        "name": "Avito",
        "url": "https://www.avito.ru/rossiya?q={q}&s=1",
        "link": r"avito\.ru/[^?#]+_\d{6,}",
        "condition": "used",
    },
}

# Runs in the page. Finds product links, climbs up to the smallest element
# that also contains a price, and returns title + prices from that card.
# Does not depend on CSS class names, which these sites change often.
EXTRACT_JS = r"""
(linkPattern) => {
  const re = new RegExp(linkPattern);
  const norm = (h) => h.split('?')[0].split('#')[0];
  const priceRe = /(\d[\d\s   ]{0,9})\s*₽(?!\s*\/\s*мес)/g;
  const seen = new Set();
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    if (!re.test(a.href)) continue;
    const key = norm(a.href);
    if (seen.has(key)) continue;
    let el = a, card = null;
    for (let i = 0; i < 10 && el; i++, el = el.parentElement) {
      if (/\d\s*₽/.test(el.innerText || '')) { card = el; break; }
    }
    if (!card) continue;
    const links = [...card.querySelectorAll('a[href]')].filter(x => re.test(x.href));
    if (new Set(links.map(x => norm(x.href))).size > 1) continue;  // card spans several products
    seen.add(key);
    const text = card.innerText || '';
    const prices = [...text.matchAll(priceRe)]
      .map(m => parseInt(m[1].replace(/[\s   ]/g, ''), 10))
      .filter(x => x >= 100);
    let title = links.map(x => (x.innerText || x.getAttribute('title') || '').trim())
      .sort((x, y) => y.length - x.length)[0] || '';
    if (title.length < 10) {
      const named = card.querySelector('[itemprop=name], [title]');
      title = (named && (named.innerText || named.getAttribute('title')) || text.split('\n')[0]).trim();
    }
    out.push({url: key, title: title.replace(/\s+/g, ' '), prices});
  }
  return out;
}
"""


def matches(title, rule, condition):
    t = title.lower()
    if not all(re.search(p, t) for p in rule["include"]):
        return False
    excludes = list(rule["exclude"]) + ([USED_EXCLUDE] if condition == "used" else [])
    return not any(re.search(p, t) for p in excludes)


def load_results(page, site, query, debug_name):
    url = site["url"].format(q=urllib.parse.quote(query))
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    for attempt in range(2):
        page.wait_for_timeout(4000)
        for _ in range(4):  # lazy-loaded listings
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1200)
        cards = page.evaluate(EXTRACT_JS, site["link"])
        if cards or attempt:
            break
        print(f"    no products on the page. If you see a captcha or a city prompt "
              f"in the browser, deal with it there, then press Enter here.")
        input()
    if not cards and debug_name:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(DEBUG_DIR / f"{debug_name}.png"), full_page=True)
        (DEBUG_DIR / f"{debug_name}.html").write_text(page.content(), encoding="utf-8")
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="+", choices=list(SITES), default=list(SITES))
    ap.add_argument("--build", default="budget_am4", choices=list(CLASSES))
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    today = date.today().isoformat()
    rows = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, locale="ru-RU",
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for key in args.sites:
            site = SITES[key]
            print(f"\n== {site['name']}")
            for comp, rule in CLASSES[args.build].items():
                debug_name = f"{today}_{key}_{comp}" if args.debug else None
                try:
                    cards = load_results(page, site, rule["query"], debug_name)
                except Exception as e:  # one broken page should not stop the run
                    print(f"  {comp}: error {e}")
                    continue
                found = []
                for c in cards:
                    if not c["prices"] or not matches(c["title"], rule, site["condition"]):
                        continue
                    price = min(c["prices"])
                    if price >= rule["min_price"]:
                        found.append((price, c["title"], c["url"]))
                found.sort()
                for rank, (price, title, url) in enumerate(found[:KEEP_PER_COMPONENT], 1):
                    rows.append({
                        "date": today, "market": "RU", "retailer": site["name"],
                        "condition": site["condition"], "build": args.build,
                        "component": comp, "rank": rank, "title": title,
                        "price": price, "currency": "RUB", "url": url,
                    })
                best = f"{found[0][0]} ₽  {found[0][1][:70]}" if found else "nothing matched"
                print(f"  {comp}: {best}  ({len(cards)} cards, {len(found)} matched)")
                time.sleep(2)
        ctx.close()

    if not rows:
        print("\nNothing collected.")
        return
    out = ROOT / "data" / "raw" / f"local_{today}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("\nBuild total, cheapest per component:")
    comps = list(CLASSES[args.build])
    for key in args.sites:
        name = SITES[key]["name"]
        best = {r["component"]: r["price"] for r in rows if r["retailer"] == name and r["rank"] == 1}
        missing = [c for c in comps if c not in best]
        note = f"  (missing: {', '.join(missing)})" if missing else ""
        print(f"  {name}: {sum(best.values()):,} ₽{note}".replace(",", " "))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
