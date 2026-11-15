"""Автотест: снимок в отчёте открывается крупно по нажатию и закрывается нажатием или Esc (05.10.2026,
seocrawler/lightbox.py). Подключён в отчёт.html, отчёт для клиента и аудит.html (в PDF - без скрипта)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import lightbox  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seocrawler")
for f, need in (("report.py", ("{lightbox.CSS}", "{lightbox.JS}")),
                ("audit.py", ("{lightbox.CSS}", '"" if for_pdf else "<script>" + lightbox.JS'))):
    with open(os.path.join(here, f), encoding="utf-8") as fh:
        src = fh.read()
    check(all(n in src for n in need), f"{f}: увеличение снимков не подключено")
check("http" not in lightbox.JS + lightbox.CSS, "увеличение снимков тянет что-то из сети, а отчёт должен работать офлайн")

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None
if sync_playwright:
    pix = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='600'>"
           "<rect width='300' height='600' fill='red'/></svg>")
    doc = (f"<!doctype html><meta charset='utf-8'><style>{lightbox.CSS}</style><body style='height:3000px'>"
           f"<figure><img id='a' src=\"{pix}\" width='100'><figcaption>Снимок<br>https://site.ru/</figcaption></figure>"
           f"<img id='free' src=\"{pix}\" width='50'><script>{lightbox.JS}</script></body>")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(doc)
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1000, "height": 700})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("file:///" + p.replace("\\", "/"))
            hidden = lambda: pg.evaluate("document.getElementById('lbx').hidden")  # noqa: E731
            check(hidden(), "крупный снимок открыт сразу")
            pg.click("#a")
            check(not hidden(), "нажатие на снимок не открывает его крупно")
            h = pg.evaluate("document.querySelector('#lbx img').getBoundingClientRect().height")
            check(h > 400, f"снимок открылся не крупно: высота {h}")
            check("site.ru" in pg.inner_text("#lbx p"), "нет подписи под крупным снимком")
            pg.keyboard.press("Escape")
            check(hidden(), "Esc не закрывает снимок")
            pg.click("#a")
            pg.mouse.click(30, 30)
            check(hidden(), "нажатие не закрывает снимок")
            pg.click("#free")
            check(hidden(), "картинка вне снимков (не в <figure>) тоже открывается")
            check(not errs, f"ошибки в странице: {errs}")
            b.close()

if fails:
    print("ОШИБКИ в увеличении снимков:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ снимки крупно: открываются нажатием, закрываются нажатием и Esc, в отчёте, для клиента и в аудите")
