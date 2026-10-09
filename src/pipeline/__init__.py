"""Processing layer: raw shop CSVs -> clean tables for analysis and the dashboard.

    python -m src.pipeline            # regenerate data/processed/
    python -m src.pipeline --check    # exit 1 if data/processed/ is stale

Raw files in data/raw/ are read only. Outputs (all UTF-8 CSV):

    items.csv               every price line, normalized, with selection flags
    builds.csv              one priced build per shop snapshot, with completeness
    ru_us_components.csv    RU vs US per component, with match type
    ru_us_builds.csv        RU vs US per build: total and same-SKU premiums,
                            comparability and its build-specific limitations
    ru_us_limitations.csv   limitations that apply to every RU/US comparison
    price_history.csv       monthly Regard prices from the web archive
    observations.csv        single shelf prices from screenshots
"""

import csv
import io
from decimal import Decimal
from pathlib import Path

from .builds import assemble, select_alternatives
from .compare import GENERAL_LIMITATIONS, compare
from .sources import discover, load_fx, load_history, load_observations, load_reference, load_snapshot
from .specs import part_numbers, product_key, spec_key
from .taxonomy import build_label, build_order

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
REFERENCE = ROOT / "data" / "reference"
PROCESSED = ROOT / "data" / "processed"


def _fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")), "f")
    if value is None:
        return ""
    return value


def _share(value):
    return "" if value is None else format(Decimal(value).quantize(Decimal("0.0001")), "f")


def run(raw_dir=RAW, reference_dir=REFERENCE):
    """Build every output table in memory: {file name: (header, rows)}."""
    reference = load_reference(Path(reference_dir) / "builds.csv")
    fx = load_fx(Path(reference_dir) / "fx_rates.csv")
    items = [it for path in discover(raw_dir) for it in load_snapshot(path)]
    select_alternatives(items, reference)
    builds = assemble(items, reference)
    comp_rows, build_rows = compare(builds, fx)

    items.sort(key=lambda it: (it["snapshot_date"], it["market"], it["retailer"],
                               build_order(it["build"]), it["source_row"]))
    tables = {}
    tables["items.csv"] = (
        ["snapshot_date", "market", "retailer", "build", "component", "variant", "raw_component",
         "sku", "product_key", "spec_key", "part_numbers", "unit_price", "qty", "line_total",
         "currency", "selected", "meets_spec", "selection_note", "source_file", "source_row"],
        [[it["snapshot_date"], it["market"], it["retailer"], it["build"], it["component"], it["variant"],
          it["raw_component"], it["sku"], product_key(it["component"], it["sku"]) or "",
          spec_key(it["component"], it["sku"], it["qty"]) or "",
          ";".join(sorted(part_numbers(it["sku"]))), it["unit_price"], it["qty"], it["line_total"],
          it["currency"], it["selected"], it["meets_spec"], it["selection_note"],
          it["source_file"], it["source_row"]] for it in items],
    )
    tables["builds.csv"] = (
        ["snapshot_date", "market", "retailer", "build", "build_label", "currency", "total",
         "complete", "components_present", "components_required", "missing_components",
         "incomplete_reason", "memory_ssd_share", "gpu_share", "ram_choice"],
        [[b["snapshot_date"], b["market"], b["retailer"], b["build"], build_label(b["build"]), b["currency"],
          b["total"], b["complete"], b["components_present"], b["components_required"],
          b["missing_components"], b["incomplete_reason"], _share(b["memory_ssd_share"]), _share(b["gpu_share"]), b["ram_choice"]]
         for b in builds],
    )
    comp_cols = ["snapshot_date", "build", "component", "match_type", "checked_params", "ru_retailer", "ru_sku", "ru_qty",
                 "ru_rub", "ru_spec", "us_retailer", "us_sku", "us_qty", "us_usd", "us_rub", "us_spec",
                 "ru_premium"]
    tables["ru_us_components.csv"] = (
        comp_cols,
        [[_share(r[c]) if c == "ru_premium" else r[c] for c in comp_cols] for r in comp_rows],
    )
    build_cols = ["snapshot_date", "build", "ru_retailer", "us_retailer", "fx_rub_per_usd", "ru_total_rub",
                  "us_total_usd", "us_total_rub", "ru_premium", "comparability", "comparable_verified",
                  "limitations", "n_same_sku", "n_analogous",
                  "n_different_spec", "n_unverified", "same_sku_ru_rub", "same_sku_us_rub", "same_sku_premium"]
    tables["ru_us_builds.csv"] = (
        build_cols,
        [[_share(r[c]) if c.endswith("premium") else
          (format(r[c], "f") if c == "fx_rub_per_usd" else r[c]) for c in build_cols] for r in build_rows],
    )
    tables["ru_us_limitations.csv"] = (
        ["scope", "limitation"],
        [["all", text] for text in GENERAL_LIMITATIONS],
    )
    history = load_history(Path(raw_dir) / "regard_history.csv")
    history.sort(key=lambda h: (h["component"], h["product_id"], h["month"]))
    tables["price_history.csv"] = (
        ["month", "snapshot", "product_id", "component", "variant", "sku", "price", "in_stock", "currency"],
        [[h["month"], h["snapshot"], h["product_id"], h["component"], h["variant"], h["sku"],
          h["price"], h["in_stock"], h["currency"]] for h in history],
    )
    obs = load_observations(Path(raw_dir) / "manual_observations.csv")
    tables["observations.csv"] = (
        ["date", "market", "retailer", "component", "variant", "sku", "unit_price", "qty_for_build",
         "build_cost", "currency", "note"],
        [[o["date"], o["market"], o["retailer"], o["component"], o["variant"], o["sku"], o["unit_price"],
          o["qty_for_build"], o["build_cost"], o["currency"], o["note"]] for o in obs],
    )
    return tables


def render(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows([[_fmt(v) for v in row] for row in rows])
    return buf.getvalue()


def write(tables, out_dir=PROCESSED):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in tables.items():
        (out_dir / name).write_text(render(header, rows), encoding="utf-8")


def stale(tables, out_dir=PROCESSED):
    """Names of output files that are missing or differ from a fresh run."""
    out_dir = Path(out_dir)
    return [name for name, (header, rows) in tables.items()
            if not (out_dir / name).exists()
            or (out_dir / name).read_text(encoding="utf-8") != render(header, rows)]
