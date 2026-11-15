"""Автотест: очередь сайтов и семантика (план, раздел 2, 10.10.2026). Без сети и без настоящего обхода.

- Быстрая семантика (build(light=True), crawl.py --light): маски не подтверждены - программа предлагает их сама
  и собирает только главную и разделы (уровни 1-2), без подразделов глубже и карточек; файл масок остаётся
  неподтверждённым, чтобы человек потом их увидел.
- Очередь: галочка «После проверки собрать семантику» - после готового сайта следующим идёт его семантика, потом
  следующий сайт; строка «семантика» (kind sem, «Собрать семантику» для выбранных в «Отчётах»); «Остановить» во
  время семантики - очередь на паузе, семантика соберётся заново; история очередей и оценка оставшегося времени;
  итог в Telegram считает семантику.
- Пары «похоже на синонимы» запоминаются в папке проверки и показываются в «Ждут подтверждения» без пересчёта;
  ответ «да» / «нет» пачкой убирает пары из списка.
- Избранное в «Отчётах»; частотность для нескольких сайтов встаёт в очередь Директа.
Запуск: py -3 тест/проверить_очередь_семантики.py"""
import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="clayler-qsem-")
os.environ.update(CLAYLER_DECISIONS_DIR=os.path.join(TMP, "решения"), CLAYLER_DICTS_FILE=os.path.join(TMP, "словари.json"),
                  CLAYLER_DICT_FILE=os.path.join(TMP, "словарь.json"), CLAYLER_REPORTS=os.path.join(TMP, "отчёты"),
                  CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import build, export as SX, masks as MK, synonyms as SY, dictionary as D  # noqa: E402
from seocrawler import site_queue as Q  # noqa: E402
from seocrawler.window import reports_list as RL  # noqa: E402
import seocrawler.window as W  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


REPORTS = os.environ["CLAYLER_REPORTS"]
os.makedirs(REPORTS)
W.REPORTS = RL.REPORTS = REPORTS
B = "https://own.ru"
MENU = [(B + "/kotly/", "Газовые котлы"), (B + "/zapchasti/", "Запчасти")]
SUB = [(B + "/kotly/nastennye/", "Настенные"), (B + "/kotly/nastennye/kondensacionnye/", "Конденсационные котлы")]


def make(folder):
    os.makedirs(folder)
    st = Store(os.path.join(folder, "crawl.db"))
    st.set_meta("start", B + "/")
    st.set_meta("finished_at", "2026-10-10 10:05:00")
    st.set_meta("started_at", "2026-10-10 10:00:00")
    st.set_meta("summary", {"pages": 40, "health": 90})
    prods = [f"{B}/product/kotel-{i}/" for i in range(32)]
    pages = [B + "/"] + [f"{B}/p{i}/" for i in range(6)] + [u for u, _ in MENU + SUB] + prods
    for u in pages:
        h1 = (f"Котел Baxi Eco {u.rsplit('-', 1)[-1].strip('/')} кВт" if "/product/" in u
              else "Газовые котлы в Уфе" if u == B + "/" else "")
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": h1 or u, "h1": h1,
                      "word_count": 300})
    for src in pages:
        st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in MENU])
    for src in pages[:7]:
        st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in SUB])
        st.add_links([(src, prods[0], prods[0], "Котел Baxi Eco 0", 0, "a", 1)])
    st.commit()
    st.db.close()
    with open(os.path.join(folder, "отчёт.html"), "w", encoding="utf-8") as f:
        f.write("<html></html>")


# ---------- быстрая семантика: маски сами, только уровни 1-2
F = os.path.join(REPORTS, "own.ru_2026-10-10_10-00-00")
make(F)
SUG = {"газовые котлы": ["газовые котлы", "газовые котлы цены", "газовые котлы двухконтурные"],
       "настенные газовые котлы": ["настенные газовые котлы", "настенные газовые котлы купить"],
       "конденсационные котлы": ["конденсационные котлы", "конденсационные котлы купить", "конденсационные котлы плюсы"],
       "запчасти": ["запчасти для котлов", "запчасти для котлов baxi"]}
