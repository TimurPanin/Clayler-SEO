"""Никаких сырых английских ошибок и JSON в журнале окна (plain_errors.humanize, window/job.py) и «старый расчёт
здоровья» у отчётов до 15.10.2026 (window/reports_list.py).
Было (17.10.2026, «Обновить отчёт» dog-comfort.kz): «Page.goto: net::ERR_CONNECTION_CLOSED at …»,
«<urlopen error _ssl.c:1064: The handshake operation timed out>», JSON «Request had insufficient authentication
scopes» от Google; в «Сравнить с конкурентами» у многих сайтов «здоровье 0%» по старому расчёту.
Запуск: py -3 тест/проверить_понятные_ошибки.py (и из проверить_всё.py)."""
import json
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("CLAYLER_REPORTS", tempfile.mkdtemp(prefix="clayler-plain-"))
from seocrawler.plain_errors import humanize  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


RAW = ("<urlopen", "Page.goto", "net::ERR", "{", "Request had", "_ssl.c", "Unauthorized", "WinError")


def main():
    cases = [
        ("Яндекс Вебмастер: не получилось получить список сайтов - <urlopen error _ssl.c:1064: The handshake "
         "operation timed out>", "нет связи с Яндекс Вебмастером"),
        ('Search Console: не получилось получить список сайтов - Google Search Console ответил 403: { "error": '
         '{ "code": 403, "message": "Request had insufficient authentication scopes.", "status": "PERMISSION_DENIED"',
         "нет доступа к Search Console"),
        ("   https://dog-comfort.kz/aktau/: страница не открылась - Page.goto: net::ERR_CONNECTION_CLOSED at "
         "https://dog-comfort.kz/aktau/", "соединение оборвали"),
        ("Яндекс Метрика: данные не загружены - HTTP Error 401: Unauthorized", "вход истёк"),
        ("Орфография: не проверена - [WinError 10060] timed out", "нет связи"),
    ]
    for line, want in cases:
        out = humanize(line)
        check(want in out, f"нет «{want}»: {out}")
        check(not any(r in out for r in RAW), f"осталась техническая ошибка: {out}")
        check(out.split(" - ")[0] == line.split(" - ")[0], f"начало строки изменилось: {out}")
    for same in ("Traceback (most recent call last):", '  File "x.py", line 3, in <module>', "KeyError: 'x'",
                 "Проверка SSL-сертификатов: система (truststore)", "   Страниц сайта: 5 из 100 | 1.0 адр/с",
                 "Шаг 3 из 4. Обхожу сайт по ссылкам, начиная с главной."):
        check(humanize(same) == same, f"строку без ошибки изменили: {same!r} → {humanize(same)!r}")

    # окно: строка в журнале простыми словами, оригинал - в «Журнал» (Подробнее)
    from seocrawler.window import job as J
    from seocrawler import applog
    got = []
    applog.write = lambda kind, text, site="", detail="": got.append((kind, text, detail))
    j = J.Job()
    j.add(cases[0][0])
    check(j.lines[-1] == humanize(cases[0][0]), f"в окне сырая строка: {j.lines[-1]}")
    check(got and "urlopen error" in got[-1][2], f"оригинал не попал в «Журнал»: {got}")
    j.add("Traceback (most recent call last):")
    j.add("KeyError: 'x'")
    from seocrawler.site_queue import _crash_line
    check(_crash_line(j.lines) == "KeyError: 'x'", "сбой программы перестал находиться по трассировке")

    # маски семантики готовы - жёлтая плашка «готовы», а не красная «Маски не предложились» (gruzoperevozka23.ru)
    from seocrawler.window import events
    pushed = []
    events.push = lambda kind, title, text="", *a, **k: pushed.append((kind, title, text))
    mj = J.Job()
    mj.sites, mj.site, mj.started, mj.out_dir = [], "https://gruzoperevozka23.ru/", 0, ""
    mj.lines = ["Предлагаю маски семантики: gruzoperevozka23.ru_2026-10-17_14-25-23",
                "маски готовы: 18 - главная и меню 17, разделы 1, подразделов и карточек на сайте не нашлось (структура плоская)"]
    events.job_finished(mj, "masks")
    check(pushed and pushed[-1][0] == "warn" and "готовы" in pushed[-1][1] and "Подтвердить" in pushed[-1][2],
          f"готовые маски показаны ошибкой: {pushed}")

    # старый расчёт здоровья: отчёт до 15.10.2026 без hv - пометка; новый (hv) - без неё
    from seocrawler.window import reports_list as R
    base = tempfile.mkdtemp(prefix="clayler-hv-")
    for name, summary, mtime in (("old.ru_2026-10-08", {"health": 0, "pages": 10}, R.HEALTH_V2_AT - 86400),
                                 ("new.ru_2026-10-17", {"health": 0, "pages": 10, "hv": 2}, R.HEALTH_V2_AT + 86400),
                                 ("rebuilt.ru_2026-10-08", {"health": 40, "pages": 10}, R.HEALTH_V2_AT + 3600)):
        d = os.path.join(base, name)
        os.makedirs(d)
        con = sqlite3.connect(os.path.join(d, "crawl.db"))
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO meta VALUES ('summary', ?)", (json.dumps(summary),))
        con.commit()
        con.close()
        open(os.path.join(d, "отчёт.html"), "w").close()
        os.utime(os.path.join(d, "отчёт.html"), (mtime, mtime))
    it = {n: R._read_check(os.path.join(base, n), n) for n in os.listdir(base)}
    check(it["old.ru_2026-10-08"].get("health_old"), "старый отчёт без пометки «старый расчёт здоровья»")
    check(not it["new.ru_2026-10-17"].get("health_old"), "новый отчёт помечен старым расчётом")
    check(not it["rebuilt.ru_2026-10-08"].get("health_old"), "пересобранный после 15.10 отчёт помечен старым")

    # окно «Сравнить с конкурентами»: кнопки внизу, счётчик, клик мимо не теряет выбор
    page = open(os.path.join(ROOT, "seocrawler", "window", "page", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "seocrawler", "window", "page", "app.js"), encoding="utf-8").read()
    check('id="cmpN"' in page and "Нажмите «Сравнить» внизу" in page, "в окне сравнения нет подсказки и счётчика")
    check("cmpPicked" in js and "Чтобы сравнить, нажмите «Сравнить» внизу" in js, "клик мимо окна сравнения теряет выбор")

    if fails:
        print("✗ понятные ошибки:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ понятные ошибки: журнал без сырых ошибок и JSON, оригинал в «Журнале», трассировка не тронута, "
          "старый расчёт здоровья помечен, окно сравнения с кнопкой внизу")


if __name__ == "__main__":
    main()
