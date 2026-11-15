"""Сайт отвечает через раз (crawler/shaky.py): программа сама ставит паузу, идёт медленнее, адреса без ответа
проверяет ещё раз, а не записывает в отчёт ошибкой. Если сайт так и не отвечает - обход прекращается сам.
Было: dog-comfort.kz 16.10.2026 - 70 из 190 страниц в отчёте «Соединение сброшено».

1) Сайт после 8 нормальных ответов несколько секунд обрывает соединение на каждый запрос, потом оживает:
   в журнале «Сайт отвечает через раз», все страницы проверены, ни одной «Соединение сброшено», в базе meta shaky.
2) Сайт после 8 страниц больше не отвечает: обход прекращается сам («Сайт перестал отвечать: сайт отвечал через раз»).
3) Окно: уведомление один раз на сайт, строка прогресса своего сайта, пауза между запросами растёт и возвращается.
Запуск: py -3 тест/проверить_сбои_сайта.py (и из проверить_всё.py)."""
import glob
import json
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
sys.path.insert(0, ROOT)
PORT = 8774
SITE = f"http://127.0.0.1:{PORT}"
PAGES, GOOD, BAD_SECONDS = 40, 8, 20
MODE = {"bad_forever": False, "n": 0, "bad_from": 0.0}
LOCK = threading.Lock()
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        with LOCK:   # сбои начинаются после GOOD страниц товаров (до них - robots.txt, зеркала, главная)
            if self.path.startswith("/p"):
                MODE["n"] += 1
                if MODE["n"] == GOOD + 1:
                    MODE["bad_from"] = time.time()
            bad = MODE["n"] > GOOD and (MODE["bad_forever"] or time.time() - MODE["bad_from"] < BAD_SECONDS)
        if bad and self.path != "/robots.txt":
            self.close_connection = True   # оборвать без ответа - у программы «Соединение сброшено»
            return
        p = self.path
        if p == "/robots.txt":
            body, ctype = b"", "text/plain"
        else:
            links = "".join(f'<a href="/p{i}">Товар {i}</a> ' for i in range(PAGES))
            body = f"<html><head><title>Стр {p}</title></head><body><h1>Магазин</h1>{links}</body></html>".encode("utf-8")
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def crawl(tmp, pauses="2,4,8,16,30"):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_REPORTS=tmp, NO_PROXY="*", no_proxy="*",
               CLAYLER_SHAKY_PAUSES=pauses, CLAYLER_SHAKY_MIN="8", CLAYLER_SHAKY_OK="5",
               CLAYLER_RETRIES="0")  # без повторов: адрес без ответа сразу итог, тест быстрее
    before = set(glob.glob(os.path.join(tmp, "*")))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE + "/", "--no-open", "--delay", "0",
                        "--no-sitemap", "--no-exposed", "--no-search-urls"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400)
    new = sorted(set(glob.glob(os.path.join(tmp, "*"))) - before)
    if r.returncode != 0 or not new:
        fails.append("программа завершилась с ошибкой: " + (r.stdout + r.stderr)[-800:])
        return None, ""
    if os.environ.get("SHOW"):
        print(r.stdout[-6000:])
    return sqlite3.connect(os.path.join(new[-1], "crawl.db")), r.stdout


def meta(db, key):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def window_checks():
    os.environ.setdefault("CLAYLER_REPORTS", tempfile.mkdtemp(prefix="clayler-shaky-"))
    from seocrawler.window import job as J, events
    got = []
    events.push = lambda *a, **k: got.append((a, k))
    j = J.Job()
    j.site = "https://www.shop.test/"
    j.add("   Страниц сайта: 5 из 100 | картинок и файлов: 3 | ждут проверки: 7 | 1.0 адр/с")
    j.add("   Сайт отвечает через раз: из последних 30 адресов не ответили 14. Ставлю паузу на 1 мин")
    j.add("   Сайт отвечает через раз: главная после паузы не открылась. Ставлю паузу на 2 мин")
    check(len(got) == 1 and "shop.test" in got[0][0][1] and got[0][0][0] == "warn",
          f"уведомление о сбоях сайта: {got}")
    check(j.prog_line().startswith("   Страниц сайта: 5 из 100"), "строка прогресса своего сайта")
    from seocrawler.crawler.common import RateLimiter
    lim = RateLimiter(0.2)
    lim.calm(0, 1.0)
    for _ in range(50):
        lim.success(0.1)
    check(lim.delay >= 1.0, f"на паузе после сбоев ускорился: {lim.delay}")
    lim.uncalm()
    for _ in range(80):
        lim.success(0.1)
    check(lim.delay <= 0.2, f"после сбоев скорость не вернулась: {lim.delay}")


def main():
    window_checks()
    tmp = tempfile.mkdtemp(prefix="clayler-shaky-")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    t0 = time.time()
    try:
        db, out = crawl(tmp)
        if db:
            check("Сайт отвечает через раз" in out, "в журнале нет «Сайт отвечает через раз»")
            pages = db.execute("SELECT COUNT(*) FROM urls WHERE internal=1 AND kind='page' AND state='done'").fetchone()[0]
            check(pages == PAGES + 1, f"проверено страниц {pages} из {PAGES + 1}")
            bad = db.execute("SELECT COUNT(*) FROM pages WHERE error<>''").fetchone()[0]
            check(bad == 0, f"в отчёт попали страницы с ошибкой: {bad}")
            sh = meta(db, "shaky") or {}
            check(sh.get("pauses", 0) >= 1 and sh.get("repeated", 0) >= 1, f"meta shaky: {sh}")
            check(not meta(db, "site_down"), "сайт ожил, а записан как переставший отвечать")
            db.close()
        MODE.update(bad_forever=True, n=0, bad_from=0.0)
        db, out = crawl(tmp, "1,1,1,1,1")
        if db:
            down = meta(db, "site_down") or ""
            check("через раз" in down, f"сайт не отвечает совсем, а обход не прекратился сам: {down!r}")
            check("Сайт перестал отвечать" in out, "в журнале нет «Сайт перестал отвечать»")
            # причина (access_check.py): подключиться можно, а на запрос сайт молчит и обрывает
            check("обрывает соединение без ответа" in down, f"нет причины в «перестал отвечать»: {down!r}")
            db.close()
    finally:
        srv.shutdown()
    if fails:
        print("✗ сбои сайта:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ сбои сайта: пауза и повтор адресов без ответа, ошибок в отчёте нет, «перестал отвечать» сам, "
          f"уведомление один раз, {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
