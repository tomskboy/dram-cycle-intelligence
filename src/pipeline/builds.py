"""Turn line items into one priced build per shop snapshot.

Two rules matter for the totals:

* Alternatives. A collector may record more than one way to buy a component
  (Regard's AM4 build has a 2x8 GB kit and two single 8 GB sticks). Exactly one
  is selected: the cheapest line whose total capacity meets the reference spec,
  ties going to the line with fewer units (the kit).
* Completeness. A build is complete only when every component of its reference
  spec is present. Incomplete builds still get a partial total, but are flagged
  and listed with what is missing, and comparisons skip them.
"""

from collections import defaultdict
from decimal import Decimal

from .specs import parse_ram, parse_ram_target
from .taxonomy import COMPONENTS, build_order

GROUP = ("snapshot_date", "market", "retailer", "build")


def _ram_meets(item, target):
    if target is None:
        return None
    cap_target, ddr_target, _ = target
    r = parse_ram(item["sku"])
    if r["capacity_gb"] is None:
        return None
    if r["capacity_gb"] * item["qty"] != cap_target:
        return False
    return r["ddr"] in (None, ddr_target)


def select_alternatives(items, reference):
    """Mark every item selected=True/False and give a selection_note."""
    groups = defaultdict(list)
    for it in items:
        groups[tuple(it[k] for k in GROUP) + (it["component"],)].append(it)

    for key, group in groups.items():
        build, component = key[3], key[4]
        target = parse_ram_target(reference.get(build, {}).get("ram", "")) if component == "ram" else None
        for it in group:
            it["meets_spec"] = _ram_meets(it, target) if component == "ram" else None
        if len(group) == 1:
            group[0]["selected"] = True
            group[0]["selection_note"] = ""
            continue
        eligible = [it for it in group if it["meets_spec"] is not False] or group
        chosen = min(eligible, key=lambda it: (it["line_total"], it["qty"], it["source_row"]))
        for it in group:
            it["selected"] = it is chosen
            others = ", ".join(f"{o['variant'] or o['raw_component']} {o['line_total']}" for o in group if o is not it)
            if it is chosen:
                it["selection_note"] = f"cheapest of {len(group)} alternatives meeting spec (others: {others})"
            elif it["meets_spec"] is False:
                it["selection_note"] = "alternative not selected: does not meet reference capacity"
            else:
                it["selection_note"] = f"alternative not selected: {chosen['variant'] or chosen['raw_component']} is cheaper"
    return items


def assemble(items, reference):
    """One row per (snapshot_date, market, retailer, build) from selected items."""
    groups = defaultdict(dict)
    for it in items:
        if it["selected"]:
            groups[tuple(it[k] for k in GROUP)][it["component"]] = it

    builds = []
    for key, parts in groups.items():
        row = dict(zip(GROUP, key))
        required = [c for c in COMPONENTS if c in reference.get(row["build"], dict.fromkeys(COMPONENTS))]
        missing = [c for c in required if c not in parts]
        total = sum((p["line_total"] for p in parts.values()), Decimal(0))
        currencies = {p["currency"] for p in parts.values()}
        if len(currencies) != 1:
            raise ValueError(f"mixed currencies in build {key}: {currencies}")
        memory = sum((parts[c]["line_total"] for c in ("ram", "ssd") if c in parts), Decimal(0))
        gpu = parts["gpu"]["line_total"] if "gpu" in parts else Decimal(0)
        ram = parts.get("ram")
        row.update({
            "currency": currencies.pop(),
            "components_present": len(parts),
            "components_required": len(required),
            "complete": not missing,
            "missing_components": ";".join(missing),
            "total": total,
            "memory_ssd_share": (memory / total) if total else None,
            "gpu_share": (gpu / total) if total else None,
            "ram_choice": f"{ram['variant'] or 'listing'} x{ram['qty']}" if ram else "",
            "parts": parts,
        })
        builds.append(row)
    builds.sort(key=lambda b: (b["snapshot_date"], b["market"], b["retailer"], build_order(b["build"])))
    return builds
