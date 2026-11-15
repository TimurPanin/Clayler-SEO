"""Автотест масок семантики и стоп-слов клиента (semantics/masks.py). Без сети: сайт - маленькая выдуманная проверка,
подсказки - заранее в кеше. Проверяется: маски по уровням (меню - 1, разделы и подразделы - 2, глубже и карточки - 3),
служебная страница и карточки предлагаются выключенными; правки человека (текст, выкл, своя маска) сохраняются
при новом предложении, новый раздел снимает подтверждение; сбор идёт только по включённым маскам; стоп-слово клиента
отсеивает при сборе и сразу при чтении семантики; Вордстат - сначала уровень 1; «Остановить» прерывает сбор."""
import json
import os
import shutil
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="clayler-masks-")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import direct  # noqa: E402
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import Stopped, build, export as SX, masks as MK  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


B = "https://own.ru"
ALL = [(B + "/kotly/", "Газовые котлы"), (B + "/kak-sdelat-zakaz/", "Как сделать заказ"), (B + "/zapchasti/", "Запчасти")]
SOME = [(B + "/kotly/nastennye/", "Настенные"), (B + "/radiatory/", "Радиаторы отопления"),
        (B + "/zapchasti-baxi/", "Запчасти Baxi"), (B + "/kotly/nastennye/kondensacionnye/", "Конденсационные котлы")]


def make(folder, extra=()):
    os.makedirs(folder)
    st = Store(os.path.join(folder, "crawl.db"))
    st.set_meta("start", B + "/")
    st.set_meta("finished_at", "2026-10-07 10:05:00")
    some = SOME + list(extra)
    prods = [f"{B}/product/kotel-{i}/" for i in range(32)]
    pages = [B + "/"] + [f"{B}/p{i}/" for i in range(6)] + [u for u, _ in ALL + some] + prods
    for u in pages:
        h1 = (f"Котел Baxi Eco {u.rsplit('-', 1)[-1].strip('/')} кВт" if "/product/" in u
              else "Газовые котлы в Уфе" if u == B + "/" else "")
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": h1 or u, "h1": h1,
                      "word_count": 300})
    for src in pages:
        st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in ALL])
    for src in pages[:7]:
        st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in some])
    for src in pages[:7]:
        st.add_links([(src, prods[0], prods[0], "Котел Baxi Eco 0", 0, "a", 1)])
    st.commit()
    st.db.close()


F = os.path.join(TMP, "own.ru_2026-10-07_10-00-00")
make(F)
d = MK.propose(F, log=lambda *a: None)
by = {m["t"]: m for m in d["masks"]}
check(by.get("газовые котлы", {}).get("lv") == 1 and by["газовые котлы"]["on"], f"меню - уровень 1: {by.get('газовые котлы')}")
check(by.get("как сделать заказ", {}).get("on") is False, "служебная страница предлагается выключенной")
check(by.get("настенные газовые котлы", {}).get("lv") == 2, f"подраздел по адресу - уровень 2: {sorted(by)}")
check(by.get("запчасти baxi", {}).get("lv") == 2, "«запчасти baxi» внутри «запчасти» по словам - уровень 2")
check(any(m["lv"] == 3 and m["src"] == "подраздел" and not m["on"] for m in d["masks"]), "подраздел глубже - уровень 3, выключен")
cards = [m for m in d["masks"] if m["src"] == "карточка"]
check(cards and not any(m["on"] for m in cards) and all(m["lv"] == 3 for m in cards), f"карточки - уровень 3 по выбору: {len(cards)}")
check(not d["confirmed"], "новые маски не подтверждены")

# правки человека: выключить радиаторы, поправить «запчасти», своя маска, стоп-слово, подтвердить
edit = []
for m in d["masks"]:
    x = {"k": m["k"], "t": m["t"], "lv": m["lv"], "on": m["on"]}
    if m["t"] == "радиаторы отопления":
        x["on"] = False
    if m["name"] == "Запчасти":   # текст маски с 15.10.2026 - «запчасти газовые котлы» (слово темы сайта)
        x["t"] = "запчасти для котлов"
    edit.append(x)
edit.append({"k": "", "t": "Ремонт котлов", "lv": 2, "on": True})
d = MK.update("own.ru", masks=edit, stop=["оптом", "своими руками", " Оптом "], confirmed=True)
by = {m["t"]: m for m in d["masks"]}
check(d["confirmed"] and d["stop"] == ["оптом", "своими руками"], f"подтверждено, стоп-слова без повторов: {d['stop']}")
check("запчасти для котлов" in by and by["запчасти для котлов"].get("edited"), "текст маски поправлен")
check(by.get("ремонт котлов", {}).get("src") == "своя", "своя маска добавлена")

# новое предложение по той же проверке: правки на месте, подтверждение остаётся
d = MK.propose(F, log=lambda *a: None)
by = {m["t"]: m for m in d["masks"]}
check(d["confirmed"] and "запчасти для котлов" in by and by["радиаторы отопления"]["on"] is False and "ремонт котлов" in by,
      "повторное предложение не теряет правки")

# сбор: подсказки в кеше, только по включённым маскам
SUG = {"газовые котлы": ["газовые котлы", "газовые котлы цены", "газовые котлы оптом", "газовые котлы двухконтурные"],
       "настенные газовые котлы": ["настенные газовые котлы", "настенные газовые котлы купить"],
       "радиаторы отопления": ["радиаторы отопления", "радиаторы отопления цены", "радиаторы отопления купить"],
       "запчасти для котлов": ["запчасти для котлов", "запчасти для котлов baxi", "запчасти для котлов цены"],
       "запчасти baxi": ["запчасти baxi", "запчасти baxi котел"],
       "ремонт котлов": ["ремонт котлов", "ремонт котлов цены", "ремонт котлов на дому", "ремонт котлов своими руками"]}
