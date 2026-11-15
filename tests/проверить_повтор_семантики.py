"""Автотест: семантика одинаковая при каждом сборе, бренды и серии при конкуренте по адресу, город сайта в ТЗ
(находки рефакторинга Семантики).
- Два сбора подряд на одних данных - один и тот же семантика.json и дерево сайта. Раньше порядок слов в описании,
  страница-фильтр и место среди равных менялись от запуска к запуску (перебор множеств Python и ответы подсказок
  вразнобой). Сборы идут в отдельных процессах с разным PYTHONHASHSEED - как два запуска программы.
- Бренды и серии из названий товаров собираются и с конкурентом по адресу, а в быстром сборе (очередь) - нет.
- Город в названиях фильтров и словах ТЗ - город самого сайта, а не зашитые «уфа», «уфе».
Запуск: py -3 tests/проверить_повтор_семантики.py (и из проверить_всё.py)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
B = "https://kotly.ru"


def child(folder):
    """Сбор в отдельном процессе: печатает семантику и дерево одной строкой JSON."""
    from seocrawler.semantics import build, export as SX, decisions, plan, tree
    sem = build(folder, log=lambda *a: None, offline=True, region="Москва")
    sem["made"] = sem["seconds"] = None
    SX.write_json(os.path.join(folder, SX.JSON_NAME), sem)
    data = plan.enrich(decisions.apply(SX.load(folder), folder), folder)
    t = tree.build(data, folder)
    print(json.dumps({"sem": SX.to_data(sem), "tree": t}, ensure_ascii=False, sort_keys=True, default=str))


if len(sys.argv) > 2 and sys.argv[1] == "--child":
    child(sys.argv[2])
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="clayler-semrepeat-")
ENV = dict(os.environ, CLAYLER_DECISIONS_DIR=os.path.join(TMP, "решения"), CLAYLER_DICTS_FILE=os.path.join(TMP, "словари.json"),
           CLAYLER_DICT_FILE=os.path.join(TMP, "словарь.json"), CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
           PYTHONIOENCODING="utf-8")
os.environ.update({k: v for k, v in ENV.items() if k.startswith("CLAYLER_")})
from seocrawler.storage import Store  # noqa: E402
from seocrawler import semantics as SEM  # noqa: E402
from seocrawler.semantics import pages as PG, models as MD  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# ---------- выдуманный магазин котлов в Москве: много равных по оценке запросов и уточнений
F = os.path.join(TMP, "kotly.ru_2026-10-16_10-00-00")
os.makedirs(F)
st = Store(os.path.join(F, "crawl.db"))
st.set_meta("start", B + "/")
st.set_meta("finished_at", "2026-10-16 10:05:00")
MENU = [(B + "/gazovye-kotly/", "Газовые котлы"), (B + "/boylery/", "Бойлеры"), (B + "/zapchasti/", "Запчасти")]
# ещё раздел с тем же H1 и тем же числом ссылок: какой из двух главный - не должно зависеть от запуска
MENU.append((B + "/kotly/", "Котлы"))
SAME_H1 = {B + "/kotly/": "Газовые котлы"}
BRANDS = ["baxi", "navien", "bosch", "vaillant", "protherm", "ariston"]
prods = [(f"{B}/gazovye-kotly/{b}-{i}/", f"Газовый котел {b.title()} {i} кВт") for b in BRANDS for i in (18, 24)]
TEXT = ("Газовые котлы настенные и напольные, двухконтурные и одноконтурные, бойлеры косвенного нагрева, запчасти: "
        "платы, датчики, насосы. Доставка по Москве, установка и монтаж, гарантия. ")
ABC = "бвгдклмнпрст"
FILLER = " ".join(a + v + b + "о" + c for v in "аи" for a in ABC for b in ABC for c in ABC)
OTHER = [(f"{B}/p{i}/", "Газовые котлы в Москве") for i in range(6)]
for u, h1 in [(B + "/", "Газовые котлы в Москве")] + OTHER + [(u, a) for u, a in MENU] + prods:
    h1 = SAME_H1.get(u, h1)
    st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": h1 + " купить в Москве",
                  "h1": h1, "word_count": 300, "blocks": zlib.compress((TEXT + FILLER).encode("utf-8"), 6)})
for src in [B + "/"] + [u for u, _ in OTHER + MENU]:
    st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in MENU])
    st.add_links([(src, u, u, a, 0, "a", 1) for u, a in prods])
st.commit()
st.db.close()
# у каждой марки три запроса, и во всех - город: в названии фильтра его быть не должно («Газовые котлы baxi»)
SUG = {"газовые котлы": [f"газовые котлы {b} москва" for b in BRANDS] + [f"купить газовые котлы {b} в москве" for b in BRANDS]
       + [f"газовые котлы {b} москва цены" for b in BRANDS]
       + ["газовые котлы настенные", "газовые котлы напольные", "газовые котлы двухконтурные", "газовые котлы цены"],
       "бойлеры газовые котлы": ["бойлеры косвенного нагрева", "бойлеры baxi", "бойлеры ariston", "бойлеры москва"],
       "запчасти газовые котлы": ["запчасти для котлов", "запчасти baxi", "запчасти navien", "запчасти платы"]}
now = time.time()
cache = {}
for ph, lst in SUG.items():
    for e, r in (("yandex", "213"), ("google", "ru")):
        cache[f"{e}|{r}|{ph}"] = {"s": lst, "t": now}
        cache[f"{e}|{r}|{ph} "] = {"s": list(reversed(lst)), "t": now}
with open(os.path.join(F, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)

# ---------- 1. два сбора - один результат
outs = []
for seed in ("1", "2", "3", "4", "5", "6"):   # на старом коде отличался сбор с PYTHONHASHSEED=5
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", F], env=dict(ENV, PYTHONHASHSEED=seed),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    check(r.returncode == 0, f"сбор упал: {r.stderr[-500:]}")
    outs.append(r.stdout.strip())
if all(outs):
    check(len(json.loads(outs[0])["sem"]["groups"]) >= 3, "сбор почти пустой - тест ничего не проверяет")
    for i, o in enumerate(outs[1:], 2):
        if o != outs[0]:
            a, b = outs[0], o
            j = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            check(False, f"сбор {i} отличается от первого: …{a[max(0, j - 80):j + 60]}… != …{b[max(0, j - 80):j + 60]}…")

# ---------- 2. бренды и серии из названий товаров: и с конкурентом по адресу, но не в быстром сборе
MD.seeds = lambda folder: [{"t": "газовый котел baxi eco"}]
main = {"host": "kotly.ru", "topic": [], "own": [], "models": None}
_n, _tm, _om, models = SEM._topic_phrases(main, {}, F, False, False)
check(models == ["газовый котел baxi eco"], f"обычный сбор: бренды и серии из названий товаров не собраны: {models}")
_n, _tm, _om, models = SEM._topic_phrases(main, {}, F, False, True)
check(models == [], f"быстрый сбор собирает бренды и серии из названий товаров: {models}")

calls = []
MD.seeds = lambda folder: calls.append(folder) or [{"t": "газовый котел baxi eco"}]
SEM._rivals_by_address = lambda hosts, *a: [{"host": "rival.ru", "sections": [], "brand": []}] if hosts else []
SEM.build(F, log=lambda *a: None, offline=True, region="Москва", rival_hosts=("rival.ru",))
check(calls, "с конкурентом по адресу бренды и серии из названий товаров не собираются")

# ---------- 3. город сайта в названиях фильтров и словах ТЗ
src = open(os.path.join(ROOT, "seocrawler", "semantics", "pages.py"), encoding="utf-8").read()
check('"уфа"' not in src and '"уфе"' not in src, "в pages.py снова зашит город «уфа»")
sem = json.loads(outs[0])["sem"] if outs[0] else {"groups": []}
names = [f["n"] if isinstance(f, dict) and "n" in f else f.get("name", "") for g in sem["groups"] for f in g.get("f") or []]
check(names and not any("москв" in n.lower() for n in names), f"в названии фильтра остался город сайта: {names}")

# ---------- 4. примерный спрос: без Вебмастера и Вордстата число запросов - круглое, «около …»
from seocrawler.fmt import approx  # noqa: E402
from seocrawler.semantics import client as CL  # noqa: E402
check([approx(x) for x in (5, 437, 1460, 9016)] == [5, 440, 1500, 9000], "fmt.approx округляет не так")
check(CL._count({"queries": 9016}) == "около 9 000 запросов", f"без настоящих данных: {CL._count({'queries': 9016})}")
check(CL._count({"queries": 9016, "real": True}) == "9 016 запросов", "с Вебмастером число запросов точное")
tree_js = open(os.path.join(ROOT, "seocrawler", "semantics", "tree.py"), encoding="utf-8").read()
check("'высокий' : d >= MID ? 'средний' : 'низкий'" in tree_js, "дерево сайта без частотности снова показывает баллы числом")

# ---------- 5. «Главное» для клиента: 3-4 вывода сверху раздела «Семантика»
S5 = {"cnt": {"ok": 10, "fix": 4, "create": 5}, "groups": 20, "queries": 300, "create": [
    {"name": "Котлы", "h1": "Газовые котлы", "url": "/kotly/"}, {"name": "Бойлеры", "h1": "", "url": "/b/"},
    {"name": "Насосы", "h1": "Насосы", "url": "/n/"}, {"name": "Трубы", "h1": "Трубы", "url": "/t/"}],
    "other_n": 0, "fix_types": [("В H1 нет главного запроса", 3)], "gaps_n": 7, "articles": 2}
kp = CL.key_points(S5)
check(len(kp) == 4 and kp[0].startswith("Под 14 из 20 групп") and "«Газовые котлы», «Бойлеры», «Насосы» и ещё 2" in kp[1]
      and "в H1 нет главного запроса - 3 страницы" in kp[2] and "7 тем" in kp[3], f"«Главное» для клиента: {kp}")
html_s = dict(S5, city="", rows=[], tz=0, other=[], gaps=[], real=False, freq=False, made="", brands=None)
check("<b>Главное</b>" in CL.html_block(html_s), "в разделе для клиента нет блока «Главное»")

if fails:
    print("✗ повтор семантики:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ повтор семантики: два сбора - один результат, бренды и серии с конкурентом по адресу, город сайта в ТЗ, "
      "примерный спрос - примерно")
