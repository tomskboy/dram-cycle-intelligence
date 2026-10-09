"""Collector selection rules, on page excerpts saved from the shops on 2026-10-09.

tests/fixtures/ holds trimmed copies of real search pages (only the fields the
parsers read). Each test reproduces one error seen in the 2026-10-08 snapshot
(PR #4) or found while fixing it. No network access.
"""

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import collect_newegg as newegg  # noqa: E402
import collect_regard as regard  # noqa: E402
from collect_rules import Rule, check, pick, row  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def regard_listings(name):
    return regard.listings_from_next_data(json.loads((FIX / name).read_text(encoding="utf-8")))


def newegg_listings(name):
    return newegg.listings_from_state(newegg.state_from_html((FIX / name).read_text(encoding="utf-8")))


def rule_for(module, build, component):
    return next(r for r in module.CLASSES[build] if r.component == component)


class RegardRepairedBoard(unittest.TestCase):
    """PR #4: budget_am4/motherboard was "Biostar A520MT (4640) из ремонта"."""

    def setUp(self):
        self.listings = regard_listings("regard_a520m.json")
        self.rule = rule_for(regard, "budget_am4", "motherboard")

    def test_repaired_boards_are_parsed_as_not_new(self):
        repaired = [x for x in self.listings if "ремонта" in x.title]
        self.assertEqual(len(repaired), 2)
        self.assertTrue(all(x.condition == "repaired" and x.category == regard.REPAIRED for x in repaired))

    def test_repaired_board_rejected_and_cheapest_new_board_chosen(self):
        for x in self.listings:
            if "ремонта" in x.title:
                self.assertEqual(check(x, self.rule), "category")
        best, outcomes, accepted = pick(self.listings, self.rule)
        self.assertEqual(best.title, "ASUS PRO A520M-C II/CSM")
        self.assertEqual(best.price, Decimal(4390))
        self.assertEqual(outcomes["category"], 2)
        self.assertTrue(best.url.startswith("https://www.regard.ru/product/655150/"))

    def test_condition_is_checked_even_inside_the_right_category(self):
        x = next(x for x in self.listings if "ремонта" in x.title)
        x.category = regard.MB  # a repaired item mis-filed into the board category
        self.assertEqual(check(x, self.rule), "condition")


class RegardLaptopMemory(unittest.TestCase):
    """The old single-stick and kit patterns let SO-DIMM (laptop) modules through."""

    def setUp(self):
        self.listings = regard_listings("regard_ddr4.json")

    def test_sodimm_rejected_desktop_single_stick_chosen(self):
        r = rule_for(regard, "budget_am4", "ram_single")
        for x in self.listings:
            if "SO-DIMM" in x.title and x.title.startswith("8GB"):
                self.assertEqual(check(x, r), "excluded")
        best, _, _ = pick(self.listings, r)
        self.assertEqual(best.title, "8GB DDR4 3200MHz ExeGate HiPower (EX293814RUS)")
        self.assertEqual(r.qty, 2)

    def test_sodimm_kit_rejected(self):
        r = rule_for(regard, "budget_am4", "ram_kit")
        kit = next(x for x in self.listings if "SO-DIMM" in x.title and x.title.startswith("16GB"))
        self.assertEqual(check(kit, r), "excluded")
        best, _, _ = pick(self.listings, r)
        self.assertEqual(best.price, Decimal(14040))

    def test_kit_is_not_a_single_stick(self):
        r = rule_for(regard, "budget_am4", "ram_single")
        kit = next(x for x in self.listings if "Netac" in x.title)
        self.assertIsNotNone(check(kit, r))


class NeweggPageWithoutCards(unittest.TestCase):
    """PR #4: mid/cpu and mid/gpu came back empty when the HTML had no product
    cards; the listing is read from window.__initialState__ instead."""

    def test_page_has_no_html_cards_but_listings_are_read(self):
        html = (FIX / "newegg_mid_cpu.html").read_text(encoding="utf-8")
        self.assertNotIn('class="item-cell', html)
        listings = newegg_listings("newegg_mid_cpu.html")
        self.assertGreater(len(listings), 5)
        x = listings[0]
        self.assertEqual(x.currency, "USD")
        self.assertTrue(x.url.startswith("https://www.newegg.com/p/") and "Item=" in x.url)

    def test_search_url_is_limited_to_the_subcategory(self):
        r = rule_for(newegg, "mid", "cpu")
        self.assertIn("N=100007671", newegg.page_url(r.queries[0], r.params["N"]))


