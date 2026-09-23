"""Component classes for price collection.

Each class says what to search for and how to tell a matching listing from
noise (laptops, prebuilt PCs, adapters, external drives, etc.). Titles on
marketplaces are messy, so every rule is a set of regexes on the lowercased
title plus a price floor that cuts off accessories.
"""

# PSU brands people actually put in a gaming PC. The very cheapest listings
# (ExeGate, CBR, no-name OEM) are excluded on purpose.
PSU_BRANDS = (r"deepcool|aerocool|zalman|chieftec|cougar|be quiet|thermaltake|1stplayer"
              r"|montech|xpg|cooler master|corsair|seasonic|fsp|powercase|formula|msi|gigabyte|ardor")

NOT_A_PART = r"ноутбук|laptop|системный блок|игровой (пк|компьютер)|\bкомпьютер\b|\bсборка\b"

# build -> component -> rule
#   query:    search text
#   include:  all of these must match the title
#   exclude:  none of these may match the title (laptops and prebuilt PCs always are)
#   exclude_text: none of these may match the title or the spec line under it
#   min_price: listings below this are accessories or scams
#   qty:      units needed for the build
CLASSES = {
    "budget_am4": {
        "cpu": {
            "query": "процессор AMD Ryzen 5 5600",
            "include": [r"ryzen 5 5600(?![xgt\d])"],
            "exclude": [],
            "min_price": 5000,
        },
        "gpu": {
            "query": "видеокарта RTX 5050",
            "include": [r"rtx\s*5050"],
            "exclude": [r"кронштейн|держатель|кабель"],
            "min_price": 25000,
        },
        "ram": {
            "query": "оперативная память DDR4 3200 16 ГБ",
            "include": [r"ddr4", r"3200", r"16\s*(гб|gb)"],
            "exclude": [r"so-?dimm|ddr5"],
            "exclude_text": [r"so-?dimm|ddr5"],
            "min_price": 3000,
        },
        "ssd": {
            "query": "SSD 1 ТБ",
            "include": [r"ssd|nvme|m\.2|sata", r"\b1\s*(тб|tb)\b|10(00|24)\s*(гб|gb)"],
            "exclude": [r"внешн|portable|usb|hdd|жестк|бокс|корпус для|переходник|адаптер|радиатор"],
            "min_price": 4000,
        },
        "motherboard": {
            "query": "материнская плата A520M",
            "include": [r"a520"],
            "exclude": [r"комплект|ryzen"],
            "min_price": 3000,
        },
        "cooler": {
            "query": "кулер ID-COOLING SE-902-SD V3",
            "include": [r"se-?902"],
            "exclude": [],
            "min_price": 500,
        },
        "psu": {
            "query": "блок питания 500W",
            "include": [r"(450|500|550)\s*(w|вт)", PSU_BRANDS],
            "exclude": [r"адаптер|внешн"],
            "min_price": 2000,
        },
        "case": {
            "query": "корпус mATX без блока питания",
            "include": [r"корпус"],
            # cases sold with a PSU: "450W", or a model suffix like -AAA450, -M350, -SX450R
            "exclude": [r"\d{3}\s*(w|вт)|-[a-z]*[3-8]\d0[a-z]?\b|с бп|блок(ом)? питания в комплекте|для (ssd|hdd|диска|ноутбука)"],
            "min_price": 1000,
        },
    },
}

# Avito is the used market: drop wanted-ads and broken parts on top of the rules above.
USED_EXCLUDE = r"куплю|скупка|обмен|запчаст|не рабоч|нерабоч|неисправ|сломан|на восстановлен"
