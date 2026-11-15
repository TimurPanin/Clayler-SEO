"""Автотест: раздел «Что не проверено и почему» (seocrawler/coverage.py) - фильтры, метки, robots.txt, лимит,
ошибки, вход, фото с других сайтов, страницы из поиска; тексты без служебных слов.
Запуск: py -3 тест/проверить_непроверенное.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seocrawler import coverage  # noqa: E402
from seocrawler.client_report import leftovers  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

fails = []


def check(cond, text):
    if not cond:
        fails.append(text)


def make(tmp, name, left=0, search=None):
    st = Store(os.path.join(tmp, name + ".db"))
    S = "https://s.ru/"
    rows = [(S + "f1?a=1&b=2&c=3&d=4", "skipped", "Больше 3 параметров в URL", 1, "page"),
            (S + "f2?a=1&b=2&c=3&d=4", "skipped", "Больше 3 параметров в URL", 1, "page"),
            (S + "private/1", "skipped", "Закрыт в robots.txt (Disallow: /private/)", 1, "page"),
            (S + "trap/trap/trap/", "skipped", "Повторяющийся путь (ловушка)", 1, "page"),
            (S + "img.jpg", "skipped", "Закрыт в robots.txt (Disallow: /img)", 1, "resource"),  # файл - своей строкой
            ("https://cdn.ru/1.jpg", "skipped", "Фото или файл с другого сайта (cdn.ru): проверены первые 1 000", 0,
             "resource"),
            (S + "err", "done", None, 1, "page"), (S + "lk", "done", None, 1, "page")]
    rows += [(S + f"q{i}", "queued", None, 1, "page") for i in range(left)]   # остаток очереди - из самих адресов
    for u, state, why, internal, kind in rows:
        st.enqueue(u, 1, internal, kind, S, state, why)
    st.save_page({"url": S + "err", "status": 0, "error": "Нет ответа"})
    st.save_page({"url": S + "lk", "status": 403})
    st.add_param_links([(S, S + "?utm_source=x", S, "utm_source"), (S, S + "?yclid=1", S, "yclid")])
    st.set_meta("config", {"max_pages": 100, "max_params": 3, "max_depth": 50})
    st.set_meta("max_pages", 100)
    st.set_meta("pages_left_in_queue", left)
    if search:
        st.set_meta("search_urls", search)
    st.commit()
    return st


tmp = tempfile.mkdtemp(prefix="clayler-cov-")
st = make(tmp, "a", left=5, search={"complete": True, "urls": {}, "sources": {
    "yandex": {"state": "ok", "n": 12}, "google": {"state": "no_access", "n": 0}}})
cov = coverage.collect(st, {"pages": 100, "checked": 300})
got = {r["what"]: r["n"] for r in cov["rows"]}
want = {"Не успели проверить: набран лимит 100 страниц": 5, "Адреса фильтров и сортировок каталога": 2,
        "Ссылки с метками (utm, yclid) и лишними параметрами": 2,
        "Закрыто правилами сайта для поисковых роботов (robots.txt)": 1, "Адреса-ловушки": 1,
        "Картинки и файлы, закрытые в robots.txt": 1,
        "Не открылись: сервер не ответил или выдал ошибку": 1, "Закрыты входом или паролем (код 401 или 403)": 1,
        "Фото и файлы с других сайтов - проверены выборочно": 1, "Страницы из поиска Яндекса сверены с сайтом": 12,
        "Страницы из поиска Google не сверялись": None}
for k, v in want.items():
    check(got.get(k, "нет") == v, f"«{k}»: {got.get(k, 'нет строки')} (ждали {v})")
check(not cov["all_done"] and "осталось непроверенным" in coverage.intro(cov), "при лимите - «осталось непроверенным»")
check(any("Нет доступа к сайту в Google Search Console" in r["why"] for r in cov["rows"]), "пометка «нет доступа»")

html = coverage.html_block(cov)
check("Что не проверено и почему" in html and "1 000" in html, "раздел в HTML")
check(not leftovers(html), f"служебные слова в тексте: {leftovers(html)}")
check("—" not in html, "длинное тире в тексте")
from seocrawler.audit import _para, _run  # noqa: E402
check(any("Что не проверено" in p for p in coverage.docx_paras(cov, _para, _run)), "раздел в Word")
check(len(coverage.xlsx_rows(cov)) == len(cov["rows"]), "строки для Excel")

# сайт целиком, без лимита и ошибок: «проверено всё»
st2 = make(tmp, "b")
st2.db.execute("DELETE FROM pages")
st2.commit()
cov2 = coverage.collect(st2, {"pages": 3, "checked": 9})
check(cov2["all_done"] and "Проверено всё, что можно было открыть" in coverage.intro(cov2), "«проверено всё»")
check(coverage.intro(cov2).startswith("Проверено 3 страницы сайта"), f"число страниц: {coverage.intro(cov2)}")

if fails:
    print("✗ «Что не проверено и почему»:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ «Что не проверено и почему»: фильтры, метки, robots.txt, лимит, ошибки, вход, страницы из поиска")
