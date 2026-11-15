"""Автотест: бренды с самого сайта (пример - exist.ru). Без сети.
Проверяется: раздел марок по устройству сайта (/catalog/cars/Audi «Запчасти для Audi (Ауди)», русское название
в адресе %D0%93%D0%90%D0%97 = ГАЗ) - без /brands/ в адресе; вид «марка, для которой товары» и «производитель»;
модели из подразделов марки (/cars/Suzuki/Grand_Vitara) и из запросов («suzuki grand vitara» - Suzuki, модель
«grand vitara», а не бренды «Suzuki Grand» и «Vitara»); модель после марки только из запросов (chery tiggo);
Royal Thermo по-прежнему один бренд; бренд и название товара из микроразметки (parser.schema_info) - производитель;
одинаковое «название» у многих товаров (шаблон сайта) не считается названием."""
import json
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-brands-site-")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.parser import parse_html  # noqa: E402
from seocrawler.semantics import brands as BR, models, plan  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# 1. микроразметка: название и бренд товара текстом, название магазина в шапке - не товар
h = ('<html><body><div itemscope itemtype="http://schema.org/Organization"><span itemprop="name">Магазин</span></div>'
     '<div itemscope itemtype="http://schema.org/Product"><h2 itemprop="name">Присадка Suprotec <b>Active</b> 120987</h2>'
     '<div itemprop="brand" itemscope itemtype="http://schema.org/Brand"><span itemprop="name">Suprotec</span></div>'
     '</div></body></html>').encode()
p = json.loads(parse_html(h)["schema_info"])["product"]
check(p.get("title") == "Присадка Suprotec Active 120987" and p.get("brand") == "Suprotec", f"microdata: {p}")
h = (b'<html><head><script type="application/ld+json">{"@type":"Product","name":"LAVR LN1484",'
     b'"brand":{"@type":"Brand","name":"LAVR"}}</script></head><body></body></html>')
p = json.loads(parse_html(h)["schema_info"])["product"]
check(p.get("title") == "LAVR LN1484" and p.get("brand") == "LAVR", f"json-ld: {p}")

# 2. маленький сайт автозапчастей
S = "https://parts.ru"
OWN = os.path.join(TMP, "reports", "parts.ru_2026-10-11_10-00-00")
os.makedirs(OWN)
st = Store(os.path.join(OWN, "crawl.db"))
st.set_meta("start", S + "/")
MAKES = [("Audi", "Ауди"), ("BMW", "БМВ"), ("Kia", "Киа"), ("Mitsubishi", "Мицубиси"), ("Suzuki", "Сузуки"),
         ("Toyota", "Тойота"), ("Land_Rover", "Ленд Ровер"), ("Chery", "Чери"), ("Skoda", "Шкода")]
pages = [(S + "/", "Автозапчасти", "", ""), (S + "/catalog/cars/", "Каталог", "", "")]
for slug, ru in MAKES:
    nm = slug.replace("_", " ")
    pages.append((S + f"/catalog/cars/{slug}", "", f"Запчасти для {nm} ({ru})", ""))
pages.append((S + "/catalog/cars/%D0%93%D0%90%D0%97", "", "Запчасти для ГАЗ", ""))
for m in ("Grand_Vitara", "Jimny", "SX4", "Vitara"):
    pages.append((S + f"/catalog/cars/Suzuki/{m}", "", f"Запчасти для Suzuki {m.replace('_', ' ')} II", ""))
info = lambda b, t: json.dumps({"product": {"src": "microdata", "name": True, "title": t, "brand": b}})  # noqa: E731
for i in range(40):     # товары без H1, с одинаковым title-шаблоном: название и бренд - из разметки
    b = ("Suprotec", "LAVR", "Fenox")[i % 3]
    pages.append((S + f"/goods/{i}", "", "Автозапчасти | Интернет-магазин", "Product", info(b, f"{b} {1000 + i}")))
for row in pages:
    u, h1, title, schema = row[:4]
    st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": title, "h1": h1,
                  "word_count": 300, "schema_types": schema, "schema_info": row[4] if len(row) > 4 else "{}"})
st.commit()
st.db.close()

