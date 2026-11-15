"""Баги после очереди 07-09.10: сбой проверки в очереди - видна сама ошибка, журнал в
«очередь\\сбои»; обрыв соединения окна не печатается; список отчётов запоминается; «тепловентиляторы
тепловентиляторы» - дубль; Вебмастер - главное зеркало; главная со сбросом соединения - ждём и пробуем ещё.
Запуск: python tests/проверить_баги_раздела1.py (и из проверить_всё.py)."""
import os
import socket
import struct
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("CLAYLER_JOURNAL_DIR", tempfile.mkdtemp(prefix="clayler-bugs1-"))   # «Журнал» - не в папку программы
os.environ["CLAYLER_NO_SOUND"] = "1"
PORT = 8774
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def queue_crash():
    from seocrawler import site_queue as Q
    lines = ["Шаг 1 из 4.", "Traceback (most recent call last):", '  File "x.py", line 3, in f', "    a[1]",
             "KeyError: 'regions'"]
    check(Q._crash_line(lines) == "KeyError: 'regions'", f"строка ошибки: {Q._crash_line(lines)}")
    check(Q._crash_line(["всё хорошо"]) == "", "ошибка без трассировки")


def window_abort():
    from seocrawler.window.server import Server
    printed = []

    class S(Server):
        def __init__(self):
            pass
    s = S()
    import socketserver
    orig = socketserver.BaseServer.handle_error
    socketserver.BaseServer.handle_error = lambda self, r, a: printed.append(1)
    try:
        for exc in (ConnectionAbortedError(10053, "abort"), ConnectionResetError(), ValueError("x")):
            try:
                raise exc
            except Exception:
                s.handle_error(None, ("127.0.0.1", 1))
    finally:
        socketserver.BaseServer.handle_error = orig
    check(printed == [1], f"обрыв соединения окна: напечатано {len(printed)} из 3 (нужна только настоящая ошибка)")


def reports_cache():
    from seocrawler.window import reports_list as RL
    base = tempfile.mkdtemp(prefix="clayler-rl-")
    d = os.path.join(base, "site.ru_2026-10-10_10-00-00")
    os.makedirs(d)
    import sqlite3
    con = sqlite3.connect(os.path.join(d, "crawl.db"))
    con.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('start', '\"https://site.ru/\"')")
    con.commit()
    con.close()
    a = RL.read_check(base, os.path.basename(d))
    calls = []
    orig = RL._read_check
    RL._read_check = lambda *x: calls.append(1) or orig(*x)
    try:
        b = RL.read_check(base, os.path.basename(d))
        check(a == b and not calls, "список отчётов: папка без изменений перечитана")
        time.sleep(0.02)
        open(os.path.join(d, "отчёт.html"), "w").close()
        c = RL.read_check(base, os.path.basename(d))
        check(calls and c["has_html"], "список отчётов: новый отчёт не замечен")
    finally:
        RL._read_check = orig


def semantics_repeat():
    from seocrawler.semantics import repeated_word, tokens, norm
    for q, want in (("тепловентиляторы тепловентиляторы", "тепловентиляторы"), ("котел котла газовый", "котла"),
                    ("подводка для воды гайка гайка", ""), ("котел для дома для дачи", ""), ("газовый котел", "")):
        got = repeated_word(tokens(norm(q)))
        check(got == want, f"повтор слова «{q}»: {got!r}")


def webmaster_mirror():
    from seocrawler import webmaster, accounts
    hosts = [{"verified": True, "ascii_host_url": "https://timurpanin.ru:443", "host_id": "https:timurpanin.ru:443",
              "main_mirror": {"host_id": "http:timurpanin.ru:80"}},
             {"verified": True, "ascii_host_url": "http://timurpanin.ru:80", "host_id": "http:timurpanin.ru:80"}]
    orig = accounts._api
    accounts._api = lambda svc, path: {"hosts": hosts}
    try:
        h = webmaster.find_host("1", "https://timurpanin.ru/")
    finally:
        accounts._api = orig
    check(h and h["host_id"] == "http:timurpanin.ru:80", f"Вебмастер: не главное зеркало {h}")


RESETS = {"left": 0}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/" and RESETS["left"] > 0:
            RESETS["left"] -= 1
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.connection.close()   # сброс соединения, как у защиты от частых запросов
            self.close_connection = True
            return
        body = b"<html><head><title>ok</title></head><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_reset():
    from seocrawler.crawler import Crawler
    from seocrawler.crawler.common import Config
    from seocrawler.crawler.page import PageMixin
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    PageMixin.START_WAITS = (0.5, 0.5)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "*"
    try:
        site = f"http://127.0.0.1:{PORT}/"
        log = []
        c = Crawler(Config(start_url=site, delay=0), os.path.join(tempfile.mkdtemp(), "c.db"), log=log.append)
        c.fetcher._proxies = {}
        c.store.set_meta("robots", {site.rstrip("/"): {"status": 200, "text": ""}})
        RESETS["left"] = 4   # 3 обычные попытки + первая после паузы
        r, _ = c.work(site, True, "page")
        check(r.status == 200 and any("жду" in x for x in log), f"главная после сброса: {r.status} {r.error} {log}")
        # сайт не отвечал вообще (robots.txt не открылся) - не ждём
        c2 = Crawler(Config(start_url=site, delay=0), os.path.join(tempfile.mkdtemp(), "c.db"), log=log.append)
        c2.fetcher._proxies = {}
        RESETS["left"] = 10
        t = time.time()
        r, _ = c2.work(site, True, "page")
        check(r.error.startswith("Соединение сброшено") and not getattr(c2, "_start_waited", False),
              f"сайт без robots.txt: {r.error}")
        RESETS["left"] = 0
        c.store.db.close()
        c2.store.db.close()
    finally:
        srv.shutdown()


def main():
    for f in (queue_crash, window_abort, reports_cache, semantics_repeat, webmaster_mirror, start_reset):
        try:
            f()
        except Exception as e:
            import traceback
            fails.append(f"{f.__name__}: {traceback.format_exc()[-600:]}")
    if fails:
        print("✗ баги раздела 1:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ баги раздела 1: сбой в очереди с текстом ошибки, обрыв окна не печатается, список отчётов запоминается, "
          "повтор слова, главное зеркало Вебмастера, главная после сброса соединения")


if __name__ == "__main__":
    main()
