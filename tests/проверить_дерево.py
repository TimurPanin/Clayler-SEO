"""Автотест «Дерево сайта и карта признаков» (semantics/tree.py). Без сети: маленький выдуманный сайт и конкурент.
Проверяется: вложенность по адресам (подраздел - внутри раздела, промежуточная страница сайта без группы - из
обхода); страница-фильтр из блока фильтров каталога (ссылка «Baxi» на /kotly/brand-baxi/) - синяя; уточнение со
спросом без страницы - «создать»; «решить» - отдельной веткой; красная отметка - большой спрос и место хуже 10-го
(места Яндекса и Google порознь); карта признаков: цвет и стиль по словарю, назначение «для …», бренд по латинице
и по звучанию («бакси» = Baxi), значение только у конкурента, сочетания со спросом; страница и копия «для
клиента» без длинного тире и служебных слов; листы Excel «Дерево сайта» и «Признаки»."""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-tree-")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import plan, tree as TR  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


REP = os.path.join(TMP, "reports")


def site(folder, start, pages, links):
    os.makedirs(folder)
    st = Store(os.path.join(folder, "crawl.db"))
    st.set_meta("start", start)
    for u, h1, schema in pages:
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": h1, "h1": h1,
                      "word_count": 300, "schema_types": schema})
    st.add_links([(s, d, d, a, 0, "a", 1) for s, d, a in links])
    st.commit()
    st.db.close()
    return folder


S = "https://a.ru"
OWN = site(os.path.join(REP, "a.ru_2026-10-06_10-00-00"), S + "/", [
    (S + "/", "Котлы и кухни в Уфе", ""), (S + "/katalog/", "Каталог", ""), (S + "/katalog/kotly/", "Котлы", ""),
    (S + "/katalog/kotly/brand-baxi/", "Котлы Baxi", "BreadcrumbList"),
    (S + "/katalog/kotly/kotel-baxi-eco-24/", "Котел Baxi Eco 24", "Product, Offer"),
    (S + "/katalog/kotly/nastennye/", "Настенные котлы", ""), (S + "/kuhni/", "Кухни", "")],
    [(S + "/katalog/kotly/", S + "/katalog/kotly/brand-baxi/", "Baxi"),
     (S + "/katalog/kotly/", S + "/katalog/kotly/brand-navien/", "Navien"),
     (S + "/katalog/kotly/", S + "/katalog/kotly/kotel-baxi-eco-24/", "Котел"),     # товар, не фильтр
     (S + "/katalog/kotly/", S + "/katalog/kotly/?PAGEN_1=2", "2"),                  # листание
     (S + "/katalog/kotly/", S + "/katalog/kotly/?sort=price", "Дешевле")])
R = "https://rival.ru"
site(os.path.join(REP, "rival.ru_2026-10-06_10-00-00"), R + "/", [(R + "/kuhni/", "Кухни", "")],
     [(R + "/kuhni/", R + "/kuhni/loft/", "Лофт"), (R + "/kuhni/", R + "/kuhni/prjamye/", "Прямые")])


def q(text, extra, score, freq=0, shows=0, py=0, pg=0):
    # запрос, уточнение, намерение, оценка, Я, G, показы, проверить, место, страница, переходы, частотность, Я место, G место
    return [text, extra, "Общий", score, 1, 1, shows, "", min([p for p in (py, pg) if p] or [0]), "", 0, freq, py, pg]


