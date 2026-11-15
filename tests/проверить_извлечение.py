"""Автотест «Свои данные со страниц» (seocrawler/extract.py): CSS-селекторы, XPath, регулярные выражения, проверка правил.
Запуск: py -3 tests/проверить_извлечение.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import extract as X  # noqa: E402
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

HTML = """<!doctype html><html><head><title>Котёл Baxi</title>
<script>var x = "<div class='price'>999</div>";</script>
<script src="https://mc.yandex.ru/metrika/tag.js"></script></head>
<body><div id="main" class="card product">
<h1 itemprop="name">Котёл  Baxi&nbsp;Eco</h1>
<span class="price new" data-sum="45990">45 990 ₽</span><span class="price old">52 000 ₽</span>
<ul class="props"><li>Мощность: 24 кВт<li>Вес: 30 кг<li class="sku">Артикул: BX-24</ul>
<p>Доставка <a href="/dostavka/" rel="nofollow">по городу</a></p><p>Телефон +7 (343) 123-45-67</p>
<img src="/img/1.jpg" alt="Котёл"><img src="/img/2.jpg">
</div><div class="footer"><span class="price">0</span></div></body></html>"""

R = X.tree(HTML)
fails = []


def eq(what, got, want):
    if got != want:
        fails.append(f"{what}: получилось {got!r}, ждали {want!r}")


def css(sel, what="text"):
    return X.apply_rule({"type": "css", "expr": sel, "what": what}, HTML, R)


def xp(expr, what="text"):
    return X.apply_rule({"type": "xpath", "expr": expr, "what": what}, HTML, R)


eq("класс", css(".price.new"), ["45 990 ₽"])
eq("потомок", css("#main .price"), ["45 990 ₽", "52 000 ₽"])
eq("все .price (скрипт не считается)", css(".price", "count"), ["3"])
eq("ребёнок", css("div.footer > span"), ["0"])
eq("атрибут", css("span[data-sum]", "attr:data-sum"), ["45990"])
eq("атрибут ^=", css("img[src^='/img/']", "attr:src"), ["/img/1.jpg", "/img/2.jpg"])
eq("картинка без alt", css("img:not([alt])", "attr:src"), ["/img/2.jpg"])
eq("незакрытые li", css("ul.props li"), ["Мощность: 24 кВт", "Вес: 30 кг", "Артикул: BX-24"])
eq("nth-child", css("ul.props li:nth-child(2)"), ["Вес: 30 кг"])
eq("last-child", css("ul.props li:last-child"), ["Артикул: BX-24"])
eq("сосед +", css("span.new + span"), ["52 000 ₽"])
eq("запятая", css("h1, li.sku"), ["Котёл Baxi Eco", "Артикул: BX-24"])
eq("код внутри", css("p:first-of-type", "html") if False else css("#main > p:nth-of-type(1)", "html"),
   ['Доставка <a href="/dostavka/" rel="nofollow">по городу</a>'])
eq("ничего", css(".nothing"), [])
eq("ничего, сколько", css(".nothing", "count"), ["0"])

eq("xpath //h1", xp("//h1"), ["Котёл Baxi Eco"])
eq("xpath атрибут", xp("//span[@class='price new']/@data-sum"), ["45990"])
eq("xpath contains", xp("//span[contains(@class,'old')]"), ["52 000 ₽"])
eq("xpath text()", xp("//li[contains(text(),'Артикул')]/text()"), ["Артикул: BX-24"])
eq("xpath позиция", xp("//ul/li[2]"), ["Вес: 30 кг"])
eq("xpath last()", xp("//ul/li[last()]"), ["Артикул: BX-24"])
eq("xpath путь от корня", xp("/html/body/div[@id='main']/h1"), ["Котёл Baxi Eco"])
eq("xpath and", xp("//img[@src and @alt]/@src"), ["/img/1.jpg"])
eq("xpath сколько", xp("//img", "count"), ["2"])

rx = lambda e, w="text": X.apply_rule({"type": "regex", "expr": e, "what": w}, HTML, R)  # noqa: E731
eq("regex группа", rx(r"Артикул:\s*([\w\-]+)"), ["BX-24"])
eq("regex телефон", rx(r"\+7 \(\d{3}\) [\d\-]+"), ["+7 (343) 123-45-67"])
eq("regex в коде (скрипт)", rx(r"mc\.yandex\.ru/metrika", "count"), ["1"])
eq("regex нет в коде", rx(r"googletagmanager", "count"), ["0"])

for bad in ({"name": "", "expr": "x"}, {"name": "a", "expr": ""}, {"name": "a", "type": "css", "expr": "div["},
            {"name": "a", "type": "xpath", "expr": "//div[@a=]"}, {"name": "a", "type": "regex", "expr": "("},
            {"name": "a", "expr": "div", "what": "attr:"}, {"name": "a", "type": "xpath", "expr": "//@a/b"}):
    ok, err = X.check_rule(bad)
    if ok or not err:
        fails.append(f"плохое правило прошло: {bad}")
ok, _ = X.check_rule({"name": " Цена ", "type": "css", "expr": ".price", "what": "text", "site": "https://www.Site.ru/x"})
eq("правило", ok, {"name": "Цена", "type": "css", "expr": ".price", "what": "text", "site": "site.ru"})
rules = [ok, {"name": "Чужое", "type": "css", "expr": "h1", "what": "text", "site": "other.ru"},
         {"name": "Общее", "type": "regex", "expr": "x", "what": "count", "site": ""}]
eq("правила сайта", [r["name"] for r in X.for_site("https://site.ru/", rules)], ["Цена", "Общее"])

res = X.apply([ok, {"name": "Сломанное", "type": "regex", "expr": "(", "what": "text"}], HTML)
eq("apply", res, {"Цена": ["45 990 ₽", "52 000 ₽", "0"], "Сломанное": []})

pages = [{"url": "https://site.ru/b", "extract": '{"Цена": ["1"], "Общее": ["0"]}'},
         {"url": "https://site.ru/a", "extract": '{"Цена": [], "Общее": ["3"]}'}, {"url": "https://site.ru/c"}]
r2 = [ok, rules[2]]
eq("таблица", X.table(r2, pages), (["Адрес", "Цена", "Общее"], [["https://site.ru/a", "", "3"], ["https://site.ru/b", "1", "0"]]))
eq("итог", X.summary(r2, pages), ([{"name": "Цена", "found": 1, "missing": 1}, {"name": "Общее", "found": 1, "missing": 1}], 2))
html = X.report_html(r2, pages)
if "Свои данные со страниц" not in html or "—" in html:
    fails.append("раздел отчёта")



def crawl_check():
    """Обход тестового сайта с правилами: колонка pages.extract, «свои данные.csv», раздел в отчёте (не клиенту)."""
    import json
    import sqlite3
    import subprocess
    import tempfile
    import time
    import urllib.request
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    port = 8812
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="clayler-extract-")
    rules_file = os.path.join(tmp, "правила.json")
    with open(rules_file, "w", encoding="utf-8") as f:
        json.dump({"rules": [{"name": "Заголовок", "type": "css", "expr": "h1", "what": "text"},
                             {"name": "Ссылок в коде", "type": "regex", "expr": "<a\\s", "what": "count"},
                             {"name": "Чужой сайт", "type": "css", "expr": "h1", "what": "text", "site": "other.ru"}]},
                  f, ensure_ascii=False)
    srv = subprocess.Popen([sys.executable, os.path.join(here, "testsite.py"), str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.1)
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
                   CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
                   CLAYLER_NO_PROBLEM_SHOTS="1", CLAYLER_REPORTS=tmp, CLAYLER_EXTRACT_FILE=rules_file)
        r = subprocess.run([sys.executable, os.path.join(root, "crawl.py"), base + "/catalog/", "--only-section",
                            "--no-open", "--delay", "0"], env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
        folders = [os.path.join(tmp, d) for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
        if r.returncode != 0 or not folders:
            fails.append("обход с правилами не прошёл: " + (r.stdout + r.stderr)[-600:])
            return
        folder = folders[0]
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
        rules = json.loads(db.execute("SELECT value FROM meta WHERE key='extract_rules'").fetchone()[0])
        eq("правила проверки", [x["name"] for x in rules], ["Заголовок", "Ссылок в коде"])
        rows = dict(db.execute("SELECT url, extract FROM pages WHERE extract IS NOT NULL"))
        db.close()
        if not rows:
            fails.append("ни у одной страницы нет своих данных")
        for u, v in rows.items():
            d = json.loads(v)
            if set(d) != {"Заголовок", "Ссылок в коде"} or not d["Ссылок в коде"][0].isdigit():
                fails.append(f"свои данные {u}: {d}")
                break
        csv_path = os.path.join(folder, "свои данные.csv")
        if not os.path.exists(csv_path):
            fails.append("нет файла «свои данные.csv»")
        rep = open(os.path.join(folder, "отчёт.html"), encoding="utf-8").read()
        if "Свои данные со страниц" not in rep:
            fails.append("нет раздела в отчёте")
        cl = os.path.join(folder, "отчёт_для_клиента.html")
        if os.path.exists(cl) and "Свои данные со страниц" in open(cl, encoding="utf-8").read():
            fails.append("раздел попал в отчёт для клиента")
    finally:
        srv.terminate()


if "--быстро" not in sys.argv:
    crawl_check()
if fails:
    print("✗ извлечение:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ свои данные со страниц (CSS, XPath, регулярные выражения, обход с правилами)")
