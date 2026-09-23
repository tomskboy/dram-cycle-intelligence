"""Build the unit economics model for the gaming PC subscription business case.

Everything the reader may want to change is an input cell on the "Допущения"
sheet; every other number is a formula, so the workbook recalculates in Excel.

Usage:
    python src/build_model.py      # writes reports/pc_subscription_model.xlsx
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "pc_subscription_model.xlsx"

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT)
GREEN = Font(name=FONT, color="008000")
BOLD = Font(name=FONT, bold=True)
TITLE = Font(name=FONT, bold=True, size=14)
NOTE = Font(name=FONT, italic=True, color="666666", size=9)
KEY = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="DDE4EE")
THIN = Border(bottom=Side(style="thin", color="999999"))

RUB = '#,##0 "₽";(#,##0 "₽");"-"'
PCT = '0.0%;(0.0%);"-"'
NUM = '#,##0;(#,##0);"-"'
MONTHS = '0.0 "мес."'

wb = Workbook()


def header(ws, row, labels, widths=None):
    for i, label in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=label)
        c.font, c.fill, c.border = BOLD, HEAD, THIN
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for i, w in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ---------------------------------------------------------------- Цены
prices = wb.active
prices.title = "Цены"
prices["A1"] = "Бюджетная игровая сборка (AM4), самые дешёвые позиции в DNS"
prices["A1"].font = TITLE
prices["A2"] = "Источник: data/raw/local_2026-09-24.csv, сбор src/collect_local.py, 24.09.2026, Москва"
prices["A2"].font = NOTE
header(prices, 4, ["Компонент", "Позиция", "Цена, ₽"], [18, 62, 14])
BUILD = [
    ("Процессор", "AMD Ryzen 5 5600 OEM", 11999),
    ("Видеокарта", "MSI GeForce RTX 5050 SHADOW 2X OC 8 ГБ", 39499),
    ("Оперативная память", "Digma 16 ГБ DDR4-3200", 12599),
    ("SSD", "DEXP C100 1 ТБ SATA", 10999),
    ("Материнская плата", "MSI PRO A520M-S", 4599),
    ("Кулер", "ID-COOLING SE-902-SD V3", 850),
    ("Блок питания", "Formula ECO-500W", 2299),
    ("Корпус", "ExeGate BAA-109U2", 1450),
]
for i, (comp, sku, price) in enumerate(BUILD, 5):
    prices.cell(row=i, column=1, value=comp).font = BLACK
    prices.cell(row=i, column=2, value=sku).font = BLACK
    c = prices.cell(row=i, column=3, value=price)
    c.font, c.number_format = BLUE, RUB
last = 4 + len(BUILD)
tot = last + 1
prices.cell(row=tot, column=1, value="Итого").font = BOLD
c = prices.cell(row=tot, column=3, value=f"=SUM(C5:C{last})")
c.font, c.number_format = BOLD, RUB
prices.cell(row=tot + 1, column=1, value="Память и SSD, доля").font = BLACK
c = prices.cell(row=tot + 1, column=3, value=f"=(C7+C8)/C{tot}")
c.font, c.number_format = BLACK, PCT
prices.cell(row=tot + 2, column=1, value="Видеокарта, доля").font = BLACK
c = prices.cell(row=tot + 2, column=3, value=f"=C6/C{tot}")
c.font, c.number_format = BLACK, PCT
BUILD_TOTAL = f"Цены!$C${tot}"

# ---------------------------------------------------------------- Допущения
a = wb.create_sheet("Допущения")
a["A1"] = "Допущения модели: игровой ПК по подписке"
a["A1"].font = TITLE
a["A2"] = ("Синие ячейки — входные данные, их можно менять. Жёлтые — ключевые рычаги. "
           "Зелёные — ссылки на другие листы. Всё остальное считается формулами.")
a["A2"].font = NOTE
header(a, 4, ["Параметр", "Значение", "Ед.", "Источник / логика"], [46, 14, 10, 90])

INPUTS = [
    # key, label, value, unit, format, source, is_key
    ("build", "Стоимость сборки в рознице", f"={BUILD_TOTAL}", "₽", RUB,
     "Лист «Цены»: DNS, 24.09.2026", False),
    ("discount", "Скидка при закупке у дистрибьютора", 0.08, "%", PCT,
     "Допущение: оптовая цена на 5–10% ниже розничной", False),
    ("assembly", "Сборка, тест, упаковка", 2500, "₽ / ПК", RUB,
     "Допущение: ~1 час сборщика + упаковка", False),
    ("price", "Цена подписки", 4990, "₽ / мес", RUB,
     "Решение. Ориентиры: клуб 1 570–1 900 ₽/мес на гостя (АРКИ, IV кв. 2025); "
     "Aura-Rent, ПК уровня RTX 4060 — 13 000 ₽/мес (краткосрочная аренда)", True),
    ("idle", "Простой ПК между клиентами", 0.10, "% времени", PCT,
     "Допущение: доставка, чистка, проверка, поиск нового клиента", False),
    ("life_contract", "Средняя длительность подписки", 18, "мес", NUM,
     "Допущение: минимальный срок 12 мес, часть клиентов продлевает", True),
    ("cac", "Стоимость привлечения клиента (CAC)", 4000, "₽ / договор", RUB,
     "Допущение: таргет и блогеры в игровых нишах", True),
    ("delivery", "Доставка и забор ПК", 2000, "₽ / договор", RUB,
     "Допущение: курьер в обе стороны по городу", False),
    ("acquiring", "Эквайринг", 0.025, "% выручки", PCT,
     "Типовая ставка интернет-эквайринга", False),
    ("tax", "Налог (УСН «доходы»)", 0.06, "% выручки", PCT, "НК РФ, ст. 346.20", False),
    ("repairs", "Ремонт и поддержка", 0.06, "% стоимости ПК в год", PCT,
     "Допущение: гарантийные замены, термопаста, поддержка", False),
    ("losses", "Потери (невозврат, порча)", 0.03, "% парка в год", PCT,
     "Допущение: частично покрывается скорингом и договором", False),
    ("horizon", "Срок службы ПК в парке", 36, "мес", NUM,
     "Допущение: после 3 лет ПК продаётся на вторичном рынке", False),
    ("residual", "Остаточная стоимость ПК через 36 мес", 0.35, "% цены закупки", PCT,
     "Допущение. Дорогая память поднимает и цены б/у, это работает в плюс", True),
    ("rate", "Стоимость денег", "=0.14+0.04", "% годовых", PCT,
     "Ключевая ставка ЦБ 14% на 23.09.2026 (cbr.ru) + 4 п.п. банковская маржа", False),
]
ROW = {}
r = 5
for key, label, value, unit, fmt, source, is_key in INPUTS:
    a.cell(row=r, column=1, value=label).font = BLACK
    c = a.cell(row=r, column=2, value=value)
    c.number_format = fmt
    c.font = GREEN if isinstance(value, str) and "!" in value else BLUE
    if is_key:
        c.fill = KEY
    a.cell(row=r, column=3, value=unit).font = BLACK
    a.cell(row=r, column=4, value=source).font = NOTE
    ROW[key] = r
    r += 1


def A(key):
    return f"Допущения!$B${ROW[key]}"


# derived values
r += 1
a.cell(row=r, column=1, value="Расчётные величины").font = BOLD
r += 1
DERIVED = [
    ("capex_pc", "Закупка комплектующих", f"={A('build')}*(1-{A('discount')})", RUB),
    ("capex", "Вложения в один ПК (закупка + сборка)", f"={A('build')}*(1-{A('discount')})+{A('assembly')}", RUB),
    ("rate_m", "Ставка в месяц", f"=(1+{A('rate')})^(1/12)-1", PCT),
    ("rev_m", "Выручка в месяц с учётом простоя", f"={A('price')}*(1-{A('idle')})", RUB),
    ("var_m", "Эквайринг и налог в месяц", f"=B{r + 3}*({A('acquiring')}+{A('tax')})", RUB),
    ("fleet_m", "Ремонт и потери в месяц", f"=B{r}*({A('repairs')}+{A('losses')})/12", RUB),
    ("acq_m", "CAC и доставка в месяц (на договор / его длительность)",
     f"=({A('cac')}+{A('delivery')})/{A('life_contract')}*(1-{A('idle')})", RUB),
    ("cf_m", "Чистый денежный поток в месяц", f"=B{r + 3}-B{r + 4}-B{r + 5}-B{r + 6}", RUB),
    ("margin_m", "Маржа денежного потока", f"=B{r + 7}/B{r + 3}", PCT),
]
for key, label, formula, fmt in DERIVED:
    a.cell(row=r, column=1, value=label).font = BLACK
    c = a.cell(row=r, column=2, value=formula)
    c.font, c.number_format = BLACK, fmt
    ROW[key] = r
    r += 1

# ---------------------------------------------------------------- Денежный поток
cf = wb.create_sheet("Денежный поток")
cf["A1"] = "Денежный поток одного ПК за срок службы"
cf["A1"].font = TITLE
cf["A2"] = "Месяц 0 — закупка и сборка. В последний месяц ПК продаётся по остаточной стоимости."
cf["A2"].font = NOTE
header(cf, 4, ["Месяц", "Выручка", "Эквайринг и налог", "Ремонт и потери", "CAC и доставка",
               "Вложения / продажа", "Денежный поток", "Накопленный", "Дисконтированный"],
       [9, 13, 13, 13, 13, 15, 15, 15, 16])
H = 36  # rows are laid out for the default horizon
for m in range(0, H + 1):
    row = 5 + m
    cf.cell(row=row, column=1, value=m).font = BLACK
    if m == 0:
        vals = [0, 0, 0, 0, f"=-{A('capex')}"]
    else:
        vals = [f"={A('rev_m')}", f"=-{A('var_m')}", f"=-{A('fleet_m')}", f"=-{A('acq_m')}",
                f"=IF(A{row}={A('horizon')},{A('residual')}*{A('capex_pc')},0)"]
    for j, v in enumerate(vals, 2):
        c = cf.cell(row=row, column=j, value=v)
        c.number_format = RUB
        c.font = GREEN if isinstance(v, str) else BLACK
    cf.cell(row=row, column=7, value=f"=SUM(B{row}:F{row})").number_format = RUB
    cf.cell(row=row, column=8, value=f"=G{row}" if m == 0 else f"=H{row - 1}+G{row}").number_format = RUB
    cf.cell(row=row, column=9, value=f"=G{row}/(1+{A('rate_m')})^A{row}").number_format = RUB
    for j in (7, 8, 9):
        cf.cell(row=row, column=j).font = BLACK
end = 5 + H

# ---------------------------------------------------------------- Итоги
s = wb.create_sheet("Итоги", 0)
s["A1"] = "Игровой ПК по подписке: юнит-экономика одного ПК"
s["A1"].font = TITLE
s["A2"] = "Все цифры считаются из листа «Допущения». Меняйте синие ячейки там."
s["A2"].font = NOTE
header(s, 4, ["Показатель", "Значение", "Комментарий"], [44, 16, 70])
SUMMARY = [
    ("Стоимость сборки в рознице (DNS)", f"={A('build')}", RUB, "Бюджетная сборка AM4 + RTX 5050"),
    ("Вложения в один ПК", f"={A('capex')}", RUB, "Закупка со скидкой + сборка"),
    ("Цена подписки", f"={A('price')}", RUB, "В месяц"),
    ("Чистый денежный поток в месяц", f"={A('cf_m')}", RUB, "После налога, эквайринга, ремонта, CAC"),
    ("Маржа денежного потока", f"={A('margin_m')}", PCT, ""),
    ("Срок окупаемости", f"=IFERROR({A('capex')}/{A('cf_m')},\"не окупается\")", MONTHS,
     "Без учёта продажи ПК в конце"),
    ("NPV одного ПК за 36 мес", f"=SUM('Денежный поток'!I5:I{end})", RUB,
     "Дисконт по ставке из допущений; > 0 значит бизнес зарабатывает больше стоимости денег"),
    ("IRR, годовых", f"=IFERROR((1+IRR('Денежный поток'!G5:G{end}))^12-1,\"-\")", PCT,
     "Сравните со ставкой финансирования"),
    ("Суммарная прибыль с ПК за 36 мес", f"='Денежный поток'!H{end}", RUB, "Без дисконтирования"),
]
for i, (label, formula, fmt, note) in enumerate(SUMMARY, 5):
    s.cell(row=i, column=1, value=label).font = BLACK
    c = s.cell(row=i, column=2, value=formula)
    c.font, c.number_format = GREEN, fmt
    s.cell(row=i, column=3, value=note).font = NOTE

# ---------------------------------------------------------------- Чувствительность
sens = wb.create_sheet("Чувствительность")
sens["A1"] = "Срок окупаемости (мес.) при разной цене подписки и стоимости сборки"
sens["A1"].font = TITLE
sens["A2"] = ("По строкам — цена подписки, по столбцам — изменение стоимости сборки относительно "
              "сегодняшней (сценарии цен на память). Остальные допущения — с листа «Допущения».")
sens["A2"].font = NOTE
price_steps = [3990, 4490, 4990, 5490, 5990, 6990]
cost_steps = [-0.2, -0.1, 0, 0.1, 0.2, 0.3]
sens["A4"] = "Цена \\ Сборка"
sens["A4"].font, sens["A4"].fill = BOLD, HEAD
for j, d in enumerate(cost_steps, 2):
    c = sens.cell(row=4, column=j, value=d)
    c.font, c.fill, c.number_format = BLUE, HEAD, '+0%;-0%;0%'
for i, p in enumerate(price_steps, 5):
    c = sens.cell(row=i, column=1, value=p)
    c.font, c.fill, c.number_format = BLUE, HEAD, RUB
    for j in range(2, 2 + len(cost_steps)):
        col = get_column_letter(j)
        capex_pc = f"{A('build')}*(1+{col}$4)*(1-{A('discount')})"
        capex = f"({capex_pc}+{A('assembly')})"
        rev = f"$A{i}*(1-{A('idle')})"
        cfm = (f"({rev}*(1-{A('acquiring')}-{A('tax')})"
               f"-{capex_pc}*({A('repairs')}+{A('losses')})/12-{A('acq_m')})")
        c = sens.cell(row=i, column=j, value=f"=IFERROR(IF({cfm}>0,{capex}/{cfm},\"—\"),\"—\")")
        c.font, c.number_format = BLACK, '0.0'
for j in range(1, 8):
    sens.column_dimensions[get_column_letter(j)].width = 15
sens["A12"] = ("Как читать: при сегодняшних ценах и подписке 4 990 ₽ ПК окупается за значение в центре. "
               "Если память подешевеет на 20%, срок сокращается; если подорожает ещё на 30% — растёт.")
sens["A12"].font = NOTE

# ---------------------------------------------------------------- Альтернативы
alt = wb.create_sheet("Альтернативы")
alt["A1"] = "Что дешевле для геймера: купить, ходить в клуб, облако или подписка"
alt["A1"].font = TITLE
alt["A2"] = "Сравнение расходов геймера за период. Часы игры в месяц — входной параметр."
alt["A2"].font = NOTE
alt["A4"], alt["B4"] = "Часов игры в месяц", 60
alt["A5"], alt["B5"] = "Ставка по рассрочке / кредиту", 0.25
alt["A6"], alt["B6"] = "Срок рассрочки, мес", 12
alt["A7"], alt["B7"] = "Клуб: средние траты гостя в месяц", 1570
alt["A8"], alt["B8"] = "Облако (МТС Fog Play), ₽ за час", 24
for rr, fmt in ((4, NUM), (5, PCT), (6, NUM), (7, RUB), (8, RUB)):
    alt[f"A{rr}"].font = BLACK
    alt[f"B{rr}"].font, alt[f"B{rr}"].number_format = BLUE, fmt
alt["C5"] = "Допущение: рассрочка с переплатой, типично для потребкредита при ставке ЦБ 14%"
alt["C7"] = "АРКИ, IV кв. 2025: медианная выручка на гостя 1 570 ₽ (Москва и СПб ~1 900 ₽)"
alt["C8"] = "fogplay.mts.ru: от 24 ₽/час, поминутная оплата"
for rr in (5, 7, 8):
    alt[f"C{rr}"].font = NOTE
header(alt, 10, ["Вариант", "Платёж в месяц", "За 12 мес", "За 24 мес", "Комментарий"], [40, 16, 14, 14, 70])
rows = [
    ("Купить сразу в DNS", "=0", f"={A('build')}", f"={A('build')}", "Нужна вся сумма сразу"),
    ("Купить в кредит", f"=PMT($B$5/12,$B$6,-{A('build')})", "=B12*$B$6", "=B12*$B$6",
     "Аннуитет; после выплаты ПК ваш"),
    ("Компьютерный клуб", "=$B$7", "=B13*12", "=B13*24", "Нет ПК дома, ограничено часами"),
    ("Облачный гейминг", "=$B$4*$B$8", "=B14*12", "=B14*24", "Нужен быстрый интернет, задержки"),
    ("Подписка на ПК", f"={A('price')}", "=B15*12", "=B15*24", "ПК дома, без первого взноса, можно вернуть"),
]
for i, (label, m, y1, y2, note) in enumerate(rows, 11):
    alt.cell(row=i, column=1, value=label).font = BLACK
    for j, v in enumerate((m, y1, y2), 2):
        c = alt.cell(row=i, column=j, value=v)
        c.font, c.number_format = BLACK, RUB
    alt.cell(row=i, column=5, value=note).font = NOTE

# ---------------------------------------------------------------- Рынок
mk = wb.create_sheet("Рынок")
mk["A1"] = "Оценка рынка: TAM / SAM / SOM"
mk["A1"].font = TITLE
mk["A2"] = "Сверху вниз. Синие ячейки — источники или допущения, их можно уточнять."
mk["A2"].font = NOTE
header(mk, 4, ["Шаг", "Значение", "Источник / логика"], [58, 16, 90])
M = [
    ("Аудитория видеоигр в России, чел.", 108_000_000, NUM,
     "РВИ, ИФСИ, НАФИ (2025): 106–110 млн, берём середину"),
    ("Доля считающих себя геймерами", 0.17, PCT, "Там же: каждый шестой играющий (17%)"),
    ("Геймеры, чел.", "=B5*B6", NUM, ""),
    ("Доля играющих в основном на ПК", 0.5, PCT, "Допущение; опросы дают 50–60%"),
    ("Нет подходящего игрового ПК или пора менять", 0.3, PCT, "Допущение; проверить опросом"),
    ("TAM, чел.", "=B7*B8*B9", NUM, "Все, кому нужен новый игровой ПК"),
    ("TAM, ₽ в год", f"=B10*{A('price')}*12", RUB, "Если бы все платили за подписку"),
    ("Доля в городах-миллионниках", 0.24, PCT, "Росстат: ~35 млн из 146 млн жителей"),
    ("Готовы платить за подписку, а не покупать", 0.10, PCT, "Допущение; проверить опросом и пилотом"),
    ("SAM, чел.", "=B10*B12*B13", NUM, "Реально достижимый сегмент"),
    ("SAM, ₽ в год", f"=B14*{A('price')}*12", RUB, ""),
    ("Доля SAM через 3 года", 0.05, PCT, "Цель, допущение"),
    ("SOM, подписчиков", "=B14*B16", NUM, ""),
    ("SOM, ₽ в год", f"=B17*{A('price')}*12", RUB, ""),
    ("Нужно вложить в парк ПК", f"=B17*{A('capex')}*(1+{A('idle')})", RUB,
     "Парк с запасом на простой"),
    ("Проверка: гостей компьютерных клубов в месяц", 1_000_000, NUM,
     "АРКИ: >1 млн уникальных гостей в месяц, пик ~1,2 млн (ноябрь 2025)"),
]
for i, (label, v, fmt, src) in enumerate(M, 5):
    mk.cell(row=i, column=1, value=label).font = BOLD if label.startswith(("TAM", "SAM", "SOM")) else BLACK
    c = mk.cell(row=i, column=2, value=v)
    c.number_format = fmt
    c.font = BLUE if not isinstance(v, str) else BLACK
    mk.cell(row=i, column=3, value=src).font = NOTE

# ---------------------------------------------------------------- Источники
src = wb.create_sheet("Источники")
src["A1"] = "Источники"
src["A1"].font = TITLE
SOURCES = [
    ("Цены DNS", "Собственный сбор, src/collect_local.py, 24.09.2026", ""),
    ("Цены Регард и история", "Собственный сбор, src/collect_regard.py, src/collect_history.py (Wayback Machine)", ""),
    ("Контрактные цены DRAM", "TrendForce, пресс-релизы 05.01.2026, 31.03.2026, 01.06.2026, 03.07.2026",
     "https://www.trendforce.com/presscenter/news/20260601-13070.html"),
    ("Аудитория видеоигр", "РВИ, ИФСИ, НАФИ, исследование «Гейминг в России»", "https://creative.hse.ru/news/6359"),
    ("Компьютерные клубы", "АРКИ, барометр за IV кв. 2025 (CNews, 30.01.2026)",
     "https://www.cnews.ru/news/line/2026-01-30_rynok_kompyuternyh_klubov"),
    ("Аренда игровых ПК", "Aura-Rent, прайс на аренду игровых ПК, Москва", "https://msk.aura-rent.ru/arenda-igrovyh-kompjuterov/"),
    ("Облачный гейминг", "МТС Fog Play, тарифы", "https://fogplay.mts.ru/"),
    ("Ключевая ставка", "Банк России, 14% на 23.09.2026", "https://www.cbr.ru/hd_base/KeyRate/"),
]
header(src, 3, ["Что", "Источник", "Ссылка"], [26, 80, 70])
for i, row in enumerate(SOURCES, 4):
    for j, v in enumerate(row, 1):
        src.cell(row=i, column=j, value=v).font = BLACK

for ws in wb.worksheets:
    ws.sheet_view.showGridLines = False
    for row in ws.iter_rows():
        for c in row:
            if c.font and c.font.name != FONT:
                c.font = Font(name=FONT, bold=c.font.bold, italic=c.font.italic,
                              color=c.font.color, size=c.font.size)

OUT.parent.mkdir(exist_ok=True)
wb.save(OUT)
print(f"saved {OUT}")
