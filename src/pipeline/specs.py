"""Read product identity and specs out of listing titles.

Two different questions are answered here, and the RU/US comparison depends on
keeping them apart:

* product_key / part numbers - is this the *same product* (same SKU)?
* spec_key - is this an *analogous configuration* (same GPU chip, same RAM
  capacity and speed, same PSU wattage...), even if the brand differs?

Titles are free text from different shops and languages, so every parser
returns None when the title does not say enough; callers treat None as
"cannot verify", never as a match.
"""

import re

# ---------------------------------------------------------------- RAM

_KIT = re.compile(r"(\d+)\s*x\s*(\d+)\s*(?:gb|гб)")
_CAPACITY = re.compile(r"(\d+)\s*(?:gb|гб)\b")
_DDR = re.compile(r"\bddr\s*([45])\b")
_RAM_SPEED = re.compile(r"\bddr[45][\s-]*(\d{4})\b|\b(\d{4})\s*mhz")


def parse_ram(title):
    """Capacity of one listing (a kit counts as one listing), modules in it,
    memory type and speed. modules is None when the title does not say."""
    t = title.lower()
    kit = _KIT.search(t)
    if kit:
        modules, per_module = int(kit.group(1)), int(kit.group(2))
        capacity = modules * per_module
    else:
        cap = _CAPACITY.search(t)
        capacity = int(cap.group(1)) if cap else None
        modules = None
    ddr = _DDR.search(t)
    speed = _RAM_SPEED.search(t)
    return {
        "capacity_gb": capacity,
        "modules": modules,
        "ddr": f"ddr{ddr.group(1)}" if ddr else None,
        "speed": int(speed.group(1) or speed.group(2)) if speed else None,
    }


_TARGET_RAM = re.compile(r"(\d+)\s*GB\s*DDR(\d)-(\d{4})", re.I)


def parse_ram_target(spec):
    """'16 GB DDR4-3200 (2x8)' from the reference table -> (16, 'ddr4', 3200)."""
    m = _TARGET_RAM.search(spec)
    if not m:
        return None
    return int(m.group(1)), f"ddr{m.group(2)}", int(m.group(3))


# ---------------------------------------------------------------- other specs

_CPU = re.compile(r"ryzen\s+(\d)\s+(\d{4}x3d|\d{4}[a-z]?)\b")
_GPU = re.compile(r"rtx\s*(\d{4})(\s*ti)?\b")
_SSD_TB = re.compile(r"\b(\d+)\s*tb\b")
_SSD_GB = re.compile(r"\b(\d{3,4})\s*(?:gb|гб)\b")
_CHIPSET = re.compile(r"(?<![a-z0-9])([abx]\d{3})(e(?![a-z]))?")
_WATTS = re.compile(r"(\d{3,4})\s*-?\s*w(?:att)?\b")


def cpu_model(title):
    m = _CPU.search(title.lower())
    return f"ryzen {m.group(1)} {m.group(2)}" if m else None


def cpu_packaging(title):
    """'oem' or 'box' when the title says so, else None."""
    t = title.lower()
    if re.search(r"\boem\b|\btray\b", t):
        return "oem"
    if re.search(r"\bbox\b|\bwof\b|with wraith|with .*cooler", t):
        return "box"
    return None


def ssd_capacity_tb(title):
    t = title.lower()
    m = _SSD_TB.search(t)
    if m:
        return int(m.group(1))
    m = _SSD_GB.search(t)
    if m:  # 960/1000/1024 GB all sell as "1 TB"
        return round(int(m.group(1)) / 1000)
    return None


def spec_key(component, title, qty=1):
    """Configuration class used for "analogous" comparisons, or None if the
    title does not state it. Coolers and cases are treated as interchangeable
    within the build's class: titles rarely carry a comparable spec."""
    t = title.lower()
    if component == "cpu":
        return cpu_model(t)
    if component == "gpu":
        m = _GPU.search(t)
        return f"rtx {m.group(1)}{' ti' if m.group(2) else ''}" if m else None
    if component == "ram":
        r = parse_ram(t)
        if None in (r["capacity_gb"], r["ddr"], r["speed"]):
            return None
        return f"{r['capacity_gb'] * qty}gb {r['ddr']}-{r['speed']}"
    if component == "ssd":
        tb = ssd_capacity_tb(t)
        return f"{tb}tb" if tb else None
    if component == "motherboard":
        m = _CHIPSET.search(t)
        return f"{m.group(1)}{m.group(2) or ''}" if m else None
    if component == "psu":
        m = _WATTS.search(t)
        return f"{m.group(1)}w" if m else None
    if component in ("cooler", "case"):
        return component
    raise ValueError(f"unknown component {component!r}")


# ---------------------------------------------------------------- identity

# Product lines whose name alone identifies the product (plus capacity for
# drives). Titles of these lines often carry no part number, e.g. Newegg's
# "SAMSUNG 990 PRO 2TB ...", so a part-number match alone would miss them.
FAMILIES = (
    ("ssd", r"samsung\s+990\s+pro", "samsung 990 pro"),
    ("ssd", r"samsung\s+990\s+evo\s+plus", "samsung 990 evo plus"),
    ("ssd", r"kingston\s+nv3", "kingston nv3"),
    ("ssd", r"crucial\s+bx500", "crucial bx500"),
    ("ssd", r"wd\s+green\s+sn350", "wd green sn350"),
    # versions are different products: "120 SE", "120 SE V3", "120 SE ARGB V2"
    ("cooler", r"peerless\s+assassin\s+120\s+se\b(?:\s+(argb))?(?:\s+(v\d))?", "thermalright peerless assassin 120 se"),
    ("cooler", r"se-902-sd", "id-cooling se-902-sd v3"),
    ("cooler", r"se-224-xts", "id-cooling se-224-xts"),
    ("cooler", r"thermaltake\s+ux400", "thermaltake ux400"),
)

# Manufacturer part numbers: an upper-case token with letters and digits,
# usually hyphenated (GV-N5070EAGLE, KF560C30BBEK2-16, MZ-V9P2T0BW).
_PART = re.compile(r"(?<![A-Za-z0-9])(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9]+(?:-[A-Z0-9]+)+(?![A-Za-z0-9])"
                   r"|(?<![A-Za-z0-9])(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{9,}(?![A-Za-z0-9])")
# Tokens that look like part numbers but describe a standard, not a product.
_NOT_PART = re.compile(r"^(PC[45]-?\d+|DDR\d.*|GDDR\d.*|PCIE.*|USB.*|ATX\d.*|M2|\d+-PIN)$")


def part_numbers(title):
    return {p for p in _PART.findall(title) if not _NOT_PART.match(p) and len(p) >= 6}


def product_key(component, title):
    """Canonical product identity, or None when the title is not specific
    enough. CPUs include packaging (OEM vs boxed are different SKUs) and
    return None when packaging is not stated."""
    t = title.lower()
    if component == "cpu":
        model, pack = cpu_model(t), cpu_packaging(t)
        return f"amd {model} {pack}" if model and pack else None
    for comp, pattern, family in FAMILIES:
        m = re.search(pattern, t) if comp == component else None
        if m:
            variant = " ".join(g for g in m.groups() if g)
            if variant:
                return f"{family} {variant}"
            if component == "ssd":
                tb = ssd_capacity_tb(t)
                return f"{family} {tb}tb" if tb else None
            return family
    return None
