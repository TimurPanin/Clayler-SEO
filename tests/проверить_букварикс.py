"""Автотест «Видимость» (semantics/bukvarix.py): запросы сайта и конкурентов из Букварикса. Без сети.
Проверяется: файл «Анализ домена» узнаётся (и не путается с Вордстатом), сайт и город - из имени файла
(msk_site.ru.csv, «(1)» в конце); запросы раскладываются по группам семантики; у группы - по каким запросам
сайт виден (с местом и местом по Вебмастеру) и каких запросов конкурента у него нет; в «Отсеяно» - чужой город,
название конкурента, чужая фирма («ооо …», адрес), длинная фраза; запрос с названием своего сайта не отсеивается;
вопросы - в «Статьи для блога»; хранение и «убрать»; город семантики → регион Букварикса."""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-bx-")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.semantics import bukvarix as B, assign as A  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


HEAD = '﻿"Ключевое слово";"Результатов в Яндексе";"Слов";"Символов";"Частотность Весь мир";"""!Частотность !Весь !мир""";"Позиция в выдаче Яндекса"\n'


def csv_(rows):
    return (HEAD + "".join(f'"{q}";1000;{len(q.split())};{len(q)};{f};{e};{p}\n' for q, f, e, p in rows)).encode("utf-8")


OWN = csv_([("газовый котел бакси 24", 500, 60, 2), ("газмастерсервис уфа официальный сайт", 20, 19, 1),
            ("ооо газмастерсервис", 20, 4, 1), ("счетчик газа g4", 300, 40, 7), ("как выбрать газовый котел", 900, 80, 12),
            ("ремонт газовых котлов в казани", 50, 10, 30),
            ("купить соль для очистки воды в мешках цена 25кг", 30, 5, 9)])
RIVAL = csv_([("газовый котел", 9000, 800, 5), ("газовый котел бакси 24", 500, 60, 4), ("вигаз уфа", 300, 100, 1),
              ("ооо газовик", 40, 10, 2), ("улица менделеева 137", 40, 10, 3), ("счетчик газа купить", 700, 90, 6),
              ("термопара для колонки", 200, 30, 8)])

check(B.detect(OWN), "файл Букварикса не узнан")
check(not B.detect("Фраза\tЧастотность\nгазовый котел\t100\n".encode("utf-8")), "Вордстат принят за Букварикс")
check(B.from_name("msk_gasmasterservis.ru.csv") == ("gasmasterservis.ru", "msk"), "сайт и город из имени файла")
check(B.from_name("ufa_vigas.su (1).csv") == ("vigas.su", "ufa"), "имя файла с «(1)»")
check(B.from_name("запросы.csv") == (None, None), "чужое имя файла")
rows = B.parse_text(OWN.decode("utf-8-sig"))
check(rows[0] == ["газовый котел бакси 24", 500, 60, 2], f"строка файла: {rows[0]}")
check(B.region_of("Уфа") == "ufa" and B.region_of("Москва") == "msk" and B.region_of("Бирск") == "rus", "город → регион")

HOST = "gasmasterservis.ru"
info = B.add_file(HOST, "ufa_gasmasterservis.ru.csv", OWN)
check(info["domain"] == HOST and info["region"] == "ufa" and info["n"] == 7 and "ваш сайт" in info["label"], f"свой файл: {info}")
info = B.add_file(HOST, "ufa_vigas.su.csv", RIVAL)
check(info["domain"] == "vigas.su", f"файл конкурента: {info}")
B.add_file(HOST, "msk_other.ru.csv", csv_([("газовый котел", 9000, 800, 9)]))
B.remove(HOST, "other.ru")
check([d["domain"] for d in B.listing(HOST)] == [HOST, "vigas.su"], f"список доменов: {B.listing(HOST)}")


def g(name, qs, page="", kind="page"):
    return {"name": name, "page": page, "kind": kind,
            "q": [[q, "", "Общий", 5, 0, 0, 0, "", 0, "", 0, 0, wm, 0] for q, wm in qs]}


data = {"host": HOST, "city": "Уфа", "competitors": ["vigas.su"], "groups": [
    g("Газовые котлы", [("газовые котлы", 0), ("газовый котел купить", 0), ("котел газовый настенный", 0),
                        ("газовый котел бакси 24", 3.4)], "https://gasmasterservis.ru/kotly/"),
    g("Счётчики газа", [("счетчики газа", 0), ("счетчик газа купить", 0), ("газовый счетчик g4", 0)],
      "https://gasmasterservis.ru/schetchiki/"),
    g("Термопары", [("термопара", 0), ("термопара для котла", 0)], "", "create")]}