now = time.time()
cache = {f"{e}|{r}|{ph}": {"s": lst, "t": now} for ph, lst in SUG.items() for e, r in (("yandex", "172"), ("google", "ru"))}
with open(os.path.join(F, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)
logs = []
sem = build(F, log=logs.append, offline=True, region="Уфа", light=True)
qs = set(sem["queries"])
check("настенные газовые котлы купить" in qs and "газовые котлы цены" in qs, f"быстрый сбор: главная и разделы: {sorted(qs)}")
check(not any("конденсационные" in q for q in qs), "быстрый сбор: подраздел третьего уровня не собирается")
check(not any("baxi eco" in q for q in qs), "быстрый сбор: карточки товаров не собираются")
m = MK.load("own.ru")
check(m.get("masks") and not m.get("confirmed"), "маски предложены и сохранены неподтверждёнными")
check(any("Быстрый сбор" in x and "не подтверждены" in x for x in logs), f"в журнале - быстрый сбор: {[x for x in logs if 'аск' in x]}")
check(MK.for_build({"host": "own.ru", "sections": []}, log=lambda *a: None) is None,
      "обычный сбор без подтверждения - как раньше, по всем разделам")
SX.write_json(os.path.join(F, SX.JSON_NAME), sem)

# ---------- очередь: семантика после проверки, строка «семантика», пауза, история, оценка времени
Q.FILE = os.path.join(TMP, "очередь.json")
Q.HISTORY = os.path.join(TMP, "очередь история.json")
Q.LISTS = os.path.join(TMP, "списки")
sent = []
Q._tg = sent.append
Q._reports = lambda: REPORTS


class Job:
    def __init__(self):
        self.running, self.out_dir, self.lines, self.was_stopped = False, "", [], False
        self.started = self.finished = 0
        self.site_pages, self.site_down = [], ""

    def add(self, line):
        self.lines.append(line)

    def stop(self):
        self.was_stopped = True

    def status(self):
        return {"overall": 50}


JOB = Job()
started = []


def start_check(data):
    started.append(("check", data["site"]))
    JOB.running, JOB.was_stopped, JOB.lines = True, False, []
    JOB.started = time.time() - 600
    return ""


def start_sem(folder):
    started.append(("sem", folder))
    JOB.running, JOB.was_stopped, JOB.lines = True, False, []
    JOB.started = time.time() - 120
    return ""


def finish(out_dir="", stopped=False, sem_ok=False):
    if sem_ok:   # сбор записал свежую семантику
        p = os.path.join(out_dir, SX.JSON_NAME)
        os.utime(p, None)
    JOB.running, JOB.finished, JOB.out_dir = False, time.time(), out_dir
    JOB.was_stopped = stopped or JOB.was_stopped
    Q.on_finished(JOB)


n, err = Q.add(B + "/\nhttps://two.ru/", pages=50)
check(n == 2 and not err, f"добавлено {n}: {err}")
check(Q.action("sem_after", {"on": True}) == "" and Q.load()["sem_after"], "галочка «После проверки собрать семантику»")
check(Q.status(JOB)["eta"] is None, "оценки времени нет, пока не с чем сравнить")
Q.action("start", {})
Q.tick(JOB, start_check, start_sem)
check(started[-1] == ("check", B + "/"), f"первым - проверка сайта: {started}")
check(Q.status(JOB)["eta"] is None, "оценки нет, пока ни один сайт не закончен")
finish(F)
it = Q._find(Q.load(), B + "/")
check(it["state"] == "done" and it.get("sem") == "wait" and it["pages"] == 40, f"готово, семантика ждёт: {it}")
Q.tick(JOB, start_check, start_sem)
check(started[-1] == ("sem", os.path.basename(F)), f"следом - семантика этого сайта, а не следующий: {started}")
it = Q._find(Q.load(), B + "/")
check(it.get("sem") == "run", f"семантика идёт: {it.get('sem')}")
e = Q.status(JOB)["eta"]
check(e and e["seconds"] > 0 and e["sites"] == 1, f"оценка после первого сайта: {e}")
# «Остановить» во время семантики: на паузу, семантика соберётся заново
Q._current["stopping"] = "stop"
finish(F, stopped=True)
d = Q.load()
it = Q._find(d, B + "/")
check(d["paused"] and it.get("sem") == "wait", f"остановили семантику: пауза и снова ждёт: {it.get('sem')}, {d['paused']}")
Q.action("start", {})
Q.tick(JOB, start_check, start_sem)
check(started[-1][0] == "sem", "после «Продолжить» - снова семантика")
finish(F, sem_ok=True)
it = Q._find(Q.load(), B + "/")
check(it.get("sem") == "done" and it.get("sem_queries"), f"семантика собрана: {it.get('sem')}, {it.get('sem_queries')}")
Q.tick(JOB, start_check, start_sem)
check(started[-1] == ("check", "https://two.ru/"), f"потом следующий сайт: {started[-1]}")
JOB.lines = ["Не понял адрес"]
finish("")   # второй не открылся
check(Q._find(Q.load(), "https://two.ru/")["state"] == "fail", "второй сайт пропущен")
check(not Q._find(Q.load(), "https://two.ru/").get("sem"), "у пропущенного сайта семантика не собирается")
# «Собрать семантику» для выбранных в «Отчётах»: строка kind sem
check(Q.add_sem([(os.path.basename(F), B + "/")]) == 1, "строка «семантика» добавлена")
check(Q.add_sem([(os.path.basename(F), B + "/")]) == 0, "та же семантика второй раз не ставится")
Q.tick(JOB, start_check, start_sem)
check(started[-1] == ("sem", os.path.basename(F)), f"строка «семантика» - сбор без проверки: {started[-1]}")
finish(F, sem_ok=True)
s = Q._find(Q.load(), B + "/", "sem")
check(s and s["state"] == "done" and s.get("took"), f"строка «семантика» готова: {s}")
Q.tick(JOB, start_check, start_sem)
check(Q.load().get("notified") and sent, "очередь закончилась, итог отправлен")
check(sent and "Семантика собрана: 2 из 2" in sent[-1], f"итог считает семантику: {sent[-1:]}")
h = Q.history_view()
check(len(h) == 1 and h[0]["done"] == 1 and h[0]["fail"] == 1 and h[0]["sem"] == 2 and h[0]["pages"] == 40,
      f"история очереди: {h and {k: h[0][k] for k in ('done', 'fail', 'sem', 'pages')}}")
Q.action("clear_all", {})
check(Q.history_view() and not Q.load()["items"], "«Очистить очередь» не трогает историю")
Q.add("https://three.ru/", pages=100)
e = Q.eta(Q.load())
check(e and e["sites"] == 1 and e["seconds"] > 0, f"оценка по истории прошлых очередей: {e}")

# ---------- пары синонимов: запомнены в папке, «да» / «нет» пачкой
data = {"host": "own.ru", "groups": [{"name": "Бойлеры", "q": [["бойлер косвенного нагрева", 0]]}]}
pairs = [{"a": "фыва", "b": "ролд", "n": 3, "ex": []}, {"a": "газовый", "b": "электрический", "n": 2, "ex": []},
         {"a": "illy", "b": "илли", "n": 2, "ex": []}]
SY.save_pairs(F, data, pairs)
got = SY.cached_pairs(F, "own.ru", D.site_node(data)[0])
check(got is not None and len(got) == 3, f"пары запомнены: {got}")
D.confirm(data, "illy", "илли", None)
D.reject(data, "газовый", "электрический")
got = SY.cached_pairs(F, "own.ru", D.site_node(data)[0])
check(got is not None and [p["a"] for p in got] == ["фыва"], f"отвеченные пары убраны: {got}")
os.utime(os.path.join(F, SX.JSON_NAME), (time.time() + 5, time.time() + 5))
check(SY.cached_pairs(F, "own.ru") is None, "семантику собрали заново - старые пары не показываются")
SY.save_pairs(F, data, pairs)
v = D.view()
site = next((x for x in v["sites"] if x["host"] == "own.ru"), None)
check(site and site.get("pairs") == 1, f"в «Ждут подтверждения» сайт с числом пар: {site and site.get('pairs')}")

# «Да» / «Нет» пачкой через окно (window/dictview.py)
from seocrawler.window import dictview, semdec  # noqa: E402
semdec.REPORTS = REPORTS
SY.save_pairs(F, data, [{"a": "фыва", "b": "ролд", "n": 3, "ex": []}, {"a": "йцук", "b": "енгш", "n": 2, "ex": []},
                        {"a": "ячсм", "b": "итьб", "n": 2, "ex": []}])


class H:
    def send(self, code, body):
        self.code, self.body = code, body


h = H()
dictview.post(h, {"act": "no_many", "f": os.path.basename(F), "pairs": [{"a": "йцук", "b": "енгш"}, {"a": "ячсм", "b": "итьб"}]})
check(h.code == 200 and h.body.get("done") == 2 and [p["a"] for p in h.body["suggest"]] == ["фыва"],
      f"«Нет для отмеченных»: {getattr(h, 'code', None)}, {h.body.get('error') or [p['a'] for p in h.body.get('suggest') or []]}")
dictview.post(h, {"act": "yes_many", "f": os.path.basename(F), "pairs": [{"a": "фыва", "b": "ролд", "node": "common"}]})
check(h.code == 200 and not h.body["suggest"] and any("фыва = ролд" in ln for ln in D.all_lines()),
      f"«Да для отмеченных»: {h.body.get('error') or h.body.get('suggest')}")
dictview.post(h, {"act": "yes_many", "f": os.path.basename(F), "pairs": []})
check(h.code == 400, "пачка без пар - понятная ошибка")

# ---------- избранное в «Отчётах»
RL.FAV = os.path.join(TMP, "избранное.json")
check(RL.set_favorite("www.own.ru", True) == "" and RL.favorites() == ["own.ru"], f"в избранное: {RL.favorites()}")
RL.REPORTS = REPORTS
g = next((x for x in RL.list_reports()["sites"] if x["key"] == "own.ru"), None)
check(g and g["fav"] and g["sem_folder"] == os.path.basename(F), f"карточка сайта: избранное и семантика: {g and (g['fav'], g['sem_folder'])}")
RL.set_favorite("own.ru", False)
check(RL.favorites() == [], "из избранного убрано")

# ---------- частотность для нескольких сайтов - в очередь Директа
from seocrawler import direct  # noqa: E402
store = {"token": "x"}
direct._cfg = lambda: dict(store)
direct._put = lambda **kw: store.update(kw)
direct.start = lambda folder: store.update(job=folder) or ""
direct._reports = lambda: REPORTS
G = os.path.join(REPORTS, "two.ru_2026-10-10_11-00-00")
os.makedirs(G)
with open(os.path.join(G, SX.JSON_NAME), "w", encoding="utf-8") as f:
    f.write("{}")
check(direct.start_many([os.path.basename(F), os.path.basename(G)]) == "", "частотность для выбранных")
check(store.get("job") == os.path.basename(F) and store.get("next") == [os.path.basename(G)],
      f"первый сайт идёт, второй ждёт: {store.get('job')}, {store.get('next')}")
check(direct._next_folder() == os.path.basename(G) and store.get("next") == [], "следующий сайт берётся из очереди")

if fails:
    print("✗ очередь и семантика:")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("✓ очередь и семантика: быстрая семантика, галочка в очереди, строка «семантика», история, оценка времени, "
      "пары в Словаре, избранное, частотность для выбранных")
