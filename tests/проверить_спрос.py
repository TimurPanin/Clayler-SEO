"""Автотест вкладки «Спрос» (semantics/demand.py): Вордстат через Директ без сети - поддельный сервер Директа v4.
Узнаваемость: названия сайта (из заголовков страниц и домена, кириллица на слух), свои названия, фразы по городу и
России, хвосты; очередь заданий тратит суточный лимит и при нехватке ждёт следующего дня."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="clayler-demand-")
os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(TMP, "доступы.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


SRV = {"reports": {}, "next": 100, "created": []}
SHOWS = {}   # фраза (как отправлена) → показов; нет - по длине


RFS = {}     # фраза → показов по России
TAILS = {}   # фраза → [(хвост, показов)]


def shows(x, geo):
    if geo == [225] and x in RFS:
        return RFS[x]
    n = SHOWS.get(x, len(x) * 10)
    return n * 50 if geo == [225] else n


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        m, p = body["method"], body.get("param")
        if "/json/v5/" in self.path:
            out = {"result": {"HasSearchVolumeResults": [{"Keyword": k, "AllDevices": "YES"}
                                                         for k in body["params"]["SelectionCriteria"]["Keywords"]]}}
        elif m == "CreateNewWordstatReport":
            rid = SRV["next"]
            SRV["next"] += 1
            SRV["reports"][rid] = p
            SRV["created"].append(p)
            out = {"data": rid}
        elif m == "GetWordstatReportList":
            out = {"data": [{"ReportID": r, "StatusReport": "Done"} for r in SRV["reports"]]}
        elif m == "GetWordstatReport":
            geo = SRV["reports"][p]["GeoID"]
            out = {"data": [{"Phrase": x, "GeoID": geo,
                             "SearchedWith": [{"Phrase": x.strip('"'), "Shows": shows(x, geo)}] + [
                                 {"Phrase": t, "Shows": n} for t, n in TAILS.get(x, [(x.strip('"') + " отзывы", 7),
                                                                                      (x.strip('"') + " адрес", 3)])],
                             "SearchedAlso": [{"Phrase": "дымоход для котла", "Shows": 40}]}
                            for x in SRV["reports"][p]["Phrases"]]}
        elif m == "DeleteWordstatReport":
            SRV["reports"].pop(p, None)
            out = {"data": 1}
        else:
            out = {"error_code": 55, "error_str": "Нет метода"}
        raw = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["CLAYLER_DIRECT_TEST"] = f"http://127.0.0.1:{srv.server_port}"

from seocrawler import direct as D  # noqa: E402
from seocrawler.semantics import demand as M  # noqa: E402

D.PAUSE = 0
_sleep = time.sleep
fast = type("T", (), {"sleep": staticmethod(lambda s: _sleep(0.01)), "time": staticmethod(time.time),
                      "strftime": staticmethod(time.strftime)})
D.time = fast
M.time = fast
D.save("9e2a", "y0_TESTTOKEN_abcdefghijklmnop")


def wait():
    for _ in range(1000):
        if not M.QUEUE and M.RUN.get("state") != "running":
            return
        _sleep(0.02)


# ---- папка проверки: заголовки страниц с названием сайта
folder = os.path.join(TMP, "site.ru_2026-10-07")
os.makedirs(folder)
db = sqlite3.connect(os.path.join(folder, "crawl.db"))
db.execute("CREATE TABLE pages (url TEXT, title TEXT, status INT)")
db.executemany("INSERT INTO pages VALUES (?,?,200)", [(f"https://teplo-sad.ru/{i}", f"Товар {i} | ТеплоСад") for i in range(30)])
db.commit()
db.close()


def row(q, score):
    return [q, "", "Общий", score, 1, 1, 0, "", 0, "", 0, 0, 0, 0]


data = {"site": "https://teplo-sad.ru/", "host": "teplo-sad.ru", "city": "Уфа", "competitors": ["https://vigas.su/"],
        "groups": [{"name": "Газовые котлы", "q": [row("газовые котлы", 20)]}]}

# ---- узнаваемость: названия
check(M.cyr("vigas") == "вигас" and M.cyr("gasmasterservis") == "гасмастерсервис", f"кириллица: {M.cyr('vigas')} {M.cyr('gasmasterservis')}")
nm = M.names_of(data, "teplo-sad.ru", folder)
check(nm == {"teplo-sad.ru": ["теплосад"], "vigas.su": ["vigas", "вигас"]}, f"названия: {nm}")
M.set_names("teplo-sad.ru", "teplo-sad.ru", "ТеплоСад, teplosad ,  ")
check(M.names_of(data, "teplo-sad.ru", folder)["teplo-sad.ru"] == ["теплосад", "teplosad"], "свои названия")
v = M.build(data, "teplo-sad.ru", folder)
check(v["brand"]["cost"] == 8 and v["brand"]["city"] == "Уфа", f"сколько фраз уйдёт: {v['brand']['cost']}")

# ---- загрузка: город и Россия, без кавычек; лимит дня кончился посередине - ждёт следующего дня
D.DAY_LIMIT = 5
check(M.start(data, "teplo-sad.ru", "brand", folder) == "", "старт узнаваемости")
for _ in range(500):
    if M.RUN.get("state") == "waiting":
        break
    _sleep(0.02)
check(M.RUN.get("state") == "waiting" and "исчерпан" in M.RUN.get("msg", ""), f"лимит дня: {M.RUN}")
check([len(c["Phrases"]) for c in SRV["created"]] == [4, 1], f"по лимиту: {SRV['created']}")
check(M.start(data, "teplo-sad.ru", "brand", folder) == "Это уже в очереди.", "повтор в очереди")
st = M.run_state("teplo-sad.ru")
check(st["queue"][0]["left"] == 3 and st["queue"][0]["total"] == 8, f"очередь: {st}")
M.cancel("teplo-sad.ru")   # отмена во время ожидания: очередь пустеет, поток заканчивается
wait()
check(not M.QUEUE and M.RUN["state"] == "idle", f"отмена: {M.QUEUE} {M.RUN}")
D.DAY_LIMIT = 1000   # «наступил новый день»: загружается только то, чего нет за этот месяц
FIRST = list(SRV["created"])
SRV["created"].clear()
check(M.build(data, "teplo-sad.ru", folder)["brand"]["cost"] == 3, "уже загруженное снова в цене")
check(M.start(data, "teplo-sad.ru", "brand", folder) == "", "старт после нового дня")
wait()
check(len([x for c in SRV["created"] for x in c["Phrases"]]) == 3, f"догрузка: {SRV['created']}")
check(M.start(data, "teplo-sad.ru", "brand", folder) == "Всё уже загружено.", "повторная загрузка за месяц")
SRV["created"] = FIRST + SRV["created"]
sent = [x for c in SRV["created"] for x in c["Phrases"]]
check(len(sent) == 8 and all(not x.startswith('"') for x in sent), f"без кавычек: {sent}")
geos = sorted({c["GeoID"][0] for c in SRV["created"]})
check(geos == [172, 225], f"регионы: {geos}")
b = M.build(data, "teplo-sad.ru", folder)["brand"]
own = b["sites"][0]
check(own["own"] and own["city"] == 80 + 80 and own["rf"] == 160 * 50, f"узнаваемость: {own}")
check(own["rows"][0]["with"][0] == ["теплосад отзывы", 7], f"хвосты: {own['rows'][0].get('with')}")

# ---- местный спрос: самые востребованные в городе (без названия города, «котлы газовые» = «газовые котлы») и Россия
qs = ["газовые котлы", "котлы газовые", "монтаж котла", "котел купить", "котел уфа", "радиатор", "насос", "кран"]
data["groups"] = [{"name": "Котлы", "q": [row(q, 10) for q in qs]}]
D._store("teplo-sad.ru", 172, "Уфа", {"газовые котлы": 100, "котлы газовые": 100, "монтаж котла": 50, "котел купить": 40,
                                      "котел уфа": 500, "радиатор": 30, "насос": 20, "кран": 0})
RFS.update({'"газовые котлы"': 10000, '"монтаж котла"': 1000, '"котел купить"': 4000, '"радиатор"': 3000, '"насос"': 8000})
lv = M.local_view(data, "teplo-sad.ru")
check([r["q"] for r in lv["rows"]] == ["газовые котлы", "монтаж котла", "котел купить", "радиатор", "насос"]
      and lv["cost"] == 5 and lv["in"] == "Уфе", f"местный спрос, запросы: {lv}")
SRV["created"].clear()
check(M.start(data, "teplo-sad.ru", "rf", folder) == "", "старт местного спроса")
wait()
check(SRV["created"] == [{"Phrases": ['"газовые котлы"', '"монтаж котла"', '"котел купить"', '"радиатор"', '"насос"'],
                          "GeoID": [225]}], f"местный спрос, отправлено: {SRV['created']}")
lv = M.local_view(data, "teplo-sad.ru")
check({r["q"]: (r["share"], r["kind"]) for r in lv["rows"]} == {"газовые котлы": (1.0, ""), "монтаж котла": (5.0, "local"),
      "котел купить": (1.0, ""), "радиатор": (1.0, ""), "насос": (0.25, "wide")} and lv["median"] == 1.0 and lv["cost"] == 0,
      f"местный спрос, доли: {lv}")

# ---- своя сезонность: старт берёт цифры этого месяца из загруженной частотности (бесплатно), новый месяц - сам
M.SEASON_TOP = 3
SRV["created"].clear()
check(M.start(data, "teplo-sad.ru", "season", folder) == "", "старт сезонности")
wait()
sv = M.season_view("teplo-sad.ru")
check(not SRV["created"] and sv["on"] and sv["months"] == [M._month()] and sv["total"] == [500 + 100 + 50]
      and sv["cost"] == 0, f"сезонность, этот месяц: {sv} {SRV['created']}")
real_day = M._day
M._day = lambda: "07.11.2099"
M.season_tick()
wait()
check(sorted(x for c in SRV["created"] for x in c["Phrases"]) == ['"газовые котлы"', '"котел уфа"', '"монтаж котла"']
      and SRV["created"][0]["GeoID"] == [172], f"сезонность, новый месяц: {SRV['created']}")
sv = M.season_view("teplo-sad.ru")
check(sv["months"] == [real_day()[6:] + "-" + real_day()[3:5], "2099-11"] and sv["rows"][0]["q"] == "котел уфа"
      and sv["rows"][0]["m"] == [500, 110], f"сезонность, два месяца: {sv}")
SRV["created"].clear()
M.season_tick()
wait()
check(not SRV["created"], "сезонность: месяц спрошен второй раз")
M._day = real_day

# ---- что ещё искали: дозагрузка для главных запросов; новое - по группам (уже собранное не показывается)
data["groups"] = [{"name": "Котлы", "q": [row(q, 10) for q in qs]}, {"name": "Дымоходы", "q": [row("дымоход", 5)]}]
D._store("teplo-sad.ru", 172, "Уфа", {"дымоход": 5}, "phr")
M.ALSO_TOP = 2
av = M.also_view(data, "teplo-sad.ru")
check(av["cost"] == 2 and av["n"] == 0, f"что ещё искали, до загрузки: {av}")
SRV["created"].clear()
M.start(data, "teplo-sad.ru", "also", folder)
wait()
check(SRV["created"] == [{"Phrases": ['"котел уфа"', '"газовые котлы"'], "GeoID": [172]}], f"что ещё искали, отправлено: {SRV['created']}")
av = M.also_view(data, "teplo-sad.ru")
check(av["n"] == 2 and av["cost"] == 0 and [x["q"] for x in av["add"]] == ["дымоход для котла"] and av["add"][0]["group"] == "Дымоходы"
      and av["add"][0]["n"] == 40, f"что ещё искали, разложено: {av}")

# ---- ёлочка: хвосты главных фраз (без кавычек), второй круг с минус-словами; чужие города отсеяны
M.TREE_ROOTS = 1
TAILS["газовые котлы"] = [(f"газовые котлы купить {i}", 50 - i) for i in range(22)] + [("газовые котлы цена", 30), ("газовые котлы москва", 9),
                                                                              ("как выбрать газовые котлы", 8)]
tv = M.tree_view(data, "teplo-sad.ru")
check(tv["cost"] == 2 and not tv["roots"], f"ёлочка, до загрузки: {tv}")
SRV["created"].clear()
M.start(data, "teplo-sad.ru", "tree", folder)
wait()
sent = [c["Phrases"] for c in SRV["created"]]
check(sent[0] == ["газовые котлы"] and len(sent) == 2 and sent[1][0].startswith("газовые котлы -купить -цена"), f"ёлочка, отправлено: {sent}")
tv = M.tree_view(data, "teplo-sad.ru")
check(tv["roots"][0]["q"] == "газовые котлы" and tv["roots"][0]["r1"] == 25 and tv["roots"][0]["minus"][:2] == ["купить", "цена"],
      f"ёлочка, корни: {tv['roots']}")
check([x["q"] for x in tv["articles"]] == ["как выбрать газовые котлы"] and tv["dropped"] >= 1
      and "газовые котлы москва" not in [x["q"] for x in tv["add"] + tv["topics"]], f"ёлочка, разложено: {tv}")
check(M.tree_items(data, "teplo-sad.ru")[0][0] == "котел уфа", "ёлочка: следующий корень")

srv.shutdown()
shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("СПРОС: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Спрос (Вордстат через Директ): всё в порядке")
