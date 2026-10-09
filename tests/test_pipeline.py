"""Tests for src/pipeline. Run from the repository root: python -m unittest"""

import csv
import hashlib
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.pipeline import PROCESSED, RAW, REFERENCE, run, stale, write
from src.pipeline.builds import assemble, select_alternatives
from src.pipeline.compare import compare, match_type
from src.pipeline.sources import discover, load_observations, load_snapshot
from src.pipeline.specs import parse_ram, part_numbers, product_key, spec_key
from src.pipeline.taxonomy import normalize_build, normalize_component

REF = {b: {"cpu": "", "gpu": "", "ram": "16 GB DDR4-3200 (2x8)", "ssd": "", "motherboard": "",
           "cooler": "", "psu": "", "case": ""} for b in ("budget_am4",)}

REGARD_HEADER = ["date", "market", "retailer", "build", "component", "sku", "unit_price", "qty", "price",
                 "currency", "candidates"]


def regard_row(component, sku, unit, qty=1, build="budget_am4", date="2026-01-01"):
    return [date, "RU", "Regard", build, component, sku, unit, qty, unit * qty, "RUB", 1]


FULL_AM4 = [
    regard_row("cpu", "AMD Ryzen 5 5600 OEM", 10000),
    regard_row("gpu", "NVIDIA GeForce RTX 5050 8GB", 40000),
    regard_row("ram_kit", "16GB DDR4 3200MHz Brand (2x8GB KIT)", 12000),
    regard_row("ram_single", "8GB DDR4 3200MHz Brand", 5500, qty=2),
    regard_row("ssd", "1TB Brand", 9000),
    regard_row("motherboard", "Brand A520M", 5000),
    regard_row("cooler", "Some cooler", 1000),
    regard_row("psu", "500W Brand", 3000),
    regard_row("case", "Some case", 1500),
]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def item(component, sku, line_total, qty=1, variant="", **kw):
    base = {"snapshot_date": "2026-01-01", "market": "RU", "retailer": "Regard", "build": "budget_am4",
            "component": component, "variant": variant, "raw_component": component, "sku": sku,
            "unit_price": Decimal(line_total) / qty, "qty": qty, "line_total": Decimal(line_total),
            "currency": "RUB", "source_file": "t.csv", "source_row": 2}
    base.update(kw)
    return base


class Taxonomy(unittest.TestCase):
    def test_build_aliases(self):
        self.assertEqual(normalize_build("budget"), "budget_am5")
        self.assertEqual(normalize_build(" Budget_AM4 "), "budget_am4")
        self.assertEqual(normalize_build("high"), "high")

    def test_component_aliases_keep_variant(self):
        self.assertEqual(normalize_component("ram_kit"), ("ram", "kit"))
        self.assertEqual(normalize_component("ram_single"), ("ram", "single"))
        self.assertEqual(normalize_component("ram_ddr5"), ("ram", "ddr5"))
        self.assertEqual(normalize_component("ssd_nvme"), ("ssd", "nvme"))
        self.assertEqual(normalize_component("psu"), ("psu", ""))

    def test_unknown_names_raise(self):
        with self.assertRaises(ValueError):
            normalize_build("ultra")
        with self.assertRaises(ValueError):
            normalize_component("fan")


