"""Дашборд «Цикл памяти 2026». Запуск: streamlit run dashboard/app.py"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import data as d  # noqa: E402

MEM, GPU, OTHER, INK, MUTE = "#D1495B", "#E08E2B", "#8C95A3", "#14171F", "#6B7280"
# legend as text: a chart legend gets cut off on a narrow phone screen
LEGEND = ":red[■] Память и SSD\u2003:orange[■] Видеокарта\u2003:gray[■] Остальное"
GROUP_COLORS = alt.Scale(domain=["Память и SSD", "Видеокарта", "Остальное"], range=[MEM, GPU, OTHER])

st.set_page_config(page_title="Цикл памяти 2026", page_icon="📈", layout="centered")


@st.cache_data
def tables(directory):
    return d.load(directory)


missing = d.missing_tables()
if missing:
    st.error(f"Нет обработанных данных в {d.data_dir()}: {', '.join(missing)}. "
             "Их создаёт `python -m src.pipeline` из CSV в data/raw/.", icon="🚫")
    st.stop()

T = tables(str(d.data_dir()))

st.title("Цикл памяти 2026")
st.caption("Как рост цен на память изменил стоимость игрового ПК. Данные: собственный сбор цен "
           "в Регарде, DNS и Newegg и история цен Регарда из веб-архива.")

tab_cost, tab_structure, tab_history, tab_ruus = st.tabs(
    ["Стоимость сборок", "Структура расходов", "История цен", "Россия/США"])


def snapshot_filters(prefix):
    """Date, shop and configuration pickers shared by the first two sections."""
    b = T["builds"]
    dates = d.dates(b)
    date = st.selectbox("Дата снимка", dates, index=len(dates) - 1, format_func=d.ru_date, key=f"{prefix}_date")
    shops = d.retailers(b, date)
    retailer = st.selectbox("Магазин", shops, index=shops.index("Regard") if "Regard" in shops else 0,
                            format_func=lambda r: d.RETAILER_LABELS.get(r, r), key=f"{prefix}_shop")
    builds = d.configurations(b, date, retailer)
    build = st.selectbox("Конфигурация", builds, format_func=lambda x: d.build_label(T, x), key=f"{prefix}_build")
    return date, retailer, build


def incomplete_notice(view):
    missing = ", ".join(d.COMPONENT_LABELS[c].lower() for c in view.missing)
    st.warning(f"**Неполная сборка** — нет: {missing}. Ниже частичная сумма доступных компонентов; "
               "это не стоимость готового ПК.", icon="⚠️")
    if view.row["incomplete_reason"]:
        st.caption(f"Причина: {d.reason_label(view.row['incomplete_reason'])}")


# ---------------------------------------------------------------- 1. cost
with tab_cost:
    st.subheader("Стоимость сборок")
    date, retailer, build = snapshot_filters("cost")
    view = d.build_view(T, date, retailer, build)
    cur = view.row["currency"]
    shop = d.RETAILER_LABELS.get(retailer, retailer)

    if not view.complete:
        incomplete_notice(view)
    st.metric(view.total_label, d.money(view.row["total"], cur),
              help="Сумма выбранных позиций: цена × количество.")
    st.caption(f"Цены на {d.ru_date(date)} · {shop} · {d.CURRENCY_LABELS[cur]} · компонентов: "
               f"{view.row['components_present']} из {view.row['components_required']}")

    # price columns first, so they stay visible on a phone without scrolling sideways
    parts = pd.DataFrame({
        "Компонент": view.parts["component"].map(d.COMPONENT_LABELS),
        "Сумма": view.parts["line_total"].map(lambda v: d.money(v, cur)),
        "Кол-во": view.parts["qty"],
        "Товар": view.parts["sku"],
        "Цена за шт.": view.parts["unit_price"].map(lambda v: d.money(v, cur)),
    })
    st.dataframe(parts, hide_index=True, column_config={"Товар": st.column_config.TextColumn(width="medium")})

    if len(view.rejected):
        with st.expander(f"Не выбранные варианты и пропуски ({len(view.rejected)})"):
            st.dataframe(pd.DataFrame({
                "Компонент": view.rejected["component"].map(d.COMPONENT_LABELS),
                "Сумма": view.rejected["line_total"].map(lambda v: d.money(v, cur)),
                "Почему не выбран": view.rejected.apply(d.rejection_reason, axis=1),
                "Кол-во": view.rejected["qty"],
                "Товар": view.rejected["sku"].replace("", "—"),
            }), hide_index=True)

# ---------------------------------------------------------------- 2. structure
with tab_structure:
    st.subheader("Структура расходов")
    date, retailer, build = snapshot_filters("struct")
    view = d.build_view(T, date, retailer, build)
    cur = view.row["currency"]
    shop = d.RETAILER_LABELS.get(retailer, retailer)
    if not view.complete:
        incomplete_notice(view)
    share_base = "стоимости сборки" if view.complete else "частичной суммы"

    s = d.spending(view)
    mem = s[s["component"].isin(d.MEMORY)]["share"].sum()
    gpu = s[s["component"] == "gpu"]["share"].sum()
    c1, c2 = st.columns(2)
    c1.metric("Память и SSD", d.pct(mem, signed=False), help=f"Доля от {share_base}")
    c2.metric("Видеокарта", d.pct(gpu, signed=False), help=f"Доля от {share_base}")
    st.caption(f"Доли от {share_base} · цены на {d.ru_date(date)} · {shop} · {d.CURRENCY_LABELS[cur]} · "
               f"{d.build_label(T, build)}")

    s["Сумма"] = s["line_total"].map(lambda v: d.money(v, cur))
    s["Доля"] = s["share"].map(lambda v: d.pct(v, signed=False))
    bars = alt.Chart(s).mark_bar(cornerRadiusEnd=3).encode(
        y=alt.Y("label:N", sort=list(s["label"]), title=None, axis=alt.Axis(labelLimit=160)),
        x=alt.X("line_total:Q", title=f"Сумма, {'₽' if cur == 'RUB' else '$'}", axis=alt.Axis(format="~s")),
        color=alt.Color("group:N", scale=GROUP_COLORS, legend=None),
        tooltip=[alt.Tooltip("label:N", title="Компонент"), alt.Tooltip("Сумма:N"), alt.Tooltip("Доля:N")],
    )
    st.markdown(LEGEND)
    labels = bars.mark_text(align="left", dx=4, color=INK, fontSize=12).encode(text="Доля:N")
    st.altair_chart((bars + labels).properties(height=34 * len(s) + 40), width="stretch")

    st.markdown("**Все конфигурации этого снимка**")
    st.markdown(LEGEND)
    frame, skipped = d.structure_across_builds(T, date, retailer)
    if len(frame):
        order = list(dict.fromkeys(frame["build_label"]))
        stack = alt.Chart(frame).mark_bar().encode(
            y=alt.Y("build_label:N", sort=order, title=None),
            x=alt.X("share:Q", stack="normalize", title="Доля от стоимости сборки", axis=alt.Axis(format="%")),
            color=alt.Color("group:N", scale=GROUP_COLORS, legend=None),
            order=alt.Order("group:N", sort="descending"),
            tooltip=[alt.Tooltip("build_label:N", title="Сборка"), alt.Tooltip("label:N", title="Компонент"),
                     alt.Tooltip("share:Q", title="Доля", format=".1%")],
        ).properties(height=46 * len(order) + 30)
        st.altair_chart(stack, width="stretch")
    if skipped:
        st.caption("Не показаны неполные сборки (доли посчитаны бы от частичной суммы): " + ", ".join(skipped))

# ---------------------------------------------------------------- 3. history
with tab_history:
    st.subheader("История цен")
    st.caption("Цены Регарда в рублях (₽) по снимкам веб-архива; дата каждого снимка — в таблице ниже. Архив сохраняет страницы не каждый месяц; "
               "пропущенные месяцы не заполняются.")
    products = d.history_products(T)
    kinds = list(dict.fromkeys(products["component"]))
    kind = st.selectbox("Тип комплектующих", kinds, format_func=lambda c: d.COMPONENT_LABELS[c], key="hist_kind")
    options = products[products["component"] == kind]
    pid = st.selectbox("Товар", list(options["product_id"]), key="hist_product",
                       format_func=lambda p: f"{options.set_index('product_id').loc[p, 'sku']} "
                                             f"({options.set_index('product_id').loc[p, 'n']} набл.)")
    series = d.history_series(T, pid)

    c1, c2, c3 = st.columns(3)
    c1.metric("Первое наблюдение", d.money(series["price"].iloc[0], "RUB"))
    c1.caption(f"снимок {series['snapshot_date'].iloc[0]:%d.%m.%Y}")
    c2.metric("Последнее", d.money(series["price"].iloc[-1], "RUB"))
    c2.caption(f"снимок {series['snapshot_date'].iloc[-1]:%d.%m.%Y}")
    c3.metric("Наблюдений", f"{len(series)} из {series.attrs['span_months']} мес.")
    c3.caption(f"без снимка: {series.attrs['gap_months']} мес.")

    plot = series.assign(
        Наличие=series["in_stock"].map({True: "в наличии", False: "нет в наличии"}),
        Цена=series["price"].map(lambda v: d.money(v, "RUB")),
        Снимок=series["snapshot_date"].dt.strftime("%d.%m.%Y"),
    )
    line = alt.Chart(plot).mark_line(color=MEM, strokeWidth=2).encode(
        x=alt.X("month_start:T", title=None, axis=alt.Axis(format="%m.%Y")),
        y=alt.Y("price:Q", title="Цена, ₽", scale=alt.Scale(zero=False), axis=alt.Axis(format="~s")),
        detail="segment:N",
    )
    points = alt.Chart(plot).mark_point(size=70, filled=True).encode(
        x="month_start:T", y="price:Q",
        color=alt.Color("Наличие:N", scale=alt.Scale(domain=["в наличии", "нет в наличии"], range=[MEM, OTHER]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("Снимок:N", title="Дата снимка"), "Цена:N", "Наличие:N"],
    )
    st.altair_chart((line + points).properties(height=300), width="stretch")
    st.caption("Линия соединяет только соседние месяцы; разрыв означает, что снимков за эти месяцы нет.")
    with st.expander("Все наблюдения"):
        st.dataframe(pd.DataFrame({
            "Месяц": series["month_start"].map(d.ru_month),
            "Дата снимка": plot["Снимок"],
            "Цена": plot["Цена"],
            "Наличие": plot["Наличие"],
        }), hide_index=True)

# ---------------------------------------------------------------- 4. RU / US
def ru_us_section():
    st.subheader("Россия/США")
    dates = d.ru_us_dates(T)
    if not dates:
        st.info(f"**{d.NO_RU_US}**", icon="ℹ️")
        st.caption(d.no_ru_us_reason(T))
        return
    date = st.selectbox("Дата снимка", dates, index=len(dates) - 1, format_func=d.ru_date, key="ruus_date")
    opts = d.ru_us_options(T, date)
    default = next((n for n, o in enumerate(opts) if o[1] == "Regard"), 0)
    build, ru_shop = st.selectbox(
        "Конфигурация и магазин в России", opts, index=default, key="ruus_build",
        format_func=lambda o: f"{d.build_label(T, o[0])} — {d.RETAILER_LABELS.get(o[1], o[1])}")
    row, comps = d.ru_us_view(T, date, build, ru_shop)
    us_shop = d.RETAILER_LABELS.get(row["us_retailer"], row["us_retailer"])

    st.info(f"Цены на **{d.ru_date(date)}** · курс ЦБ на эту дату **{d.fx_rate(row['fx_rub_per_usd'])} ₽ за $1**",
            icon="💱")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Россия, {d.RETAILER_LABELS.get(ru_shop, ru_shop)}", d.money(row["ru_total_rub"], "RUB"))
    c2.metric(us_shop, d.money(row["us_total_rub"], "RUB"))
    c2.caption(d.money(row["us_total_usd"], "USD") + " по курсу")
    c3.metric("Разница", d.pct(row["ru_premium"]), help="Россия к США в рублях, на всю сборку")

    if row["comparable_verified"]:
        st.success(f"**{row['comparability'].capitalize()}**: все проверенные параметры совпадают. "
                   "Это не полная равнозначность — см. ограничения ниже.", icon="✅")
    else:
        st.warning(f"**{row['comparability'].capitalize()}**. Расхождения:\n\n"
                   + "\n".join(f"- {d.limitation_label(x)}" for x in row["limitations"].split("; ")), icon="⚠️")

    counts = " · ".join(f"{d.MATCH_LABELS[m]}: {row['n_' + m]}" for m in d.MATCH_LABELS)
    st.caption(f"Типы совпадения по 8 компонентам — {counts}")
    if row["n_same_sku"]:
        st.metric("Разница только на одинаковых SKU", d.pct(row["same_sku_premium"]),
                  help=f"{row['n_same_sku']} комп.: {d.money(row['same_sku_ru_rub'], 'RUB')} в России "
                       f"против {d.money(row['same_sku_us_rub'], 'RUB')} в США")

    st.dataframe(pd.DataFrame({
        "Компонент": comps["component"].map(d.COMPONENT_LABELS),
        "Разница": comps["ru_premium"].map(d.pct),
        "Совпадение": comps["match_type"].map(d.MATCH_LABELS),
        "Россия": comps["ru_rub"].map(lambda v: d.money(v, "RUB")),
        "США": comps["us_usd"].map(lambda v: d.money(v, "USD")) + " ≈ " + comps["us_rub"].map(lambda v: d.money(v, "RUB")),
        "Проверено": comps["checked_params"],
        "Товар в России": comps["ru_sku"],
        "Товар в США": comps["us_sku"],
    }), hide_index=True)

    with st.expander("Что значат типы совпадения"):
        st.markdown("\n".join(f"- **{d.MATCH_LABELS[m]}** — {d.MATCH_HELP[m]}" for m in d.MATCH_LABELS))
    with st.expander("Ограничения сравнения", expanded=True):
        st.markdown("\n".join(f"- {x.replace('колонка checked_params', 'колонка «Проверено»')}"
                               for x in T["ru_us_limitations"]["limitation"]))
    excluded = d.excluded_from_ru_us(T, date)
    st.caption("Неполные сборки в сравнение не входят" + (": " + ", ".join(excluded) if excluded else
                                                           "; на эту дату таких нет."))


with tab_ruus:
    ru_us_section()
