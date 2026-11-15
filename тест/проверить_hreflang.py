"""Автотест: hreflang (analyze/checks/hreflang.py), постраничная навигация (analyze/checks/pagination.py) и
«Не обходить адреса» по маске (crawl.py --skip-mask). Свой маленький сайт в этом же скрипте.
Запуск: py -3 тест/проверить_hreflang.py"""
import csv
import glob
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seocrawler.analyze.checks.hreflang import code_problem  # noqa: E402
from seocrawler.analyze.checks.pagination import series  # noqa: E402
from seocrawler.crawler.common import mask_to_regex, read_masks  # noqa: E402

PORT = 8813
B = f"http://127.0.0.1:{PORT}"
fails = []


def eq(what, got, want):
    if got != want:
        fails.append(f"{what}: получилось {got!r}, ждали {want!r}")


# ---- без сети
for c in ("ru", "ru-RU", "en-GB", "zh-Hant-TW", "x-default", "es-419"):
    eq("код " + c, code_problem(c), "")
for c in ("ua", "en-UK", "russian", "qq", "ru_RU"):
    if not code_problem(c):
        fails.append(f"код {c} должен быть с ошибкой")
eq("серия ?page", series("https://a.ru/cat/?sort=new&page=3"), ("https://a.ru/cat/?sort=new", 3))
eq("серия PAGEN", series("https://a.ru/cat/?PAGEN_1=2"), ("https://a.ru/cat/", 2))
eq("серия /page/", series("https://a.ru/blog/page/4/"), ("https://a.ru/blog/", 4))
eq("не серия ?p=", series("https://a.ru/?p=123"), (None, None))
eq("маски", read_masks("/filter/\n *?sort=* \n*\n/filter/"), ["/filter/", "*?sort=*"])

# ---- сайт
TXT = lambda k: "<p>" + " ".join(f"Товар номер {k * 100 + i} котёл газовый настенный цена {k * 7 + i} рублей"  # noqa: E731
                                 for i in range(20)) + "</p>"
