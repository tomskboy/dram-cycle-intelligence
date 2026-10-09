"""Screenshots of the four dashboard tabs (phone and desktop width) with
browser-level filter checks. Needs Playwright with Chromium and a running app:

    streamlit run dashboard/app.py --server.headless true --server.port 8501
    python dashboard/screenshots.py docs/dashboard
"""
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = "http://localhost:8501/"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
NB = "\u00a0"  # Streamlit formats prices with non-breaking spaces

def panel(page):
    return page.locator('[data-testid="stTabPanel"]:visible').first

def choose(page, label, option):
    p = panel(page)
    p.get_by_role("combobox", name=label, exact=True).click()
    page.get_by_role("option", name=option, exact=True).click()
    page.wait_for_timeout(1200)

def settle(page):
    page.wait_for_timeout(800)
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=20000)
    page.wait_for_timeout(800)

def full(page, name, width):
    page.evaluate("""() => { window.scrollTo(0, 0);
        document.querySelectorAll('[data-testid="stMain"], [data-testid="stAppViewContainer"]').forEach(e => e.scrollTop = 0); }""")
    page.wait_for_timeout(300)
    h = page.evaluate("""() => {
        const m = document.querySelector('[data-testid="stMainBlockContainer"]');
        return m.getBoundingClientRect().bottom + window.scrollY + 8; }""")
    page.set_viewport_size({"width": width, "height": int(h)})
    page.wait_for_timeout(900)
    page.screenshot(path=str(OUT / name))
    page.set_viewport_size({"width": width, "height": 900})

def run(width, scale, suffix, checks):
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
        page = b.new_page(viewport={"width": width, "height": 900}, device_scale_factor=scale, locale="ru-RU")
        page.goto(URL); page.wait_for_selector('[data-testid="stMetric"]', timeout=60000); settle(page)

        # 1. cost
        if checks:
            expect(panel(page)).to_contain_text(f"90{NB}260{NB}₽")
            choose(page, "Конфигурация", "Топовая"); settle(page)
            expect(panel(page)).to_contain_text(f"339{NB}300{NB}₽")
            choose(page, "Магазин", "Newegg (США)"); settle(page)
            expect(panel(page)).to_contain_text(f"$3{NB}086,34")
            choose(page, "Магазин", "Регард"); choose(page, "Конфигурация", "Бюджетная AM4"); settle(page)
            expect(panel(page)).to_contain_text(f"90{NB}260{NB}₽")
        panel(page).get_by_text("Не выбранные варианты").click(); settle(page)
        full(page, f"1_cost_{suffix}.png", width)

        # 2. structure
        page.get_by_role("tab", name="Структура расходов").click(); settle(page)
        choose(page, "Конфигурация", "Бюджетная AM5"); settle(page)
        if checks:
            expect(panel(page)).to_contain_text("40,1%")
        full(page, f"2_structure_{suffix}.png", width)

        # 3. history
        page.get_by_role("tab", name="История цен").click(); settle(page)
        choose(page, "Тип комплектующих", "Оперативная память"); settle(page)
        choose(page, "Товар", "Kingston Fury Beast 16GB (2x8) DDR4-3200 (12 набл.)"); settle(page)
        if checks:
            expect(panel(page)).to_contain_text("12 из")
            expect(panel(page)).to_contain_text(f"4{NB}620{NB}₽")
        full(page, f"3_history_{suffix}.png", width)

        # 4. RU / US
        page.get_by_role("tab", name="Россия/США").click(); settle(page)
        choose(page, "Конфигурация и магазин в России", "Топовая — Регард"); settle(page)
        if checks:
            expect(panel(page)).to_contain_text("84,3969")
            expect(panel(page)).to_contain_text("+11,7%")
            expect(panel(page)).to_contain_text("Сопоставимо частично")
        full(page, f"4_ru_us_{suffix}.png", width)
        b.close()
    print("ok", suffix)

if __name__ == "__main__":
    run(390, 2, "mobile", checks=True)
    run(1280, 1, "desktop", checks=False)