groups = [
    {"name": "Котлы", "kind": "page", "page": S + "/katalog/kotly/", "todo": "Продвигать эту страницу", "score": 120,
     "rivals": [], "a": {"problems": []},
     "q": [q("котлы", "", 30, 900, 500, 24, 18), q("котлы baxi", "baxi", 20, 300, 100, 30, 0),
           q("котлы бакси", "бакси", 15, 200), q("котлы baxi настенные", "baxi настенные", 9, 90),
           q("котлы для частного дома", "для частного дома", 18, 400), q("котлы для частного дома baxi", "для частного дома baxi", 8, 60),
           q("котлы двухконтурные", "двухконтурные", 17, 350), q("котлы двухконтурные baxi", "двухконтурные baxi", 7, 70)],
     "f": [{"word": "baxi", "name": "Котлы Baxi", "queries": 5, "score": 59, "sample": ["котлы baxi", "котлы бакси"]},
           {"word": "двухконтурные", "name": "Котлы двухконтурные", "queries": 6, "score": 24,
            "sample": ["котлы двухконтурные", "котлы двухконтурные baxi"]},
           {"word": "мини", "name": "Котлы мини", "queries": 2, "score": 3, "sample": ["котлы мини"]}]},
    {"name": "Настенные котлы", "kind": "page", "page": S + "/katalog/kotly/nastennye/", "todo": "Продвигать эту страницу",
     "score": 40, "rivals": [], "a": {"problems": ["H1"]}, "q": [q("настенные котлы", "", 20, 100)]},
    {"name": "Твердотопливные котлы", "kind": "create", "page": "", "near": S + "/katalog/kotly/",
     "todo": "Создать подраздел в «Котлы»", "score": 30, "rivals": [], "q": [q("твердотопливные котлы", "", 15, 80)]},
    {"name": "Кухни", "kind": "page", "page": S + "/kuhni/", "todo": "Продвигать эту страницу", "score": 90,
     "rivals": [R + "/kuhni/"], "a": {"problems": []},
     "q": [q("кухни", "", 20, 500), q("белые кухни прованс", "белые прованс", 12, 120), q("кухни белые в стиле прованс", "белые стиле прованс", 10, 90),
           q("кухня прованс белая", "прованс белая", 9, 60), q("угловые кухни белые", "угловые белые", 8, 40),
           q("кухни прованс", "прованс", 11, 150), q("кухни для дачи", "для дачи", 7, 30), q("белые кухни", "белые", 10, 200),
           q("кухни лофт", "лофт", 6, 20)]},
    {"name": "Шланги", "kind": "absent", "page": "", "todo": "На сайте такого нет, у конкурента есть", "score": 3,
     "rivals": [R + "/shlangi/"], "q": [q("шланги", "", 3)]},
]
data = plan.enrich({"site": S + "/", "groups": groups, "made": "06.10.2026 10:00"}, OWN)
t = TR.build(data, OWN)
idx = {n["name"]: (n, d) for n, d in TR._walk(t["root"])}
kids = lambda name: [c["name"] for c in idx[name][0]["children"]]  # noqa: E731
check(t["root"]["kind"] == "home" and t["root"]["h1"] == "Котлы и кухни в Уфе", f"главная: {t['root']['name']}, {t['root']['h1']}")
check("Каталог" in kids("Главная") and "Котлы" in kids("Каталог"), f"промежуточная страница из обхода: {kids('Главная')}")
check(idx.get("Каталог", ({},))[0].get("st") == "have", "промежуточная страница - зелёная")
check({"Настенные котлы", "Твердотопливные котлы"} <= set(kids("Котлы")), f"подразделы внутри раздела: {kids('Котлы')}")
check(idx["Твердотопливные котлы"][0]["st"] == "create" and idx["Настенные котлы"][0]["st"] == "have", "создать / есть")
check(idx["Котлы Baxi"][0]["st"] == "filter" and idx["Котлы Baxi"][0]["url"].endswith("/brand-baxi/"),
      f"фильтр из блока фильтров каталога: {idx['Котлы Baxi'][0]['st']}")
check(idx["Котлы двухконтурные"][0]["st"] == "create", f"уточнение со спросом - создать: {idx['Котлы двухконтурные'][0]['st']}")
check(idx["Котлы мини"][0]["st"] == "low", "мало спроса - без своей страницы")
other = [n for n in idx if n.startswith("Другие фильтры каталога")]
check(other and [r[0] for r in idx[other[0]][0]["q"]] == ["Navien"], f"фильтр каталога без запросов - одной строкой: {other}")
check(not any("Котел" == n or "Дешевле" in n or n == "2" for n in idx), "товар, листание и сортировка - не фильтры")
check("Решить, нужна ли" in kids("Главная") and kids("Решить, нужна ли") == ["Шланги"], "«решить» - отдельной веткой")
k = idx["Котлы"][0]
check(k["py"] and k["pg"] and k["py"] > k["pg"] and k["bad"], f"места порознь и красная отметка: {k['py']}, {k['pg']}, {k['bad']}")
check(not idx["Настенные котлы"][0]["bad"], "без мест нет красной отметки")
check(t["freq"] and k["d"] == sum(r[11] for r in groups[0]["q"]), f"спрос - частотность: {k['d']}")