class Specs(unittest.TestCase):
    def test_ram_kit_and_single(self):
        self.assertEqual(parse_ram("16GB DDR4 3200MHz Netac (2x8GB KIT)"),
                         {"capacity_gb": 16, "modules": 2, "ddr": "ddr4", "speed": 3200})
        self.assertEqual(parse_ram("Silicon Power 16GB (2 x 8GB) DDR4 3200 (PC4 25600)"),
                         {"capacity_gb": 16, "modules": 2, "ddr": "ddr4", "speed": 3200})
        self.assertEqual(parse_ram("8GB DDR4 3200MHz ExeGate Value")["capacity_gb"], 8)
        self.assertIsNone(parse_ram("Оперативная память Digma DGMAD43200016D 16 ГБ")["ddr"])

    def test_ram_spec_accounts_for_qty(self):
        self.assertEqual(spec_key("ram", "8GB DDR4 3200MHz ExeGate", qty=2), "16gb ddr4-3200")
        self.assertEqual(spec_key("ram", "8GB DDR4 3200MHz ExeGate", qty=1), "8gb ddr4-3200")

    def test_other_specs(self):
        self.assertEqual(spec_key("gpu", "NVIDIA GeForce RTX 5060 Ti 16GB"), "rtx 5060 ti")
        self.assertEqual(spec_key("ssd", '1024 ГБ 2.5" SATA накопитель DEXP C100'), "1tb")
        self.assertEqual(spec_key("motherboard", "MSI PRO X870E-P WIFI"), "x870e")
        self.assertEqual(spec_key("motherboard", "Biostar A520MHP 2.0"), "a520")
        self.assertEqual(spec_key("psu", "Блок питания Formula ECO-500W"), "500w")
        self.assertEqual(spec_key("cpu", "AMD Ryzen 7 9800X3D - Ryzen 7 9000 Series"), "ryzen 7 9800x3d")

    def test_cpu_identity_needs_packaging(self):
        self.assertEqual(product_key("cpu", "AMD Ryzen 5 5600 OEM"), "amd ryzen 5 5600 oem")
        self.assertEqual(product_key("cpu", "AMD Ryzen 5 5600 with Wraith Stealth Cooler"), "amd ryzen 5 5600 box")
        self.assertIsNone(product_key("cpu", "AMD Ryzen 5 9600X - Ryzen 5 9000 Series"))

    def test_part_numbers_skip_standards(self):
        self.assertEqual(part_numbers("2TB Samsung 990 PRO (MZ-V9P2T0BW)"), {"MZ-V9P2T0BW"})
        self.assertEqual(part_numbers("16GB (2 x 8GB) DDR4 3200 (PC4 25600) PCIE-4"), set())


class MatchTypes(unittest.TestCase):
    def check(self, component, ru, us, expected, ru_qty=1, us_qty=1):
        got = match_type(component, {"sku": ru, "qty": ru_qty}, {"sku": us, "qty": us_qty})
        self.assertEqual(got, expected, f"{ru} vs {us}")

    def test_same_sku(self):
        self.check("ssd", "2TB Samsung 990 PRO (MZ-V9P2T0BW)", "SAMSUNG 990 PRO 2TB, 3-bit MLC V-NAND", "same_sku")
        self.check("cpu", "AMD Ryzen 7 9800X3D OEM", "AMD Ryzen 7 9800X3D - 100-000001084 - OEM", "same_sku")
        self.check("gpu", "RTX 5070 Brand (GV-N5070EAGLE)", "Gigabyte RTX 5070 GV-N5070EAGLE", "same_sku")

    def test_same_product_different_packaging_is_analogous(self):
        self.check("cpu", "AMD Ryzen 5 5600 OEM", "AMD Ryzen 5 5600 with Wraith Stealth Cooler", "analogous")

    def test_analogous_and_different_spec(self):
        self.check("gpu", "NVIDIA GeForce RTX 5070 Palit Infinity 3 12GB", "GIGABYTE Eagle GeForce RTX 5070 12GB", "analogous")
        self.check("cpu", "AMD Ryzen 5 7500F OEM", "AMD Ryzen 5 7600 - Ryzen 5 7000 Series", "different_spec")
        self.check("psu", "500W Formula FV-500WD", "SEGOTEP 650W 80 Plus Gold", "different_spec")
        self.check("ram", "8GB DDR4 3200MHz ExeGate", "Silicon Power 16GB (2 x 8GB) DDR4 3200", "analogous", ru_qty=2)

    def test_same_title_different_qty_is_not_same_sku(self):
        self.check("ram", "8GB DDR4 3200MHz Kingston (KVR32N22S8-8)", "Kingston 8GB DDR4 3200 KVR32N22S8-8",
                   "different_spec", ru_qty=2, us_qty=1)

    def test_missing_spec_is_unverified(self):
        self.check("ram", "Оперативная память Digma DGMAD43200016D 16 ГБ", "Silicon Power 16GB (2 x 8GB) DDR4 3200",
                   "unverified")


