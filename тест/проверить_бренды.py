"""Автотест «Бренды» (semantics/brands.py). Без сети: маленький выдуманный сайт и конкурент.
Проверяется: бренды со страниц брендов (/brendy/baxi/), фильтров каталога (/kotly/brand-navien/, у конкурента
/filter/brand-is-haier/apply/) и запросов; написания - по звучанию (бакси), «х» вместо «x» (бахи), одна другая буква
(бакис), пара из словаря «Бренды» (Samsung = самсунк); два слова рядом - один бренд (Royal Thermo); серия при бренде
(Seoul у Master Gas) - не бренд; товары по брендам; бренд × категория: фильтр есть / создать / есть у конкурента;
«Только бренд»; листы Excel; раздел в отчёте для клиента; запоминание результата обхода в «.бренды сайта.json»."""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-brands-")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import brands as BR, dicts as DI, plan, labels as L  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


REP = os.path.join(TMP, "отчёты")


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
    (S + "/", "Котлы в Уфе", ""), (S + "/katalog/kotly/", "Котлы", ""), (S + "/brendy/baxi/", "Котлы Baxi", ""),
    (S + "/katalog/kotly/brand-navien/", "Котлы Navien", ""),
    (S + "/katalog/kotly/kotel-baxi-eco-24/", "Котел Baxi Eco 24", "Product, Offer"),
    (S + "/katalog/kotly/kotel-baxi-eco-4s/", "Котел Baxi Eco 4s", "Product, Offer"),
    (S + "/katalog/kotly/kotel-navien-deluxe/", "Котел Navien Deluxe", "Product, Offer"),
    (S + "/radiatory/", "Радиаторы", ""), (S + "/boilery/", "Бойлеры", "")],
    [(S + "/", S + "/brendy/baxi/", "Baxi"),
     (S + "/katalog/kotly/", S + "/katalog/kotly/brand-baxi/", "Baxi"),
     (S + "/katalog/kotly/", S + "/katalog/kotly/brand-navien/", "Navien"),
     (S + "/katalog/kotly/", S + "/katalog/kotly/kotel-baxi-eco-24/", "Котел Baxi Eco 24")])
R = "https://rival.ru"
site(os.path.join(REP, "rival.ru_2026-10-06_10-00-00"), R + "/", [
    (R + "/brands/haier/", "Haier", ""), (R + "/boilery/", "Бойлеры", ""), (R + "/brands/master-gas/", "Master Gas", "")],
    [(R + "/", R + "/brands/haier/", "HAIER"), (R + "/boilery/", R + "/boilery/filter/brand-is-haier/apply/", "Haier"),
     (R + "/", R + "/brands/master-gas/", "Master Gas")])
DI.save("brands", ["Samsung = самсунк", "# LG = элджи"])


def q(text, score=5):
    return [text, "", "Общий", score, 1, 1, 0, "", 0, "", 0, 0, 0, 0]


groups = [
    {"name": "Котлы", "kind": "page", "page": S + "/katalog/kotly/", "todo": "Продвигать эту страницу", "score": 90,
     "rivals": [], "a": {"problems": []},
     "q": [q("котлы"), q("котлы baxi"), q("котлы бакси"), q("котлы бахи"), q("котлы baxi настенные"), q("котлы бакис"),
           q("котлы навьен"), q("котлы master gas seoul"), q("master gas seoul 13"), q("котел seoul master gas")]},
    {"name": "Бойлеры", "kind": "create", "page": "", "near": "", "todo": "Создать раздел", "score": 40, "rivals": [R + "/boilery/"],
     "q": [q("бойлеры"), q("бойлеры baxi"), q("бойлеры бакси"), q("бойлер baxi 80"), q("бойлер бакси купить"),
           q("бойлеры baxi цена"), q("бойлер хайер"), q("бойлер самсунк")]},
    {"name": "Радиаторы", "kind": "page", "page": S + "/radiatory/", "todo": "Продвигать эту страницу", "score": 30,
     "rivals": [], "a": {"problems": []},
     "q": [q("радиаторы"), q("радиаторы royal thermo"), q("радиаторы роял термо"), q("royal thermo уфа")]},
    {"name": "Baxi", "kind": "page", "page": S + "/brendy/baxi/", "todo": "Продвигать эту страницу", "score": 20,
     "rivals": [], "a": {"problems": []}, "q": [q("baxi уфа"), q("бакси официальный сайт"), q("котлы baxi купить")]},
]
data = plan.enrich({"site": S + "/", "host": "a.ru", "groups": groups, "made": "06.10.2026 10:00", "city": "Уфа",
                    "competitors": ["rival.ru"], "total": 25, "dropped": {}}, OWN)
