"""Автотест: смена сайта на странице «Семантика» (16.10.2026, по замечанию пользователя: на franmeb.ru было видно
семантику gasprof - дату, город, конкурента gigas.su, «ТЗ копирайтеру · 137»).
Причина была в гонке: при открытии страницы грузилась семантика первого сайта, человек успевал выбрать другой,
и ответ про первый сайт приходил позже и рисовался поверх. Проверяется в настоящем браузере (Chromium) на тестовой
копии окна: семантика сайта А нарочно отвечает медленно, сразу выбирается сайт Б без семантики - от А ничего не
должно остаться; потом А открывается как обычно. И блок «Маски и стоп-слова» свёрнут, пока человек его не
развернёт, и это запоминается по сайту.
Запуск: py -3 тест/проверить_смену_сайта_семантики.py (и из проверить_всё.py). Без playwright - пропускается."""
import json
import os
import sys
import tempfile
import threading
import time

TMP = tempfile.mkdtemp(prefix="clayler-semsite-")
# своя папка «данные»: журнал программы (выбор сайта, развёрнутые блоки) пишется туда, а не в ваш (30.10.2026)
os.environ.update(CLAYLER_DATA_DIR=os.path.join(TMP, "данные"), CLAYLER_DECISIONS_DIR=os.path.join(TMP, "решения"), CLAYLER_DICTS_FILE=os.path.join(TMP, "словари.json"),
                  CLAYLER_DICT_FILE=os.path.join(TMP, "словарь.json"), CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("✓ смена сайта в «Семантике»: пропущено - нет playwright")
    sys.exit(0)
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import build, export as SX  # noqa: E402
import seocrawler.window as W  # noqa: E402
from seocrawler.window import reports_list as RL, semdec, server  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


REPORTS = os.path.join(TMP, "отчёты")
os.makedirs(REPORTS)
for m in (W, RL, semdec, server):
    m.REPORTS = REPORTS


def make(folder, base, menu):
    os.makedirs(folder)
    st = Store(os.path.join(folder, "crawl.db"))
    st.set_meta("start", base + "/")
    st.set_meta("started_at", "2026-10-15 10:00:00")
    st.set_meta("finished_at", "2026-10-15 10:05:00")
    st.set_meta("summary", {"pages": 10, "health": 90})
    pages = [base + "/"] + [u for u, _ in menu]
    for u in pages:
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1,
                      "title": "Газовые котлы в Уфе", "h1": "Газовые котлы", "word_count": 300})
    for src in pages:
        st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a in menu])
    st.commit()
    st.db.close()
    with open(os.path.join(folder, "отчёт.html"), "w", encoding="utf-8") as f:
        f.write("<html></html>")


