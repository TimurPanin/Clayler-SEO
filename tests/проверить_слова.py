"""Автотест «Одни слова и одни числа» (semantics/labels.py). Без сети.
1) В коде семантики, окна и бота нет старых вариантов названий («решить, нужно ли», «групп со страницей»,
   «Таких товаров у вас нет», «Продвигать - страница есть»).
2) На одной выдуманной семантике числа запросов, групп и групп по видам одинаковые в окне (export.summary),
   Telegram, отчёте для клиента, Excel и подписях дерева сайта, и написаны одними словами из labels.py.
3) Адреса из файлов (Вебмастер, Search Console, свои группы) сравниваются с адресами обхода по одному правилу:
   http/https, www, слэш в конце, регистр домена."""
import json
import os
import re
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-words-")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seocrawler.semantics import labels as L, export as SX, plan, client, tree as TR  # noqa: E402
from seocrawler import telegram  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# ---- 1. старые варианты
OLD = ["решить, нужно ли", "Решить, нужно ли", "решить, нужны ли", "Решить, нужны ли", "со страницей`",
       "Таких товаров у вас нет", "Продвигать - страница есть", "у конкурента есть, у вас нет:", "'Нет у вас'",
       "страниц создать", "страниц уже есть", "есть у конкурентов, решить"]
files = [os.path.join(ROOT, "seocrawler", "telegram.py")]
for d in ("seocrawler/semantics", "seocrawler/window/page"):
    for n in os.listdir(os.path.join(ROOT, d)):
        if n.endswith((".py", ".js", ".html")) and (d.endswith("semantics") or n.startswith("sem")):
            files.append(os.path.join(ROOT, d, n))
for p in files:
    text = open(p, encoding="utf-8").read()
    for o in OLD:
        if o in text:
            fails.append(f"старое название «{o}» в {os.path.relpath(p, ROOT)}")
js = open(os.path.join(ROOT, "seocrawler/window/page/semantics.js"), encoding="utf-8").read()
m = re.search(r"let KIND = \{page: \['([^']+)'.*?create: \['([^']+)'.*?absent: \['([^']+)'.*?manual: \['([^']+)'", js, re.S)
check(m and list(m.groups()) == [L.KIND[k][0] for k in ("page", "create", "absent", "manual")],
      "запасные названия в semantics.js не совпадают с labels.py")

# ---- 2. одна семантика - одни числа
S = "https://a.ru"
FOLDER = os.path.join(TMP, "a.ru_2026-10-06_10-00-00")
os.makedirs(FOLDER)


def q(text, score=5):
    return [text, "", "Общий", score, 1, 1, 0, "", 0, "", 0, 0, 0, 0]


groups = [
    {"name": "Котлы", "kind": "page", "page": S + "/kotly/", "todo": "Продвигать эту страницу", "score": 50, "near": "",
     "rivals": [], "a": {"problems": []}, "q": [q("котлы"), q("котлы цена")]},
    {"name": "Насосы", "kind": "page", "page": S + "/nasosy/", "todo": "Продвигать эту страницу", "score": 40, "near": "",
     "rivals": [], "a": {"problems": ["Title без «насосы»"], "main": "насосы", "title": "Насосы в Уфе", "h1": "Насосы",
                         "description": ""}, "q": [q("насосы")]},
    {"name": "Бойлеры", "kind": "create", "page": "", "near": "", "todo": "Создать раздел", "score": 30, "rivals": [],
     "q": [q("бойлеры"), q("бойлеры купить"), q("бойлер косвенного нагрева")]},
    {"name": "Шланги", "kind": "absent", "page": "", "near": "", "score": 3, "rivals": ["https://b.ru/shlangi/"],
     "todo": "На сайте такого нет, у конкурента есть - " + L.DECIDE, "q": [q("шланги")]},
    {"name": "Без группы", "kind": "manual", "page": "", "near": "", "score": 1, "rivals": [],
     "todo": "Разобрать вручную", "q": [q("что-то странное")]},
]
TOTAL = sum(len(g["q"]) for g in groups)
raw = {"site": S + "/", "host": "a.ru", "city": "Уфа", "competitors": ["b.ru"], "made": "06.10.2026 10:00",
       "seconds": 1, "wm": False, "gsc": False, "total": TOTAL, "dropped": {"мусор": ["скачать котлы"]},
       "groups": groups, "cannibal": [], "geo": {"checks": [], "faq_pages": []}, "real": {}, "articles": [],
       "light": [], "new_site": None}
