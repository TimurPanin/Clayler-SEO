"""Автотест: каждый код ответа от 200 до 5xx программа понимает правильно (04.11.2026, по просьбе пользователя).
Тестовый сайт без сети: с главной ссылки на /c/<код>/ - каждая страница отдаёт свой код; редиректы без адреса и на
ошибку; robots.txt всегда отвечает 503. Обход программой, потом сверка по файлам «проблемы/<пункт>.csv»:
- 4xx - только настоящие ошибки запроса (404, 403, 410…), с колонкой «Что это значит»; 408 и 429 - не там;
- 408 и 429 - отдельно («сервер просил обходить реже»), и не в битых ссылках;
- 5xx - только 500-599, нестандартный 999 - не ошибка сервера;
- 201, 202, 203, 204, 206, 300, 304, 999 - «Необычный код ответа» (раньше молча выпадали из отчёта);
- 301 без адреса перехода - «Редирект без адреса», а 302 на tg:// - нет (адрес есть, хоть и не http); редирект на 404 и на 500 - «Редирект ведёт на ошибку», и в
  «Ссылках на адреса с редиректом» нет совета поставить в ссылку страницу 404;
- 302, 303, 307 - «Временные редиректы», 301 и 308 - нет;
- robots.txt с ошибкой сервера - пункт «robots.txt не открывается».
Запуск: py -3 тест/проверить_коды_ответа.py (и из проверить_всё.py), около 3 минут."""
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
PORT = 8792
SITE = f"http://127.0.0.1:{PORT}/"
CODES = [200, 201, 202, 203, 204, 206, 300, 301, 302, 303, 304, 307, 308, 400, 401, 403, 404, 405, 408, 410, 418, 429,
         451, 500, 501, 502, 503, 504, 520, 999]
SPECIAL = ["/r/noloc/", "/r/to404/", "/r/to500/", "/r/tg/"]
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if code not in (204, 304):
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if code not in (204, 304):
            self.wfile.write(body)

    @staticmethod
    def page(title, links=""):
        return (f"<html><head><title>{title} - тестовый сайт кодов</title></head><body><h1>{title}</h1>"
                f"<p>{'текст страницы ' * 100}</p>{links}</body></html>").encode()

    def do_GET(self):
        p = self.path
        if p == "/robots.txt":
            return self.send(503, b"down", {"Retry-After": "1"})
        if p == "/":
            links = "".join(f'<a href="/c/{c}/">код {c}</a> ' for c in CODES)
            links += "".join(f'<a href="{s}">особый {s}</a> ' for s in SPECIAL)
            return self.send(200, self.page("Главная", links))
        if p.startswith("/ok/"):
            return self.send(200, self.page("Цель " + p, '<a href="/">главная</a>'))
        if p == "/r/noloc/":
            return self.send(301)
        if p == "/r/to404/":
            return self.send(301, headers={"Location": "/c/404/"})
        if p == "/r/to500/":
            return self.send(302, headers={"Location": "/c/500/"})
        if p == "/r/tg/":   # адрес перехода есть, но не http(s) - это не «редирект без адреса»
            return self.send(302, headers={"Location": "tg://resolve?domain=shop"})
        parts = p.split("/")
        if p.startswith("/c/") and len(parts) > 2 and parts[2].isdigit():
            c = int(parts[2])
            hdr = {}
            if 300 <= c < 400 and c != 304:
                hdr["Location"] = f"/ok/{c}/"
            if c in (429, 503):
                hdr["Retry-After"] = "1"
            return self.send(c, self.page(f"Код {c}") if c < 300 else b"error", hdr)
        return self.send(404, b"not found")


def rows(folder, key):
    path = os.path.join(folder, "проблемы", key + ".csv")
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path, encoding="utf-8-sig"), delimiter=";"))


