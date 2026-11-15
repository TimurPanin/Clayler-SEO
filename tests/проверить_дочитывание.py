"""Автотест: то, что обход не открыл или не сохранил, не пропадает молча (seocrawler/reread.py, разбор thehome.ru
06.11.2026).
Тестовый сайт без сети, проверка обходом и отчётом:
- редиректы на адреса, закрытые в robots.txt: конец с 404 - в «Редирект ведёт на ошибку», рабочий - в новом пункте
  «Редирект ведёт на страницу, закрытую в robots.txt», у временных редиректов колонка «Код в конце»;
- адрес из sitemap без ссылок: пустая страница «Элемент не найден» - в «Страница не найдена», а не в рабочих сиротах и
не в
  «Нет title», «Нет H1»; живая страница остаётся сиротой, а без H1 попадает в «Нет H1»;
- готовая проверка без текста страниц (как старые базы): текст дочитывается при сборке отчёта, результат тот же;
- остаток шаблона показан с окружающим текстом и подписью рядом, один кусок - один раз.
Проверено на коде до правки (e7f6ddd): падает. Запуск: py -3 tests/проверить_дочитывание.py, около минуты."""
import glob
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from помощь_тестам import issue_rows, quiet_env  # noqa: E402
PORT = 8797
SITE = f"http://127.0.0.1:{PORT}/"
SITEMAP = f"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{SITE}</loc></url><url><loc>{SITE}p/dead/</loc></url>
<url><loc>{SITE}p/alive/</loc></url><url><loc>{SITE}p/noh1/</loc></url></urlset>""".encode()
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def page(title, h1, body):
    return (f"<html><head><title>{title}</title><meta name=description content='описание'></head><body>"
            + (f"<h1>{h1}</h1>" if h1 else "") + f"<p>{body}</p></body></html>").encode()


TEXT = "текст настоящей страницы сайта " * 40
ROUTES = {
    "/": page("Главная страница сайта", "Главная", TEXT + "".join(
        f'<a href="{u}">ссылка</a> ' for u in ("/r/temp-dead/", "/r/perm-dead/", "/r/temp-ok/", "/r/chain/"))),
    "/closed/ok/": page("Закрытая рабочая", "Закрытая", TEXT),
    "/p/dead/": page("", "", TEXT[:200] + "</p><div>Элемент не найден</div><p>"),
    "/p/alive/": page("Настоящий товар из sitemap", "Настоящий товар", TEXT),
    "/p/noh1/": page("Товар без заголовка на странице", "", TEXT),
}
REDIRECTS = {"/r/temp-dead/": (302, "/closed/dead/"), "/r/perm-dead/": (301, "/closed/dead/"),
             "/r/temp-ok/": (302, "/closed/ok/"), "/r/chain/": (301, "/closed/next/"),
             "/closed/next/": (302, "/closed/dead/")}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", location=""):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path
        if p == "/robots.txt":
            return self.send(200, f"User-agent: *\nDisallow: /closed/\nSitemap: {SITE}sitemap.xml\n".encode(),
                             "text/plain")
        if p == "/sitemap.xml":
            return self.send(200, SITEMAP, "application/xml")
        if p in REDIRECTS:
            return self.send(REDIRECTS[p][0], location=REDIRECTS[p][1])
        return self.send(200, ROUTES[p]) if p in ROUTES else self.send(404, page("Нет", "Нет", "нет страницы"))


def adr(folder, key):
    return sorted(r["Адрес"].replace(SITE, "/") for r in issue_rows(folder, key))


def check_report(folder, when):
    temp = {r["Адрес"].replace(SITE, "/"): r.get("Код в конце") for r in issue_rows(folder, "redirect_temp")}
    check(temp.get("/r/temp-dead/") == "404, закрыт в robots.txt", f"{when}: временный редирект, код в конце: {temp}")
    check(temp.get("/r/temp-ok/") == "200, закрыт в robots.txt", f"{when}: временный редирект на рабочую: {temp}")
    check(adr(folder, "redirect_to_error") == ["/r/chain/", "/r/perm-dead/", "/r/temp-dead/"],
          f"{when}: редирект на ошибку: {adr(folder, 'redirect_to_error')}")
    check(adr(folder, "redirect_to_blocked") == ["/r/temp-ok/"],
          f"{when}: редирект на закрытую: {adr(folder, 'redirect_to_blocked')}")
    check(adr(folder, "soft404") == ["/p/dead/"], f"{when}: пустая страница из sitemap: {adr(folder, 'soft404')}")
    check(adr(folder, "orphans") == ["/p/alive/", "/p/noh1/"],
          f"{when}: сироты только рабочие: {adr(folder, 'orphans')}")
    check("/p/dead/" not in adr(folder, "title_missing"),
          f"{when}: пустой странице нужен 404, а не title: {adr(folder, 'title_missing')}")
    check("/p/dead/" not in adr(folder, "h1_missing"),
          f"{when}: пустой странице нужен 404, а не H1: {adr(folder, 'h1_missing')}")
    check("/p/noh1/" in adr(folder, "h1_missing"), f"{when}: живая без H1 из sitemap: {adr(folder, 'h1_missing')}")
    check("/p/alive/" not in adr(folder, "h1_missing"), f"{when}: настоящая страница не должна быть без H1")


def check_junk_place():
    from seocrawler.analyze.checks.buy import _junk_where
    blocks = ["Характеристики", "Коллекция", "Chrome#Classic#Vanda II", "Коллекция", "Chrome#Classic#Vanda II",
              "Длинный текст " * 30 + "#PRICE#" + " хвост" * 30]
    page = {"url": "u", "blocks": zlib.compress("\n".join(blocks).encode())}
    got = _junk_where(page, ["#Classic#", "#Classic#", "#Classic#"])
    check(got == "«Chrome#Classic#Vanda II» (рядом: Коллекция)", f"остаток шаблона с местом: {got}")
    long_one = _junk_where(page, ["#PRICE#"])
    quoted = long_one.split("»")[0]
    check("#PRICE#" in quoted and len(quoted) <= 81, f"длинный блок режется вокруг куска: {long_one}")
    check(_junk_where({"url": "нет"}, ["#X#"]) == "«#X#»", "нет текста страницы - сам кусок")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    check_junk_place()
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(quiet_env(tmp),
                   CLAYLER_NO_PDF="1",
                   CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        crawl = os.path.join(ROOT, "crawl.py")
        r = subprocess.run([sys.executable, crawl, SITE, "--no-open", "--delay", "0", "--no-images", "--no-external",
                            "--no-search-urls", "--no-exposed"], env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        folders = glob.glob(os.path.join(tmp, "127.0.0.1*"))
        if not folders:
            print("НЕ ПРОШЁЛ: обход не создал папку\n", r.stdout[-1500:], r.stderr[-1500:])
            return 1
        folder = folders[0]
        check_report(folder, "новая проверка")

        # готовая проверка старым кодом: текста страницы из sitemap в базе нет, цели редиректов не дочитаны
        path = os.path.join(folder, "crawl.db")
        db = sqlite3.connect(path)
        with db:
            db.execute("UPDATE pages SET blocks=NULL WHERE url LIKE '%/p/%'")
            db.execute("DELETE FROM meta WHERE key IN ('redirect_ends', 'sitemap_blocks')")
        db.close()
        r = subprocess.run([sys.executable, crawl, "--report", folder, "--no-open"], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
        check(r.returncode == 0, f"«Обновить отчёт»: код {r.returncode}: {r.stderr[-600:]}")
        check_report(folder, "обновить отчёт")
    srv.shutdown()
    if fails:
        print("НЕ ПРОШЁЛ:\n  " + "\n  ".join(fails))
        return 1
    print("Дочитывание при сборке: всё в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
