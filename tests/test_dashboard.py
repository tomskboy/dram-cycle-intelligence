"""Tests for the dashboard. Need the dashboard dependencies:
    pip install -r requirements-dashboard.txt
    python -m unittest tests.test_dashboard
They are skipped when pandas or streamlit is not installed."""

import csv
import os
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    import pandas as pd
    from streamlit.testing.v1 import AppTest
    HAVE_DEPS = True
except ImportError:  # pragma: no cover
    HAVE_DEPS = False

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "dashboard" / "app.py")


SEPTEMBER = "2026-09-24"  # the snapshot the original assertions were written for


def pin_date(at, date=SEPTEMBER):
    """Set every date filter that exists to one snapshot date."""
    for key in ("cost_date", "struct_date", "ruus_date"):
        box = next((b for b in at.selectbox if b.key == key), None)
        if box is not None:
            box.set_value(date)
    return at.run()


def metrics(at):
    return {m.label: m.value for m in at.metric}


@unittest.skipUnless(HAVE_DEPS, "dashboard dependencies not installed")
class DataLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dashboard import data as d
        cls.d = d
        cls.T = d.load(ROOT / "data" / "processed")

    def test_money_and_pct(self):
        d = self.d
        self.assertEqual(d.money(90260, "RUB"), "90 260 ₽")
        self.assertEqual(d.money(815.36, "USD"), "$815,36")
        self.assertEqual(d.pct(0.3117), "+31,2%")
        self.assertEqual(d.pct(-0.112), "−11,2%")
        self.assertEqual(d.pct(0.264, signed=False), "26,4%")
        self.assertEqual(d.fx_rate(84.3969), "84,3969")
        self.assertEqual(d.ru_date("2026-09-24"), "24.09.2026")

    def test_history_keeps_gaps(self):
        # Ryzen 5 5600 OEM: 4 observations over 13 months
        s = self.d.history_series(self.T, "418665")
        raw = self.T["price_history"]
        self.assertEqual(len(s), len(raw[raw["product_id"] == "418665"]))
        self.assertEqual(s.attrs["span_months"], 13)
        self.assertEqual(s.attrs["gap_months"], 13 - len(s))
        months = list(s["month"])
        for (a, b), (sa, sb) in zip(zip(months, months[1:]), zip(s["segment"], s["segment"][1:])):
            ya, ma = map(int, a.split("-"))
            yb, mb = map(int, b.split("-"))
            adjacent = (yb * 12 + mb) - (ya * 12 + ma) == 1
            self.assertEqual(sa == sb, adjacent, f"{a} -> {b}")

    def test_build_view_and_spending(self):
        view = self.d.build_view(self.T, "2026-09-24", "Regard", "budget_am4")
        self.assertTrue(view.complete)
        self.assertEqual(view.total_label, "Стоимость сборки")
        self.assertEqual(len(view.parts), 8)
        self.assertEqual(list(view.rejected["variant"]), ["kit"])
        s = self.d.spending(view)
        self.assertAlmostEqual(s["share"].sum(), 1.0)
        self.assertAlmostEqual(s[s["component"].isin(["ram", "ssd"])]["share"].sum(), 0.2640, places=4)

    def test_reason_label(self):
        self.assertEqual(
            self.d.reason_label("psu: not collected; ram: 2 line(s) collected, none meets reference spec"),
            "Блок питания: нет в собранных данных; "
            "Оперативная память: найдено вариантов — 2, ни один не подходит под типовую сборку")

    def test_limitation_label(self):
        self.assertEqual(self.d.limitation_label("psu: разные характеристики (500w и 650w)"),
                         "Блок питания: разные характеристики (500w и 650w)")


