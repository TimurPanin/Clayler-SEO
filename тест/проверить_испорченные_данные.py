"""Автотест: испорченные данные страницы не пропадают молча (закон сохранения, ИНЖЕНЕРНЫЕ_ПРАВИЛА 1а; обзор/06, часть
1).
Настоящих случаев на 13 готовых базах 0 (06.11.2026), поэтому порча устраивается руками: сжатый текст, JSON. Отчёт
должен
собраться и показать служебный пункт «Данные, которые не прочитались», а целые страницы - остаться в проверках.
Запуск: py -3 тест/проверить_испорченные_данные.py, меньше минуты."""
import csv
import glob
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
from seocrawler.analyze import common  # noqa: E402

PORT = 8796
SITE = f"http://127.0.0.1:{PORT}/"
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def page(i):
    links = "".join(f'<a href="/p/{k}/">страница {k}</a> ' for k in range(1, 6))
    return (f"<html><head><title>Страница номер {i} на сайте</title><meta name=description content='описание {i}'>"
            f"</head><body><h1>Страница {i}</h1>"
            f"<p>{('текст страницы номер ' + str(i) + ' ') * 40}</p>{links}</body></html>").encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        code, body = 200, page(self.path)
        if self.path in ("/robots.txt", "/sitemap.xml") or self.path.startswith("/clayler"):
            code, body = 404, b"no"
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def unit():
    common.FAULTS.clear()
    check(common.unpack_blocks({"url": "u", "blocks": b"not zlib"}) is None, "испорченный текст - None")
    check(common.unpack_blocks({"url": "u", "blocks": None}) is None, "нет текста - None")
    check(common.page_json({"url": "u", "shop": "{плохой"}, "shop") is None, "испорченный JSON - None")
    check(common.page_json({"url": "u", "shop": '{"a": 1}'}, "shop") == {"a": 1}, "целый JSON читается")
    check(set(common.FAULTS) == {"текст страницы", "данные страницы (shop)"}, f"учёт: {common.FAULTS}")
    common.unpack_blocks({"url": "u", "blocks": b"not zlib"})
    check(len(common.FAULTS["текст страницы"][0]) == 1, "одну страницу прочитали дважды - страница одна")
    check("нет" not in common.FAULTS, "отсутствие данных - не порча")
    common.FAULTS.clear()


def main():
    unit()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
                   CLAYLER_NO_PDF="1",
                   CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        crawl = os.path.join(ROOT, "crawl.py")
        subprocess.run([sys.executable, crawl, SITE, "--no-open", "--delay", "0", "--no-images", "--no-external",
                        "--no-search-urls", "--no-exposed"], env=env, capture_output=True, timeout=300)
        folder = glob.glob(os.path.join(tmp, "127.0.0.1*"))[0]
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
        with db:
            db.execute("UPDATE pages SET blocks=x'00112233' WHERE url LIKE '%/p/1/'")
            db.execute("UPDATE pages SET shop='{плохой', schema_info='{плохой' WHERE url LIKE '%/p/2/'")
        db.close()
        os.remove(os.path.join(folder, ".анализ.pickle"))   # готовый анализ не знает о порче, сделанной руками
        r = subprocess.run([sys.executable, crawl, "--report", folder, "--no-open"], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        check(r.returncode == 0, f"отчёт не собрался: {r.stdout[-400:]} {r.stderr[-400:]}")
        path = os.path.join(folder, "проблемы", "data_fault.csv")
        if not os.path.exists(path):
            fails.append("нет служебного пункта «Данные, которые не прочитались»")
        else:
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = {x["Что"]: x for x in csv.DictReader(f, delimiter=";")}
            check("текст страницы" in rows and rows["текст страницы"]["Например"].endswith("/p/1/"),
                  f"порча текста: {rows}")
            check("данные страницы (shop)" in rows, f"порча shop: {rows}")
            check("данные страницы (schema_info)" in rows, f"порча schema_info: {rows}")
        with open(os.path.join(folder, "отчёт_для_клиента.html"), encoding="utf-8") as f:
            check("не прочитались" not in f.read(), "служебный пункт попал клиенту")
    srv.shutdown()
    if fails:
        print("✗ испорченные данные:\n   " + "\n   ".join(str(x)[:500] for x in fails))
        return 1
    print("✓ испорченные данные: отчёт собирается, порча видна служебным пунктом, клиенту не показывается")
    return 0


if __name__ == "__main__":
    sys.exit(main())