fm = idx["Кухни"][0].get("fm")
axes = {a["name"]: {v["v"]: v for v in a["values"]} for a in (fm or {}).get("axes", [])}
check("белые" in axes.get("Цвет", {}) and "прованс" in axes.get("Стиль", {}), f"цвет и стиль по словарю: {list(axes)}")
check("угловые" in axes.get("Форма и размер", {}), "форма по словарю")
check("для дачи" in axes.get("Назначение", {}), "назначение «для …»")
check(axes.get("Стиль", {}).get("Лофт", axes.get("Стиль", {}).get("лофт", {})).get("st") == "rival",
      f"значение и у конкурента: {axes.get('Стиль')}")
check(axes.get("Форма и размер", {}).get("прямые", {}).get("st") == "rival", f"значение только у конкурента: {axes}")
combos = {(c["a"], c["b"]): c for c in fm["combos"]} if fm else {}
cw = combos.get(("белые", "прованс")) or combos.get(("прованс", "белые"))
check(cw and cw["n"] == 3 and cw["worth"], f"сочетание «белые + прованс» стоит страницы: {list(combos)}")
fk = idx["Котлы"][0].get("fm")
brands = {v["v"].lower(): v for a in (fk or {}).get("axes", []) if a["name"] == "Бренд" for v in a["values"]}
check("baxi" in brands and brands["baxi"]["n"] == 5 and brands["baxi"]["st"] == "filter",
      f"бренд по латинице и звучанию, страница есть: {brands}")
check("navien" in brands, "бренд из блока фильтров без запросов тоже на карте")

page, t2 = TR.write(OWN, data)
text = open(page, encoding="utf-8").read()
check("Дерево сайта: a.ru" in text and "/katalog/kotly/brand-baxi/" in text, "страница дерева")
check("—" not in text and "программ" not in text.lower(), "без длинного тире и слова «программа»")
check(os.path.exists(os.path.join(OWN, "для клиента", "Дерево сайта - a.ru.html")), "копия в «для клиента»")
try:
    from openpyxl import load_workbook
    from seocrawler.semantics import export as SX
    sem = {"site": S + "/", "city": None, "competitors": [], "made": "", "queries": {}, "groups": [], "dropped": [],
           "wm": False, "gsc": False}
    SX.write_xlsx(os.path.join(OWN, "t.xlsx"), sem, tree=t2)
    wb = load_workbook(os.path.join(OWN, "t.xlsx"))
    check(wb.sheetnames[:2] == ["Дерево сайта", "Признаки"], f"листы Excel: {wb.sheetnames}")
    rows = [r for r in wb["Дерево сайта"].iter_rows(min_row=2, values_only=True) if r[0]]
    lv = [r[0] for r in rows]
    check(lv[0] == "Главная" and "Раздел" in lv and "Подраздел" in lv and "Фильтр" in lv and "Решить, нужна ли" in lv,
          f"уровни: {lv}")
    red = [r[1].strip() for r in rows if (r[4] or "").startswith("Спрос большой")]
    check(red == ["Котлы"], f"красная отметка в Excel: {red}")
    sig = [r for r in wb["Признаки"].iter_rows(min_row=2, values_only=True) if r[2] in ("белые + прованс", "прованс + белые")]
    check(sig and sig[0][5] == "стоит сделать страницу", f"сочетание в Excel: {sig}")
except ImportError:
    pass

if fails:
    print("ДЕРЕВО САЙТА: ОШИБКИ")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("ДЕРЕВО САЙТА: всё в порядке")
