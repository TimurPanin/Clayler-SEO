"""Автотест: бренды, серии и модели из названий товаров (semantics/models.py, план 3.1) и намерения «Сравнение»
и «Навигация» (words.refine_intent, план 3.2). Без сети.
- «Оправа Christian Lacroix CL1160 004»: тип «оправа», бренд из двух слов «christian lacroix», модель, цвет;
- серия: латиницей или с большой буквы, не начало артикула (DB, PLD) и не слово («средней обжарки»);
- фразы для подсказок: «тип + бренд» и «бренд + серия», мало товаров - ничего;
- маски: эти фразы - уровень 3, включены; быстрый сбор (уровни 1-2) их не берёт; сбор - подсказки по ним;
- намерения: сравнение, навигация (официальный сайт, название своего сайта), покупка важнее.
Запуск: py -3 tests/проверить_модели.py"""
import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="clayler-models-")
os.environ.update(CLAYLER_DECISIONS_DIR=os.path.join(TMP, "решения"), CLAYLER_DICTS_FILE=os.path.join(TMP, "словари.json"),
                  CLAYLER_DICT_FILE=os.path.join(TMP, "словарь.json"), CLAYLER_NO_USER_SETTINGS="1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import build, masks as MK, models as M  # noqa: E402
from seocrawler.semantics.words import own_names, refine_intent  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


t, w, m, c = M.split("Оправа Christian Lacroix CL1160 004")
check((t, [x.lower() for x in w], m, c) == ("оправа", ["christian", "lacroix"], "cl1160", "004"), f"разбор: {(t, w, m, c)}")
t, w, m, c = M.split("Солнцезащитные очки David Beckham DB 7127/S EX4")
check(t == "солнцезащитные очки" and m == "7127/s", f"тип из двух слов: {(t, w, m)}")
names = ([f"Оправа Christian Lacroix CL{1100 + i} 00{i % 5}" for i in range(6)]
         + [f"Оправа David Beckham DB {7100 + i} 06J" for i in range(5)]
         + [f"ACUVUE OASYS with HydraLuxe ({i} линз) -1.00/8.5" for i in range(4)]
         + [f"ACUVUE MOIST ({i} линз)" for i in range(3)]
         + [f"Кофе молотый Illy средней обжарки, {i}00 гр." for i in range(4)]
         + [f"Насос Grundfos UPS 25-{40 + i}" for i in range(4)] + [f"Насос Grundfos ALPHA2 {i}" for i in range(2)])
p = M.parse(names)
pairs = {(a, b): n for a, b, n, _ in p["pairs"]}
series = {(a, b): n for a, b, n, _ in p["series"]}
check(pairs.get(("оправа", "christian lacroix")) == 6, f"тип + бренд из двух слов: {pairs}")
check(("оправа", "christian") not in pairs and ("кофе молотый", "illy") in pairs and pairs.get(("оправа", "david beckham")) == 5, f"бренды: {pairs}")
check(series.get(("acuvue", "oasys")) == 4 and series.get(("acuvue", "moist")) == 3, f"серии: {series}")
check(("david beckham", "db") not in series, "начало артикула - не серия")
check(("illy", "средней") not in series, "обычное слово - не серия")
check(series.get(("grundfos", "ups")) == 4, f"серия из трёх букв: {series}")


def make(folder, n):
    os.makedirs(folder)
    st = Store(os.path.join(folder, "crawl.db"))
    st.set_meta("start", "https://optic.ru/")
    st.set_meta("finished_at", "2026-10-10 10:05:00")
    pages = ["https://optic.ru/", "https://optic.ru/opravy/"]
    for u in pages:
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1,
                      "title": "Оправы" if u.endswith("opravy/") else "Оптика", "h1": "Оправы" if u.endswith("opravy/") else "Оптика",
                      "word_count": 300})
    for i in range(n):
        nm = names[i % len(names)] + f" v{i}"
        u = f"https://optic.ru/opravy/p{i}/"
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": nm, "h1": nm,
                      "word_count": 100, "schema_types": "Product"})
        pages.append(u)
    for src in pages:
        st.add_links([(src, "https://optic.ru/opravy/", "https://optic.ru/opravy/", "Оправы", 0, "a", 1)])
    st.commit()
    st.db.close()


small = os.path.join(TMP, "small.ru_2026-10-10_10-00-00")
make(small, 10)
check(M.seeds(small) == [], "мало товаров - фраз нет")
F = os.path.join(TMP, "optic.ru_2026-10-10_10-00-00")
make(F, 40)
sd = {x["t"]: x for x in M.seeds(F)}
check("оправа christian lacroix" in sd and "acuvue oasys" in sd and sd["acuvue oasys"]["src"] == "бренд + серия",
      f"фразы: {sorted(sd)}")
d = MK.propose(F, log=lambda *a: None)
mm = [x for x in d["masks"] if x["k"].startswith("m:")]
check(mm and all(x["lv"] == 3 and x["on"] for x in mm) and "товаров" in mm[0].get("note", ""), f"маски уровня 3: {mm[:2]}")
now = time.time()
cache = {f"{e}|{r}|{ph}": {"s": lst, "t": now} for ph, lst in
         {"оправа christian lacroix": ["оправа christian lacroix", "оправы christian lacroix женские"],
          "acuvue oasys": ["acuvue oasys", "acuvue oasys 1 day"]}.items() for e, r in (("yandex", "213"), ("google", "ru"))}
with open(os.path.join(F, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)
logs = []
sem = build(F, log=logs.append, offline=True, region="Москва")
check("оправы christian lacroix женские" in sem["queries"] and "acuvue oasys 1 day" in sem["queries"],
      f"подсказки по брендам и сериям: {sorted(sem['queries'])[:20]}")
check(any("Бренды и серии из названий товаров" in x for x in logs), "в журнале - бренды и серии")
light_logs = []
sem2 = build(F, log=light_logs.append, offline=True, region="Москва", light=True)
check(not any("Бренды и серии" in x for x in light_logs) and "acuvue oasys 1 day" not in sem2["queries"],
      "быстрый сбор без брендов и серий")

# ---------- намерения
names_ = own_names("gasprofservice.ru")
cases = [("котел или колонка", "Информация", "Сравнение"), ("котел или колонка купить", "Покупка", "Покупка"),
         ("чем отличается бойлер от водонагревателя", "Информация", "Сравнение"),
         ("какой котел лучше для дома", "Информация", "Сравнение"), ("baxi официальный сайт", "Общий", "Навигация"),
         ("газпрофсервис уфа", "Общий", "Навигация"), ("котел телефон адрес", "Общий", "Навигация"),
         ("импульсный режим работы кофемолки что это", "Информация", "Информация"),
         ("ремонт котлов адрес", "Услуга", "Услуга"), ("газовый котел", "Общий", "Общий")]
for q, was, want in cases:
    got = refine_intent(q, was, names_)
    check(got == want, f"намерение «{q}»: {got}, а нужно {want}")

if fails:
    print("✗ бренды, серии и намерения:")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("✓ бренды, серии и модели из названий товаров; намерения «Сравнение» и «Навигация»")
