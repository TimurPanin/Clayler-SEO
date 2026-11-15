"""Полнота отчёта (05.11.2026, ИНЖЕНЕРНЫЕ_ПРАВИЛА.md, раздел 1а, корень 3): каждый найденный адрес своего сайта -
проверен или стоит в «Что не проверено и почему» с причиной, а «проверено всё» - только когда непроверенного нет.
1. Закон сохранения раздела (coverage.ledger): на искусственной базе со всеми видами адресов, состояниями и причинами
   (и с неизвестными) и на всех готовых проверках из «отчёты» (только чтение) сумма строк учёта = все непроверенные
   адреса своего сайта, ничего не считается дважды и не теряется.
2. Обход: адрес из sitemap глубже предела не отбрасывается как ловушка (oidbearing.ru: 50 товаров из sitemap),
   а адрес глубже предела без sitemap - в разделе с причиной.
3. Страница, которую браузер не дождался, открывается ещё раз в конце обхода (crawler/extra_passes.recheck_js).
Запуск: py -3 тест/проверить_полноту.py (и из проверить_всё.py)."""
import glob
import json
import os
import re
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
from seocrawler import coverage  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

PORT = 8787
SITE = f"http://127.0.0.1:{PORT}/"
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class RO:
    """Готовая проверка только для чтения - как store для coverage.collect."""

    def __init__(self, path):
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    def get_meta(self, key, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default


def law(store, name):
    """Сумма строк раздела, взятых из учёта адресов, = все непроверенные адреса своего сайта."""
    led, _ = coverage.ledger(store.db)
    total = store.db.execute("SELECT COUNT(*) FROM urls WHERE internal=1").fetchone()[0]
    check(sum(led.values()) == total, f"{name}: в учёте {sum(led.values())} адресов, а своих в базе {total}")
    unchecked = sum(n for (g, b), n in led.items() if b != "checked")
    summ = store.get_meta("summary", {}) or {}
    cov = coverage.collect(store, {"pages": summ.get("pages", 0), "queue_left": summ.get("queue_left", 0)})
    shown = sum(r["n"] for r in cov["rows"] if r.get("ledger"))
    check(shown == unchecked, f"{name}: в разделе «Что не проверено» {shown} адресов, а непроверенных {unchecked}")
    if unchecked and any(b in ("left", "other", "broken") for (g, b), n in led.items() if n):
        check(not cov["all_done"], f"{name}: остались непроверенные адреса, а раздел пишет «проверено всё»")
    return cov


def synthetic(tmp):
    """Все виды адресов x все состояния x все причины, плюс неизвестная причина и неизвестный вид."""
    st = Store(os.path.join(tmp, "synthetic.db"))
    reasons = ["Закрыт в robots.txt (Disallow: /x)", "Больше 3 параметров в URL", "Глубина больше 50",
               "Повторяющийся путь (ловушка)", "URL длиннее 2000 символов", "Исключён правилом",
               "Копия сайта: открывается без редиректа, страницы копии не проверялись", "Проверка картинок выключена",
               "Совсем новая причина, которой нет в правилах", None]
    n = 0
    for kind in ("page", "sitemap", "resource", "новый_вид"):
        for state, why in [("done", None), ("done", "Сбой обработки: разобрана не вся страница"), ("queued", None),
                           ("fetching", None), ("странное", None)] + [("skipped", r) for r in reasons]:
            for k in range(1 + n % 3):   # разное число в ящиках - сумма не сойдётся случайно
                n += 1
                st.enqueue(f"{SITE}{kind}/{n}/{k}", 1, True, kind, SITE, state, why)
    st.enqueue("https://other.example/", 1, False, "external", SITE)   # чужой адрес в учёт своих не входит
    st.commit()
    cov = law(st, "искусственная база")
    titles = " | ".join(r["what"] for r in cov["rows"])
    for want in ("Не проверены по другой причине", "Картинки и файлы сайта: не успели проверить",
                 "Копия сайта", "Разобраны не целиком", "Адреса из sitemap, закрытые в robots.txt"):
        check(want in titles, f"искусственная база: нет строки «{want}» в разделе: {titles}")
    other = next((r for r in cov["rows"] if r["what"] == "Не проверены по другой причине"), {})
    check("Совсем новая причина" in other.get("why", ""), f"неизвестная причина не названа: {other}")
    check(not cov["all_done"], "искусственная база: раздел пишет «проверено всё»")
    st.db.close()


class H(BaseHTTPRequestHandler):
    hung = [0]

    def log_message(self, *a):
        pass

    def send(self, body, ctype="text/html; charset=utf-8", code=200):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:   # браузер не дождался и закрыл соединение - так и задумано
            pass

    def do_GET(self):
        p = self.path
        if p == "/robots.txt":
            return self.send(f"User-agent: *\nDisallow:\nSitemap: {SITE}sitemap.xml\n", "text/plain")
        if p == "/sitemap.xml":
            return self.send(f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                             f'<url><loc>{SITE}c3/</loc></url></urlset>', "application/xml")
        m = re.fullmatch(r"/(?:c(\d)/)?", p)
        if m:   # цепочка: главная → c1 → c2 → c3 (есть в sitemap) → c4 (нет)
            k = int(m.group(1) or 0)
            nxt = f'<a href="/c{k + 1}/">дальше</a>' if k < 4 else ""
            slow = '<a href="/slow/">медленная</a>' if k == 0 else ""
            return self.send(f"<html><head><title>Шаг {k}</title></head><body><h1>Шаг {k}</h1>"
                             f"<p>Текст страницы номер {k} для проверки полноты.</p>{nxt}{slow}</body></html>")
        if p == "/slow/":
            return self.send('<html><head><title>Медленная</title><script src="/hang.js"></script></head>'
                             '<body><h1>Медленная</h1><p>Страница со скриптом.</p></body></html>')
        if p == "/hang.js":
            # браузер (Sec-Fetch-Dest: script) в первый раз ждёт дольше срока вкладки, потом - сразу
            if self.headers.get("Sec-Fetch-Dest") == "script" and H.hung[0] == 0:
                H.hung[0] = 1
                time.sleep(35)
            return self.send("document.title='Медленная';", "application/javascript")
        self.send("", code=404)


def crawl(tmp, *extra):
    env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8",
               PYTHONUTF8="1")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE, "--no-open", "--delay", "0",
                        "--no-images", "--no-external", "--no-search-urls", "--no-exposed", *extra],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    folder = (sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*"))) or [""])[-1]
    return r, folder


def depth_and_js(tmp):
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r, folder = crawl(os.path.join(tmp, "d"), "--depth", "2")
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
        st = {u: (s, why) for u, s, why in db.execute("SELECT url, state, skip_reason FROM urls")}
        db.close()
        check(st.get(SITE + "c3/", ("",))[0] == "done",
              f"адрес из sitemap глубже предела не проверен: {st.get(SITE + 'c3/')} {r.stdout[-300:]}")
        check(st.get(SITE + "c4/", ("", ""))[1] == "Глубина больше 2", f"глубже предела без sitemap: {st.get(SITE + 'c4/')}")
        cov = law(RO(os.path.join(folder, "crawl.db")), "обход с пределом глубины")
        check(any(x["what"] == "Слишком глубоко от главной" and x["n"] == 1 for x in cov["rows"]),
              f"нет строки «Слишком глубоко от главной» - 1: {cov['rows']}")

        from seocrawler import renderer
        ok, why = renderer.available()
        if not ok:
            print(f"   (браузер недоступен: {why} - повторное открытие в браузере не проверено)")
            return
        H.hung[0] = 0   # снимок страницы на телефоне в первом обходе тоже открывал браузер
        r, folder = crawl(os.path.join(tmp, "j"), "--js", "--js-wait", "1", "--no-sitemap")
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
        row = db.execute("SELECT js_error, js_time FROM pages WHERE url=?", (SITE + "slow/",)).fetchone()
        meta = db.execute("SELECT value FROM meta WHERE key='js_rechecked'").fetchone()
        db.close()
        out = r.stdout + r.stderr
        check(meta and json.loads(meta[0]) == {"checked": 1, "fixed": 1},
              f"страницу, которую браузер не дождался, ещё раз не открыли: {meta} {out[-600:]}")
        check(row and not row[0] and row[1], f"после повторного открытия у страницы ошибка браузера: {row}")
        check("со второго раза в браузере открылись 1 из 1" in out, "в журнале нет итога повторного открытия")
        law(RO(os.path.join(folder, "crawl.db")), "обход с JavaScript")
    finally:
        srv.shutdown()


def main():
    tmp = tempfile.mkdtemp(prefix="clayler_full_")
    synthetic(tmp)
    n = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "отчёты", "*", "crawl.db"))):
        try:
            law(RO(path), os.path.basename(os.path.dirname(path)))
            n += 1
        except sqlite3.Error as e:   # база занята идущей проверкой - не повод падать
            print(f"   (не прочитана {os.path.basename(os.path.dirname(path))}: {e})")
    depth_and_js(tmp)
    if fails:
        print("✗ полнота:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ полнота: закон сохранения раздела «Что не проверено» на искусственной базе и {n} готовых проверках, "
          "адрес из sitemap глубже предела проверен, страница, которую браузер не дождался, открыта ещё раз")


if __name__ == "__main__":
    main()
