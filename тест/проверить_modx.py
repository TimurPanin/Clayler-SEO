"""Автотест: проверки безопасности MODX и настройки вкладок браузера (06.11.2026). Тестовый сайт без сети:
- MODX с забытым setup/, открытой папкой core, копией настроек и входом /manager/ - всё находится;
- сайт на MODX, отдающий на любой адрес главную (как nabiullin.com), - ничего ложного;
- сайт не на MODX - эти адреса не проверяются;
- вкладки: обычная и быстрая скорость - 6 и потоков на 2 больше, «Бережно» - 3 и потоки прежние.
Запуск: py -3 тест/проверить_modx.py"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import security  # noqa: E402
from seocrawler.crawler.common import js_load  # noqa: E402

PORT = 8799
SITE = f"http://127.0.0.1:{PORT}/"
MODE = {"name": "open"}
SEEN = []
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


HOME = b'<html><head><title>Site</title><link href="/assets/components/x.css"></head><body>MODX home</body></html>'
PLAIN = b"<html><head><title>Plain site</title></head><body>home</body></html>"
OPEN = {
    "/setup/": b"<html><head><title>MODX Revolution 2.8 &raquo; Install</title></head><body>install</body></html>",
    "/core/docs/changelog.txt": b"This file shows the changes in recent releases of MODX.",
    "/core/config/config.inc.php.bak": b"<?php\n$database_user = 'u';\n$database_password = 'p';\n",
    "/manager/": b'<html><head><title>MODX</title></head><body><form><input type="password" '
    b'name="password"></form></body></html>',
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN.append(self.path)
        mode = MODE["name"]
        code, body = 200, HOME
        if mode == "plain":
            code, body = (200, PLAIN) if self.path == "/" else (404, b"no")
        elif mode == "open" and self.path != "/":
            code, body = (200, OPEN[self.path]) if self.path in OPEN else (404, b"no")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(mode):
    MODE["name"] = mode
    SEEN.clear()
    return security.check(SITE, None, True, lambda *_: None)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    sec = run("open")
    what = {f["what"] for f in sec["found"]}
    check("установщик движка MODX (папка setup)" in what, f"setup: {what}")
    check("служебная папка движка MODX открыта (core)" in what, f"core: {what}")
    check(any("config.inc.php.bak" in f["url"] for f in sec["found"]), f"копия настроек: {sec['found']}")
    check(sec.get("modx_manager", "").endswith("/manager/"), f"вход: {sec.get('modx_manager')}")

    sec = run("any_home")
    check(not [f for f in sec["found"] if "MODX" in f["what"] or "config.inc" in f["url"]],
          f"ложная находка: {sec['found']}")
    check(not sec.get("modx_manager"), f"ложный вход: {sec.get('modx_manager')}")

    run("plain")
    check(not [p for p in SEEN if "/core/" in p or p == "/setup/" or p == "/manager/"], f"не MODX, а проверяли: {SEEN}")

    check(js_load(0.2, 4) == (6, 8), f"обычная скорость: {js_load(0.2, 4)}")
    check(js_load(0.05, 8) == (6, 8), f"быстрая скорость: {js_load(0.05, 8)}")
    check(js_load(1, 2) == (3, 2), f"«Бережно»: {js_load(1, 2)}")
    check(js_load(0.2, 4, 2) == (2, 4), f"своё число вкладок: {js_load(0.2, 4, 2)}")
    check(js_load(0.2, 2, 3) == (3, 2), f"конкурент: потоки не растут: {js_load(0.2, 2, 3)}")
    srv.shutdown()
    if fails:
        print("✗ MODX:\n   " + "\n   ".join(str(x)[:400] for x in fails))
        return 1
    print("✓ MODX: setup, core, копия настроек и вход находятся, главная на любой адрес - без ложных находок; вкладки "
          "браузера")
    return 0


if __name__ == "__main__":
    sys.exit(main())