r = BR.build(data, OWN)
by = {b["name"]: b for b in r["brands"]}
check(set(by) >= {"Baxi", "Navien", "Haier", "Samsung", "Royal Thermo", "Master Gas"}, f"бренды: {sorted(by)}")
check("Seoul" not in by and "Royal" not in by and "Thermo" not in by, f"лишние бренды: {sorted(by)}")
b = by.get("Baxi") or {}
forms = {f["w"]: f["how"] for f in b.get("forms") or []}
check({"baxi", "бакси", "бахи", "бакис"} <= set(forms) and forms.get("бахи") == "x" and forms.get("бакис") == "typo",
      f"написания Baxi: {forms}")
check(b.get("page") == S + "/brendy/baxi/" and b.get("st") == "have" and b.get("products") == 2, f"Baxi: {b}")
cats = {c["cat"]: c for c in b.get("cats") or []}
check(cats.get("Котлы", {}).get("st") == "filter" and cats["Котлы"]["url"].endswith("/katalog/kotly/brand-baxi/"),
      f"Baxi × Котлы - фильтр есть: {cats.get('Котлы')}")
check(cats.get("Бойлеры", {}).get("st") == "create" and cats["Бойлеры"]["n"] == 5, f"Baxi × Бойлеры - создать: {cats.get('Бойлеры')}")
check(cats.get("", {}).get("n") == 2, f"Baxi - только бренд: {cats.get('')}")
check(cats.get("Котлы", {}).get("n") == 6, f"«котлы baxi купить» из группы бренда - в категории «Котлы»: {cats.get('Котлы')}")
nv = by.get("Navien") or {}
check(nv.get("products") == 1 and {c["cat"]: c["st"] for c in nv.get("cats") or []}.get("Котлы") == "filter", f"Navien: {nv}")
hr = by.get("Haier") or {}
check(hr.get("rivals") == ["rival.ru"] and hr.get("st") == "create" and hr.get("page") == ""
      and {c["cat"]: c["st"] for c in hr.get("cats") or []}.get("Бойлеры") == "rival", f"Haier: {hr}")
sm = by.get("Samsung") or {}
check(sm.get("user") and [f["w"] for f in sm.get("forms") or []] == ["самсунк"], f"Samsung из словаря: {sm}")
check(r["count"] == {k: sum(1 for x in r["brands"] if x["st"] == k) for k in ("have", "create", "decide")}, "счёт брендов")
check(os.path.exists(os.path.join(OWN, BR.CACHE_FILE)), "обход сайта не запомнился в «.бренды сайта.json»")
BR._CACHE.clear()
r2 = BR.build(data, OWN)
check([x["name"] for x in r2["brands"]] == [x["name"] for x in r["brands"]], "из запомненного - другой результат")
v = BR.view(r)
check(v["labels"]["brand"]["have"] == L.TREE["have"] and v["labels"]["cell"]["filter"] == L.TREE["filter"], "подписи как в дереве")

# Excel и отчёт для клиента
from seocrawler.semantics import xlsx_dec, export as SX, client  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
SX.write_json(os.path.join(OWN, SX.JSON_NAME), {**{k: data[k] for k in ("site", "host", "city", "competitors", "made")},
                                                "seconds": 1, "wm": False, "gsc": False, "deep": False, "queries": {},
                                                "groups": [], "dropped": [], "cannibal": [], "geo": None, "real": {},
                                                "light": [], "new_site": None})
wb = load_workbook(xlsx_dec.write(OWN, data), read_only=True)
check("Бренды" in wb.sheetnames and "Бренды по категориям" in wb.sheetnames, f"листы Excel: {wb.sheetnames}")
rows = list(wb["Бренды по категориям"].iter_rows(values_only=True))
check(any(r_[0] == "Baxi" and r_[1] == "Бойлеры" and r_[4] == L.TREE["create"] for r_ in rows), "Excel: Baxi × Бойлеры - создать")
wb.close()
html = client._brands_html(client._brands(data, OWN))
check("Бренды" in html and "Бойлеры Baxi" in html and L.count("have", 1, "brand").split(":")[0] in html and "—" not in html,
      "раздел «Бренды» в отчёте для клиента")

if fails:
    print("БРЕНДЫ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Бренды: всё в порядке")