A = os.path.join(REPORTS, "own.ru_2026-10-15_10-00-00")
Bf = os.path.join(REPORTS, "two.ru_2026-10-15_11-00-00")
make(A, "https://own.ru", [("https://own.ru/kotly/", "Газовые котлы"), ("https://own.ru/zapchasti/", "Запчасти")])
make(Bf, "https://two.ru", [("https://two.ru/kotly/", "Котлы")])
now = time.time()
SUG = {"газовые котлы": ["газовые котлы", "газовые котлы цены"], "запчасти": ["запчасти для котлов"]}
with open(os.path.join(A, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump({f"{e}|{r}|{ph}": {"s": lst, "t": now} for ph, lst in SUG.items() for e, r in (("yandex", "172"), ("google", "ru"))},
              f, ensure_ascii=False)
sem = build(A, log=lambda *a: None, offline=True, region="Уфа", rival_hosts=())
sem["light"] = ["rival.ru"]   # конкурент по адресу - у сайта Б его быть не должно
SX.write_json(os.path.join(A, SX.JSON_NAME), sem)

# семантика сайта А отвечает медленно: так же, как большая семантика gasprof
SLOW = {"on": True}
_load = semdec.load_semantics


def slow_load(folder):
    if SLOW["on"] and os.path.basename(folder or "") == os.path.basename(A):
        time.sleep(2.5)
    return _load(folder)


semdec.load_semantics = slow_load
from http.server import ThreadingHTTPServer  # noqa: E402
srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
srv.handle_error = lambda *a: None   # браузер закрылся посреди ответа - не ошибка теста
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"

with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 1200, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/semantics?f=" + os.path.basename(A))
    pg.wait_for_function("document.getElementById('semSite').options.length >= 2")
    pg.wait_for_timeout(300)       # семантика А ещё грузится
    pg.select_option("#semSite", "two.ru")
    pg.wait_for_timeout(4500)      # ответ про А уже пришёл
    st = pg.evaluate("""() => ({meta: document.getElementById('semMeta').innerText,
        view: document.getElementById('semView').hidden, tz: document.getElementById('semTz').hidden,
        riv: [...document.querySelectorAll('#semRivList input:checked')].length, urls: document.getElementById('semRivUrls').value,
        deep: document.getElementById('semDeep').checked, mk: document.getElementById('mkBox').open,
        crumb: [...document.querySelectorAll('.site-crumb')].map(x => x.textContent).join()})""")
    check("ещё не собрана" in st["meta"], f"у сайта без семантики видна чужая шапка: {st['meta']!r}")
    check(st["view"] and st["tz"], "у сайта без семантики видны группы или «ТЗ копирайтеру» другого сайта")
    check(not st["riv"] and not st["urls"] and not st["deep"], f"у сайта без семантики отмечены чужие конкуренты: {st}")
    check(not st["mk"], "«Маски и стоп-слова» развёрнуты, хотя их никто не разворачивал")
    check("two.ru" in st["crumb"], f"в крошках не тот сайт: {st['crumb']}")
    # А открывается как обычно, с его конкурентом по адресу
    pg.select_option("#semSite", "own.ru")
    pg.wait_for_function("document.getElementById('semMeta').innerText.includes('Собрано')", timeout=15000)
    st = pg.evaluate("""() => ({view: document.getElementById('semView').hidden, urls: document.getElementById('semRivUrls').value,
        mk: document.getElementById('mkBox').open})""")
    check(not st["view"] and st["urls"] == "rival.ru", f"семантика сайта А не открылась как раньше: {st}")
    check(not st["mk"], "«Маски и стоп-слова» развёрнуты при открытии сайта")
    # развернул на А - на Б свёрнуто, на А снова развёрнуто
    pg.click("#mkBox > summary")
    pg.wait_for_timeout(200)
    pg.select_option("#semSite", "two.ru")
    pg.wait_for_timeout(1500)
    on_b = pg.evaluate("document.getElementById('mkBox').open")
    pg.select_option("#semSite", "own.ru")
    pg.wait_for_timeout(500)
    on_a = pg.evaluate("document.getElementById('mkBox').open")
    check(not on_b and on_a, f"«Маски и стоп-слова»: развёрнуто на сайте А - на Б {on_b}, снова на А {on_a}")
    check(not errs, f"ошибки в странице: {errs}")
    br.close()
srv.shutdown()

from seocrawler import applog, paths  # noqa: E402
jp = applog.path()   # отдельно - в TMP, из проверить_всё.py - в его временную папку (CLAYLER_REPORTS)
check(not os.path.abspath(jp).startswith(os.path.abspath(paths.APP) + os.sep), f"журнал программы пишется в папку программы: {jp}")
try:
    with open(jp, encoding="utf-8") as f:
        check("two.ru" in f.read(), "выбор сайта не попал во временный журнал программы")
except OSError:
    check(False, f"временного журнала программы нет: {jp}")

if fails:
    print("✗ смена сайта в «Семантике»:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ смена сайта в «Семантике»: от прошлого сайта ничего не остаётся, свои конкуренты, маски свёрнуты и запоминаются по сайту")
