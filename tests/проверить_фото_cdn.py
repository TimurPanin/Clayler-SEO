"""Фото товаров на другом сайте (CDN, как у zoozavr.ru на detmir.st): проверяются выборкой, а не все;
если среди них нашлась битая — проверяются все. Плюс: что проверено в паузе без новых страниц,
продолжение старой проверки (фото там записаны как внешние ссылки).
Запуск: python tests/проверить_фото_cdn.py (и из проверить_всё.py)."""
import glob
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PAGES, PHOTOS, CAP = 30, 10, 50
os.environ["CLAYLER_EXT_FILES_CAP"] = str(CAP)
PORT = 8771
SITE = f"http://127.0.0.1:{PORT}"
CDN = f"http://localhost:{PORT}"  # тот же сервер под другим именем — для программы это другой сайт
BAD = {"on": False}
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self, head=False):
        p = self.path
        if p.startswith("/cdn/"):
            # битое - первое фото каждого товара: страницы обходятся параллельно, и одно битое фото у одного товара
            # могло найтись уже после выборки (тест то проходил, то нет)
            bad = BAD["on"] and p.endswith("-0.jpg")
            body = b"" if bad else b"\xff\xd8\xff\xe0" + b"0" * 200
            self.send_response(404 if bad else 200)
            self.send_header("Content-Type", "text/plain" if bad else "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return
        if p == "/":
            links = "".join(f'<a href="/p{i}">Товар {i}</a> ' for i in range(PAGES))
            html = f"<html><head><title>Магазин</title></head><body><h1>Магазин</h1>{links}</body></html>"
        elif p.startswith("/p") and p[2:].isdigit():
            n = int(p[2:])
            imgs = "".join(f'<img src="{CDN}/cdn/{n}-{k}.jpg" alt="Фото {k}">' for k in range(PHOTOS))
            html = f"<html><head><title>Товар {n}</title></head><body><h1>Товар {n}</h1>{imgs}</body></html>"
        elif p == "/robots.txt":
            html = ""
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8" if p != "/robots.txt" else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET(head=True)


def crawl(tmp):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_REPORTS=tmp, CLAYLER_EXT_FILES_CAP=str(CAP))
    before = set(glob.glob(os.path.join(tmp, "*")))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE + "/", "--no-open", "--delay", "0"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    new = sorted(set(glob.glob(os.path.join(tmp, "*"))) - before)
    if r.returncode != 0 or not new:
        fails.append("программа завершилась с ошибкой: " + (r.stdout + r.stderr)[-800:])
        return None, None, ""
    db = sqlite3.connect(os.path.join(new[-1], "crawl.db"))
    return new[-1], db, r.stdout


def photos(db):
    return dict(db.execute("SELECT state, COUNT(*) FROM urls WHERE internal=0 AND kind='resource' GROUP BY state"))


def unit_checks():
    from seocrawler.crawler.main_loop import MainLoopMixin as M
    from seocrawler.crawler.queue import QueueMixin, EXT_SKIP
    from seocrawler.storage import Store
    # что проверено в паузе
    note = M.pause_note(Counter({"f:img.detmir.st": 2300, "f:catalog-cdn.detmir.st": 50, "ext": 50}))
    check(note == "проверено 2 400 адресов, из них: фото и файлы с других сайтов - 2 350 "
                  "(в основном img.detmir.st, catalog-cdn.detmir.st), ссылки на другие сайты - 50", "пауза: " + note)
    check(M.pause_kind("https://img.detmir.st/a.webp", False, "external").startswith("f:"), "старое фото не узнано")
    check(M.pause_kind("https://vk.com/shop", False, "external") == "ext", "ссылка принята за фото")
    # продолжение старой проверки: фото записаны как внешние ссылки, лишние снимаются из очереди
    path = os.path.join(tempfile.mkdtemp(prefix="clayler-cdn-"), "crawl.db")
    st = Store(path)
    for i in range(CAP + 30):
        st.enqueue(f"https://img.cdn.test/{i}.webp", 1, False, "external", "https://shop.test/p",
                   "done" if i < CAP + 5 else "queued")
    st.enqueue("https://vk.com/shop", 1, False, "external", "https://shop.test/p")
    st.commit()

    class D(QueueMixin):
        pass
    d = D()
    d.store, d.log = st, lambda m: None
    v = d._ext_files()["img.cdn.test"]
    left = st.db.execute("SELECT COUNT(*) FROM urls WHERE state='queued'").fetchone()[0]
    check(left == 1 and v[1] == 25, f"продолжение: в очереди осталось {left}, снято {v[1]}")
    check(st.db.execute("SELECT COUNT(*) FROM urls WHERE skip_reason LIKE ?", (EXT_SKIP + "%",)).fetchone()[0] == 25,
          "продолжение: нет причины пропуска")
    # нашлась битая — отложенные возвращаются в очередь
    d.ext_file_result("https://img.cdn.test/x.webp", 404)
    left = st.db.execute("SELECT COUNT(*) FROM urls WHERE state='queued'").fetchone()[0]
    check(left == 26, f"битая: в очередь вернулось {left - 1} из 25")
    st.db.close()


def main():
    unit_checks()
    tmp = tempfile.mkdtemp(prefix="clayler-cdn-")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        # 1. Фото исправны: проверена выборка, остальные отложены, в отчёте пояснение
        folder, db, out = crawl(tmp)
        if db:
            ph = photos(db)
            pages = db.execute("SELECT COUNT(*) FROM urls WHERE internal=1 AND kind='page' AND state='done'").fetchone()[0]
            check(pages == PAGES + 1, f"выборка: обойдено страниц {pages}")
            check(ph.get("done") == CAP and ph.get("skipped") == PAGES * PHOTOS - CAP, f"выборка: фото {ph}")
            sample = json.loads(db.execute("SELECT value FROM meta WHERE key='ext_files_sample'").fetchone()[0])
            check(sample == {"localhost": [CAP, PAGES * PHOTOS - CAP]}, f"выборка: meta {sample}")
            check("проверены выборочно" in open(os.path.join(folder, "отчёт.html"), encoding="utf-8").read(),
                  "выборка: нет пояснения в отчёте")
            db.close()
        # 2. Среди фото есть битое: проверены все
        BAD["on"] = True
        folder, db, out = crawl(tmp)
        if db:
            ph = photos(db)
            check(ph.get("done") == PAGES * PHOTOS and not ph.get("skipped"), f"битое фото: {ph}")
            db.close()
    finally:
        srv.shutdown()
    if fails:
        print("✗ фото на другом сайте:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ фото на другом сайте: выборка, битое фото - проверка всех, пауза в журнале, продолжение проверки")


if __name__ == "__main__":
    main()
