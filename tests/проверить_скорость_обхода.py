"""Скорость обхода: ссылки на другие сайты проверяются выборкой (до N на сайт и до M адресов, которые отличаются
только параметрами, как кнопки «Поделиться»), картинки сайта не открывают новое соединение на каждый файл,
у своих файлов и у чужих сайтов свои паузы. Плюс: продолжение старой проверки снимает лишние ссылки из очереди.
Запуск: python tests/проверить_скорость_обхода.py (и из проверить_всё.py)."""
import glob
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PAGES, LINKS, CAP, PATH_CAP = 30, 5, 40, 5
os.environ["CLAYLER_EXT_LINKS_CAP"] = str(CAP)
os.environ["CLAYLER_EXT_PATH_CAP"] = str(PATH_CAP)
PORT = 8773
SITE = f"http://127.0.0.1:{PORT}"
EXT = f"http://localhost:{PORT}"  # тот же сервер под другим именем — для программы это другой сайт
IMG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") * 2 + b"\x08\x02\x00\x00\x00" \
    + b"0" * 100_000  # 100 КБ: больше, чем программа читает, чтобы узнать размеры картинки
STAT = {"conn": 0, "req": 0}
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def setup(self):
        STAT["conn"] += 1
        super().setup()

    def send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        STAT["req"] += 1
        p = self.path
        if p.startswith("/img/"):
            return self.send(200, "image/png", IMG)
        if p.startswith("/share") or p.startswith("/ext/"):
            return self.send(200, "text/html; charset=utf-8", b"<html><body>ok</body></html>")
        if p == "/robots.txt":
            return self.send(200, "text/plain", b"")
        if p == "/":
            html = "".join(f'<a href="/p{i}">Товар {i}</a> ' for i in range(PAGES))
        elif p.startswith("/p") and p[2:].isdigit():
            n = int(p[2:])
            html = (f'<img src="/img/{n}.png" alt="Фото"> <a href="{EXT}/share?url={SITE}/p{n}">Поделиться</a> '
                    + "".join(f'<a href="{EXT}/ext/{n}-{k}">Ссылка {k}</a> ' for k in range(LINKS)))
        else:
            return self.send(404, "text/plain", b"")
        html = f"<html><head><title>Стр {p}</title></head><body><h1>Магазин</h1>{html}</body></html>"
        self.send(200, "text/html; charset=utf-8", html.encode("utf-8"))


def crawl(tmp):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_REPORTS=tmp, NO_PROXY="*", no_proxy="*")
    before = set(glob.glob(os.path.join(tmp, "*")))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE + "/", "--no-open", "--delay", "0"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    new = sorted(set(glob.glob(os.path.join(tmp, "*"))) - before)
    if r.returncode != 0 or not new:
        fails.append("программа завершилась с ошибкой: " + (r.stdout + r.stderr)[-800:])
        return None, None
    return new[-1], sqlite3.connect(os.path.join(new[-1], "crawl.db"))


