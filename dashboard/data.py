"""Data layer for the dashboard: reads data/processed/ and prepares views.

No Streamlit here, so every rule the dashboard shows can be tested on its own.
The dashboard only reads the processed tables; it never recomputes totals or
match types (that is src/pipeline's job) and never invents values: months with
no archived snapshot stay empty in the price history.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "processed"

COMPONENT_LABELS = {
    "cpu": "Процессор",
    "gpu": "Видеокарта",
    "ram": "Оперативная память",
    "ssd": "SSD",
    "motherboard": "Материнская плата",
    "cooler": "Кулер",
    "psu": "Блок питания",
    "case": "Корпус",
}
COMPONENT_ORDER = list(COMPONENT_LABELS)
MEMORY = ("ram", "ssd")

RETAILER_LABELS = {"Regard": "Регард", "DNS": "DNS", "Newegg": "Newegg (США)"}
MARKET_LABELS = {"RU": "Россия", "US": "США"}

MATCH_LABELS = {
    "same_sku": "Тот же SKU",
    "analogous": "Аналог",
    "different_spec": "Другие характеристики",
    "unverified": "Не проверено",
}
MATCH_HELP = {
    "same_sku": "тот же товар: линейка и объём или общий парт-номер; у процессора ещё и упаковка OEM/BOX",
    "analogous": "другой товар, но проверенные параметры совпадают",
    "different_spec": "магазины выбрали товары с разными проверенными параметрами",
    "unverified": "в названии товара не хватает данных для проверки",
}

TABLES = ("builds", "items", "price_history", "ru_us_builds", "ru_us_components", "ru_us_limitations")


def data_dir():
    """DASHBOARD_DATA_DIR overrides the default (used by tests)."""
    return Path(os.environ.get("DASHBOARD_DATA_DIR", DEFAULT_DATA_DIR))


def _bool(series):
    return series.map({"true": True, "false": False})


def load(directory=None):
    """All processed tables as DataFrames with parsed types."""
    directory = Path(directory or data_dir())
    t = {name: pd.read_csv(directory / f"{name}.csv", dtype=str, keep_default_na=False) for name in TABLES}

    b = t["builds"]
    b["total"] = b["total"].astype(float)
    b["complete"] = _bool(b["complete"])
    for col in ("memory_ssd_share", "gpu_share"):
        b[col] = pd.to_numeric(b[col], errors="coerce")
    for col in ("components_present", "components_required"):
        b[col] = b[col].astype(int)

    i = t["items"]
    for col in ("unit_price", "line_total"):
        i[col] = i[col].astype(float)
    i["qty"] = i["qty"].astype(int)
    i["selected"] = _bool(i["selected"])

    h = t["price_history"]
    h["price"] = h["price"].astype(float)
    h["in_stock"] = _bool(h["in_stock"])
    h["month_start"] = pd.to_datetime(h["month"] + "-01")
    h["snapshot_date"] = pd.to_datetime(h["snapshot"].str[:8], format="%Y%m%d")

    rb = t["ru_us_builds"]
    for col in ("fx_rub_per_usd", "ru_total_rub", "us_total_usd", "us_total_rub", "same_sku_ru_rub", "same_sku_us_rub"):
        rb[col] = rb[col].astype(float)
    for col in ("ru_premium", "same_sku_premium"):
        rb[col] = pd.to_numeric(rb[col], errors="coerce")
    for col in ("n_same_sku", "n_analogous", "n_different_spec", "n_unverified"):
        rb[col] = rb[col].astype(int)
    rb["comparable_verified"] = _bool(rb["comparable_verified"])

    rc = t["ru_us_components"]
    for col in ("ru_rub", "us_usd", "us_rub"):
        rc[col] = rc[col].astype(float)
    rc["ru_premium"] = pd.to_numeric(rc["ru_premium"], errors="coerce")
    return t


# ---------------------------------------------------------------- formatting

def _group(number, decimals):
    text = f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text


def money(value, currency):
    if value is None or pd.isna(value):
        return "—"
    if currency == "RUB":
        return f"{_group(round(value), 0)} ₽"
    return f"${_group(value, 2)}"


def fx_rate(value):
    return _group(value, 4)


def pct(value, signed=True, decimals=1):
    if value is None or pd.isna(value):
        return "—"
    sign = "+" if signed and value > 0 else ("−" if value < 0 else "")
    return f"{sign}{_group(abs(value) * 100, decimals)}%"


def ru_date(iso):
    """'2026-09-24' -> '24.09.2026'."""
    y, m, d = str(iso)[:10].split("-")
    return f"{d}.{m}.{y}"


def ru_month(ts):
    return ts.strftime("%m.%Y")


# ---------------------------------------------------------------- builds

@dataclass
class BuildView:
    row: pd.Series
    parts: pd.DataFrame        # selected lines, component order
    rejected: pd.DataFrame     # lines collected but not selected

    @property
    def complete(self):
        return bool(self.row["complete"])

    @property
    def missing(self):
        return [c for c in self.row["missing_components"].split(";") if c]

    @property
    def total_label(self):
        """What the sum may be called. A partial sum of an incomplete build
        is not the price of a working PC."""
        if self.complete:
            return "Стоимость сборки"
        return "Частичная сумма доступных компонентов"


def dates(builds):
    return sorted(builds["snapshot_date"].unique())


def retailers(builds, date):
    sub = builds[builds["snapshot_date"] == date]
    return sorted(sub["retailer"].unique(), key=lambda r: (sub[sub["retailer"] == r]["market"].iloc[0], r))


def configurations(builds, date, retailer):
    sub = builds[(builds["snapshot_date"] == date) & (builds["retailer"] == retailer)]
    return list(sub["build"])  # already in build order


def build_view(tables, date, retailer, build):
    b = tables["builds"]
    row = b[(b["snapshot_date"] == date) & (b["retailer"] == retailer) & (b["build"] == build)].iloc[0]
    i = tables["items"]
    lines = i[(i["snapshot_date"] == date) & (i["retailer"] == retailer) & (i["build"] == build)].copy()
    lines["order"] = lines["component"].map(COMPONENT_ORDER.index)
    lines = lines.sort_values(["order", "source_row"])
    return BuildView(row=row, parts=lines[lines["selected"]], rejected=lines[~lines["selected"]])


def rejection_reason(line):
    if line["meets_spec"] == "false":
        return "не подходит под типовую сборку (объём или тип памяти)"
    return "есть подходящий вариант дешевле"


# ---------------------------------------------------------------- spending

def spending(view):
    """Selected lines grouped by component with share of the (partial) sum."""
    parts = view.parts
    total = parts["line_total"].sum()
    out = (parts.groupby("component", sort=False)["line_total"].sum().reset_index())
    out["label"] = out["component"].map(COMPONENT_LABELS)
    out["share"] = out["line_total"] / total if total else float("nan")
    out["group"] = out["component"].map(lambda c: "Память и SSD" if c in MEMORY else
                                        ("Видеокарта" if c == "gpu" else "Остальное"))
    return out.sort_values("line_total", ascending=False).reset_index(drop=True)


def structure_across_builds(tables, date, retailer):
    """Component shares for every complete build of a shop snapshot.
    Incomplete builds are returned separately: their shares would be shares
    of a partial sum."""
    b = tables["builds"]
    sub = b[(b["snapshot_date"] == date) & (b["retailer"] == retailer)]
    rows, skipped = [], []
    for _, r in sub.iterrows():
        if not r["complete"]:
            skipped.append(r["build_label"])
            continue
        s = spending(build_view(tables, date, retailer, r["build"]))
        s["build_label"] = r["build_label"]
        rows.append(s)
    frame = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return frame, skipped


# ---------------------------------------------------------------- history

def history_products(tables):
    h = tables["price_history"]
    first = h.sort_values("month").groupby("product_id").agg(
        sku=("sku", "first"), component=("component", "first"), n=("month", "size"))
    first["order"] = first["component"].map(COMPONENT_ORDER.index)
    return first.sort_values(["order", "sku"]).reset_index()


def history_series(tables, product_id):
    """Observed months only. A new segment starts after every gap, so a line
    is drawn only between neighbouring months and never across missing ones."""
    h = tables["price_history"]
    s = h[h["product_id"] == product_id].sort_values("month_start").reset_index(drop=True)
    months = s["month_start"].dt.year * 12 + s["month_start"].dt.month
    s["segment"] = (months.diff() != 1).cumsum()
    first, last = months.min(), months.max()
    s.attrs["span_months"] = int(last - first + 1) if len(s) else 0
    s.attrs["gap_months"] = s.attrs["span_months"] - len(s)
    return s


# ---------------------------------------------------------------- RU / US

def ru_us_dates(tables):
    return sorted(tables["ru_us_builds"]["snapshot_date"].unique())


def ru_us_options(tables, date):
    rb = tables["ru_us_builds"]
    sub = rb[rb["snapshot_date"] == date]
    return list(zip(sub["build"], sub["ru_retailer"]))


def ru_us_view(tables, date, build, ru_retailer):
    rb = tables["ru_us_builds"]
    row = rb[(rb["snapshot_date"] == date) & (rb["build"] == build) & (rb["ru_retailer"] == ru_retailer)].iloc[0]
    rc = tables["ru_us_components"]
    comps = rc[(rc["snapshot_date"] == date) & (rc["build"] == build) & (rc["ru_retailer"] == ru_retailer)].copy()
    comps["order"] = comps["component"].map(COMPONENT_ORDER.index)
    return row, comps.sort_values("order")


def excluded_from_ru_us(tables, date):
    """Incomplete builds of the date: never compared."""
    b = tables["builds"]
    sub = b[(b["snapshot_date"] == date) & (~b["complete"])]
    return [f"{RETAILER_LABELS.get(r['retailer'], r['retailer'])}: {r['build_label']}" for _, r in sub.iterrows()]


def reason_label(text):
    """Pipeline's incomplete_reason ('psu: not collected; ram: 2 line(s)
    collected, none meets reference spec') in Russian."""
    out = []
    for part in filter(None, text.split("; ")):
        component, _, rest = part.partition(": ")
        name = COMPONENT_LABELS.get(component, component)
        if rest == "not collected":
            out.append(f"{name}: нет в собранных данных")
        elif rest.endswith("none meets reference spec"):
            n = rest.split(" ")[0]
            out.append(f"{name}: найдено вариантов — {n}, ни один не подходит под типовую сборку")
        else:
            out.append(f"{name}: {rest}")
    return "; ".join(out)


def limitation_label(text):
    """'psu: разные характеристики (500w и 650w)' -> 'Блок питания: ...'."""
    component, sep, rest = text.partition(": ")
    return f"{COMPONENT_LABELS[component]}: {rest}" if sep and component in COMPONENT_LABELS else text


def build_label(tables, build):
    b = tables["builds"]
    return b[b["build"] == build]["build_label"].iloc[0]
