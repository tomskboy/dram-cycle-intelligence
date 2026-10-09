"""Collector selection rules, on page excerpts saved from the shops on 2026-10-09.

tests/fixtures/ holds trimmed copies of real search pages (only the fields the
parsers read). Each test reproduces one error seen in the 2026-10-08 snapshot
(PR #4) or found while fixing it. No network access.
"""

import copy
import json
import sys
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path
from unittest import mock

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


def newegg_state(name):
    return newegg.state_from_html((FIX / name).read_text(encoding="utf-8"))


def newegg_page(state):
    """A results page carrying the given search state, as Newegg embeds it."""
    return f"<html><head></head><body><script>window.__initialState__ = {json.dumps(state)};</script></body></html>"


EMPTY_RESULT = {"Products": [], "TotalItemCount": 0}
BLOCKED_PAGE = "<html><head><title>Are you a human?</title></head><body>Please complete the captcha.</body></html>"


def pages(*htmls):
    """A fake fetch returning the given pages in order and recording the URLs."""
    queue = list(htmls)

    def fetch(url):
        fetch.urls.append(url)
        page = queue.pop(0)
        if isinstance(page, Exception):
            raise page
        return page
    fetch.urls = []
    return fetch


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


class NeweggFailedPageIsNotAnEmptyResult(unittest.TestCase):
    """A page that did not load or is not a search result must stop the run,
    not turn into "not_found" rows of a snapshot that looks successful."""

    def setUp(self):
        self.rule = rule_for(newegg, "mid", "cpu")
        state = newegg_state("newegg_mid_cpu.html")
        self.first = newegg_page(state)  # 14 products of 378: more pages are expected

    def assertFetchError(self, html, text):
        with self.assertRaises(newegg.FetchError) as ctx:
            newegg.state_from_html(html)
        self.assertIn(text, str(ctx.exception))

    def test_page_without_state_json(self):
        self.assertFetchError("<html><body><div>Server busy</div></body></html>", "no window.__initialState__")

    def test_blocked_page(self):
        self.assertFetchError(BLOCKED_PAGE, "blocked")

    def test_state_json_that_does_not_parse(self):
        self.assertFetchError('<script>window.__initialState__ = {"Products": [,]};</script>', "not valid JSON")

    def test_state_without_search_result(self):
        self.assertFetchError(newegg_page({"PageInfo": {}}), "no Products list")
        self.assertFetchError(newegg_page({"Products": None, "TotalItemCount": 0}), "no Products list")
        self.assertFetchError(newegg_page({"Products": []}), "no TotalItemCount")

    def test_failed_first_page_is_not_an_empty_result(self):
        with self.assertRaises(newegg.FetchError):
            newegg.collect(self.rule, fetch=pages(BLOCKED_PAGE), pause=0)

    def test_failed_later_page_discards_the_whole_search(self):
        for bad in (BLOCKED_PAGE, "<html></html>", newegg.FetchError("download failed: HTTP Error 503")):
            fetch = pages(self.first, bad)
            with self.assertRaises(newegg.FetchError) as ctx:
                newegg.collect(self.rule, fetch=fetch, pause=0)
            self.assertIn("page 2", str(ctx.exception))
            self.assertEqual(len(fetch.urls), 2)

    def test_later_page_empty_before_the_reported_total(self):
        fetch = pages(self.first, newegg_page({"Products": [], "TotalItemCount": 378}))
        with self.assertRaises(newegg.FetchError) as ctx:
            newegg.collect(self.rule, fetch=fetch, pause=0)
        self.assertIn("Newegg reports 378 items", str(ctx.exception))

    def test_empty_first_page_with_items_reported(self):
        with self.assertRaises(newegg.FetchError):
            newegg.collect(self.rule, fetch=pages(newegg_page({"Products": [], "TotalItemCount": 5})), pause=0)

    def test_download_errors_become_fetch_errors(self):
        errors = (urllib.error.HTTPError("u", 403, "Forbidden", {}, None),
                  urllib.error.URLError("connection reset"), TimeoutError("timed out"))
        for err in errors:
            with mock.patch.object(newegg.urllib.request, "urlopen", side_effect=err):
                with self.assertRaises(newegg.FetchError):
                    newegg.fetch_html("https://www.newegg.com/p/pl?N=1")

    def test_no_snapshot_file_after_a_failed_page(self):
        n_rules = sum(len(rules) for rules in newegg.CLASSES.values())
        good = [newegg_page(EMPTY_RESULT)] * (n_rules - 1)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as ctx, mock.patch("sys.stderr"):
                newegg.main(fetch=pages(*good, BLOCKED_PAGE), raw_dir=d, pause=0)
            self.assertIn("snapshot not saved", str(ctx.exception.code))
            self.assertEqual(list(Path(d).iterdir()), [])


