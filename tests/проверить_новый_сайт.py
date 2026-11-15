"""Автотест «Семантика нового сайта» (semantics/newsite.py): проекта без своего сайта. Без сети: конкурент -
маленькая выдуманная проверка, подсказки - заранее в кеше. Проверяется: проект создаётся и не попадает в список
проверок; тема без уточнений - главная («/»); раздел конкурента со спросом - «Создать раздел»; вложенный у
конкурента и по словам - подраздел с адресом внутри раздела; страница бренда - в /brands/; раздел без спроса -
«решить»; структура для клиента и лист «Структура сайта» в Excel; у обычной семантики адреса не меняются."""
import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="clayler-newsite-")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import build, decisions, export as SX, newsite as NS, plan  # noqa: E402
from seocrawler.window.reports_list import list_checks  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


REP = os.path.join(TMP, "reports")
os.makedirs(REP)

# ---- конкурент: главная, 6 страниц, меню на каждой
RIV = os.path.join(REP, "rival.ru_2026-10-06_10-00-00")
os.makedirs(RIV)
st = Store(os.path.join(RIV, "crawl.db"))
st.set_meta("start", "https://rival.ru/")
st.set_meta("finished_at", "2026-10-06 10:05:00")
MENU = [("https://rival.ru/gazovye-kotly/", "Газовые котлы"), ("https://rival.ru/gazovye-kotly/nastennye/", "Настенные"),
        ("https://rival.ru/radiatory/", "Радиаторы отопления"), ("https://rival.ru/radiatory/bimetallicheskie/", "Биметаллические"), ("https://rival.ru/brands/baxi/", "Baxi"),
        ("https://rival.ru/shlangi/", "Шланги"), ("https://rival.ru/gidrostrelki/", "Гидрострелки")]
TITLE = "рифар алюминиевые стальные как подключить работают газовые котлы настенные двухконтурные радиаторы отопления биметаллические baxi бакси шланги для газа цены уфа"
pages = ["https://rival.ru/"] + [f"https://rival.ru/p{i}/" for i in range(6)] + [u for u, _ in MENU]
for u in pages:
    st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1,
                  "title": TITLE if u.startswith("https://rival.ru/p") else u.rsplit("/", 2)[-2], "h1": "", "word_count": 300})
for src in pages[:7]:
    st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in MENU])
st.commit()
st.db.close()

# ---- проект нового сайта и подсказки в кеше
P = NS.create(REP, "Газовые котлы в Уфе", "газовые котлы, газовое оборудование", "Уфа")
check(os.path.basename(P).startswith("gazovye-kotly.new_"), f"имя папки проекта: {os.path.basename(P)}")
info = NS.info(P)
check(info and info["city"] == "Уфа" and info["words"] == ["газовые котлы", "газовое оборудование"], f"meta проекта: {info}")
check(NS.info(RIV) is None, "обычная проверка не считается новым сайтом")
items = {c["folder"]: c for c in list_checks(REP)}
check(items[os.path.basename(P)].get("new_site") and not items[os.path.basename(RIV)].get("new_site"),
      "в списке проверок у проекта есть new_site, у проверки нет")

SUG = {"газовые котлы": ["газовые котлы", "газовые котлы цены", "газовые котлы купить в уфе", "газовые котлы двухконтурные",
                         "газовые котлы настенные", "газовые котлы бакси"],
       "газовые котлы как": ["газовые котлы как выбрать", "газовые котлы как работают", "газовые котлы как подключить"],
       "настенные газовые котлы": ["настенные газовые котлы", "настенные газовые котлы цены", "настенные газовые котлы двухконтурные"],
       "радиаторы отопления": ["радиаторы отопления", "радиаторы отопления цены", "радиаторы отопления купить",
                               "радиаторы отопления алюминиевые", "радиаторы отопления стальные"],
       "baxi": ["baxi котел", "baxi котлы цены", "baxi бакси", "baxi котел двухконтурный"],
       "биметаллические радиаторы отопления": ["биметаллические радиаторы отопления", "биметаллические радиаторы отопления цены",
                                               "биметаллические радиаторы отопления рифар"],
       "шланги": ["шланги для газа"],
       "газовое оборудование": ["газовое оборудование", "газовое оборудование уфа", "газовое оборудование цены"]}
