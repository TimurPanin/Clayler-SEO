"""Автотест таблицы «Запрос → страница → место и клики» в «Где теряем клики» (без сети).
Проверяет seocrawler/lost_clicks: Яндекс (мониторинг запросов Вебмастера) и Google (Search Console) по одному
запросу - одна строка, даже если формы и порядок слов разные; разные страницы в Яндексе и Google отмечены;
группа Семантики привязана, «поиск показывает другую» - если ни Яндекс, ни Google не показывают страницу группы;
в отчёте нет длинного тире. Запуск: py -3 tests/проверить_запрос_страница.py (и из проверить_всё.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import lost_clicks as L  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class Store:
    def __init__(self, meta):
        self.meta = meta

    def get_meta(self, key, default=None):
        return self.meta.get(key, default)


class Ctx:
    pages = [{"url": "https://site.ru/kotly/", "status": 200, "title": "Газовые котлы купить в Москве", "depth": 1,
              "description": "Котлы", "word_count": 600}]
    inl = {}


wm = {"qa_urls": [{"text": "https://site.ru/kotly/", "shows": 140, "clicks": 4, "pos": 6}],
      "qa_queries": [{"text": "газовые котлы купить", "other": "https://site.ru/kotly/", "shows": 100, "clicks": 3, "pos": 6.2},
                     {"text": "котел отопления", "other": "https://www.site.ru/kotly", "shows": 40, "clicks": 1, "pos": 12}]}
gsc = {"pages": [{"url": "https://site.ru/kotly/", "shows": 280, "clicks": 5, "pos": 9}],
       "queries": [{"q": "купить газовый котел", "shows": 200, "clicks": 4, "pos": 8.4},
                   {"q": "котел отопления", "shows": 80, "clicks": 1, "pos": 15}],
       "qp": [{"q": "купить газовый котел", "url": "https://site.ru/kotly/", "shows": 200},
              {"q": "котел отопления", "url": "https://site.ru/blog/kak-vybrat/", "shows": 80}]}
ctx = Ctx()
ctx.store = Store({"webmaster": wm, "gsc": gsc, "start": "https://site.ru/"})
d = L.compute(ctx)
qs = {r["q"]: r for r in d.get("queries") or []}
check(len(qs) == 2, f"две строки (формы слов склеены): {list(qs)}")
a = qs.get("газовые котлы купить") or qs.get("купить газовый котел") or {}
check(a.get("y_pos") == 6.2 and a.get("g_pos") == 8.4 and not a.get("diff"), f"Яндекс и Google в одной строке: {a}")
b = qs.get("котел отопления") or {}
check(b.get("diff") is True, f"разные страницы в Яндексе и Google: {b}")
check(round(b.get("g_shows") or 0) == round(80 * 30 / 28), f"показы Google приведены к месяцу: {b.get('g_shows')}")

groups = {L.qkey("газовый котел купить"): {"name": "Газовые котлы", "page": "/kotly/"},
          L.qkey("котел отопления"): {"name": "Котлы отопления", "page": "/kotly-otopleniya/"}}
L.bind_semantics(d, groups)
check(a.get("group") == "Газовые котлы" and not a.get("group_other"), f"группа, страница та же: {a}")
check(b.get("group") == "Котлы отопления" and b.get("group_other"), f"поиск показывает другую: {b}")
html = L.html_block(d)
check("Запрос → страница → место и клики" in html and "Группа в Семантике" in html, "таблица в отчёте")
check("поиск показывает другую" in html and "разные страницы" in html, "пояснения в отчёте")
check("—" not in html, "длинное тире в отчёте")

d2 = L.compute(ctx)
check("Группа в Семантике" not in L.html_block(d2), "без Семантики колонки группы нет")
ctx.store = Store({"start": "https://site.ru/"})
check(not L.compute(ctx).get("queries"), "без данных поиска таблицы нет")
check("Нет данных" in L.html_block(L.compute(ctx)), "ничего не подключено - «нет данных»")

# всё подключено, но показов и визитов из поиска нет (новый сайт, timurpanin.ru): не «нет данных»
ctx.store = Store({"start": "https://site.ru/", "webmaster": {"host": "https://site.ru/", "qa_urls": []},
                   "gsc": {"site": "https://site.ru/", "pages": []}, "metrika": {"counter": 1, "landing": []}})
html = L.html_block(L.compute(ctx))
check("Нет данных" not in html and "Подключено: Яндекс Вебмастер, Google Search Console, Яндекс Метрика" in html
      and "Не подключено" not in html, f"подключено, но показов нет: {html}")
ctx.store = Store({"start": "https://site.ru/", "gsc": {"site": "https://site.ru/", "pages": []}})
html = L.html_block(L.compute(ctx))
check("Подключено: Google Search Console" in html and "Не подключено: Яндекс Вебмастер, Яндекс Метрика" in html,
      f"часть подключена: {html}")
check(L.html_block(L.compute(ctx), client=True) == "", "клиенту раздел без данных не показывается")
# Вебмастер подключён, но не загрузился (сброс входа у Яндекса): не «показов пока нет», а «не загрузилось»
ctx.store = Store({"start": "https://site.ru/", "webmaster": {"host": "https://site.ru/", "errors": ["qa_urls: 401"]},
                   "gsc": {"site": "https://site.ru/", "pages": []}})
html = L.html_block(L.compute(ctx))
check("Не загрузилось: Яндекс Вебмастер" in html and "Подключено: Google Search Console," in html
      and "Подключено: Яндекс Вебмастер" not in html and "Не подключено: Яндекс Метрика" in html,
      f"не загрузилось: {html}")

# сводка Вебмастера отстаёт: «0 в поиске», а в списке страниц в поиске уже есть главная
from seocrawler import webmaster as W  # noqa: E402
from seocrawler.fmt import esc  # noqa: E402
wh = W.report_html({"host": "https://site.ru/", "fetched": "26.10.2026", "summary": {"searchable_pages_count": 0},
                    "in_search": [{"url": "https://site.ru/"}]}, esc)
check('<b class="big">1</b><span>страниц в поиске Яндекса (по списку' in wh, "сводка Вебмастера с задержкой")
wh = W.report_html({"host": "https://site.ru/", "fetched": "26.10.2026", "summary": {"searchable_pages_count": 40},
                    "in_search": [{"url": "https://site.ru/"}]}, esc)
check('<b class="big">40</b><span>страниц в поиске Яндекса</span>' in wh, "обычная сводка Вебмастера")

if fails:
    print("✗ запрос → страница:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ запрос → страница: Яндекс и Google в одной строке, разные страницы, группа Семантики; "
      "подключено без показов - не «нет данных»; сводка Вебмастера с задержкой")
