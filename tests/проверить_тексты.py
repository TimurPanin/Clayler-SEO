"""Автотест текстов отчёта, которые видит клиент (после замечаний к демо-PDF):
- готовый title не обрезается на полуслове или по первой запятой («Мебель для дома: кухни»);
- короткий H1 («3D-программа») не вытесняет более полное начало title;
- кавычки: текст сайта в «…» с кавычками внутри не даёт «««Электра», Тумба»», "…" становятся „…“;
- пример в совете про почти одинаковые title — с самого сайта, без чужой ниши.
Без сети и без настоящих проверок: выдуманные страницы."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.fmt import quote, balance_quotes, when, when_range  # noqa: E402
from seocrawler.settings import TITLE_LONG  # noqa: E402
from seocrawler.analyze.checks import meta_suggest as M, cannibalization as C  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# 1. Кавычки
check(quote("Тумба") == "«Тумба»", quote("Тумба"))
check(quote("«Электра», Тумба под раковину") == "«„Электра“, Тумба под раковину»", quote("«Электра», Тумба под раковину"))
check(quote('Тумба "Электра" СВ-910') == "«Тумба „Электра“ СВ-910»", quote('Тумба "Электра" СВ-910'))
check(quote("«Фран» — мебель»") .count("«") == 1, quote("«Фран» — мебель»"))

check(balance_quotes("Уголок для цоколя «Диадема»»") == "Уголок для цоколя «Диадема»", balance_quotes("Уголок «Диадема»»"))
check(balance_quotes("«Фран — мебель") == "Фран — мебель", balance_quotes("«Фран — мебель"))
# даты проверки по-нашему, без секунд (в отчёте было «2026-10-28 23:11:00 - 2026-10-28 23:25:12»)
check(when_range("2026-10-28 23:11:00", "2026-10-28 23:25:12") == "28.10.2026 23:11 - 23:25", when_range("2026-10-28 23:11:00", "2026-10-28 23:25:12"))
check(when_range("2026-10-28 23:50:00", "2026-10-29 00:40:01") == "28.10.2026 23:50 - 29.10.2026 00:40", "даты через полночь")
check(when("2026-10-04") == "04.10.2026" and when("") == "", "дата без времени")

# 2. Сокращение перечисления по пунктам, не по первой запятой
LONG = "Мебель для дома: кухни, спальни, кровати, стенки, комоды, детская мебель"
short = M._short(LONG, 60)
check(short == "Мебель для дома: кухни, спальни, кровати, стенки, комоды", f"_short: {short}")
check(list(M._shorter("A, B"))[-1] == "A, B", "_shorter оставляет меньше двух пунктов")
br = M._short("Сборка мебели, установка и монтаж (шкафы, кухни и корпусная мебель) от интернет-магазина Фран", 45)
check("(" not in br and br.startswith("Сборка мебели"), f"_short со скобками: {br}")
col = M._short("Эффективные техники запоминания английских слов: интервальные повторения и контекст", 60)
check(not col.endswith("интервальные"), f"_short после двоеточия: {col}")
check(M._strip_tail("Все внимание – на обивку: сравнение кожаных и тканевых диванов | Фран", "Фран", "")
      == "Все внимание - на обивку: сравнение кожаных и тканевых диванов", "короткая первая часть title")


# 3. Готовые title на выдуманном сайте
class Store:
    path = os.path.join(tempfile.mkdtemp(prefix="clayler-txt-"), "crawl.db")


class Ctx:
    store, issues, html_ok, soft404, home_copies = Store(), [], [], set(), set()


S = "https://mebel.test"
pages = [{"url": S + "/", "depth": 0, "h1_count": 1, "description": "Мебель от производителя.",
          "title": "Мебель для дома: кухни, спальни, кровати, стенки, комоды, детская мебель купить в интернет магазине мебели Фран",
          "h1": "«Фран» — мебель для дома от производителя, детские, гостиные, спальни, кухни, стенки, комоды» | Мебель"},
         {"url": S + "/3d.html", "depth": 1, "h1_count": 1, "description": "Программа расстановки мебели.",
          "title": "3D программа расстановки мебели онлайн бесплатно для вашей квартиры | интернет-магазин Фран",
          "h1": "3D-программа"}]
for i in range(12):  # обычные страницы: общий хвост title — название компании
    pages.append({"url": f"{S}/p{i}.html", "depth": 1, "h1_count": 1, "description": f"Описание страницы номер {i} про мебель.",
                  "title": f"Страница номер {i} про мебель | Фран", "h1": f"Страница {i}"})
ctx = Ctx()
ctx.indexable = pages
M.run(ctx)
by = {r["url"]: r for r in ctx.meta_suggest}
home = (by.get(S + "/") or {}).get("title", "")
check(home and len(home) <= TITLE_LONG and "спальни" in home and not home.endswith(("кухни", ",")),
      f"title главной обрезан: «{home}»")
d3 = (by.get(S + "/3d.html") or {}).get("title", "")
check("расстановки мебели" in d3, f"title /3d.html слишком короткий: «{d3}»")


# 4. Пример в совете про почти одинаковые title — с сайта, кавычки не двоятся
class Ctx2:
    def __init__(self, pages):
        self.indexable, self.added = pages, {}

    def add(self, key, *a, **k):
        self.added[key] = a


tp = [{"url": f"{S}/t{i}", "title": t} for i, t in enumerate(
    ["«Электра», Тумба под раковину, СВ-910 - купить недорого", 'Тумба под раковину "Электра" СВ-910 - купить недорого'])]
c2 = Ctx2(tp)
C.run(c2)
fix = c2.added.get("title_cannibal", ("",) * 5)[4]
check("котл" not in fix and "««" not in fix and "»»" not in fix and "„Электра“" in fix, f"совет с примером: {fix}")

# 4б. Описание из текста страницы: без отзывов, поздравлений, обрывков «…акций:» и не про другое
import zlib  # noqa: E402


def page_text(*lines):
    return {"blocks": zlib.compress("\n".join(lines).encode("utf-8"))}


bad = page_text("Остался очень доволен приобретённой тумбой и сервисом, который был оказан в магазине",
                "Компания поздравляет всех покупателей тумб с Новым годом и Рождеством в этом году",
                "Размер отчислений за тумбы может меняться и зависит от условий действующих акций:",
                "Читать первые книги и делать увлекательные открытия вместе с детьми очень интересно")
check(M._sentence(bad, set(), "Тумбы для обуви") == "", f"описание из отзыва или обрывка: {M._sentence(bad, set(), 'Тумбы для обуви')}")
good = page_text("Тумбы для обуви из ЛДСП и массива подойдут для узкой прихожей и большого коридора")
check(M._sentence(good, set(), "Тумбы для обуви").startswith("Тумбы для обуви из ЛДСП"), "хорошее предложение не взято")

# 5. Excel, Word, PDF для клиента: имена листов по целым словам, без подсказок оператору, дата по-русски
from seocrawler.xlsx_report import _sheet_name  # noqa: E402
from seocrawler.client_report import client_text  # noqa: E402
from seocrawler.audit import _ru_when  # noqa: E402
sn = _sheet_name(1, "Битые ссылки: где именно исправлять", set())
check(len(sn) <= 31 and sn.endswith("исправлять") or sn.endswith("именно"), f"имя листа: {sn}")
sn = _sheet_name(2, "Страницы и файлы с ошибкой 4xx (не найдены)", set())
check(len(sn) <= 31 and not sn.endswith(("(", "ошибкой 4")) and sn.split()[-1] in "Страницы и файлы с ошибкой 4xx".split(),
      f"имя листа обрезано посреди слова: {sn}")
ct = client_text("Порог 100 КБ - как у Screaming Frog. Готово.")
check("Screaming" not in ct, f"client_text: {ct}")
check(_ru_when({"finished_at": "2026-10-04 13:45:05"}) == "04.10.2026", _ru_when({"finished_at": "2026-10-04 13:45:05"}))

# полный список проблемы клиенту: в Excel - только если помещается (не больше 50 000 строк на листе), иначе «по
# запросу», как на самом листе Excel
from seocrawler.xlsx_report import MAX_ISSUE_ROWS, full_list_where  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402
from seocrawler import report as RP  # noqa: E402
check("Excel" in full_list_where(MAX_ISSUE_ROWS) and full_list_where(MAX_ISSUE_ROWS + 1) == "Полный список - по запросу.",
      "фраза о полном списке")
for n, want in ((60_000, "Полный список - по запросу."), (300, "Полный список можно получить таблицей Excel.")):
    big = Issue("4xx", "critical", "Коды ответа", "Страницы и файлы с ошибкой 4xx", "Почему.", "Что сделать.",
                ["Адрес", "Код"], [[f"https://x.ru/{k}", 404] for k in range(n)])
    doc = "".join(RP._issues_html([big], 100, True, None)[0])
    check(want in doc, f"отчёт для клиента, {n} строк: нет «{want}»")

if fails:
    print("✗ тексты отчёта:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ тексты отчёта: готовые title без обрезков, кавычки, пример с сайта, Excel и Word для клиента")