def unit_checks():
    from seocrawler.crawler.queue import QueueMixin, EXT_LINK_SKIP
    from seocrawler.crawler import Crawler
    from seocrawler.crawler.common import Config
    from seocrawler.storage import Store
    tmp = tempfile.mkdtemp(prefix="clayler-speed-")
    # продолжение старой проверки: ссылки сверх выборки снимаются из очереди
    st = Store(os.path.join(tmp, "crawl.db"))
    for i in range(CAP + 30):
        st.enqueue(f"https://sub.shop.test/hotel/{i}", 1, False, "external", "https://shop.test/p",
                   "done" if i < CAP - 10 else "queued")
    for i in range(30):
        st.enqueue(f"https://vk.com/share.php?url=https://shop.test/p{i}", 1, False, "external", "https://shop.test/p")
    st.enqueue("https://img.cdn.test/a.webp", 1, False, "external", "https://shop.test/p")  # старое фото — не трогаем
    st.commit()

    class D(QueueMixin):
        pass
    d = D()
    d.store, d.log, d.root_host = st, lambda m: None, "www.shop.test"
    d._ext_links()
    q = dict(st.db.execute("SELECT substr(url, 1, 18), COUNT(*) FROM urls WHERE state='queued' GROUP BY 1"))
    check(q == {"https://sub.shop.t": 10, "https://vk.com/sha": PATH_CAP, "https://img.cdn.te": 1},
          f"продолжение: в очереди осталось {q}")
    check(d.ext_links_sample() == {"поддомены shop.test": [CAP, 30], "vk.com": [PATH_CAP, 30 - PATH_CAP]},
          f"продолжение: выборка {d.ext_links_sample()}")
    n = st.db.execute("SELECT COUNT(*) FROM urls WHERE skip_reason LIKE ?", (EXT_LINK_SKIP + "%",)).fetchone()[0]
    check(n == 30 + 30 - PATH_CAP, f"продолжение: с причиной пропуска {n}")
    st.db.close()
    # паузы: страницы, свои файлы и каждый чужой сайт — порознь
    c = Crawler(Config(start_url="https://shop.test/"), os.path.join(tmp, "c.db"), log=lambda m: None)
    lp, lr = c.limiter_for("https://shop.test/a", True, "page"), c.limiter_for("https://shop.test/i.png", True, "resource")
    la, lb = c.limiter_for("https://vk.com/x", False, "external"), c.limiter_for("https://t.me/x", False, "external")
    check(lp is c.limiter and lr is c.res_limiter and len({id(lp), id(lr), id(la), id(lb)}) == 4
          and c.limiter_for("https://vk.com/y", False, "external") is la, "паузы не разделены")
    # страниц больше нет: картинки берут ту очередь пауз, что освободится раньше (обе по очереди), страницы - свою
    c.pages_idle = True
    c.res_limiter.next_at, c.limiter.next_at = 100.0, 50.0
    check(c.limiter_for("https://shop.test/i.png", True, "resource") is c.limiter, "картинки после страниц - нет второй очереди")
    c.res_limiter.next_at, c.limiter.next_at = 50.0, 100.0
    check(c.limiter_for("https://shop.test/i.png", True, "resource") is c.res_limiter, "картинки после страниц - своя очередь")
    check(c.limiter_for("https://shop.test/a", True, "page") is c.limiter, "страница после страниц - чужая очередь")
    c.pages_idle = False
    c.res_limiter.next_at, c.limiter.next_at = 100.0, 50.0
    check(c.limiter_for("https://shop.test/i.png", True, "resource") is c.res_limiter, "картинки забрали очередь страниц")
    c.store.db.close()


def main():
    unit_checks()
    tmp = tempfile.mkdtemp(prefix="clayler-speed-")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        folder, db = crawl(tmp)
        if db:
            ext = dict(db.execute("SELECT state, COUNT(*) FROM urls WHERE internal=0 AND kind='external' GROUP BY state"))
            total = PAGES * (LINKS + 1)
            check(ext.get("done") == CAP and ext.get("skipped") == total - CAP, f"выборка ссылок: {ext}")
            share = dict(db.execute("SELECT state, COUNT(*) FROM urls WHERE url LIKE ? GROUP BY state", (EXT + "/share%",)))
            check(share.get("done", 0) <= PATH_CAP, f"«Поделиться»: проверено {share}")
            sample = json.loads(db.execute("SELECT value FROM meta WHERE key='ext_links_sample'").fetchone()[0])
            check(sample == {"localhost": [CAP, total - CAP]}, f"выборка ссылок: meta {sample}")
            img = db.execute("SELECT p.status, p.img_width FROM urls u JOIN pages p ON p.url=u.url "
                             "WHERE u.internal=1 AND u.kind='resource'").fetchall()
            check(len(img) == PAGES and all(r == (200, 64) for r in img), f"картинки: {img[:3]}")
            html = open(os.path.join(folder, "отчёт.html"), encoding="utf-8").read()
            check("Ссылки на другие сайты - проверены выборочно" in html, "нет строки о выборке ссылок в отчёте")
            # картинки 100 КБ дочитываются, и соединение используется дальше, а не открывается на каждый файл
            check(STAT["conn"] * 3 < STAT["req"], f"соединений {STAT['conn']} на {STAT['req']} запросов")
            # время по этапам: обход и перепроверка записаны, вместе не больше всей работы
            tm = json.loads((db.execute("SELECT value FROM meta WHERE key='timings'").fetchone() or ["{}"])[0])
            work = float(json.loads(db.execute("SELECT value FROM meta WHERE key='work_seconds'").fetchone()[0]))
            check("обход: страницы, картинки, ссылки" in tm and "перепроверка ошибок" in tm
                  and sum(tm.values()) <= work + 2, f"время по этапам: {tm}, всего {work}")
            db.close()
    finally:
        srv.shutdown()
    if fails:
        print("✗ скорость обхода:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ скорость обхода: выборка ссылок на другие сайты, соединения ({STAT['conn']} на {STAT['req']} запросов), "
          "паузы порознь, продолжение проверки")


if __name__ == "__main__":
    main()
