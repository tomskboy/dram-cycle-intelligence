"""Canonical build and component names.

Raw files name the same thing differently: the reference table calls the AM5
budget build "budget", Regard splits memory into "ram_kit" / "ram_single", the
price history uses "ram_ddr4" / "ssd_nvme". Everything downstream works with
the canonical ids below. Unknown names raise instead of passing through, so a
new raw file with a typo fails loudly rather than creating a ninth component.
"""

BUILDS = {
    # id: (Russian label, English label, sort order)
    "budget_am4": ("Бюджетная AM4", "Budget AM4", 1),
    "budget_am5": ("Бюджетная AM5", "Budget AM5", 2),
    "mid": ("Средняя", "Mid-range", 3),
    "high": ("Топовая", "High-end", 4),
}

BUILD_ALIASES = {
    "budget": "budget_am5",
    "budget-am4": "budget_am4",
    "budget-am5": "budget_am5",
}

# Order matters: it is the order of parts in every output table.
COMPONENTS = ("cpu", "gpu", "ram", "ssd", "motherboard", "cooler", "psu", "case")

# raw name -> (canonical component, variant). The variant keeps the distinction
# the raw file made (a RAM kit vs single sticks, SATA vs NVMe) without turning
# it into a separate component.
COMPONENT_ALIASES = {
    "ram_kit": ("ram", "kit"),
    "ram_single": ("ram", "single"),
    "ram_ddr4": ("ram", "ddr4"),
    "ram_ddr5": ("ram", "ddr5"),
    "ssd_sata": ("ssd", "sata"),
    "ssd_nvme": ("ssd", "nvme"),
}


def normalize_build(name):
    key = name.strip().lower()
    key = BUILD_ALIASES.get(key, key)
    if key not in BUILDS:
        raise ValueError(f"unknown build {name!r}")
    return key


def normalize_component(name):
    """Return (component, variant); variant is "" when the raw name has none."""
    key = name.strip().lower()
    if key in COMPONENT_ALIASES:
        return COMPONENT_ALIASES[key]
    if key not in COMPONENTS:
        raise ValueError(f"unknown component {name!r}")
    return key, ""


def build_label(build, lang="ru"):
    ru, en, _ = BUILDS[build]
    return ru if lang == "ru" else en


def build_order(build):
    return BUILDS[build][2]
