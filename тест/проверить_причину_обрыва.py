"""Сайт не открывается: понятная причина (access_check.py, crawler/access.py).
Было: dog-comfort.kz 17.10.2026 - напрямую соединение сбрасывалось на шаге https-рукопожатия (через VPN проходило),
а программе («ClaylerSEO/1.0») сайт отдавал 403, браузеру Chrome - 200. В журнале было только «Соединение сброшено».

1) Причина по шагам на выдуманных серверах: обрыв на рукопожатии https («соединение режут по дороге»), обрыв
   через раз, то же через прокси Windows (VPN-программа), сайт не пускает программы, закрыт и для браузера,
   обрывает соединение без ответа, всё открывается.
2) Обрыв на рукопожатии в загрузчике - «Соединение сброшено на шаге https» (повторяется, как обычный сброс).
3) Обход сайта, который не пускает программы: дальше идёт как браузер Chrome, страницы проверены, в отчёте
   оператора плашка, в отчёте для клиента её нет.
4) Окно: уведомления и тексты простыми словами.
Запуск: py -3 тест/проверить_причину_обрыва.py (и из проверить_всё.py)."""
import glob
import json
import os
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seocrawler import access_check as A  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def _rst(conn):
    """Оборвать соединение сбросом (RST), как делает блокировка по дороге."""
    try:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    except OSError:
        pass
    conn.close()


class TLSServer:
    """https на 127.0.0.1: reset - каждое подключение обрывается после первого сообщения рукопожатия;
    flaky - обрываются подключения 1 и 3, остальные отвечают 200; ok - всегда 200."""

    def __init__(self, mode):
        self.mode, self.n = mode, 0
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(os.path.join(HERE, "https_test.crt"), os.path.join(HERE, "https_test.key"))
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(20)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.n += 1
            threading.Thread(target=self.one, args=(conn, self.n), daemon=True).start()

    def one(self, conn, n):
        conn.settimeout(5)
        try:
            if self.mode == "reset" or (self.mode == "flaky" and n in (1, 3)):
                conn.recv(4096)
                return _rst(conn)
            s = self.ctx.wrap_socket(conn, server_side=True)
            s.recv(65536)
            body = b"<html><head><title>ok</title></head><body>ok</body></html>"
            s.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\nContent-Length: "
                      + str(len(body)).encode() + b"\r\n\r\n" + body)
            s.close()
        except Exception:
            try:
                conn.close()
            except OSError:
                pass


class Proxy:
    """Прокси Windows (как у VPN-программы): на CONNECT отвечает 200 и сразу обрывает (или 403)."""

    def __init__(self, code=200):
        self.code = code
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(20)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                conn.recv(4096)
                conn.sendall(f"HTTP/1.1 {self.code} X\r\n\r\n".encode())
                conn.recv(4096)
            except OSError:
                pass
            _rst(conn)


PAGES = 6


class H(BaseHTTPRequestHandler):
    """http-сайт: MODE bots - 403 всему, что не браузер Chrome; blocked - 403 всем; dropped - обрыв без ответа."""
    protocol_version = "HTTP/1.1"
    MODE = "bots"

    def log_message(self, *a):
        pass

    def do_GET(self):
        ua = self.headers.get("User-Agent", "")
        if self.MODE == "dropped":
            self.close_connection = True
            return
        if self.MODE == "blocked" or "ClaylerSEO" in ua or "Chrome" not in ua:
            body, code = b"Forbidden", 403
        elif self.path == "/robots.txt":
            body, code = b"User-agent: *\nAllow: /\n", 200
        else:
            links = "".join(f'<a href="/p{i}">Товар {i}</a> ' for i in range(PAGES))
            body = (f"<html><head><title>Стр {self.path}</title></head><body><h1>Магазин</h1>{links}"
                    f"</body></html>").encode("utf-8")
            code = 200
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8" if code == 200 else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def http_server(mode):
    cls = type("H_" + mode, (H,), {"MODE": mode})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def diag(url, **kw):
    return A.diagnose(url, verify_ssl=False, timeout=5, **kw)


def diagnose_checks():
    A._proxy = lambda scheme, host: None   # в тесте - напрямую, без прокси Windows компьютера
    d = diag(f"https://127.0.0.1:{TLSServer('reset').port}/")
    check(d["kind"] == "tls_reset" and "режут по дороге" in d["title"] and "VPN" in d["todo"],
          f"обрыв на рукопожатии https: {d}")
    check(A.line(d).startswith("Сайт не открывается: соединение режут по дороге"), f"строка журнала: {A.line(d)}")
    d = diag(f"https://127.0.0.1:{TLSServer('flaky').port}/")
    check(d["kind"] == "tls_flaky" and d.get("failed") == 2, f"обрыв через раз: {d}")
    d = diag(f"https://127.0.0.1:{TLSServer('ok').port}/")
    check(d["kind"] == "ok" and d.get("program") == 200, f"https открывается: {d}")
    srv, url = http_server("bots")
    d = diag(url)
    check(d["kind"] == "bots_blocked" and d.get("program") == 403 and d.get("browser") == 200,
          f"сайт не пускает программы: {d}")
    srv.shutdown()
    srv, url = http_server("blocked")
    d = diag(url)
    check(d["kind"] == "blocked", f"закрыт и для браузера: {d}")
    srv.shutdown()
    srv, url = http_server("dropped")
    d = diag(url)
    check(d["kind"] == "dropped", f"обрыв без ответа: {d}")
    srv.shutdown()
    d = diag("https://nonexistent-domain-clayler.invalid/")
    check(d["kind"] == "dns", f"домен не находится: {d}")
    # через прокси Windows (VPN-программа): CONNECT прошёл, рукопожатие оборвали; прокси не подключился
    tls = TLSServer("ok")
    k, _ = A._handshake("127.0.0.1", tls.port, 5, ("127.0.0.1", Proxy(200).port))
    check(k == "reset", f"обрыв рукопожатия через прокси: {k}")
    k, _ = A._handshake("127.0.0.1", tls.port, 5, ("127.0.0.1", Proxy(403).port))
    check(k == "tcp", f"прокси не подключился к сайту: {k}")
    A._proxy = lambda scheme, host: ("127.0.0.1", 1)
    d = diag(f"https://127.0.0.1:{TLSServer('reset').port}/", tries=1)
    check("мимо VPN" in d["todo"], f"совет при включённом прокси: {d['todo']}")


