"""Проверка списка адресов и переезда (seocrawler/urllist.py), вход на закрытый сайт (seocrawler/site_auth.py)
и поиск по готовой проверке (seocrawler/search.py) - без интернета, на своём маленьком сервере.
Запуск: python тест/проверить_список.py (и из проверить_всё.py)."""
import base64
import os
import sqlite3
import sys
import tempfile
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="clayler-list-")
os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(TMP, "доступы.json")  # не трогаем настоящие доступы
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import urllist, site_auth, search  # noqa: E402

AUTH_SEEN = {"main": [], "other": []}
PAGE = '<html><head><title>{t}</title>{h}</head><body><h1>{t}</h1><p>{w}</p></body></html>'
WORDS = " ".join(f"слово{i}" for i in range(300))
ROUTES = {  # путь: (код, куда / title, лишнее в <head>)
    "/": (200, "Главная", ""), "/a": (200, "A", ""), "/b": (200, "B", ""), "/c": (200, "C", ""), "/d": (200, "D", ""),
    "/old-b": (301, "/b", ""), "/old-c": (302, "/c", ""), "/old-d": (301, "/x", ""), "/x": (301, "/d", ""),
    "/old-e": (301, "/", ""), "/noidx": (200, "N", '<meta name="robots" content="noindex">'),
    "/changed": (200, "Новый title", ""), "/loop1": (301, "/loop2", ""), "/loop2": (301, "/loop1", ""),
}


def make_handler(name, secret=False):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            AUTH_SEEN[name].append(self.headers.get("Authorization") or "")
            if secret and self.path == "/secret" and self.headers.get("Authorization") != \
                    "Basic " + base64.b64encode(b"tester:pa55").decode():
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="test"')
                self.end_headers()
                return
            code, x, head = ROUTES.get(self.path, (404, "", "")) if self.path != "/secret" else (200, "Секрет", "")
            self.send_response(code)
            if 300 <= code < 400:
                self.send_header("Location", x)
                self.end_headers()
                return
            body = PAGE.format(t=x or "404", h=head, w=WORDS if code == 200 else "").encode("utf-8")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return H


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def main():
    bad = []

    def check(ok, what):
        if not ok:
            bad.append(what)

    p1 = serve(make_handler("main", secret=True))
    p2 = serve(make_handler("other"))
    B, OTHER = f"http://127.0.0.1:{p1}", f"http://localhost:{p2}"

    # список: адреса вперемешку с мусором, как из Excel
    urls = urllist.read_list(f"Адрес;Код\n{B}/a;200\n{B}/old-b\n{B}/old-b\nне адрес\n{B}/gone, {OTHER}/a\t{B}/secret")
    check(urls == [f"{B}/a", f"{B}/old-b", f"{B}/gone", f"{OTHER}/a", f"{B}/secret"], f"чтение списка: {urls}")

    # переезд: что было на старых адресах
    old = {f"{B}{p}": {"title": t, "h1": t, "words": 300} for p, t in
           [("/a", "A"), ("/old-b", "B"), ("/old-c", "C"), ("/old-d", "D"), ("/gone", "G"), ("/old-e", "E"),
            ("/noidx", "N"), ("/changed", "Старый title"), ("/loop1", "L"), ("/secret", "Секрет")]}
    old[f"{OTHER}/a"] = {"title": "A", "h1": "A", "words": 300}
    # логин и пароль - только для 127.0.0.1 (сохраняются зашифрованными, в тесте - во временном файле)
    check(site_auth.save(B, "tester", "pa55") == "", "сохранение доступа")
    auth = site_auth.headers_for(B + "/")
    check(bool(auth) and "127.0.0.1" in auth and site_auth.sites()[0]["user"] == "tester", f"доступ: {site_auth.sites()}")
    rows = urllist.run(list(old), os.path.join(TMP, "переезд"), old=old, threads=2, delay=0, auth=auth,
                       log=lambda *_: None)
    got = {r["src"].split(":", 2)[-1].split("/", 1)[-1]: r["verdict"] for r in rows}
    want = {"a": "ok", "old-b": "moved", "old-c": "temp", "old-d": "chain", "gone": "gone", "old-e": "home",
            "noidx": "closed", "changed": "changed", "loop1": "loop", "secret": "ok"}
    for k, v in want.items():
        check(got.get(k) == v, f"переезд /{k}: ждали {v}, получили {got.get(k)}")
    check(not any(AUTH_SEEN["other"]), "пароль ушёл на чужой сайт")
    check(any(AUTH_SEEN["main"]), "пароль не отправлен своему сайту")
    check(os.path.exists(os.path.join(TMP, "переезд.html")) and os.path.exists(os.path.join(TMP, "переезд.csv")),
          "файлы результата")
    site_auth.remove(B)
    check(site_auth.headers_for(B) is None, "удаление доступа")

    # новый домен: старые адреса проверяются на другом адресе
    check(urllist._swap_host("https://old.ru/a/?x=1", "new.ru") == "https://new.ru/a/?x=1", "замена домена")

    # поиск по готовой проверке: маленькая база с двумя страницами
    f = os.path.join(TMP, "проверка")
    os.makedirs(f)
    db = sqlite3.connect(os.path.join(f, "crawl.db"))
    db.executescript("CREATE TABLE urls(url TEXT, internal INT, kind TEXT, depth INT);"
                     "CREATE TABLE pages(url TEXT, status INT, content_type TEXT, title TEXT, description TEXT, h1 TEXT,"
                     " blocks BLOB, counters TEXT);")
    for u, text, ctr in [("https://s.ru/", "Звоните +7 900 111-22-33\nНет в наличии", '{"ym": ["1"]}'),
                         ("https://s.ru/b", "Звоните +7 900 999-88-77", "{}")]:
        db.execute("INSERT INTO urls VALUES (?,1,'page',0)", (u,))
        db.execute("INSERT INTO pages VALUES (?,200,'text/html','T','D','H',?,?)", (u, zlib.compress(text.encode()), ctr))
    db.commit()
    db.close()
    r = search.search(f, "111-22-33", "has", "text")
    check(r["found"] == 1 and r["rows"][0]["url"] == "https://s.ru/", f"поиск «есть»: {r}")
    r = search.search(f, "111-22-33", "none", "text")
    check(r["found"] == 1 and r["rows"][0]["url"] == "https://s.ru/b", f"поиск «нет»: {r}")
    r = search.search(f, "", "no_ym")
    check(r["found"] == 1 and r["rows"][0]["url"] == "https://s.ru/b", f"нет Метрики: {r}")
    r = search.search(f, "НЕТ   в наличии", "has", "text")
    check(r["found"] == 1, "поиск без учёта регистра и пробелов")

    if bad:
        print("✗ список адресов, переезд, вход, поиск:\n   " + "\n   ".join(bad))
        sys.exit(1)
    print("✓ список адресов, переезд, вход на закрытый сайт, поиск по проверке")


if __name__ == "__main__":
    main()