class Selection(unittest.TestCase):
    def test_cheapest_alternative_meeting_spec(self):
        items = [item("ram", "16GB DDR4 3200MHz (2x8GB KIT)", 12990, variant="kit"),
                 item("ram", "8GB DDR4 3200MHz", 11880, qty=2, variant="single")]
        select_alternatives(items, REF)
        self.assertEqual([i["selected"] for i in items], [False, True])

    def test_cheaper_alternative_below_spec_is_skipped(self):
        items = [item("ram", "16GB DDR4 3200MHz (2x8GB KIT)", 12990, variant="kit"),
                 item("ram", "8GB DDR4 3200MHz", 5940, qty=1, variant="single")]
        select_alternatives(items, REF)
        self.assertEqual([i["selected"] for i in items], [True, False])
        self.assertFalse(items[1]["meets_spec"])

    def test_tie_goes_to_fewer_units(self):
        items = [item("ram", "8GB DDR4 3200MHz", 12000, qty=2, variant="single"),
                 item("ram", "16GB DDR4 3200MHz (2x8GB KIT)", 12000, variant="kit")]
        select_alternatives(items, REF)
        self.assertEqual([i["variant"] for i in items if i["selected"]], ["kit"])


NEWEGG_HEADER = ["date", "market", "retailer", "build", "component", "sku", "price", "currency", "candidates"]
FULL_AM4_US = [["2026-01-01", "US", "Newegg", "budget_am4", c, sku, price, "USD", 1] for c, sku, price in (
    ("cpu", "AMD Ryzen 5 5600 with Wraith Stealth Cooler", 100),
    ("gpu", "GeForce RTX 5050 8GB", 300),
    ("ram", "Brand 16GB (2 x 8GB) DDR4 3200", 100),
    ("ssd", "Brand 1TB NVMe", 100),
    ("motherboard", "Brand A520M", 70),
    ("cooler", "Some cooler", 20),
    ("psu", "Brand 500W", 50),
    ("case", "Some case", 30),
)]
RAM_OK = [regard_row("ram_single", "8GB DDR4 3200MHz Brand", 5500, qty=2)]
RAM_ONE_OFF_SPEC = [regard_row("ram_single", "8GB DDR4 3200MHz Brand", 5500, qty=1)]
RAM_ALL_OFF_SPEC = [regard_row("ram_kit", "8GB DDR4 3200MHz Brand (2x4GB KIT)", 4000),
                    regard_row("ram_single", "16GB DDR5 6000MHz Brand", 9000)]


def run_with_ram(ram_rows):
    """Full pipeline on a temporary raw directory: a Regard AM4 build with the
    given RAM lines plus a complete Newegg AM4 build of the same date."""
    with tempfile.TemporaryDirectory() as d:
        raw, ref = Path(d) / "raw", Path(d) / "reference"
        raw.mkdir()
        ref.mkdir()
        rows = [r for r in FULL_AM4 if not r[4].startswith("ram")] + ram_rows
        write_csv(raw / "regard_2026-01-01.csv", REGARD_HEADER, rows)
        write_csv(raw / "newegg_2026-01-01.csv", NEWEGG_HEADER, FULL_AM4_US)
        shutil.copy(RAW / "regard_history.csv", raw)
        shutil.copy(RAW / "manual_observations.csv", raw)
        shutil.copy(REFERENCE / "builds.csv", ref)
        write_csv(ref / "fx_rates.csv", ["date", "currency", "rub_per_unit", "source"],
                  [["2026-01-01", "USD", "80", "test"]])
        tables = run(raw, ref)
    out = {}
    for name, (header, rows) in tables.items():
        out[name] = [dict(zip(header, r)) for r in rows]
    return out