class NeweggEmptyResultControl(unittest.TestCase):
    """Control: a search Newegg answers with zero results is a real gap."""

    def test_empty_result_is_read_as_no_listings(self):
        self.assertEqual(newegg.listings_from_state(newegg.state_from_html(newegg_page(EMPTY_RESULT))), [])

    def test_empty_result_ends_the_search_and_gives_not_found(self):
        r = rule_for(newegg, "high", "cooler")
        fetch = pages(newegg_page(EMPTY_RESULT))
        listings = newegg.collect(r, fetch=fetch, pause=0)
        self.assertEqual((listings, len(fetch.urls)), ([], 1))
        best, outcomes, accepted = pick(listings, r)
        out = row(date="2026-10-09", collected_at="2026-10-09T13:00:00+00:00", market="US", retailer="Newegg",
                  currency="USD", build="high", rule=r, best=best, outcomes=outcomes, accepted=accepted, source="s")
        self.assertEqual((out["status"], out["candidates"], out["rejected"]), ("not_found", 0, ""))

    def test_last_page_reached_stops_without_error(self):
        state = newegg_state("newegg_mid_cpu.html")
        state["TotalItemCount"] = len(state["Products"])
        fetch = pages(newegg_page(state))
        self.assertGreater(len(newegg.collect(rule_for(newegg, "mid", "cpu"), fetch=fetch, pause=0)), 5)
        self.assertEqual(len(fetch.urls), 1)

    def test_snapshot_of_empty_results_is_written_with_explicit_gaps(self):
        n_rules = sum(len(rules) for rules in newegg.CLASSES.values())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("sys.stderr"), mock.patch("sys.stdout"):
                newegg.main(fetch=pages(*[newegg_page(EMPTY_RESULT)] * n_rules), raw_dir=d, pause=0)
            files = list(Path(d).iterdir())
            self.assertEqual(len(files), 1)
            self.assertRegex(files[0].name, r"^newegg_\d{4}-\d{2}-\d{2}\.csv$")
            lines = files[0].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), n_rules + 1)
            self.assertTrue(all(",not_found," in line for line in lines[1:]))


class NeweggConditionMetadata(unittest.TestCase):
    """A listing is new only when the Feature flags say so completely and consistently."""

    NEW = {"IsNew": True, "IsRefurbished": False, "IsOpenBoxed": False, "ProductType": 1}

    def setUp(self):
        self.rule = rule_for(newegg, "mid", "cpu")
        self.state = newegg_state("newegg_mid_cpu.html")
        best, _, _ = pick(newegg.listings_from_state(self.state), self.rule)
        self.best_id = best.product_id  # $194.99, the accepted pick

    def with_feature(self, feature):
        """The fixture page with the accepted item's Feature replaced (None: removed)."""
        state = copy.deepcopy(self.state)
        cell = next(p["ItemCell"] for p in state["Products"]
                    if p.get("ItemCell") and str(p["ItemCell"]["Item"]) == self.best_id)
        if feature is None:
            del cell["Feature"]
        else:
            cell["Feature"] = feature
        listings = newegg.listings_from_state(state)
        return listings, next(x for x in listings if x.product_id == self.best_id)

    def assertNotAccepted(self, feature, condition):
        listings, x = self.with_feature(feature)
        self.assertEqual(x.condition, condition)
        self.assertEqual(check(x, self.rule), "condition")
        best, _, _ = pick(listings, self.rule)
        self.assertNotEqual(best.product_id, self.best_id)

    def test_missing_feature(self):
        self.assertNotAccepted(None, "unknown")
        self.assertNotAccepted({}, "unknown")

    def test_missing_or_null_flags(self):
        for key in self.NEW:
            partial = {k: v for k, v in self.NEW.items() if k != key}
            self.assertNotAccepted(partial, "unknown")
            self.assertNotAccepted({**self.NEW, key: None}, "unknown")
        self.assertNotAccepted({**self.NEW, "IsNew": "true"}, "unknown")

    def test_contradictory_flags(self):
        for change in ({"IsRefurbished": True}, {"IsOpenBoxed": True}, {"ProductType": 2},
                       {"IsNew": False}, {"IsNew": False, "IsRefurbished": True, "ProductType": 1}):
            self.assertNotAccepted({**self.NEW, **change}, "conflicting")

    def test_consistent_refurbished_and_open_box(self):
        self.assertNotAccepted({"IsNew": False, "IsRefurbished": True, "IsOpenBoxed": False, "ProductType": 2},
                               "refurbished")
        self.assertNotAccepted({"IsNew": False, "IsRefurbished": False, "IsOpenBoxed": True, "ProductType": 2},
                               "open_box")

    def test_confirmed_new_item_is_accepted(self):
        """Control: the flags as Newegg sends them for a new item."""
        listings, x = self.with_feature(dict(self.NEW))
        self.assertEqual(x.condition, "new")
        self.assertIsNone(check(x, self.rule))
        best, _, _ = pick(listings, self.rule)
        self.assertEqual((best.product_id, best.price), (self.best_id, Decimal("194.99")))

    def test_fixture_pages_hold_only_complete_flags(self):
        for name in ("newegg_mid_cpu.html", "newegg_budget_am5_cpu.html", "newegg_high_gpu.html"):
            conditions = {x.condition for x in newegg_listings(name)}
            self.assertLessEqual(conditions, {"new", "refurbished"}, name)


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