ALT = lambda own, alts: "".join(f'<link rel="alternate" hreflang="{l}" href="{u}">' for l, u in alts)  # noqa: E731
PAGES = {
    "/": ALT("/", [("ru", "/"), ("en", "/en/"), ("de", "/de/"), ("ua", "/ua/"), ("fr", f"http://localhost:{PORT}/fr/")])
         + '<a href="/cat/">Каталог</a><a href="/filter/red/">Фильтр</a><a href="/cat/?sort=price">Сорт</a>'
         '<a href="/promo/">Акция</a>',
    "/fr/": ALT("/fr/", [("fr", "/fr/")]),   # другой домен, открывается: не «сломана» (oidbearing.ru, 31.10.2026)
    "/promo/": '<link rel="canonical" href="/">' + ALT("/promo/", [("ru", "/")]),   # склеена canonical: не проверяем
    "/en/": ALT("/en/", [("en", "/en/"), ("ru", "/")]),           # взаимно
    "/de/": ALT("/de/", [("de", "/de/")]),                        # нет обратной на /
    "/ua/": ALT("/ua/", [("uk", "/ua/"), ("ru", "/")]),            # код ua на главной - ошибка
    "/cat/": TXT(1) + '<a href="/cat/?page=1">1</a><a href="/cat/?page=2">2</a><a href="/cat/?page=3">3</a>'
             '<a href="/cat/?page=9">9</a>',
    "/cat/?page=1": TXT(1),
    "/cat/?page=2": TXT(2) + '<a href="/filter/blue/">Синий</a>',   # маска - и после «Дообойти»
    "/cat/?page=3": TXT(3),
    "/cat/?page=9": TXT(3),   # номер за концом списка показывает последнюю страницу
    "/filter/red/": "<p>фильтр</p>",
    "/filter/blue/": "<p>фильтр</p>",
    "/cat/?sort=price": "<p>сортировка</p>",
}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        html = f"<!doctype html><html><head><title>Стр {self.path}</title>{body if '<link' in body else ''}</head><body>" \
               f"<h1>{self.path}</h1>{'' if '<link' in body else body}<a href='/'>Главная</a></body></html>"
        b = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    tmp = tempfile.mkdtemp(prefix="clayler-hreflang-")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_NO_PROBLEM_SHOTS="1", CLAYLER_REPORTS=tmp)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), B + "/", "--no-open", "--delay", "0",
                        "--no-sitemap", "--no-search-urls", "--no-exposed", "--skip-mask", "/filter/",
                        "--skip-mask", "*?sort=*"], env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    folders = [d for d in glob.glob(os.path.join(tmp, "*")) if os.path.isdir(d)]
    if r.returncode != 0 or not folders:
        fails.append("обход не прошёл: " + (r.stdout + r.stderr)[-800:])
    else:
        f = folders[0]
        db = sqlite3.connect(os.path.join(f, "crawl.db"))
        skipped = {u[len(B):] for (u,) in db.execute("SELECT url FROM urls WHERE skip_reason LIKE 'Исключён правилом%'")}
        eq("исключены по маске", skipped, {"/filter/red/", "/filter/blue/", "/cat/?sort=price"})
        db.close()

        def rows(key):
            p = os.path.join(f, "проблемы", key + ".csv")
            if not os.path.exists(p):
                return []
            with open(p, encoding="utf-8-sig") as fh:
                return [[c.replace(B, "") for c in row] for row in list(csv.reader(fh, delimiter=";"))[1:]]
        eq("нет обратной", [r[:3] for r in rows("hreflang_no_return")], [["/", "de", "/de/"]])
        eq("плохой код", [r[:2] for r in rows("hreflang_bad_code")], [["/", "ua"]])
        eq("нет себя", [r[0] for r in rows("hreflang_no_self")], [])
        eq("сломанные версии", rows("hreflang_broken"), [])
        ext = sqlite3.connect(os.path.join(f, "crawl.db")).execute(
            "SELECT count(*) FROM links WHERE kind='hreflang' AND dst LIKE 'http://localhost%'").fetchone()[0]
        if not ext:
            fails.append("версия на другом домене не попала в ссылки hreflang - тест ничего не проверяет")
        eq("номер 1", [r[:2] for r in rows("pagination_page1")], [["/cat/?page=1", "/cat/"]])
        eq("одинаковые", [r[:2] for r in rows("pagination_same")], [["/cat/?page=9", "/cat/?page=3"]])
        rep = open(os.path.join(f, "отчёт.html"), encoding="utf-8").read()
        if "Исключены настройками проверки" not in rep or "«/filter/»" not in rep:
            fails.append("в отчёте нет строки про исключённые маски")

    # «Дообойти» (--continue) без масок в форме: маски из начала проверки действуют и дальше (23.10.2026)
    tmp2 = tempfile.mkdtemp(prefix="clayler-hreflang-")
    env2 = dict(env, CLAYLER_REPORTS=tmp2)
    base = [sys.executable, os.path.join(ROOT, "crawl.py"), B + "/", "--no-open", "--delay", "0", "--threads", "1",
            "--no-sitemap", "--no-search-urls", "--no-exposed"]
    subprocess.run(base + ["--max-pages", "2", "--skip-mask", "/filter/", "--skip-mask", "*?sort=*"], env=env2,
                   capture_output=True, timeout=300)
    r2 = subprocess.run(base + ["--continue"], env=env2, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=300)
    folders = [d for d in glob.glob(os.path.join(tmp2, "*")) if os.path.isdir(d)]
    if len(folders) != 1:
        fails.append(f"«Дообойти» создал новую папку вместо продолжения: {folders} {r2.stdout[-300:]}")
    else:
        db = sqlite3.connect(os.path.join(folders[0], "crawl.db"))
        opened = {u[len(B):] for (u,) in db.execute("SELECT url FROM pages")}
        n = db.execute("SELECT count(*) FROM pages").fetchone()[0]
        db.close()
        if n <= 2 or opened & {"/filter/red/", "/filter/blue/", "/cat/?sort=price"}:
            fails.append(f"«Дообойти» открыл адреса по маскам из начала проверки или не продолжил: {sorted(opened)}")
finally:
    srv.shutdown()

if fails:
    print("✗ hreflang, навигация, маски:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ hreflang, постраничная навигация, «Не обходить адреса» по маске")