class RamOffSpec(unittest.TestCase):
    """RAM lines that miss the reference spec are never selected; the build is
    incomplete and left out of the RU/US comparison."""

    def test_single_off_spec_line_is_not_selected(self):
        items = [item("ram", "8GB DDR4 3200MHz Brand", 5940, qty=1, variant="single")]
        select_alternatives(items, REF)
        self.assertFalse(items[0]["selected"])
        self.assertFalse(items[0]["meets_spec"])

    def test_all_off_spec_alternatives_are_not_selected(self):
        items = [item("ram", "8GB DDR4 3200MHz (2x4GB KIT)", 4000, variant="kit"),
                 item("ram", "16GB DDR5 6000MHz", 9000, variant="single")]
        select_alternatives(items, REF)
        self.assertEqual([i["selected"] for i in items], [False, False])
        self.assertEqual([i["meets_spec"] for i in items], [False, False])

    def test_control_valid_ram_is_compared(self):
        out = run_with_ram(RAM_OK)
        ru = next(b for b in out["builds.csv"] if b["market"] == "RU")
        self.assertTrue(ru["complete"])
        self.assertEqual(len(out["ru_us_builds.csv"]), 1)

    def assert_incomplete_and_not_compared(self, ram_rows, lines):
        out = run_with_ram(ram_rows)
        ru = next(b for b in out["builds.csv"] if b["market"] == "RU")
        self.assertFalse(ru["complete"])
        self.assertEqual(ru["missing_components"], "ram")
        self.assertEqual(ru["incomplete_reason"], f"ram: {lines} line(s) collected, none meets reference spec")
        self.assertEqual(ru["ram_choice"], "")
        # total without RAM: 10000+40000+9000+5000+1000+3000+1500
        self.assertEqual(ru["total"], Decimal(69500))
        self.assertEqual(out["ru_us_builds.csv"], [])
        self.assertEqual(out["ru_us_components.csv"], [])

    def test_single_off_spec_line_makes_build_incomplete(self):
        self.assert_incomplete_and_not_compared(RAM_ONE_OFF_SPEC, 1)

    def test_all_off_spec_alternatives_make_build_incomplete(self):
        self.assert_incomplete_and_not_compared(RAM_ALL_OFF_SPEC, 2)