with open(os.path.join(FOLDER, SX.JSON_NAME), "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False)

os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
data = telegram._sem_data(FOLDER)
k = SX.summary(data)
check(k == {"page": 2, "create": 1, "absent": 1, "manual": 1}, f"счёт групп по видам: {k}")
tg = telegram.semantics_text(data)
for key in ("page", "create", "absent"):
    check(L.count(key, k[key]) in tg, f"Telegram: нет строки «{L.count(key, k[key])}»")
check(f"{TOTAL} запросов в {len(groups)} группах, отсеяно 1" in tg, "Telegram: другие числа запросов и групп\n" + tg)

s = client.summary(FOLDER)
check(s["queries"] == TOTAL and s["groups"] == len(groups),
      f"отчёт для клиента: {s['queries']} запросов, {s['groups']} групп (в окне {TOTAL} и {len(groups)})")
c = s["cnt"]
check(c.get("ok", 0) + c.get("fix", 0) + c.get("wrong", 0) == k["page"] and c.get("create", 0) == k["create"]
      and c.get("absent", 0) == k["absent"], f"отчёт для клиента считает группы по-другому: {c} / {k}")
html = client.html_block(s)
for st, n in (("ok", 1), ("fix", 1), ("create", 1), ("absent", 1)):
    check(L.tile(st, n) in html, f"отчёт для клиента: нет плитки «{L.tile(st, n)}»")

xlsx = os.path.join(TMP, "семантика.xlsx")
from seocrawler.semantics import xlsx_dec  # noqa: E402
path = xlsx_dec.write(FOLDER, data)
from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(path, read_only=True)
how = {r[0]: r[1] for r in wb["Как читать"].iter_rows(values_only=True) if r and r[0]}
check(how.get("Итого", "").startswith(f"{TOTAL} запросов в {len(groups)} группах"), f"Excel «Итого»: {how.get('Итого')}")
for key in ("page", "create", "absent", "manual"):
    check(L.count(key, k[key]) in (how.get("Группы") or ""), f"Excel «Группы»: нет «{L.count(key, k[key])}»")
wb.close()

t = TR.build(plan.enrich(data, FOLDER) if not data["groups"][0].get("land") else data, FOLDER)
page = TR.html(t)
for v in L.TREE.values():
    check(v.lower() in page, f"дерево сайта: нет подписи «{v.lower()}»")

# ---- 3. адреса из файлов и из обхода
from seocrawler.urls import same_page as same_url  # noqa: E402
for a, b in (("http://a.ru/kotly", "https://a.ru/kotly/"), ("https://www.a.ru/kotly/", "https://a.ru/kotly/"),
             ("HTTPS://A.RU/kotly/", "https://a.ru/kotly/"), ("a.ru/kotly/", "https://a.ru/kotly/"),
             ("https://a.ru/kotly/#top", "https://a.ru/kotly/"), ("https://a.ru/", "https://a.ru")):
    check(same_url(a, b), f"адреса должны совпасть: {a} и {b}")
for a, b in (("https://a.ru/Kotly/", "https://a.ru/kotly/"), ("https://a.ru/kotly/?page=2", "https://a.ru/kotly/"),
             ("https://b.ru/kotly/", "https://a.ru/kotly/")):
    check(not same_url(a, b), f"адреса разные: {a} и {b}")

if fails:
    print("ОШИБКИ:")
    for x in fails:
        print(" -", x)
    sys.exit(1)
print("Одни слова и числа: всё в порядке")
