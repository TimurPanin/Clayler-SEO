"""Автотест сторожа зависших адресов (crawler/main_loop._drain, ИНЖЕНЕРНЫЕ_ПРАВИЛА.md: обещание без теста до
04.11.2026). Тестовый сайт без сети: страница /hang/ отдаёт заголовки ответа по байту в секунду - каждый байт приходит
вовремя, срок ожидания не истекает, загрузка висит (так сторож и нужен). Срок сторожа уменьшен переменной
CLAYLER_WATCHDOG. Проверяется:
- обход не ждёт зависший адрес: проверка кончается раньше, чем сайт его отдаст;
- зависший адрес в отчёте «не дождалась ответа» (код 0), остальные страницы проверены как обычно;
- перепроверка ошибок после обхода тоже не ждёт его: жёсткий срок загрузчика (fetcher._Guard, 50 с) - до
  04.11.2026 перепроверка ждала, пока сайт отдаст страницу (тест это и нашёл);
- поздний ответ брошенного потока не записывается в базу поверх («не дождалась» остаётся).
Запуск: py -3 тест/проверить_сторож.py (и из проверить_всё.py)."""
import glob
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = 8791
SITE = f"http://127.0.0.1:{PORT}/"
HANG = 300     # столько секунд /hang/ тянет заголовки (жёсткий срок загрузчика - 50 с)
WATCHDOG = 6   # срок сторожа в тесте
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/hang/":
            try:
                self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                self.wfile.flush()
                end = time.time() + HANG
                while time.time() < end:
                    time.sleep(1)
                    self.wfile.write(b"a")
                    self.wfile.flush()
                body = b"<html><head><title>Hang</title></head><body><h1>Hang</h1></body></html>"
                self.wfile.write(b"\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: "
                                 + str(len(body)).encode() + b"\r\n\r\n" + body)
            except OSError:
                pass   # программа закрыла соединение
            self.close_connection = True
            return
        pages = {"/": '<a href="/p1/">1</a> <a href="/hang/">h</a> <a href="/p2/">2</a>',
                 "/p1/": '<a href="/">home</a>', "/p2/": '<a href="/">home</a>'}
        if self.path == "/robots.txt" or self.path not in pages:
            self.send_response(404 if self.path != "/robots.txt" else 200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = (f"<html><head><title>Страница {self.path}</title></head><body><h1>Страница</h1>"
                f"{pages[self.path]}</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    tmp = tempfile.mkdtemp(prefix="clayler_watchdog_")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8",
               PYTHONUTF8="1", CLAYLER_WATCHDOG=str(WATCHDOG))
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE, "--no-open", "--delay", "0",
                            "--no-images", "--no-external", "--no-sitemap", "--no-search-urls", "--no-exposed"],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=HANG * 2)
    except subprocess.TimeoutExpired:
        fails.append(f"проверка не закончилась за {HANG * 2} с")
        r = None
    took = time.time() - t0
    out = (r.stdout + r.stderr) if r else ""
    check(r is not None and r.returncode == 0, f"проверка завершилась с ошибкой: {out[-600:]}")
    check(took < 200, f"обход или перепроверка ждали зависший адрес: {took:.0f} с (сайт отдаёт его через {HANG} с)")
    check("Загрузка дольше 50 с - прервана" in out or "повторились" in out, f"перепроверка: {out[-400:]}")
    check("Адрес не ответил" in out and "/hang/" in out, f"в журнале нет строки сторожа: {out[-600:]}")
    folder = (sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*"))) or [""])[-1]
    db = os.path.join(folder, "crawl.db")
    check(os.path.exists(db), f"нет базы проверки в {tmp}")
    if os.path.exists(db):
        c = sqlite3.connect(db)
        rows = {u: (s, e) for u, s, e in c.execute("SELECT url, status, error FROM pages")}
        c.close()
        hang = rows.get(SITE + "hang/")
        check(hang and hang[0] == 0 and "не дождалась" in (hang[1] or ""), f"/hang/ в базе: {hang}")
        check(all(rows.get(SITE + p, (0,))[0] == 200 for p in ("", "p1/", "p2/")),
              f"остальные страницы: { {u: v for u, v in rows.items() if 'hang' not in u} }")
    srv.shutdown()
    if fails:
        print("✗ сторож зависших адресов:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ сторож зависших адресов: обход не ждал зависшую страницу ({took:.0f} с вместо {HANG}), "
          "она в отчёте «не дождалась», поздний ответ не записан")


if __name__ == "__main__":
    main()