class Builds(unittest.TestCase):
    def test_qty_multiplies_and_total_uses_one_ram(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "regard_2026-01-01.csv"
            write_csv(path, REGARD_HEADER, FULL_AM4)
            items = select_alternatives(load_snapshot(path), REF)
        single = next(i for i in items if i["variant"] == "single")
        self.assertEqual(single["line_total"], Decimal(11000))
        (build,) = assemble(items, REF)
        self.assertTrue(build["complete"])
        # 10000+40000+11000 (2 x 5500, not the 12000 kit)+9000+5000+1000+3000+1500
        self.assertEqual(build["total"], Decimal(80500))
        self.assertEqual(build["ram_choice"], "single x2")

    def test_incomplete_build_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "regard_2026-01-01.csv"
            write_csv(path, REGARD_HEADER, [r for r in FULL_AM4 if r[4] not in ("psu", "case")])
            items = select_alternatives(load_snapshot(path), REF)
        (build,) = assemble(items, REF)
        self.assertFalse(build["complete"])
        self.assertEqual(build["missing_components"], "psu;case")
        self.assertEqual(build["components_present"], 6)

    def test_price_must_equal_unit_times_qty(self):
        bad = regard_row("ram_single", "8GB DDR4", 5500, qty=2)
        bad[8] = 5500
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "regard_2026-01-01.csv"
            write_csv(path, REGARD_HEADER, [bad])
            with self.assertRaises(ValueError):
                load_snapshot(path)

    def test_incomplete_builds_are_not_compared(self):
        ru = {"snapshot_date": "d", "market": "RU", "retailer": "R", "build": "mid", "complete": False,
              "currency": "RUB", "total": Decimal(1), "parts": {}}
        us = dict(ru, market="US", retailer="N", currency="USD", complete=True)
        self.assertEqual(compare([ru, us], {("d", "USD"): Decimal(80)}), ([], []))

    def test_unknown_raw_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ozon_2026-01-01.csv").write_text("x\n")
            with self.assertRaises(ValueError):
                discover(d)

    def test_observation_qty_from_note(self):
        rows = load_observations(RAW / "manual_observations.csv")
        ram = next(r for r in rows if r["component"] == "ram")
        self.assertEqual((ram["qty_for_build"], ram["build_cost"]), (2, Decimal(12998)))


class RepositoryData(unittest.TestCase):
    """The pipeline on the CSVs committed in data/raw/."""

    @classmethod
    def setUpClass(cls):
        cls.tables = run()

    def rows(self, name):
        header, rows = self.tables[name]
        return [dict(zip(header, r)) for r in rows]

    def test_build_totals_match_published_numbers(self):
        totals = {(b["retailer"], b["snapshot_date"], b["build"]): b["total"] for b in self.rows("builds.csv")}
        self.assertEqual(totals[("Regard", "2026-09-24", "budget_am4")], Decimal("90260"))
        self.assertEqual(totals[("Regard", "2026-09-24", "budget_am5")], Decimal("132190"))
        self.assertEqual(totals[("Regard", "2026-09-24", "mid")], Decimal("206410"))
        self.assertEqual(totals[("Regard", "2026-09-24", "high")], Decimal("339300"))
        self.assertEqual(totals[("DNS", "2026-09-24", "budget_am4")], Decimal("84294"))
        self.assertEqual(totals[("Newegg", "2026-09-24", "budget_am4")], Decimal("815.36"))
        self.assertEqual(totals[("Newegg", "2026-09-24", "high")], Decimal("3086.34"))

    def test_only_the_explicit_gap_is_incomplete(self):
        incomplete = [(b["snapshot_date"], b["retailer"], b["build"], b["incomplete_reason"])
                      for b in self.rows("builds.csv") if not b["complete"]]
        self.assertEqual(incomplete, [("2026-10-09", "Regard", "high", "motherboard: not found at the shop")])

    def test_one_selected_line_per_component(self):
        seen = {}
        for it in self.rows("items.csv"):
            if it["selected"]:
                key = (it["snapshot_date"], it["retailer"], it["build"], it["component"])
                self.assertNotIn(key, seen)
                seen[key] = it
        builds = self.rows("builds.csv")
        self.assertEqual(len(seen), sum(b["components_present"] for b in builds))
        self.assertEqual(len(seen), len(builds) * 8 - 1)  # one explicit gap

    def test_ru_us_match_types(self):
        mt = {(r["build"], r["ru_retailer"], r["component"]): r["match_type"]
              for r in self.rows("ru_us_components.csv") if r["snapshot_date"] == "2026-09-24"}
        self.assertEqual(mt[("high", "Regard", "ssd")], "same_sku")
        self.assertEqual(mt[("high", "Regard", "cpu")], "same_sku")
        self.assertEqual(mt[("budget_am4", "Regard", "cpu")], "analogous")
        self.assertEqual(mt[("budget_am5", "Regard", "cpu")], "different_spec")
        self.assertEqual(mt[("high", "Regard", "motherboard")], "different_spec")

    def test_premiums(self):
        b = {(r["build"], r["ru_retailer"]): r for r in self.rows("ru_us_builds.csv") if r["snapshot_date"] == "2026-09-24"}
        self.assertEqual(round(Decimal(b[("mid", "Regard")]["ru_premium"]) * 100), 27)
        self.assertTrue(b[("mid", "Regard")]["comparable_verified"])
        self.assertEqual(b[("mid", "Regard")]["comparability"], "сопоставимо по проверенным параметрам")
        self.assertEqual(b[("mid", "Regard")]["limitations"], "")
        self.assertFalse(b[("budget_am4", "Regard")]["comparable_verified"])
        self.assertEqual(b[("budget_am4", "Regard")]["limitations"], "psu: разные характеристики (500w и 650w)")
        self.assertIn("ram: не проверено, в названии RU нет параметров", b[("budget_am4", "DNS")]["limitations"])
        self.assertEqual(b[("high", "Regard")]["n_same_sku"], 3)

    def test_raw_files_unchanged_and_outputs_up_to_date(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*.csv")}
        with tempfile.TemporaryDirectory() as d:
            tables = run(RAW, REFERENCE)
            write(tables, d)
            self.assertEqual(stale(tables, d), [])
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*.csv")}
        self.assertEqual(before, after)
        self.assertEqual(stale(tables, PROCESSED), [], "run: python -m src.pipeline")


if __name__ == "__main__":
    unittest.main()