def fetcher_checks():
    from seocrawler.fetcher import Fetcher
    import urllib.request
    old = urllib.request.getproxies
    urllib.request.getproxies = lambda: {}
    try:
        r = Fetcher("x", timeout=5, verify_ssl=False).fetch(f"https://127.0.0.1:{TLSServer('reset').port}/")
    finally:
        urllib.request.getproxies = old
    check(r.retryable and r.error.startswith("Соединение сброшено"), f"обрыв на рукопожатии в загрузчике: {r.error!r}")


def crawl_checks():
    srv, url = http_server("bots")
    tmp = tempfile.mkdtemp(prefix="clayler-access-")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_REPORTS=tmp, NO_PROXY="*", no_proxy="*", CLAYLER_RETRIES="0")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), url, "--no-open", "--delay", "0",
                            "--no-sitemap", "--no-exposed", "--no-search-urls"],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400)
    finally:
        srv.shutdown()
    out = r.stdout
    dirs = sorted(glob.glob(os.path.join(tmp, "*")))
    if r.returncode or not dirs:
        return fails.append("обход завершился с ошибкой: " + (r.stdout + r.stderr)[-800:])
    check("Сайт не пускает программы" in out and "Дальше проверяю как браузер Chrome" in out,
          "в журнале нет «Сайт не пускает программы … как браузер Chrome»")
    db = sqlite3.connect(os.path.join(dirs[-1], "crawl.db"))
    meta = {k: json.loads(v) for k, v in db.execute("SELECT key, value FROM meta")}
    ok = db.execute("SELECT COUNT(*) FROM pages WHERE status=200 AND content_type LIKE '%html%'").fetchone()[0]
    db.close()
    check(ok == PAGES + 1, f"страниц с ответом 200: {ok} из {PAGES + 1}")
    check(meta.get("ua_switched") and (meta.get("config") or {}).get("user_agent") == "chrome",
          f"meta ua_switched / config: {meta.get('ua_switched')}, {(meta.get('config') or {}).get('user_agent')}")
    check((meta.get("access") or {}).get("kind") == "bots_blocked", f"meta access: {meta.get('access')}")
    rep = open(os.path.join(dirs[-1], "отчёт.html"), encoding="utf-8").read()
    check("Сайт не пускает программы" in rep and "обычный посетитель в браузере" in rep,
          "в отчёте оператора нет плашки «Сайт не пускает программы»")
    cl = os.path.join(dirs[-1], "отчёт_для_клиента.html")
    if os.path.exists(cl):
        check("не пускает программы" not in open(cl, encoding="utf-8").read(), "плашка для оператора попала клиенту")


def window_checks():
    os.environ.setdefault("CLAYLER_REPORTS", tempfile.mkdtemp(prefix="clayler-access-"))
    from seocrawler.window import job as J, events
    from seocrawler.plain_errors import explain
    got = []
    events.push = lambda *a, **k: got.append((a, k))
    j = J.Job()
    j.site = "https://www.dog.test/"
    j.add("Сайт не открывается: соединение режут по дороге. Сервер найден ... (https-рукопожатие: прошло 0 из 3)")
    check(got and got[-1][0][0] == "warn" and "dog.test" in got[-1][0][1] and "VPN" in got[-1][0][2],
          f"уведомление «Сайт не открывается»: {got}")
    check(j.access_note == "Соединение режут по дороге", f"job.access_note: {j.access_note!r}")
    j.add("Сайт не пускает программы: браузеру Chrome отвечает 200, программе - 403. Дальше проверяю как браузер "
          "Chrome, в отчёте это будет видно.")
    check(got[-1][0][0] == "info" and "делать ничего не нужно" in got[-1][0][2], f"уведомление о Chrome: {got[-1]}")
    e = explain("Сайт перестал отвечать: сайт отвечал через раз; соединение режут по дороге на шаге https")
    check(e["title"] == "Соединение режут по дороге", f"plain_errors: {e}")
    check(explain("Соединение сброшено на шаге https")["title"] == "Соединение режут по дороге", "plain_errors: сброс https")
    check(explain("Сайт не пускает программы: ...")["title"] == "Сайт не пускает программы", "plain_errors: программы")


def main():
    t0 = time.time()
    diagnose_checks()
    fetcher_checks()
    window_checks()
    crawl_checks()
    if fails:
        print("✗ причина обрыва:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ причина обрыва: режут по дороге (и через прокси), через раз, не пускает программы - обход как Chrome, "
          f"закрыт для всех, обрыв без ответа, уведомления, {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
