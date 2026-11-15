"""Автотест: код 200 ещё не значит, что отдали то, что просили (разбор nabiullin.com).
Тестовые сайты без сети, обход и отчёт:
- сайт на любой адрес отдаёт главную: находка «Сайт на любой адрес отдаёт главную страницу» со всеми копиями, «своих
слов 0»
  и новые заголовки для копий не появляются; вместо robots.txt и sitemap страница - свои находки, а готовый
  robots.txt для разработчика без HTML;
- контроль: настоящие разделы с разным текстом и своя страница «нет такой» с кодом 200 - этой находки нет;
- скрытая служебная ссылка виджета карт - не «так выглядит взлом», а скрытая ссылка на чужой сайт - да;
- ссылка без «/»: `otzyvy` с главной и из блога ведёт на разные адреса - находка; с <base> или `reviews/` у каждого
  товара (в корень не ведёт) - нет.
Запуск: py -3 tests/проверить_любой_адрес.py (и из проверить_всё.py), около минуты."""
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
sys.path.insert(0, ROOT)
from помощь_тестам import issue_rows, quiet_env  # noqa: E402
PORT = 8798
SITE = f"http://127.0.0.1:{PORT}/"
fails = []
MODE = {"any": True}
COPIES = ["/blog/", "/otzyvy", "/services/"]


def check(ok, what):
    if not ok:
        fails.append(what)


TEXT = "настоящий текст страницы про услуги компании и её работу " * 30
MENU = "".join(f'<a href="{u}">раздел</a> ' for u in ("services/", "blog/", "otzyvy"))
WIDGET = ('<div style="display:none"><a href="https://tech.yandex.ru/maps/mapsapi/?from=api-maps">API</a>'
          '<a href="https://chuzhoy-sait.example/">партнёр</a></div>')
HOME = (f'<html><head><base href="/"><title>Главная компании</title><meta name=description content="описание '
        f'главной"></head>'
        f'<body><h1>Главная</h1><p>{TEXT}</p>{MENU}{WIDGET}</body></html>').encode()


def section(path):
    return (f"<html><head><title>Раздел {path}</title><meta name=description content='описание {path}'></head>"
            f"<body><h1>Раздел {path}</h1><p>{path} {TEXT[:300]} {path * 5}</p>{MENU}</body></html>").encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        code, ctype, body = 200, "text/html; charset=utf-8", HOME
        if not MODE["any"]:   # контроль: разделы настоящие, своя страница ошибки с кодом 200
            if self.path == "/robots.txt":
                ctype, body = "text/plain", b"User-agent: *\nDisallow:\n"
            elif self.path.startswith("/sitemap") or self.path.startswith("/wp-sitemap"):
                code, body = 404, b"no"
            elif self.path in COPIES:
                body = section(self.path)
            elif self.path != "/":
                body = b"<html><head><title>Not found</title></head><body><h1>Not found</h1></body></html>"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def crawl(tmp, env):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE, "--no-open", "--delay", "0",
                        "--no-images",
                        "--no-external", "--no-search-urls", "--no-exposed"], env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    found = glob.glob(os.path.join(tmp, "127.0.0.1*"))
    if not found:
        fails.append("обход не создал папку: " + r.stdout[-800:] + r.stderr[-800:])
        return None
    return found[0]


def check_any_address(folder):
    copies = sorted(r["Адрес"].replace(SITE, "/") for r in issue_rows(folder, "any_url_home"))
    check(copies == COPIES, f"копии главной: {copies}")
    check(issue_rows(folder, "robots_html"), "нет находки «вместо robots.txt страница»")
    check(issue_rows(folder, "sitemap_none"), "нет находки «нет sitemap»")
    check(issue_rows(folder, "fake404"), "несуществующая страница должна остаться находкой")
    check(not issue_rows(folder, "thin"), f"«мало своего текста» на копиях: {issue_rows(folder, 'thin')}")
    robots = os.path.join(folder, "для клиента", "файлы для разработчика", "robots.txt")
    with open(robots, encoding="utf-8") as f:
        text = f.read()
    check("<html" not in text.lower() and "User-agent" in text, f"robots.txt для разработчика: {text[:200]}")
    path = os.path.join(folder, "заголовки.csv")
    urls = []
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            urls = [r["Адрес"].replace(SITE, "/") for r in csv.DictReader(f, delimiter=";")]
    check(not set(urls) & set(COPIES), f"заголовки для копий: {urls}")
    hidden = [r["Скрытая ссылка"] for r in issue_rows(folder, "hacked_hidden_links")]
    check(hidden and all("chuzhoy-sait" in h for h in hidden), f"скрытые ссылки: {hidden}")


def check_control(folder):
    check(not issue_rows(folder, "any_url_home"), f"настоящие разделы приняты за копии: {issue_rows(folder, 'any_url_home')}")
    check(not issue_rows(folder, "robots_html"), "настоящий robots.txt принят за страницу")
    check(issue_rows(folder, "sitemap_none"), "sitemap 404: нужна находка «нет sitemap»")
    # главная с <base>, разделы без него: `otzyvy` с главной - /otzyvy, из раздела - /blog/otzyvy. Весь путь: обход,
    # база, отчёт
    rel = {r["Как записана ссылка"]: r for r in issue_rows(folder, "relative_links")}
    check("otzyvy" in rel and "/blog/otzyvy" in rel["otzyvy"]["Куда ещё ведёт"],
          f"запись ведёт на разные адреса: {rel}")


def check_relative_rule():
    from seocrawler.analyze.checks.hacked_links import MAP_WIDGET
    from seocrawler.analyze.checks.relative_links import groups
    check(MAP_WIDGET.match("https://yandex.ru/legal/maps_termsofuse/?lang=ru"),
          "условия карт Яндекса - служебная ссылка виджета")
    check(not MAP_WIDGET.match("https://yandex-maps.chuzhoy-sait.example/"), "чужой сайт со словом maps - не виджет")
    def row(raw, dst, src):
        return {"raw": raw, "dst": "https://s.ru" + dst, "anchor": "Отзывы", "src": "https://s.ru" + src}
    got = groups([row("otzyvy", "/otzyvy", "/"), row("otzyvy", "/blog/otzyvy", "/blog/")])
    check(len(got) == 1 and got[0][3] == ["https://s.ru/blog/otzyvy"] and got[0][4] == "https://s.ru/blog/",
          f"запись ведёт на разные адреса: {got}")
    check(not groups([row("otzyvy", "/otzyvy", "/"), row("otzyvy", "/otzyvy", "/blog/")]), "<base>: везде один адрес")
    check(not groups([row("reviews/", "/p/1/reviews/", "/p/1/"), row("reviews/", "/p/2/reviews/", "/p/2/")]),
          "у каждого товара своя страница отзывов - не ошибка")


def main():
    check_relative_rule()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for any_address, verify in ((True, check_any_address), (False, check_control)):
        MODE["any"] = any_address
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(quiet_env(tmp),
                       CLAYLER_NO_PDF="1",
                       CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            folder = crawl(tmp, env)
            if folder:
                verify(folder)
    srv.shutdown()
    if fails:
        print("✗ любой адрес:\n   " + "\n   ".join(str(x)[:400] for x in fails))
        return 1
    print("✓ любой адрес: копии главной, robots.txt и sitemap вместо файла - страница, виджет карт не взлом, контроль "
          "чистый")
    return 0


if __name__ == "__main__":
    sys.exit(main())
