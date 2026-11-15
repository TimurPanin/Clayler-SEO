"""Автотест: страницы, ссылки на которые стоят только на закрытой в robots.txt постраничной навигации, а sitemap
на сайте нет (30.10.2026, vsekuhni.ru: Disallow: /*PAGEN, sitemap 404 - часть товаров не видна поисковику, а в
отчёте было только замечание «Адреса, закрытые в robots.txt»). Программа открывает закрытые страницы 2, 3… и
пишет критичную проблему hidden_behind_blocked; ссылки «войти» (закрыты), картинки и уже найденные страницы туда
не попадают; в robots.txt для разработчика правило навигации закомментировано.
Запуск: py -3 тест/проверить_закрытую_навигацию.py (и из проверить_всё.py)."""
import csv
import glob
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
fails = []

TXT = "<p>" + " ".join(f"Выдвижная корзина для кухни номер {i}, цена {i * 10} рублей" for i in range(30)) + "</p>"
LOGIN = '<a href="/login/?backurl=/catalog/&login=yes">Войти</a>'
PAGES = {
    "/": '<a href="/catalog/">Каталог</a><a href="/about/">О нас</a>',
    "/about/": TXT,
    "/catalog/": TXT + '<a href="/prod1/">Товар 1</a><a href="/catalog/?PAGEN_1=2">2</a>' + LOGIN,
    "/catalog/?PAGEN_1=2": TXT + '<a href="/prod1/">Товар 1</a><a href="/prod2/">Товар 2</a>'
                           '<a href="/catalog/?PAGEN_1=3">3</a><a href="/img/big.jpg">фото</a>' + LOGIN,
    "/catalog/?PAGEN_1=3": TXT + '<a href="/prod3/">Товар 3</a><a href="/catalog/?PAGEN_1=2">2</a>',
    "/prod1/": TXT, "/prod2/": TXT, "/prod3/": TXT,
}
SITEMAP = {"on": False}   # второй прогон: sitemap есть, в нём /prod3/ - его поисковик знает
TITLE = "Страницы, которые поисковик не находит: ссылки на них только на закрытых страницах навигации"
ROBOTS = "User-agent: *\nDisallow: /*PAGEN\nDisallow: /login/\n"


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body, ctype = ROBOTS, "text/plain"
        elif self.path == "/sitemap.xml" and SITEMAP["on"]:
            body = (f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f'<url><loc>{B}/</loc></url><url><loc>{B}/prod3/</loc></url></urlset>')
            ctype = "application/xml"
        elif self.path in PAGES:
            body = (f"<!doctype html><html><head><title>Стр {self.path}</title></head><body><h1>Стр {self.path}</h1>"
                    f"{PAGES[self.path]}<a href='/'>Главная</a></body></html>")
            ctype = "text/html; charset=utf-8"
        else:   # sitemap.xml тоже нет
            self.send_response(404)
            self.end_headers()
            return
        b = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{srv.server_address[1]}"


def crawl(*flags):
    """Обход тестового сайта; (папка проверки, журнал) или (None, журнал)."""
    tmp = tempfile.mkdtemp(prefix="clayler-hidden-")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_NO_PROBLEM_SHOTS="1", CLAYLER_REPORTS=tmp)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), B + "/", "--no-open", "--delay", "0",
                        "--no-search-urls", "--no-exposed"] + list(flags), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    folders = [d for d in glob.glob(os.path.join(tmp, "*")) if os.path.isdir(d)]
    if r.returncode != 0 or not folders:
        fails.append(f"обход {flags} не прошёл: " + (r.stdout + r.stderr)[-800:])
        return None, r.stdout
    return folders[0], r.stdout


def rows(f, key):
    p = os.path.join(f, "проблемы", key + ".csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as fh:
        return [[c.replace(B, "") for c in row] for row in list(csv.reader(fh, delimiter=";"))[1:]]


def issue(f):
    """(важность, «что это значит») новой проблемы из проблемы.csv или (None, "")."""
    with open(os.path.join(f, "проблемы.csv"), encoding="utf-8-sig") as fh:
        for x in csv.reader(fh, delimiter=";"):
            if len(x) > 4 and x[2] == TITLE:
                return x[0], x[4]
    return None, ""


H2 = ["/prod2/", "/catalog/?PAGEN_1=2", "Disallow: /*PAGEN"]
H3 = ["/prod3/", "/catalog/?PAGEN_1=3", "Disallow: /*PAGEN"]
try:
    # 1. sitemap нет (404)
    f, log = crawl()
    if f:
        got = sorted(x[:3] for x in rows(f, "hidden_behind_blocked"))
        if got != [H2, H3]:
            fails.append(f"без sitemap: {got}, ждали {[H2, H3]}")
        imp, what = issue(f)
        if imp != "Критично" or "sitemap на сайте нет" not in what:
            fails.append(f"без sitemap: важность {imp!r}, текст {what[:200]!r}")
        rb = glob.glob(os.path.join(f, "для клиента", "*", "robots.txt"))
        txt = open(rb[0], encoding="utf-8").read() if rb else ""
        if "# Disallow: /*PAGEN" not in txt or "Disallow: /login/" not in txt.replace("# Disallow: /login/", ""):
            fails.append(f"robots.txt для разработчика: навигация не открыта или тронуто лишнее: {txt[:400]!r}")
        if "Страниц, ссылки на которые есть только там" not in log:
            fails.append("в журнале проверки нет итога по закрытой навигации")
    # 2. «Не обходить адреса» /prod3/ - его и в проблеме нет (правила как при обходе)
    f, _ = crawl("--skip-mask", "/prod3/")
    if f and sorted(x[:3] for x in rows(f, "hidden_behind_blocked")) != [H2]:
        fails.append(f"с маской /prod3/: {rows(f, 'hidden_behind_blocked')}, ждали только /prod2/")
    # 3. sitemap выключен - проблема есть, но без «sitemap на сайте нет»
    f, _ = crawl("--no-sitemap")
    if f:
        imp, what = issue(f)
        if imp != "Критично" or "sitemap на сайте нет" in what or "не смотрели" not in what:
            fails.append(f"без чтения sitemap: важность {imp!r}, текст {what[:200]!r}")
    # 4. sitemap есть, в нём /prod3/ - поисковик его знает, в проблеме только /prod2/
    SITEMAP["on"] = True
    f, _ = crawl()
    if f:
        got = sorted(x[:3] for x in rows(f, "hidden_behind_blocked"))
        imp, what = issue(f)
        if got != [H2] or "в sitemap их нет" not in what:
            fails.append(f"с sitemap: {got}, текст {what[:200]!r}")
finally:
    srv.shutdown()

if fails:
    print("✗ закрытая навигация без sitemap:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ закрытая навигация без sitemap: товары только на страницах 2, 3… - критичная проблема, «войти» и картинки не в ней, "
      "robots.txt для разработчика открывает навигацию")