def codes_of(folder, key):
    return sorted(int(r["Код"]) for r in rows(folder, key))


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="clayler_codes_")
    env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8",
               PYTHONUTF8="1")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE, "--no-open", "--delay", "0",
                        "--no-images", "--no-external", "--no-sitemap", "--no-search-urls", "--no-exposed"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    srv.shutdown()
    out = r.stdout + r.stderr
    check(r.returncode == 0, f"проверка завершилась с ошибкой: {out[-800:]}")
    folder = (sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*"))) or [""])[-1]
    check(os.path.isdir(os.path.join(folder, "проблемы")), f"нет папки «проблемы» в {folder}")

    got = codes_of(folder, "4xx")
    check(got == [400, 401, 403, 404, 405, 410, 418, 451], f"4xx: {got}")
    m = {int(x["Код"]): x["Что это значит"] for x in rows(folder, "4xx")}
    check(m.get(401, "").startswith("нужен вход") and m.get(410) == "удалена навсегда" and m.get(404) == "страницы нет",
          f"4xx - что значит код: {m}")
    check(codes_of(folder, "too_many_requests") == [408, 429], f"408 и 429: {codes_of(folder, 'too_many_requests')}")
    check(codes_of(folder, "5xx") == [500, 501, 502, 503, 504, 520], f"5xx: {codes_of(folder, '5xx')}")
    check(codes_of(folder, "odd_codes") == [201, 202, 203, 204, 206, 300, 304, 999],
          f"необычные коды: {codes_of(folder, 'odd_codes')}")
    broken = {x["Куда ведёт"] for x in rows(folder, "broken_links")}
    check(not any("/c/429/" in u or "/c/408/" in u for u in broken), f"429 и 408 в битых ссылках: {sorted(broken)}")
    check(any("/c/404/" in u for u in broken) and any("/c/500/" in u for u in broken), f"битые ссылки: {sorted(broken)}")

    noloc = [x["Адрес"] for x in rows(folder, "redirect_noloc")]
    check(noloc == [SITE + "r/noloc/"], f"редирект без адреса: {noloc}")
    to_err = {x["Адрес"]: x["Код в конце"] for x in rows(folder, "redirect_to_error")}
    check(to_err == {SITE + "r/to404/": "404", SITE + "r/to500/": "500"}, f"редирект на ошибку: {to_err}")
    ltr = {x["Адрес в ссылке"]: x["Правильный адрес"] for x in rows(folder, "links_to_redirect")}
    check(ltr.get(SITE + "r/to404/", "").startswith("нет: ведёт на ошибку (404)")
          and ltr.get(SITE + "c/301/") == SITE + "ok/301/", f"ссылки на редирект: {ltr}")
    temp = sorted(x["Адрес"].replace(SITE, "/") for x in rows(folder, "redirect_temp"))
    check(temp == ["/c/302/", "/c/303/", "/c/307/", "/r/tg/", "/r/to500/"], f"временные редиректы: {temp}")
    check(ltr.get(SITE + "r/tg/") == "tg://resolve?domain=shop", f"редирект на tg://: {ltr.get(SITE + 'r/tg/')}")

    # закон сохранения на настоящем отчёте: строки пунктов о кодах + рабочие + редиректы = все проверенные адреса
    import sqlite3
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    own = db.execute("""SELECT COUNT(*) FROM pages p JOIN urls u ON u.url=p.url
                        WHERE u.internal=1 AND u.kind<>'sitemap'""").fetchone()[0]
    fine = db.execute("""SELECT COUNT(*) FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind<>'sitemap'
                         AND (p.status=200 AND p.error='' OR p.status IN (301,302,303,307,308) AND p.location<>'')""").fetchone()[0]
    db.close()
    in_issues = sum(len(rows(folder, k)) for k in ("4xx", "too_many_requests", "5xx", "odd_codes", "noresp", "redirect_noloc"))
    check(fine + in_issues == own, f"закон сохранения: рабочих и редиректов {fine} + в пунктах {in_issues} != всех {own}")
    html = open(os.path.join(folder, "отчёт.html"), encoding="utf-8").read()
    check(all(x in html for x in ("429 просит обходить реже", "410 удалена навсегда", "999 необычный код", "204 пустой ответ")),
          "в сводке «Что отвечают страницы» нет подписей кодов")

    sys.path.insert(0, ROOT)
    from seocrawler import client_report
    cpath = os.path.join(folder, client_report.FILE)
    left = client_report.leftovers(open(cpath, encoding="utf-8").read()) if os.path.exists(cpath) else ["нет файла"]
    check(not left, f"в отчёте для клиента служебные фразы: {left[:5]}")

    rb = rows(folder, "robots_unavailable")
    check(len(rb) == 1 and rb[0]["Ответ"] == "503", f"robots.txt с ошибкой сервера: {rb}")
    check("Google при такой ошибке" in out, "в журнале нет строки про robots.txt с ошибкой")

    if fails:
        print("✗ коды ответа:\n   " + "\n   ".join(fails) + f"\n   папка: {folder}")
        sys.exit(1)
    print("✓ коды ответа: 2xx, 3xx, 4xx, 5xx и нестандартные - каждый в своём пункте, редиректы без адреса и на "
          "ошибку, 429/408 не битые, robots.txt с ошибкой сервера")


if __name__ == "__main__":
    main()