now = time.time()
cache = {f"{e}|{r}|{ph}": {"s": lst, "t": now} for ph, lst in SUG.items() for e, r in (("yandex", "172"), ("google", "ru"))}
with open(os.path.join(F, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)
logs = []
sem = build(F, log=logs.append, offline=True, region="Уфа")
qs = set(sem["queries"])
check(not any("радиатор" in q for q in qs), f"выключенная маска не собирается: {sorted(q for q in qs if 'радиатор' in q)}")
check("запчасти для котлов baxi" in qs, "поправленный текст маски - фраза для подсказок")
check("ремонт котлов на дому" in qs, "своя маска собирается")
check("как сделать заказ" not in qs, "служебная страница не собирается")
dr = {q: why for q, why, _ in sem["dropped"]}
check(dr.get("газовые котлы оптом", "").startswith("стоп-слово клиента"), f"стоп-слово клиента при сборе: {dr.get('газовые котлы оптом')}")
lv = {g["name"]: g.get("level") for g in sem["groups"]}
check(lv.get("Газовые котлы") == 1 and lv.get("Настенные") == 2, f"уровни групп: {lv}")
rem = next((g for g in sem["groups"] if g["name"].lower().startswith("ремонт котлов")), None)
check(rem and not rem["main"] and rem.get("level") == 2, f"своя маска - своя группа, не главная: {rem and (rem['name'], rem['main'])}")
check(any("Маски подтверждены" in x for x in logs), "в журнале - сколько масок включено")

# стоп-слово, добавленное после сбора: сразу в «Отсеяно» и не уходит в Вордстат
SX.write_json(os.path.join(F, SX.JSON_NAME), sem)
MK.update("own.ru", stop=["оптом", "своими руками", "цены"])
data = SX.load(F)
rows = {r[0] for g in data["groups"] for r in g["q"]}
check(not any("цены" in q for q in rows) and "газовые котлы цены" in data["dropped"].get("стоп-слово клиента", []),
      "новое стоп-слово действует без нового сбора")
todo = direct.todo(data)
check(todo and not any("цены" in p for p in todo), "фразы со стоп-словом не уходят в Вордстат")
first = {g["q"][0][0] for g in data["groups"] if g.get("lv") == 1 and g["q"]}
check(todo and direct._clean(todo[0]) in {direct._clean(direct.phrase(q)) for q in first},
      f"Вордстат - сначала главная и меню: {todo[:3]}")
hit = MK.matcher(["аренда", "б/у", "своими руками"])
check(hit("аренду котла") == "аренда" and hit("котел б/у") == "б/у" and not hit("арендатор котла")
      and hit("котел своими руками") == "своими руками", "стоп-слово: формы слова, «б/у», фраза")

# «Остановить»: сбор прерывается, прежняя семантика не тронута
try:
    build(F, log=lambda *a: None, offline=True, stop=lambda: True)
    check(False, "сбор не остановился")
except Stopped:
    pass

# новая проверка с новым разделом: маски предлагаются заново, подтверждение снимается, новый - с отметкой
F2 = os.path.join(TMP, "own.ru_2026-10-08_10-00-00")
make(F2, extra=[(B + "/bojlery/", "Бойлеры косвенного нагрева")])
check(MK.view("own.ru", F2)["stale"], "проверка новее масок - маски устарели")
d = MK.propose(F2, log=lambda *a: None)
by = {m["t"]: m for m in d["masks"]}
check(by.get("бойлеры косвенного нагрева", {}).get("new") and not d["confirmed"], "новый раздел - «новая», подтвердить заново")
check(by.get("радиаторы отопления", {}).get("on") is False, "старые правки на месте")
# маски той же проверки, но по старым правилам (hightime.agency: «Собрать заново» брало маски 23.10 с
# кнопками и словарём терминов) - устарели, окно предлагает обновить
check(not MK.view("own.ru", F2)["stale"], "свежие маски той же проверки - не устарели")
old = MK.load("own.ru")
old.pop("rules", None)
MK.save("own.ru", old)
v = MK.view("own.ru", F2)
check(v["stale"] and v["stale_rules"], f"маски по старым правилам не устарели: {v['stale']}, {v.get('stale_rules')}")
MK.propose(F2, log=lambda *a: None)
check(not MK.view("own.ru", F2)["stale"], "после «Обновить маски» - не устарели")
# маска, которую человек правил, а новые правила её не предлагают (кейсы, «Тарифы»), не теряется (проверка кода 28.10)
old = MK.load("own.ru")
old["masks"].append({"k": "u:https://own.ru/cases/", "t": "кейсы по отоплению", "name": "Кейсы", "lv": 2,
                      "src": "раздел", "url": "https://own.ru/cases/", "on": True, "edited": True})
MK.save("own.ru", old)
d = MK.propose(F2, log=lambda *a: None)
check(any(m["t"] == "кейсы по отоплению" and m["on"] for m in d["masks"]), "правленная маска пропала после «Обновить маски»")

shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("МАСКИ СЕМАНТИКИ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Маски семантики и стоп-слова клиента: всё в порядке")
