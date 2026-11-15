"""Автотест запросов из файлов для семантики (semantics/imports.py): Вордстат в Excel, Key Collector в CSV (cp1251, «;»),
выгрузка Вебмастера (показы, клики, позиция), Search Console в Excel с несколькими листами, просто список запросов;
числа с пробелами, операторы Вордстата; запись, «Убрать» и слияние файлов; частотность в строке запроса.
Файлы пишутся во временную папку, «решения семантики» не трогаются."""
import io
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-imp-")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openpyxl import Workbook  # noqa: E402
from seocrawler.semantics import export, imports as I, plan  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def xlsx(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# Вордстат: строка-пояснение сверху, «Фраза» / «Число запросов», операторы
ws = xlsx([("Лист1", [["Результаты по запросу «газовые котлы»"], [], ["Фраза", "Число запросов"],
                       ["газовые котлы", 12345], ["+газовые котлы !в уфе", "1 200"], ["котлы -электрические", 50]])])
rows, kind = I.parse("wordstat.xlsx", ws)
d = {r["q"]: r for r in rows}
check(kind == "freq", f"Вордстат: вид {kind}")
check(d.get("газовые котлы", {}).get("freq") == 12345 and d.get("газовые котлы в уфе", {}).get("freq") == 1200
      and "котлы" in d, f"Вордстат: {d}")

# Key Collector: cp1251, точка с запятой
kc = "Фраза;Частота [YW];Частота \"[!YW]\"\r\nремонт котлов;2 400;800\r\nремонт котла цена;150;40\r\n".encode("cp1251")
rows, kind = I.parse("kc.csv", kc)
d = {r["q"]: r for r in rows}
check(kind == "freq" and d.get("ремонт котлов", {}).get("freq") == 800 and d["ремонт котлов"].get("freq_b") == 2400,
      f"Key Collector: точная частотность, базовая отдельно: {kind} {d}")
# Key Collector с тремя частотностями и Арсёнкин (arsenkin.ru): берётся фраза в кавычках, как у Вордстата через Директ
kc3 = 'Фраза;Базовая частотность [YW];"""Частотность"" [YW]";"""!Частотность"" [YW]"\r\nкотел бакси;900;80;70\r\n'
rows, kind = I.parse("kc3.csv", kc3.encode("cp1251"))
check(rows == [{"q": "котел бакси", "freq": 80, "freq_b": 900}], f"Key Collector, три частотности: {rows}")
ars = 'Запрос\tWS\t"WS"\t"!WS"\nгазовый котел\t5000\t300\t120\n'.encode("utf-8")
rows, kind = I.parse("arsenkin.csv", ars)
check(rows == [{"q": "газовый котел", "freq": 300, "freq_b": 5000}] and I.freq_column("arsenkin.csv", ars) == "в кавычках, столбец «ws»",
      f"Арсёнкин: {rows} {I.freq_column('arsenkin.csv', ars)}")

# Вебмастер: показы, клики, позиция - статистика сайта
wm = "Запрос,Показы,Клики,CTR,Средняя позиция показа\nгазовые котлы,1500,40,2.6%,12.4\nкотел навьен,300,5,1.6%,\"8,5\"\n".encode()
rows, kind = I.parse("webmaster.csv", wm)
d = {r["q"]: r for r in rows}
check(kind == "stats" and d.get("газовые котлы") == {"q": "газовые котлы", "shows": 1500, "clicks": 40, "pos": 12.4}
      and d.get("котел навьен", {}).get("pos") == 8.5, f"Вебмастер: {kind} {d}")

# Search Console: несколько листов, нужный - с запросами
sc = xlsx([("Диаграмма", [["Дата", "Клики"], ["2026-10-01", 3]]),
           ("Запросы", [["Популярные запросы", "Клики", "Показы", "CTR", "Позиция"], ["газовые котлы уфа", 7, 900, "0.8%", 9.1]]),
           ("Страницы", [["Популярные страницы", "Клики", "Показы"], ["https://test.ru/kotly/", 7, 900]])])
rows, kind = I.parse("sc.xlsx", sc)
check(kind == "stats" and rows and rows[0]["q"] == "газовые котлы уфа" and rows[0]["shows"] == 900, f"Search Console: {kind} {rows}")

# просто список
rows, kind = I.parse("list.txt", "котлы бакси\nкотлы аристон\n\n".encode())
check(kind == "list" and [r["q"] for r in rows] == ["котлы бакси", "котлы аристон"], f"список: {kind} {rows}")
try:
    I.parse("x.csv", "1;2\n3;4\n".encode())
    check(False, "файл без запросов должен дать ошибку")
except ValueError:
    pass

# запись, слияние, «Убрать»
I.add_file("www.test.ru", "wordstat.xlsx", ws)
I.add_file("test.ru", "webmaster.csv", wm)
R = I.rows("test.ru")
check(R["газовые котлы"] == {"freq": 12345, "shows": 1500, "clicks": 40, "pos": 12.4}, f"слияние: {R.get('газовые котлы')}")
check([f["name"] for f in I.listing("test.ru")] == ["wordstat.xlsx", "webmaster.csv"], f"список файлов: {I.listing('test.ru')}")
I.add_file("test.ru", "wordstat.xlsx", ws)   # тот же файл ещё раз - замена, не дубль
check(len(I.listing("test.ru")) == 2, "повторный файл задублировался")
I.remove_file("test.ru", "webmaster.csv")
check("shows" not in I.rows("test.ru")["газовые котлы"], "«Убрать» не убрало показы")

# строка запроса в семантика.json: показы из файла, частотность 12-м полем; у группы - спрос в месяц
Q = {"газовые котлы": {"extra": "", "intent": "Покупка", "score": 10, "y": 1, "g": None, "wm": None, "gsc": None,
                       "check": "", "imp": {"freq": 12345, "shows": 1500, "clicks": 40, "pos": 12.4}}}
row = export.to_data({"site": "https://test.ru/", "host": "test.ru", "city": None, "competitors": [], "made": "", "seconds": 0,
                      "wm": False, "gsc": False, "queries": Q, "dropped": [],
                      "groups": [{"name": "Газовые котлы", "todo": "", "prio": 1, "page": "https://test.ru/kotly/", "near": "",
                                  "score": 10, "rivals": {}, "queries": ["газовые котлы"]}]})["groups"][0]["q"][0]
check(row[6] == 1500 and row[8] == 12.4 and row[10] == 40 and row[11] == 12345, f"строка запроса: {row}")
data = plan.enrich({"site": "https://test.ru/", "groups": [{"name": "Газовые котлы", "kind": "page", "page": "https://test.ru/kotly/",
                                                            "rivals": [], "q": [row]}]}, "")
g = data["groups"][0]
check(g.get("freq") == 12345 and g.get("real", {}).get("shows") == 1500, f"группа: {g.get('freq')} {g.get('real')}")

if fails:
    print("✗ запросы из файлов:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ запросы из файлов: Вордстат, Key Collector, Вебмастер, Search Console, список; слияние и «Убрать»")
