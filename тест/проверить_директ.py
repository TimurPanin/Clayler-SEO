"""Автотест точной частотности через API Директа (direct.py). Без сети: поддельный сервер Директа v4 Live.
Проверяется: ключ сохраняется зашифрованным, адрес со страницы Яндекса целиком тоже понимается; «Проверить» -
один отчёт по одной фразе, отчёт удаляется с сервера; фраза для Вордстата - в кавычках, без лишних знаков,
длинные пропускаются; порядок фраз - сначала главные запросы каждой группы, сомнительные не берутся; загрузка по
10 фраз, регион - город семантики (Уфа - 172); фраза, на которую Директ ругается, пропускается, остальные из
отчёта загружаются; суточный лимит - загрузка ждёт следующего дня; частотность ставится в колонку «Спрос»
(export.load) и не теряется при повторном чтении; уже загруженное не запрашивается снова."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="clayler-direct-")
os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(TMP, "доступы.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
os.environ.update(CLAYLER_JOURNAL_DIR=TMP, CLAYLER_NO_SOUND="1")   # уведомления и «Журнал» - не в папку программы
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


SRV = {"reports": {}, "next": 100, "created": [], "calls": 0}


def shows(x):
    if "пустышка" in x:   # в кавычках никто, без кавычек: «мало» - и с хвостами мало, иначе хвостов много
        return 0 if x.startswith('"') else 3 if "мало" in x else 500
    return len(x) * 10


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SRV["calls"] += 1
        m, p = body["method"], body.get("param")
        if "/json/v5/" in self.path:   # Директ v5: ключ в заголовке, ответ в result / error
            kw = body["params"]["SelectionCriteria"]["Keywords"]
            SRV.setdefault("v5", []).append((self.path, kw, body["params"]["SelectionCriteria"]["RegionIds"]))
            if self.headers.get("Authorization") != "Bearer y0_TESTTOKEN_abcdefghijklmnop" or SRV.get("v5_fail"):
                out = {"error": {"error_code": 53, "error_string": "Ошибка авторизации"}}
            else:
                # «пустышка» - и по России никто, кроме «по россии» (в городе мало, по стране ищут)
                no = lambda k: "ноль" in k or ("пустышка" in k and "по россии" not in k)
                out = {"result": {"HasSearchVolumeResults": [{"Keyword": k, "AllDevices": "NO" if no(k) else "YES"}
                                                             for k in kw]}}
        elif body.get("token") != "y0_TESTTOKEN_abcdefghijklmnop":
            out = {"error_code": 53, "error_str": "Ошибка авторизации"}
        elif m == "CreateNewWordstatReport" and SRV.get("limit"):
            out = {"error_code": 56, "error_str": "Превышен лимит запросов"}
        elif m == "CreateNewWordstatReport":
            if any("плохая" in x for x in p["Phrases"]):
                out = {"error_code": 71, "error_str": "Неправильно задана фраза"}
            elif len(SRV["reports"]) >= 5:
                out = {"error_code": 31, "error_str": "Превышено число отчётов"}
            else:
                rid = SRV["next"]
                SRV["next"] += 1
                SRV["reports"][rid] = p
                SRV["created"].append(p)
                out = {"data": rid}
        elif m == "GetWordstatReportList":
            out = {"data": [{"ReportID": r, "StatusReport": "Done"} for r in SRV["reports"]]}
        elif m == "GetWordstatReport":
            out = {"data": [{"Phrase": x, "GeoID": SRV["reports"][p]["GeoID"],
                             "SearchedWith": [{"Phrase": x + " ещё", "Shows": 1}, {"Phrase": x, "Shows": shows(x)}],
                             "SearchedAlso": [{"Phrase": "дымоход", "Shows": 5}]}
                            for x in SRV["reports"][p]["Phrases"]]}
        elif m == "DeleteWordstatReport":
            SRV["reports"].pop(p, None)
            out = {"data": 1}
        elif m == "CreateNewForecast" and SRV.get("fc_fail"):
            out = {"error_code": 52, "error_str": "Прогноз недоступен"}
        elif m == "CreateNewForecast":
            SRV.setdefault("fc", {})
            if len(SRV["fc"]) >= 5:
                out = {"error_code": 31, "error_str": "Превышено число прогнозов"}
            else:
                fid = SRV["next"]
                SRV["next"] += 1
                SRV["fc"][fid] = p
                SRV.setdefault("fc_sent", []).append(p)
                out = {"data": fid}
        elif m == "GetForecastList":
            out = {"data": [{"ForecastID": f, "StatusForecast": "Done"} for f in SRV.get("fc") or {}]}
        elif m == "GetForecast":
            out = {"data": {"Phrases": [{"Phrase": x, "Shows": shows(x) if x.startswith('"') else 1000, "PremiumMin": 40.5 if "дорогой" not in x else 120,
                                         "PremiumClicks": 50} for x in SRV["fc"][p]["Phrases"] if "без цены" not in x]}}
        elif m == "DeleteForecastReport":
            SRV.get("fc", {}).pop(p, None)
            out = {"data": 1}
        elif m == "GetClientsUnits":
            out = {"data": [{"Login": p[0], "UnitsRest": 31990}]}
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

from seocrawler import direct as D, accounts  # noqa: E402
from seocrawler.semantics import export  # noqa: E402

D.PAUSE = 0
FAST_OK = D.fast_ok
D.fast_ok = lambda: False   # загрузка отчётами Вордстата; прогнозом - в конце теста
_sleep = time.sleep


def start(folder):
    """D.start, когда прошлая загрузка закончилась совсем: её поток успевает выйти не сразу после «done»,
    и D.start в этот миг отвечает «Загрузка останавливается» (тест «отсев не ответил» падал из-за этого)."""
    if D._thread:
        D._thread.join(10)
    return D.start(folder)

D.time = type("T", (), {"sleep": staticmethod(lambda s: _sleep(0.01)), "time": staticmethod(time.time),
                        "strftime": staticmethod(time.strftime)})

# ---- ключ
check(D.save("", "x") == "Вставьте ClientID приложения Директа.", "без ClientID")
check(D.save("9e2a", "коротко") != "", "не ключ принят")
check(D.save("9e2a", "https://oauth.yandex.ru/verification_code#access_token=y0_TESTTOKEN_abcdefghijklmnop&token_type=bearer",
             "t1") == "", "адрес с ключом не понят")
raw = open(os.environ["CLAYLER_ACCOUNTS_FILE"], encoding="utf-8").read()
check("TESTTOKEN" not in raw, "ключ лежит в файле открытым текстом")
st = D.status()
check(st["has_token"] and st["client_id"] == "9e2a" and "client_id=9e2a" in st["auth_url"]
      and "response_type=token" in st["auth_url"], f"состояние: {st}")

# ---- фраза
check(D.phrase("Котёл «Baxi» 24 кВт!") == '"котел baxi 24 квт"', D.phrase("Котёл «Baxi» 24 кВт!"))
check(D.phrase("купить газовый котел для частного дома в уфе недорого") == "", "длинная фраза не пропущена")
check(D.phrase("24 - 32") == "", "фраза без букв")

# ---- проверка
text, err = D.check()
check(not err and f"Проверочный запрос «{D.CHECK_PHRASE}»" in text and " показов в месяц" in text and "31 990" in text, f"проверка: {text} {err}")
check(SRV["created"][-1] == {"Phrases": [f'"{D.CHECK_PHRASE}"'], "GeoID": [225]}, f"проверка, отчёт: {SRV['created'][-1:]}")
check(not SRV["reports"], "отчёт не удалён с сервера")
check(D.used_today() == 1, f"счётчик фраз: {D.used_today()}")

# ---- семантика: тестовая папка проверки
REP = os.path.join(TMP, "отчёты")
folder = os.path.join(REP, "site.ru_2026-10-07_10-00-00")
os.makedirs(folder)


def row(q, score, odd=""):
    return [q, "", "Общий", score, 1, 1, 0, odd, 0, "", 0, 0, 0, 0]


groups = [{"name": "Газовые котлы", "q": [row("газовые котлы", 20), row("газовый котел купить", 15),
                                          row("газовый котел пиво", 30, "возможно, про другое"),
                                          row("газовый котел плохая фраза", 5)] +
           [row(f"газовый котел модель {i}", 10 - i / 100) for i in range(20)]},
          {"name": "Счетчики", "q": [row("счетчик газа", 18), row("счетчик газа g4", 12)]}]
data = {"site": "https://site.ru/", "host": "site.ru", "city": "Уфа", "groups": groups}
json.dump(data, open(os.path.join(folder, export.JSON_NAME), "w", encoding="utf-8"), ensure_ascii=False)

order = D.todo(export.load(folder))
check(order[:4] == ['"газовые котлы"', '"счетчик газа"', '"газовый котел купить"', '"счетчик газа g4"'], f"порядок: {order[:4]}")
check(not any("пиво" in x for x in order), "сомнительный запрос попал в загрузку")

D.DAY_LIMIT = 24   # 1 уже потрачена на проверку: сегодня - 2 отчёта по 10 фраз и остаток дня - отчёт на 3
D._reports = lambda: REP
SRV["created"].clear()
check(start(os.path.basename(folder)) == "", "старт загрузки")
for _ in range(500):
    if D.JOB.get("state") != "running":
        break
    _sleep(0.02)
j = D.job(os.path.basename(folder))
check(j["state"] == "waiting" and j["done"] == 23 and j["total"] == 25 and "Лимит Яндекса на сегодня исчерпан, продолжу"
      in j["msg"], f"лимит на сутки: {j}")
check([len(c["Phrases"]) for c in SRV["created"]] == [10, 10, 3], f"остаток дня: {[len(c['Phrases']) for c in SRV['created']]}")
pr = D.progress(export.load(folder))
check(pr["total"] == 25 and pr["done"] == 23 and pr["days"] == 1 and pr["region"] == "Уфа", f"ход загрузки: {pr}")
check(len(pr["feed"]) == 12 and pr["feed"][0]["freq"] > 0 and pr["feed"][0]["group"], f"лента: {pr['feed'][:1]}")
check({g["name"]: (g["n"], g["done"]) for g in pr["groups"]} == {"Газовые котлы": (23, 21), "Счетчики": (2, 2)},
      f"группы: {pr['groups']}")
# запрос из одного слова не раздувает группу с названием из нескольких слов («консультация» 3 028 у «Консультации
# по стратегии роста», hightime.agency 29.10.2026); группа из одного слова своё слово считает
d2 = {"site": "https://site2.ru/", "host": "site2.ru", "city": "Уфа",
      "groups": [{"name": "Консультация по стратегии", "q": [row("консультация", 9), row("консультация по стратегии", 9)]},
                 {"name": "Кухни", "q": [row("кухни", 9)]}]}
D._store("site2.ru", 172, "Уфа", {D._clean(D.phrase(q)): n for q, n in
                                  (("консультация", 3000), ("консультация по стратегии", 5), ("кухни", 700))})
fq = {g["name"]: g["freq"] for g in D.progress(d2)["groups"]}
check(fq == {"Консультация по стратегии": 5, "Кухни": 700}, f"одно слово в сумме группы: {fq}")
check(all(c["GeoID"] == [172] for c in SRV["created"]), "регион не Уфа")
check(len(SRV["created"][0]["Phrases"]) == 10, "в отчёте не 10 фраз")
check(not SRV["reports"], "отчёты остались на сервере")
D.stop()
_sleep(0.1)
check(D.job()["state"] == "stopped" and accounts._get("direct").get("job") is None, "остановка")

d2 = export.load(folder)
q = {r[0]: r[11] for g in d2["groups"] for r in g["q"]}
check(q["газовые котлы"] == 150, f"частотность в «Спросе»: {q['газовые котлы']}")
check(q["газовый котел пиво"] == 0, "сомнительный получил частотность")
check(d2["direct"]["region"] == "Уфа" and d2["direct"]["n"] == 23, f"источник: {d2.get('direct')}")
check(q.get("газовый котел плохая фраза") == 0, "плохая фраза")
al = D.load("site.ru")["172"].get("also") or {}
check(al.get("газовые котлы", [None])[0] == [["дымоход", 5]] and len(al) == 23, f"что ещё искали при загрузке: {len(al)}")

# ---- Яндекс говорит «лимит» (код 56): днём - ждать завтра и считать день потраченным; сразу после полуночи - через час
D.DAY_LIMIT = 1000
SRV["limit"] = True
accounts._put("direct", day=D._today(), used=500)
check(start(os.path.basename(folder)) == "", "старт при лимите")
for _ in range(500):
    if D.JOB.get("state") == "waiting":
        break
    _sleep(0.02)
j = D.job()
check(j["state"] == "waiting" and "сегодня исчерпан" in j["msg"] and "код 56" in j["detail"] and D.used_today() == 1000,
      f"код 56 днём: {j}")
D.stop()
_sleep(0.1)
accounts._put("direct", day=D._today(), used=0)
start(os.path.basename(folder))
for _ in range(500):
    if D.JOB.get("state") == "waiting":
        break
    _sleep(0.02)
j = D.job()
check(j["state"] == "waiting" and "ещё не обновил" in j["msg"] and D.used_today() == 0, f"код 56 после полуночи: {j}")
D.stop()
_sleep(0.1)
SRV["limit"] = False

# ---- назавтра, после перезапуска окна (resume): догружается только остальное, плохая фраза пропускается,
# остальные из её отчёта - есть
D.DAY_LIMIT = 1000
SRV["created"].clear()
accounts._put("direct", job=os.path.basename(folder))
D.resume()
check(D.JOB.get("folder") == os.path.basename(folder), "после перезапуска загрузка не продолжилась")
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
j = D.job()
check(j["state"] == "done", f"догрузка: {j}")
sent = [x for c in SRV["created"] for x in c["Phrases"]]
check(len(sent) == len(set(sent)) and '"газовые котлы"' not in sent, f"повтор загруженного: {sent}")
d3 = export.load(folder)
q = {r[0]: r[11] for g in d3["groups"] for r in g["q"]}
check(q["газовый котел модель 19"] > 0 and q["газовый котел плохая фраза"] == 0, "после плохой фразы")
check(d3["direct"]["n"] == 25, f"всего с частотностью: {d3['direct']}")
check(D.todo(d3) == [], "остались фразы")

# ---- пустышки проверяются без кавычек; неожиданно крупные - не из одного слова; группы - по спросу
D.EMPTY_CHECK = 2
f2 = os.path.join(REP, "site2.ru_2026-10-07_10-00-00")
os.makedirs(f2)
g2 = [{"name": "Котлы", "q": [row("котел пустышка мало", 30), row("котел пустышка хвосты", 29), row("котел пустышка третья", 28),
                             row("котел большой спрос в уфе", 1), row("север", 2)]},
      {"name": "Малая", "q": [row("малая группа", 2)]}]
json.dump({"site": "https://site2.ru/", "host": "site2.ru", "city": "Уфа", "groups": g2},
          open(os.path.join(f2, export.JSON_NAME), "w", encoding="utf-8"), ensure_ascii=False)
SRV["created"].clear()
start(os.path.basename(f2))
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
check(D.job()["state"] == "done", f"второй сайт: {D.job()}")
broad = [c["Phrases"] for c in SRV["created"] if not c["Phrases"][0].startswith('"')]
check(broad == [["котел пустышка мало", "котел пустышка хвосты"]], f"проверка без кавычек: {broad}")
pr = D.progress(export.load(f2))
check([x["q"] for x in pr["empty"]] == ["котел пустышка мало"] and pr["empty"][0]["broad"] == 3, f"пустышки: {pr['empty']}")
check(pr["empty_wait"] == 0, "кандидаты сверх EMPTY_CHECK")
rf = [x for x in SRV.get("v5", []) if x[2] == [225]]
check(rf and set(rf[-1][1]) == {'"котел пустышка мало"', '"котел пустышка хвосты"'}, f"пустышки по России: {rf}")
D._store("site2.ru", 172, "Уфа", {"котел пустышка мало": 1}, kind="rf")   # по России ищут - не пустышка
pr2 = D.progress(export.load(f2))
check(not pr2["empty"] and [x["q"] for x in pr2["city_small"]] == ["котел пустышка мало"], f"мало в городе: {pr2}")
# без подсказок Яндекса в регионе (только Google, по всей России) - не пустышка
r0 = row("котел пустышка гугл", 40)
r0[4] = 0
check(D._pool({"groups": [{"name": "К", "q": [r0]}]})[0]["котел пустышка гугл"][3] == 0, "только Google")
# «тепловентиляторы тепловентиляторы» - дубль, частотность не грузится
check(D.todo({"host": "site5.ru", "city": "Уфа", "groups": [{"name": "Т", "q": [
    row("тепловентиляторы тепловентиляторы", 9), row("подводка гайка гайка", 8)]}]}) == ['"подводка гайка гайка"'],
      "повтор слова в начале")
check([x["q"] for x in pr["big"]] == ["котел большой спрос в уфе", "малая группа"], f"крупные (без «север»): {pr['big']}")
check([g["name"] for g in pr["groups"]] == ["Котлы", "Малая"] and pr["groups"][0]["freq"] > pr["groups"][1]["freq"],
      f"группы по спросу: {pr['groups']}")

# ---- отсев фраз без показов (hasSearchVolume): сразу 0, в отчёты Вордстата не идут, второй раз не спрашиваются;
# Директ v5 не ответил - грузится как раньше
f4 = os.path.join(REP, "site4.ru_2026-10-07_10-00-00")
os.makedirs(f4)
json.dump({"site": "https://site4.ru/", "host": "site4.ru", "city": "Уфа",
           "groups": [{"name": "Котлы", "q": [row("котел ноль раз", 9), row("котел ноль два", 8), row("котел живой", 7),
                                              row("котел-на-дровах для бани ноль и дачи", 6)]}]},
          open(os.path.join(f4, export.JSON_NAME), "w", encoding="utf-8"), ensure_ascii=False)
SRV["created"].clear()
SRV["v5"] = []
start(os.path.basename(f4))
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
sent = [x for c in SRV["created"] for x in c["Phrases"] if x.startswith('"')]   # без кавычек - проверка пустышек
check(D.job()["state"] == "done" and sent == ['"котел живой"', '"котел-на-дровах для бани ноль и дачи"'],
      f"отсев: {D.job()} {sent}")
v172 = [x for x in SRV["v5"] if x[2] == [172]]   # [225] - проверка кандидатов в пустышки по России
check(len(v172) == 1 and v172[0][0].endswith("/json/v5/keywordsresearch")
      and len(v172[0][1]) == 3, f"отсев, вызов: {SRV['v5']}")   # 8 слов через дефис - не спрашивается
e4 = D.load("site4.ru")["172"]
check(e4["phr"]["котел ноль раз"][0] == 0 and e4["nv"]["котел живой"][0] == 1, f"отсев, сохранено: {e4}")
pr = D.progress(export.load(f4))
check(pr["sieved"] == 2 and pr["done"] == 4 and [x["q"] for x in pr["feed"]][-1] == "котел живой", f"отсев, ход: {pr}")
SRV["v5"] = []
start(os.path.basename(f4))
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
check(not SRV["v5"], "флаг спрошен снова")
f5 = os.path.join(REP, "site5.ru_2026-10-07_10-00-00")
os.makedirs(f5)
json.dump({"site": "https://site5.ru/", "host": "site5.ru", "city": "Уфа",
           "groups": [{"name": "Котлы", "q": [row("котел ноль раз", 9)]}]},
          open(os.path.join(f5, export.JSON_NAME), "w", encoding="utf-8"), ensure_ascii=False)
SRV["v5_fail"] = True
SRV["created"].clear()
start(os.path.basename(f5))
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
SRV["v5_fail"] = False
check(D.job()["state"] == "done" and SRV["created"] == [{"Phrases": ['"котел ноль раз"'], "GeoID": [172]}],
      f"отсев не ответил: {D.job()} {SRV['created']}")

# ---- раздел с тем же словом, что у родителя: запрос без повтора («тепловентиляторы тепловентиляторы»)
from seocrawler.semantics.seeds import query_form  # noqa: E402
check(query_form({"name": "Тепловентиляторы", "parent": "Тепловентиляторы водяные"}) == "тепловентиляторы", "повтор слова")
check(query_form({"name": "Настенные", "parent": "Котлы газовые"}) == "настенные газовые котлы", "прилагательное + родитель")

# ---- прогноз Директа: цена клика в рекламе, по 100 фраз, без кавычек, прогноз удаляется; посчитанное не спрашивается
SRV["fc"] = {77: {}, 78: {}, 79: {}, 80: {}, 81: {}}   # на сервере уже 5 прогнозов, один из них наш (после сбоя)
accounts._put("direct", fc_ids=[77])
qs = [f"котел дорогой {i}" for i in range(150)] + ["котел без цены", "«Котёл» Baxi"]
n, err = D.ads("site3.ru", "Уфа", qs)
check(n == 152 and not err, f"прогноз: {n} {err}")
check([len(x["Phrases"]) for x in SRV["fc_sent"]] == [100, 52] and SRV["fc_sent"][0]["GeoID"] == [172]
      and "котел baxi" in SRV["fc_sent"][1]["Phrases"], f"прогноз, отправлено: {[len(x['Phrases']) for x in SRV['fc_sent']]}")
check(set(SRV["fc"]) == {78, 79, 80, 81} and not accounts._get("direct").get("fc_ids"), f"прогнозы не удалены: {SRV['fc']}")
fc = D.load("site3.ru")["172"]["fc"]
check(fc["котел baxi"][0] == [40.5, 50, 1000] and fc["котел дорогой 3"][0][0] == 120 and fc["котел без цены"][0] == [0, 0, 0],
      f"прогноз, сохранено: {fc.get('котел baxi')}")
SRV["fc_sent"].clear()
check(D.ads("site3.ru", "Уфа", qs + ["новый котел"]) == (1, "") and SRV["fc_sent"][0]["Phrases"] == ["новый котел"],
      "посчитанное спрошено снова")
check(not D.load("site3.ru")["172"].get("phr"), "прогноз попал в частотность")

# ---- частота прогнозом (10.10.2026): фраза в кавычках, по 100, без суточного лимита; прогноз сломался - отчётами
D.fast_ok = FAST_OK
f6 = os.path.join(REP, "site6.ru_2026-10-10_10-00-00")
os.makedirs(f6)
json.dump({"site": "https://site6.ru/", "host": "site6.ru", "city": "Уфа",
           "groups": [{"name": "Котлы", "q": [row(f"котел быстрый {i}", 100 - i / 10) for i in range(150)]}]},
          open(os.path.join(f6, export.JSON_NAME), "w", encoding="utf-8"), ensure_ascii=False)
D.DAY_LIMIT = 24
accounts._put("direct", day=D._today(), used=24)   # лимит отчётов на сегодня уже кончился
SRV["created"].clear()
SRV["fc_sent"] = []
SRV["fc"] = {}
start(os.path.basename(f6))
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
sent = SRV["fc_sent"]
check(D.job()["state"] == "done" and [len(x["Phrases"]) for x in sent] == [100, 50]
      and all(p.startswith('"') for x in sent for p in x["Phrases"]), f"прогнозом: {D.job()} {[len(x['Phrases']) for x in sent]}")
check(not [c for c in SRV["created"] if c["Phrases"][0].startswith('"')] and D.used_today() == 24,
      f"прогноз тратит лимит отчётов: {SRV['created']}, {D.used_today()}")
e6 = D.load("site6.ru")["172"]["phr"]
check(len(e6) == 150 and e6["котел быстрый 7"][0] == shows('"котел быстрый 7"'), f"прогнозом, сохранено: {len(e6)}")
check(D.progress(export.load(f6))["fast"] and D.progress(export.load(f6))["days"] == 0, "ход загрузки: без суточного лимита")
f7 = os.path.join(REP, "site7.ru_2026-10-10_10-00-00")
os.makedirs(f7)
json.dump({"site": "https://site7.ru/", "host": "site7.ru", "city": "Уфа",
           "groups": [{"name": "Котлы", "q": [row("котел запасной", 9)]}]},
          open(os.path.join(f7, export.JSON_NAME), "w", encoding="utf-8"), ensure_ascii=False)
D.DAY_LIMIT = 1000
accounts._put("direct", day=D._today(), used=0)
SRV["fc_fail"] = True
SRV["created"].clear()
start(os.path.basename(f7))
for _ in range(500):
    if D.JOB.get("state") not in ("running",):
        break
    _sleep(0.02)
check(D.job()["state"] == "done" and SRV["created"] == [{"Phrases": ['"котел запасной"'], "GeoID": [172]}]
      and not D.fast_ok(), f"прогноз не ответил - отчётами: {D.job()} {SRV['created']}")
SRV["fc_fail"] = False

srv.shutdown()
shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("ДИРЕКТ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Директ (точная частотность): всё в порядке")