now = time.time()
cache = {}
for ph, lst in SUG.items():
    for pos, key in enumerate((f"yandex|172|{ph}", f"google|ru|{ph}")):
        cache[key] = {"s": lst if not pos or ph != "шланги" else [], "t": now}
cache["yandex|172|шланги"] = {"s": ["кабели", "провода", "трубы", "краны", "двери", "окна", "окна пвх", "шланги для газа"], "t": now}
with open(os.path.join(P, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)

sem = build(P, [RIV], log=lambda *a: None, offline=True)
SX.write_json(os.path.join(P, SX.JSON_NAME), sem)
g = {x["name"]: x for x in sem["groups"]}
check(sem.get("new_site") and sem["real"] == {"wm": "new", "gsc": "new"}, "семантика помечена как новый сайт")
home = next((x for x in sem["groups"] if x["todo"] == "Главная страница сайта"), None)
check(home is not None and home["page"] == "", f"главная - тема без уточнений: {[x['todo'] for x in sem['groups']]}")
check(g.get("Газовое оборудование", {}).get("todo") == "Создать раздел",
      f"второе слово темы - раздел: {g.get('Газовое оборудование', {}).get('todo')}")
check(g.get("Радиаторы отопления", {}).get("todo") == "Создать раздел", f"радиаторы: {g.get('Радиаторы отопления', {}).get('todo')}")
check(g.get("Газовые котлы", {}).get("main"), "первое слово темы - раздел конкурента: эта группа и есть главная")
check(g.get("Настенные газовые котлы", {}).get("todo") == "Создать раздел",
      f"настенные (родитель - главная): {g.get('Настенные газовые котлы', {}).get('todo')}")
check(g.get("Биметаллические радиаторы отопления", {}).get("todo") == "Создать подраздел в «Радиаторы отопления»",
      f"биметаллические: {g.get('Биметаллические радиаторы отопления', {}).get('todo')}")
check(g.get("Baxi", {}).get("todo") == "Создать страницу бренда", f"baxi: {g.get('Baxi', {}).get('todo')}")
check(g.get("Шланги", {}).get("prio") == 3, f"шланги без спроса - решить: {g.get('Шланги', {}).get('todo')}")
check("Гидрострелки" not in g, "раздел, который никто не ищет, не группа")

data = plan.enrich(decisions.apply(SX.load(P), P), P)
land = {x["name"]: x["land"] for x in data["groups"]}
check(home and land[home["name"]]["url"] == "https://gazovye-kotly.new/", f"адрес главной: {home and land[home['name']]['url']}")
check(land["Радиаторы отопления"]["url"] == "https://gazovye-kotly.new/radiatory-otopleniya/",
      f"раздел: {land['Радиаторы отопления']['url']}")
check(land["Биметаллические радиаторы отопления"]["url"].startswith("https://gazovye-kotly.new/radiatory-otopleniya/bimetallicheskie"),
      f"подраздел внутри раздела: {land['Биметаллические радиаторы отопления']['url']}")
check(land["Baxi"]["url"] == "https://gazovye-kotly.new/brands/baxi/", f"бренд: {land['Baxi']['url']}")

s = NS.structure(data)
top = {n["name"]: n for n in s["sections"]}
check(s["home"] and s["home"]["name"] == "Газовые котлы", "главная в структуре")
check("Радиаторы отопления" in top and [c["name"] for c in top["Радиаторы отопления"]["children"]] == ["Биметаллические радиаторы отопления"],
      f"структура: разделы {list(top)}")
check("Бренды" in top and [c["name"] for c in top["Бренды"]["children"]] == ["Baxi"], "бренды одним разделом")
check([n["name"] for n in s["decide"]] == ["Шланги"], f"решить: {[n['name'] for n in s['decide']]}")
check(any("как выбрать" in a["title"].lower() for a in s["blog"]), f"вопросы - в блог: {[a['title'] for a in s['blog']]}")
page = NS.write_client(P, data)
text = open(page, encoding="utf-8").read()
check("Структура сайта: Газовые котлы в Уфе" in text and "/radiatory-otopleniya/bimetallicheskie" in text, "страница для клиента")
check("—" not in text and ".new" not in text, "в тексте для клиента нет длинного тире и служебного адреса")
check(os.path.exists(os.path.join(P, "для клиента", "Структура сайта - Газовые котлы в Уфе.html")), "копия в «для клиента»")
try:
    from openpyxl import load_workbook
    SX.write_xlsx(os.path.join(P, SX.XLSX_NAME), sem, s)
    wb = load_workbook(os.path.join(P, SX.XLSX_NAME), read_only=True)
    check(wb.sheetnames[0] == "Структура сайта", f"первый лист Excel: {wb.sheetnames[:2]}")
    first = [r[0] for r in wb["Структура сайта"].iter_rows(min_row=2, values_only=True)]
    check(first[:2] == ["Главная", "Раздел"] and "Подраздел" in first, f"строки структуры: {first[:6]}")
except ImportError:
    pass

# дерево сайта (semantics/tree.py): у нового сайта - его структура, всё «создать»
from seocrawler.semantics import tree as TR  # noqa: E402

tpage, t = TR.write(P, data)
tn = {n["name"]: n for n, _d in TR._walk(t["root"])}
check(t["new"] and t["root"]["name"] == "Газовые котлы" and t["root"]["path"] == "/", f"дерево: главная {t['root']['name']}")
check("Биметаллические радиаторы отопления" in [c["name"] for c in tn["Радиаторы отопления"]["children"]], "дерево: подраздел")
check(all(n["st"] in ("create", "low", "decide") for n in tn.values() if n["kind"] != "group"), "у нового сайта всё «создать»")
check(tn.get("Шланги", {}).get("st") == "decide" and "Блог" in tn, "дерево: «решить» и блог")
ttext = open(tpage, encoding="utf-8").read()
check(".new" not in ttext and "—" not in ttext, "в дереве нет служебного адреса и длинного тире")
try:
    from openpyxl import load_workbook
    SX.write_xlsx(os.path.join(P, SX.XLSX_NAME), sem, tree=t)
    wb = load_workbook(os.path.join(P, SX.XLSX_NAME), read_only=True)
    check(wb.sheetnames[0] == "Структура сайта", f"дерево нового сайта - лист «Структура сайта»: {wb.sheetnames[:2]}")
    first = [r[0] for r in wb["Структура сайта"].iter_rows(min_row=2, values_only=True)]
    check(first[:2] == ["Главная", "Раздел"] and "Подраздел" in first and "Статья в блог" in first, f"строки дерева: {first[:8]}")
except ImportError:
    pass

# обычная семантика: подраздел с адресом родителя-страницы - как раньше
d2 = {"site": "https://a.ru/", "groups": [
    {"name": "Котлы", "kind": "page", "page": "https://a.ru/kotly/", "todo": "Продвигать эту страницу", "q": []},
    {"name": "Настенные котлы", "kind": "create", "page": "", "near": "https://a.ru/kotly/",
     "todo": "Создать подраздел в «Котлы»", "q": []}]}
plan.enrich(d2, None)
check(d2["groups"][1]["land"]["url"] == "https://a.ru/kotly/nastennye-kotly/", f"обычный подраздел: {d2['groups'][1]['land']['url']}")

if fails:
    print("НОВЫЙ САЙТ: ОШИБКИ")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("Новый сайт: всё в порядке")