@unittest.skipUnless(HAVE_DEPS, "dashboard dependencies not installed")
class AppFilters(unittest.TestCase):
    """Run the real app headless and drive its filters."""

    def setUp(self):
        os.environ.pop("DASHBOARD_DATA_DIR", None)
        self.at = pin_date(AppTest.from_file(APP, default_timeout=60).run())
        self.assertEqual(len(self.at.exception), 0, [e.value for e in self.at.exception])

    def test_four_sections(self):
        self.assertEqual([t.label for t in self.at.tabs],
                         ["Стоимость сборок", "Структура расходов", "История цен", "Россия/США"])

    def test_cost_filters(self):
        at = self.at
        self.assertEqual(at.selectbox(key="cost_shop").value, "Regard")
        self.assertEqual(metrics(at)["Стоимость сборки"], "90 260 ₽")
        at.selectbox(key="cost_build").set_value("high").run()
        self.assertEqual(metrics(at)["Стоимость сборки"], "339 300 ₽")
        at.selectbox(key="cost_shop").set_value("Newegg").run()
        # the chosen configuration is kept when the new shop has it too
        self.assertEqual(at.selectbox(key="cost_build").value, "high")
        self.assertEqual(metrics(at)["Стоимость сборки"], "$3\u00a0086,34")
        at.selectbox(key="cost_date").set_value("2026-09-23").run()
        self.assertEqual(at.selectbox(key="cost_shop").options, ["Регард"])
        self.assertTrue(any("Цены на 23.09.2026" in c.value for c in at.caption))

    def test_structure_filters(self):
        at = self.at
        self.assertEqual(metrics(at)["Память и SSD"], "26,4%")
        at.selectbox(key="struct_build").set_value("budget_am5").run()
        self.assertEqual(metrics(at)["Память и SSD"], "40,1%")
        self.assertEqual(metrics(at)["Видеокарта"], "38,6%")

    def test_history_filters(self):
        at = self.at
        at.selectbox(key="hist_kind").set_value("ram").run()
        at.selectbox(key="hist_product").set_value("395207").run()
        m = metrics(at)
        self.assertEqual(m["Первое наблюдение"], "4 620 ₽")
        self.assertTrue(m["Наблюдений"].startswith("12 из "))

    def test_ru_us_filters(self):
        at = self.at
        self.assertTrue(any("84,3969" in i.value and "24.09.2026" in i.value for i in at.info))
        self.assertEqual(at.selectbox(key="ruus_build").value, ("budget_am4", "Regard"))
        self.assertTrue(any("Блок питания: разные характеристики" in w.value for w in at.warning))
        at.selectbox(key="ruus_build").set_value(("mid", "Regard")).run()
        self.assertTrue(any("Сопоставимо по проверенным параметрам" in s.value for s in at.success))
        self.assertEqual(metrics(at)["Разница"], "+27,2%")
        at.selectbox(key="ruus_build").set_value(("high", "Regard")).run()
        self.assertEqual(metrics(at)["Разница только на одинаковых SKU"], "+11,7%")


@unittest.skipUnless(HAVE_DEPS, "dashboard dependencies not installed")
class IncompleteBuild(unittest.TestCase):
    """Processed data built by the real pipeline from data/raw with the PSU of
    Regard's high-end build removed."""

    @classmethod
    def setUpClass(cls):
        from src.pipeline import RAW, REFERENCE, run, write
        cls.tmp = tempfile.TemporaryDirectory()
        raw = Path(cls.tmp.name) / "raw"
        shutil.copytree(RAW, raw)
        path = raw / "regard_2026-09-24.csv"
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        rows = [r for r in rows if not (r[3] == "high" and r[4] == "psu")]
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        cls.processed = Path(cls.tmp.name) / "processed"
        write(run(raw, REFERENCE), cls.processed)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        os.environ.pop("DASHBOARD_DATA_DIR", None)

    def setUp(self):
        os.environ["DASHBOARD_DATA_DIR"] = str(self.processed)
        self.at = pin_date(AppTest.from_file(APP, default_timeout=60).run())
        self.assertEqual(len(self.at.exception), 0)

    def test_partial_sum_is_not_called_build_cost(self):
        at = self.at
        at.selectbox(key="cost_build").set_value("high").run()
        m = metrics(at)
        self.assertNotIn("Стоимость сборки", m)
        self.assertEqual(m["Частичная сумма доступных компонентов"], "334 550 ₽")  # 339 300 - 4 750
        self.assertTrue(any("Неполная сборка" in w.value and "блок питания" in w.value for w in at.warning))
        self.assertTrue(any(c.value == "Причина: Блок питания: нет в собранных данных" for c in at.caption))

    def test_incomplete_build_left_out_of_structure_and_ru_us(self):
        at = self.at
        self.assertTrue(any("Не показаны неполные сборки" in c.value and "Топовая" in c.value for c in at.caption))
        options = at.selectbox(key="ruus_build").options
        self.assertFalse(any("Топовая" in o for o in options))
        self.assertTrue(any("Неполные сборки в сравнение не входят: Регард: Топовая" in c.value for c in at.caption))


