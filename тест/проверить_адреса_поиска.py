"""Автотест: адреса из Яндекс Вебмастера и Google Search Console попадают в обход (crawler/sitemaps.py,
check_search_urls), страницы без ссылок - в проблему «Страницы, которые знает поиск, но на сайте на них нет ссылок»
(analyze/checks/search_urls.py). Яндекс и Google - поддельный сервер, сайт - тест/testsite.py.
Запуск: py -3 тест/проверить_адреса_поиска.py"""
import csv
import glob
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = 8790
SITE = f"http://127.0.0.1:{PORT}"


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def out(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/v4/user":
            return self.out({"user_id": 1})
        if path == "/v4/user/1/hosts":
            return self.out({"hosts": [{"host_id": f"http:127.0.0.1:{PORT}", "verified": True,
                                        "ascii_host_url": SITE + "/"}]})
        if path.endswith("/search-urls/in-search/samples"):
            return self.out({"samples": [{"url": SITE + "/catalog/item-77"}, {"url": SITE + "/about/"},
                                         {"url": "https://чужой-сайт.рф/x"}]})
        if path == "/webmasters/v3/sites":
            return self.out({"siteEntry": [{"siteUrl": SITE + "/", "permissionLevel": "siteOwner"}]})
        return self.out({}, 404)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if urlsplit(self.path).path.endswith("/searchAnalytics/query"):
            return self.out({"rows": [{"keys": [SITE + "/catalog/item-88"], "impressions": 40},
                                      {"keys": [SITE + "/catalog/item-77"], "impressions": 5},
                                      {"keys": [SITE + "/old"], "impressions": 9}]})
        return self.out({}, 404)


def main():
    fails = []
    tmp = tempfile.mkdtemp(prefix="clayler-search-")
    api = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    acc = os.path.join(tmp, "доступы.json")
    os.environ["CLAYLER_ACCOUNTS_FILE"] = acc
    from seocrawler import accounts, search_console, webmaster
    # без входа: шаг тихо пропускается
    open(acc, "w", encoding="utf-8").write("{}")
    if webmaster.known_urls(SITE)[0] != "not_connected" or search_console.known_urls(SITE)[0] != "not_connected":
        fails.append("без входа состояние должно быть «не подключено»")
    far = time.time() + 86400
    open(acc, "w", encoding="utf-8").write(json.dumps({
        "yandex": {"token": accounts.seal("Y"), "expires": far, "user_id": 1},
        "google": {"token": accounts.seal("G"), "expires": far}}))
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_REPORTS=tmp,
               CLAYLER_OAUTH_TEST=f"http://127.0.0.1:{api.server_port}", CLAYLER_NO_PROBLEM_SHOTS="1")
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "testsite.py"), str(PORT)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(SITE + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE + "/", "--no-open", "--delay", "0"],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    finally:
        srv.terminate()
        api.shutdown()
    folders = sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*")))
    if r.returncode != 0 or not folders:
        print("✗ адреса из поиска: программа завершилась с ошибкой\n" + (r.stdout + r.stderr)[-1500:])
        sys.exit(1)
    from seocrawler.storage import Store
    store = Store(os.path.join(folders[-1], "crawl.db"))
    meta = store.get_meta("search_urls", {}) or {}
    src = meta.get("sources") or {}
    if (src.get("yandex") or {}).get("n") != 2 or (src.get("google") or {}).get("n") != 3:
        fails.append(f"адресов из Вебмастера и Search Console: {src} (ждали 2 и 3, чужой сайт отброшен)")
    for u in ("/catalog/item-77", "/catalog/item-88"):
        st = store.db.execute("SELECT status FROM pages WHERE url=?", (SITE + u,)).fetchone()
        if not st or st[0] != 200:
            fails.append(f"{u} не проверен при обходе")
    rows = list(csv.reader(open(os.path.join(folders[-1], "проблемы.csv"), encoding="utf-8-sig"), delimiter=";"))
    got = {x[2]: x[3] for x in rows[1:]}
    title = "Страницы, которые знает поиск, но на сайте на них нет ссылок"
    if got.get(title) != "2":  # item-77 и item-88; /about/ со ссылками, /old - редирект
        fails.append(f"«{title}»: {got.get(title)} (ждали 2)")
    if fails:
        print("✗ адреса из поиска:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ адреса из Вебмастера и Search Console: страницы без ссылок проверены и показаны в отчёте")


if __name__ == "__main__":
    main()