names = models.from_db(os.path.join(OWN, "crawl.db"))
check(len(names) == 40 and "Suprotec 1000" in names and not any("Интернет" in n for n in names),
      f"названия товаров из разметки, без шаблона: {names[:3]}")
pg, _f, md = BR._site_brands(BR._ro(OWN), "parts.ru")
by = {n: (k, forms) for n, _u, k, forms in pg}
check({"Audi", "BMW", "Land Rover", "Suzuki", "ГАЗ"} <= set(by) and all(k == "for" for k, _ in by.values()),
      f"раздел марок: {by}")
check(by.get("Audi", ("", []))[1] == ["ауди"], f"русское написание из title: {by.get('Audi')}")
check({("Suzuki", "Grand Vitara"), ("Suzuki", "Jimny")} <= set(md) and not any(m == "Grand Vitara II" for _b, m in md),
      f"модели Suzuki с сайта: {md}")


def q(text, score=5):
    return [text, "", "Общий", score, 1, 1, 0, "", 0, "", 0, 0, 0, 0]


groups = [
    {"name": "Запчасти", "kind": "page", "page": S + "/catalog/cars/", "todo": "Продвигать эту страницу", "score": 90,
     "rivals": [], "a": {"problems": []},
     "q": [q("запчасти suzuki grand vitara"), q("suzuki grand vitara запчасти уфа"), q("grand vitara запчасти"),
           q("запчасти mitsubishi outlander"), q("mitsubishi outlander фильтр"), q("mitsubishi lancer запчасти"),
           q("chery tiggo запчасти"), q("chery tiggo 7 фильтр"), q("chery tiggo 4"), q("chery arrizo запчасти"),
           q("радиатор royal thermo"), q("royal thermo уфа"), q("royal thermo купить"),
           q("присадка suprotec"), q("suprotec отзывы")]},
]
data = plan.enrich({"site": S + "/", "host": "parts.ru", "groups": groups, "made": "11.10.2026 10:00", "city": "Уфа",
                    "competitors": [], "total": 15, "dropped": {}}, OWN)
r = BR.build(data, OWN)
by = {b["name"]: b for b in r["brands"]}
check({"Suzuki", "Mitsubishi", "Chery", "Audi", "Royal Thermo", "Suprotec", "Lavr"} <= set(by), f"бренды: {sorted(by)}")
bad = {"Grand", "Vitara", "Suzuki Grand", "Outlander", "Mitsubishi Outlander", "Tiggo", "Chery Tiggo", "Royal", "Thermo"}
check(not bad & set(by), f"модели и части названий стали брендами: {sorted(bad & set(by))}")
sz = by.get("Suzuki") or {}
check(sz.get("kind") == "for" and sz.get("page", "").endswith("/catalog/cars/Suzuki") and sz.get("n") == 3
      and dict(sz.get("models") or []).get("grand vitara") == 3, f"Suzuki: {sz}")
check(dict((by.get("Mitsubishi") or {}).get("models") or []).get("outlander") == 2, f"Mitsubishi: {by.get('Mitsubishi')}")
check(dict((by.get("Chery") or {}).get("models") or []).get("tiggo") == 3, f"Chery: {by.get('Chery')}")
sp = by.get("Suprotec") or {}
check(sp.get("kind") == "maker" and sp.get("products") == 14 and sp.get("n") == 2, f"Suprotec: {sp}")
check((by.get("Lavr") or {}).get("kind") == "maker" and (by.get("Lavr") or {}).get("st") == "decide",
      f"LAVR - производитель, не ищут: {by.get('Lavr')}")
check(r["kinds"]["for"] >= 10 and r["kinds"]["maker"] >= 3, f"виды: {r['kinds']}")
v = BR.view(r)
check(v["kinds"] == r["kinds"] and v["kind_names"]["for"] and any(b["models"] for b in v["brands"]), "окно: виды и модели")
b_rows, _c = BR.rows(r)
check(any(x[0] == "Suzuki" and x[9] == BR.KIND["for"] and "grand vitara (3)" in x[10] for x in b_rows), "Excel: вид и модели")

if fails:
    print("БРЕНДЫ С САЙТА: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Бренды с сайта: всё в порядке")