@unittest.skipUnless(HAVE_DEPS, "dashboard dependencies not installed")
class NoRuUsPairs(unittest.TestCase):
    """Processed data built by the real pipeline from data/raw with the PSU
    removed from every Newegg build: all US builds are incomplete, so there is
    no complete RU/US pair at all."""

    @classmethod
    def setUpClass(cls):
        from src.pipeline import RAW, REFERENCE, run, write
        cls.tmp = tempfile.TemporaryDirectory()
        raw = Path(cls.tmp.name) / "raw"
        shutil.copytree(RAW, raw)
        for path in raw.glob("newegg_*.csv"):  # every US snapshot loses its PSU
            with open(path, newline="", encoding="utf-8") as f:
                header, *body = list(csv.reader(f))
            col = header.index("component")  # position differs between snapshot layouts
            rows = [header] + [r for r in body if r[col] != "psu"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
        cls.processed = Path(cls.tmp.name) / "processed"
        write(run(raw, REFERENCE), cls.processed)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        os.environ.pop("DASHBOARD_DATA_DIR", None)

    def setUp(self):
        os.environ["DASHBOARD_DATA_DIR"] = str(self.processed)
        self.at = pin_date(AppTest.from_file(APP, default_timeout=60).run())
        self.assertEqual(len(self.at.exception), 0, [e.value for e in self.at.exception])

    def test_fixture_has_no_pairs(self):
        from dashboard import data as d
        t = d.load(self.processed)
        self.assertEqual(len(t["ru_us_builds"]), 0)
        self.assertEqual(len(t["ru_us_components"]), 0)
        self.assertFalse(t["builds"][t["builds"]["market"] == "US"]["complete"].any())

    def test_ru_us_shows_message(self):
        at = self.at
        self.assertTrue(any("Нет сопоставимых сборок для выбранных данных" in i.value for i in at.info))
        self.assertTrue(any("совпадающих пар — 0" in c.value for c in at.caption))
        self.assertIsNone(next((s for s in at.selectbox if s.key == "ruus_date"), None))

    def test_other_sections_keep_working(self):
        at = self.at
        self.assertEqual(metrics(at)["Стоимость сборки"], "90\u00a0260\u00a0₽")
        self.assertEqual(metrics(at)["Память и SSD"], "26,4%")
        at.selectbox(key="cost_shop").set_value("Newegg").run()
        self.assertEqual(len(at.exception), 0)
        self.assertIn("Частичная сумма доступных компонентов", metrics(at))
        at.selectbox(key="hist_kind").set_value("ram").run()
        at.selectbox(key="hist_product").set_value("395207").run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(metrics(at)["Наблюдений"].startswith("12 из "))
        self.assertTrue(any("Нет сопоставимых сборок" in i.value for i in at.info))


@unittest.skipUnless(HAVE_DEPS, "dashboard dependencies not installed")
class LatestSnapshot(unittest.TestCase):
    """The 2026-10-09 snapshot from the fixed collectors: Regard has no ATX X870
    board, so its high-end build is incomplete and left out of RU/US."""

    def setUp(self):
        os.environ.pop("DASHBOARD_DATA_DIR", None)
        self.at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertEqual(len(self.at.exception), 0, [e.value for e in self.at.exception])

    def test_latest_snapshot_is_the_default(self):
        self.assertEqual(self.at.selectbox(key="cost_date").value, "2026-10-09")
        self.assertEqual(self.at.selectbox(key="ruus_date").value, "2026-10-09")

    def test_explicit_gap_shown_as_incomplete_build(self):
        at = self.at
        at.selectbox(key="cost_build").set_value("high").run()
        m = metrics(at)
        self.assertNotIn("Стоимость сборки", m)
        self.assertEqual(m["Частичная сумма доступных компонентов"], "322\u00a0380\u00a0₽")
        self.assertTrue(any("Неполная сборка" in w.value and "материнская плата" in w.value for w in at.warning))
        self.assertTrue(any(c.value == "Причина: Материнская плата: подходящий товар не найден в магазине"
                            for c in at.caption))
        self.assertEqual(len(at.exception), 0)

    def test_ru_us_uses_the_new_rate_and_skips_the_incomplete_build(self):
        at = self.at
        self.assertTrue(any("85,4173" in i.value and "09.10.2026" in i.value for i in at.info))
        self.assertFalse(any("Топовая" in o for o in at.selectbox(key="ruus_build").options))
        self.assertTrue(any("Неполные сборки в сравнение не входят: Регард: Топовая" in c.value for c in at.caption))


if __name__ == "__main__":
    unittest.main()