class NeweggPrebuiltAndRefurbished(unittest.TestCase):
    """PR #4: mid/cpu and high/cpu were prebuilt gaming desktops."""

    def test_prebuilt_desktops_and_combos_rejected_for_cpu(self):
        r = rule_for(newegg, "budget_am5", "cpu")
        listings = newegg_listings("newegg_budget_am5_cpu.html")
        for x in listings:
            if x.category == "Gaming Desktop PC":
                self.assertEqual(check(x, r), "category", x.title)
            if "Combo" in x.title and x.category == "AMD Motherboards":
                self.assertEqual(check(x, r), "category")
        best, outcomes, _ = pick(listings, r)
        self.assertEqual(best.price, Decimal("201.02"))
        self.assertEqual(best.category, "Desktop CPU Processor")
        self.assertEqual(best.condition, "new")

    def test_refurbished_cpu_without_the_word_in_its_title_is_rejected(self):
        r = rule_for(newegg, "budget_am5", "cpu")
        x = next(x for x in newegg_listings("newegg_budget_am5_cpu.html") if x.price == Decimal("139.99"))
        self.assertNotIn("refurb", x.title.lower())
        self.assertEqual(x.condition, "refurbished")
        self.assertEqual(check(x, r), "condition")

    def test_cpu_and_cooler_combo_in_cpu_category_is_rejected(self):
        r = rule_for(newegg, "mid", "cpu")
        listings = newegg_listings("newegg_mid_cpu.html")
        combo = next(x for x in listings if "Combo" in x.title and x.category == "Desktop CPU Processor")
        self.assertEqual(check(combo, r), "bundle")
        best, _, _ = pick(listings, r)
        self.assertEqual(best.price, Decimal("194.99"))
        self.assertNotIn("&", best.title)

    def test_cpu_from_other_categories_is_rejected(self):
        r = rule_for(newegg, "mid", "cpu")
        listings = newegg_listings("newegg_mid_cpu.html")
        for cat in ("Server Accessories", "2 in 1 Accessories"):
            x = next(x for x in listings if x.category == cat)
            self.assertEqual(check(x, r), "category")


class NeweggCablesAndExplicitGap(unittest.TestCase):
    """PR #4: the cheapest results for "geforce rtx 5080" were power cables, and
    with no card in range the component silently went missing."""

    def test_cables_rejected_and_gap_is_explicit(self):
        r = rule_for(newegg, "high", "gpu")
        cables = [x for x in newegg_listings("newegg_high_gpu.html") if "Cable" in x.title]
        self.assertGreater(len(cables), 5)
        self.assertTrue(all(check(x, r) == "category" for x in cables))
        best, outcomes, accepted = pick(cables, r)
        self.assertIsNone(best)
        out = row(date="2026-10-09", collected_at="2026-10-09T13:00:00+00:00", market="US", retailer="Newegg",
                  currency="USD", build="high", rule=r, best=best, outcomes=outcomes, accepted=accepted, source="s")
        self.assertEqual(out["status"], "not_found")
        self.assertEqual((out["price"], out["sku"], out["url"]), ("", "", ""))
        self.assertTrue(out["rejected"].startswith("category:"))


class RuleOrder(unittest.TestCase):
    def test_no_fallback_to_a_near_match(self):
        r = Rule("gpu", ["x"], ("cat",), r"rtx 5070(?! ti)")
        listings = newegg_listings("newegg_high_gpu.html")
        for x in listings:
            x.category = "cat"
        best, outcomes, _ = pick(listings, r)
        self.assertIsNone(best)
        self.assertEqual(outcomes["model"], len({x.product_id for x in listings}))


if __name__ == "__main__":
    unittest.main()