v = B.build(data, HOST)
G = {x["name"]: x for x in v["groups"]}
kot = G.get("Газовые котлы") or {}
check([r["q"] for r in kot.get("mine", [])] == ["газовый котел бакси 24"], f"виден в «Газовые котлы»: {kot.get('mine')}")
check(kot.get("mine") and kot["mine"][0]["mine"] == 2 and kot["mine"][0]["wm"] == 3.4 and kot["mine"][0]["rivals"] == {"vigas.su": 4},
      "место, место по Вебмастеру и место конкурента")
check([r["q"] for r in kot.get("miss", [])] == ["газовый котел"], f"нет у нас в «Газовые котлы»: {kot.get('miss')}")
check(kot.get("demand") == 800, "спрос того, чего нет, - по «!частотности»")
check([r["q"] for r in (G.get("Счётчики газа") or {}).get("mine", [])] == ["счетчик газа g4"], "свой счётчик виден")
check([r["q"] for r in (G.get("Счётчики газа") or {}).get("miss", [])] == ["счетчик газа купить"], "счётчик конкурента")
check([r["q"] for r in (G.get("Термопары") or {}).get("miss", [])] == ["термопара для колонки"], "термопара конкурента")
art = G.get(A.ARTICLES) or {}
check("как выбрать газовый котел" in [r["q"] for r in art.get("mine", [])], "вопрос - в «Статьи для блога»")
why = {r["q"]: r["why"] for r in v["dropped"]}
check(why.get("вигаз уфа") == "название конкурента", f"название конкурента: {why.get('вигаз уфа')}")
check(why.get("ооо газовик") == "чужая фирма или адрес", f"чужая фирма: {why.get('ооо газовик')}")
check(why.get("улица менделеева 137") == "чужая фирма или адрес", "адрес")
check((why.get("ремонт газовых котлов в казани") or "").startswith("другой город"), "другой город")
check("ооо газмастерсервис" not in why and "газмастерсервис уфа официальный сайт" not in why, f"свой бренд отсеян: {why}")
check("купить соль для очистки воды в мешках цена 25кг" not in why, "9 слов - ещё запрос")
check(v["total"]["mine"] == 7 and v["total"]["rivals"] == 1, f"итоги: {v['total']}")
check(not any("—" in x for x in (B.NOTE, info["label"])), "длинное тире в тексте")
from seocrawler.semantics import export as SX  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
xp = os.path.join(TMP, "семантика.xlsx")
SX.write_xlsx(xp, {"site": "https://" + HOST + "/", "city": "Уфа", "competitors": ["vigas.su"], "made": "06.10.2026",
                   "queries": {}, "groups": [], "dropped": [], "wm": False, "gsc": False, "geo": None, "cannibal": []},
              visibility=v)
wb = load_workbook(xp, read_only=True)
check("Видимость" in wb.sheetnames and "Видимость - запросы" in wb.sheetnames, f"листы Excel: {wb.sheetnames}")
gr = {r[0]: r for r in wb["Видимость"].iter_rows(min_row=2, values_only=True) if r[0]}
check(gr.get("Газовые котлы", [None] * 8)[3:7] == (1, 1, 1, 800), f"Excel, группа: {gr.get('Газовые котлы')}")
qr = {r[0]: r for r in wb["Видимость - запросы"].iter_rows(min_row=2, values_only=True)}
check(qr.get("газовый котел бакси 24", [None] * 6)[2:6] == ("виден", 2, 3.4, "vigas.su - 4"), f"Excel, запрос: {qr.get('газовый котел бакси 24')}")
check(qr.get("вигаз уфа", [None, ""])[1] == "Отсеяно: название конкурента", "Excel: отсеянное")
check(any("ваш сайт" in str(r[1]) for r in wb["Видимость"].iter_rows(values_only=True)), "Excel: что загружено")
wb.close()
empty = B.build(dict(data, host="nobody.ru"), "nobody.ru")
check(empty["domains"] == [] and empty["region"] == "ufa", "пустой сайт")

# колонка «В Яндексе» в «Запрос → страница»: по номеру группы [запросов, в десятке], откуда и от какого числа;
# группа без своих запросов - нет в списке («не виден»); свой сайт не загружен - None («нет данных», а не «не виден»)
import json  # noqa: E402
before = json.dumps(data, ensure_ascii=False, sort_keys=True)
vis = B.visibility(data, HOST)
check(json.dumps(data, ensure_ascii=False, sort_keys=True) == before, "видимость поменяла семантику")
check(vis and vis["groups"] == {0: [1, 1], 1: [1, 1]}, f"«В Яндексе» по группам: {vis and vis['groups']}")
check(vis and vis["region"] == "Уфа" and len(vis["at"]) == 10 and "файл" in vis["src"], f"«В Яндексе»: откуда и когда: {vis}")
check(B.visibility(dict(data, host="nobody.ru"), "nobody.ru") is None, "без Букварикса - не «не виден»")
B.add_file("rival-only.ru", "ufa_vigas.su.csv", RIVAL)
check(B.visibility(dict(data, host="rival-only.ru"), "rival-only.ru") is None, "загружен только конкурент - не «не виден»")
from seocrawler.semantics.demand import when  # noqa: E402
check(when(["08.10.2026", "07.10.2026", "", "08.10.2026"]) == "с 07.10.2026 по 08.10.2026" and when(["07.10.2026"]) == "07.10.2026"
      and when([]) == "", "даты загрузки в подписи «откуда цифры»")

# быстрые победы: 4-15 место, страница есть, спрос не меньше 10; без Директа - частота по России с пометкой
qk = v["quick"]
check([(r["q"], r["pos"], r["freq"], r["fsrc"], r["gain"]) for r in qk["rows"]] == [("счетчик газа g4", 7, 40, "ru", 3)],
      f"быстрые победы без Директа: {qk['rows']}")
from seocrawler import direct as DR  # noqa: E402
DR._store(HOST, 172, "Уфа", {"счетчик газа g4": 200, "газовый счетчик g4": 50, "газовый котел": 16, "вигаз уфа": 2,
                             "счетчик газа купить": 2, "термопара для колонки": 1, "как выбрать газовый котел": 2})
data["groups"][1]["q"][2][12] = 9   # место по Вебмастеру - и без Букварикса
qk = B.build(data, HOST)["quick"]
got = {r["q"]: (r["pos"], r["psrc"], r["freq"], r["fsrc"], r["now"], r["gain"]) for r in qk["rows"]}
check(got == {"счетчик газа g4": (7, "Букварикс", 200, "city", 7, 13), "газовый счетчик g4": (9, "Вебмастер", 50, "city", 1, 4)},
      f"быстрые победы с частотой по городу: {got}")
check(qk["gain"] == 17 and [g["name"] for g in qk["groups"]] == ["Счётчики газа"] and abs(qk["ratio"] - 2 / 80) < 1e-9,
      f"быстрые победы, итог: {qk['gain']}, {qk['ratio']}")
check(qk["ads"]["money"] == 0 and "счетчик газа g4" in qk["ads"]["want"] and qk["ads"]["want"][0] == "счетчик газа g4",
      f"реклама до прогноза: {qk['ads']}")
DR._store(HOST, 172, "Уфа", {"счетчик газа g4": [40, 50, 900], "газовый счетчик g4": [0, 0, 0]}, kind="fc")
qk = B.build(data, HOST)["quick"]
ad = {r["q"]: (r["now"], r["cpc"], r["money"]) for r in qk["ads"]["rows"]}
check(ad == {"счетчик газа g4": (7, 40, 280)} and qk["ads"]["money"] == 280 and qk["ads"]["visitors"] == 7,
      f"стоимость в рекламе: {ad}, {qk['ads']['money']}")
check(qk["rows"][0]["gmoney"] == 520 and qk["groups"][0]["gmoney"] == 520 and "счетчик газа g4" not in qk["ads"]["want"]
      and "газовый счетчик g4" not in qk["ads"]["want"], f"быстрые победы в рублях: {qk['rows'][0]}")
DR._store("nobody.ru", 172, "Уфа", {"газовый счетчик g4": 50})
check(B.build(dict(data, host="nobody.ru"), "nobody.ru")["quick"]["rows"][0]["q"] == "газовый счетчик g4",
      "быстрые победы по Вебмастеру без Букварикса")
SX.write_xlsx(xp, {"site": "https://" + HOST + "/", "city": "Уфа", "competitors": [], "made": "06.10.2026",
                   "queries": {}, "groups": [], "dropped": [], "wm": False, "gsc": False, "geo": None, "cannibal": []},
              visibility=B.build(data, HOST))
wb = load_workbook(xp, read_only=True)
qw = [r for r in wb["Быстрые победы"].iter_rows(min_row=2, values_only=True) if r[2]] if "Быстрые победы" in wb.sheetnames else []
check([r[2:] for r in qw] == [("счетчик газа g4", 7, "Букварикс", 200, "по городу", 7, 13, 520),
                              ("газовый счетчик g4", 9, "Вебмастер", 50, "по городу", 1, 4, None)], f"Excel, быстрые победы: {qw}")
aw = [r for r in wb["Стоимость в рекламе"].iter_rows(min_row=2, values_only=True) if r[0]] if "Стоимость в рекламе" in wb.sheetnames else []
check(aw[:1] == [("счетчик газа g4", "Счётчики газа", 7, 200, "по городу", 7, 40, 280)], f"Excel, стоимость в рекламе: {aw}")
wb.close()
check("—" not in B.QUICK_NOTE, "длинное тире в быстрых победах")

if fails:
    print("БУКВАРИКС: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Букварикс (видимость): всё в порядке")
