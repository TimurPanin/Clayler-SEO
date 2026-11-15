"""Прокси Windows от выключенного VPN (адрес остался, прокси не отвечает): обход сайта и запросы к службам идут
напрямую. Было: напрямую ходили только «Подключения» и подсказки, а обход, орфография,
Telegram, Букварикс, обновления поиска и др. падали с «WinError 10061 … actively refused it»."""
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><head><title>ok</title></head><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=srv.serve_forever, daemon=True).start()
site = f"http://127.0.0.1:{srv.server_address[1]}/"
dead = f"http://127.0.0.1:{free_port()}"
# только прокси из окружения, без исключений для 127.0.0.1: иначе тестовый сайт и так шёл бы напрямую
for k in list(os.environ):
    if k.lower() in ("http_proxy", "https_proxy", "no_proxy", "all_proxy"):
        del os.environ[k]
os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = dead

from seocrawler import sysproxy  # noqa: E402
from seocrawler.fetcher import Fetcher  # noqa: E402

bad = []
live = sysproxy.live_proxies()
if live.get("http"):
    bad.append(f"мёртвый прокси не отброшен: {live}")
r = Fetcher("Mozilla/5.0").fetch(site)
if r.status != 200:
    bad.append(f"обход через мёртвый прокси: {r.status} {r.error}")
f = Fetcher("Mozilla/5.0")
f.keep_alive = False   # путь через urllib (прокси с паролем, CLAYLER_NO_KEEPALIVE)
r = f.fetch(site)
if r.status != 200:
    bad.append(f"обход через urllib и мёртвый прокси: {r.status} {r.error}")
try:
    with sysproxy.urlopen(site, 10) as resp:
        if resp.status != 200:
            bad.append(f"запрос к службе: {resp.status}")
except Exception as e:
    bad.append(f"запрос к службе через мёртвый прокси: {e}")
# все запросы к службам - через sysproxy.urlopen (окно ходит только к себе на 127.0.0.1 - его не смотрим)
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seocrawler")
for d, dirs, fs in os.walk(ROOT):
    dirs[:] = [x for x in dirs if x != "window"]
    for name in fs:
        if name.endswith(".py") and name != "sysproxy.py":
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                if "urllib.request.urlopen(" in fh.read():
                    bad.append(f"{os.path.relpath(os.path.join(d, name), ROOT)}: urllib.request.urlopen мимо sysproxy")
srv.shutdown()

# свой компьютер - всегда без прокси, даже живого (в исключениях VPN Throne только «*.local»: 127.0.0.1 уходил в
# прокси с ответом 502, тестовые сайты и «программа уже открыта» не работали)
from seocrawler import sysproxy as SP  # noqa: E402
from seocrawler.fetcher import Fetcher  # noqa: E402
for h, want in (("127.0.0.1", True), ("localhost", True), ("::1", True), ("127.12.0.5", True), ("show.localhost", True),
                ("127.ru", False), ("site.ru", False), ("", False)):
    if SP.is_local(h) != want:
        bad.append(f"is_local({h!r}) = {not want}")
f = Fetcher("t")
f._proxies = {"http": "http://127.0.0.1:2080", "https": "http://127.0.0.1:2080"}
if f._proxy_for("http", "127.0.0.1") is not None:
    bad.append("загрузчик шлёт 127.0.0.1 через прокси")
if f._proxy_for("https", "site.ru") != ("127.0.0.1", 2080):
    bad.append("загрузчик перестал брать прокси для обычного сайта")
# запасной путь загрузчика (urllib: проверка 304, прокси с паролем) - тоже напрямую, даже с живым прокси, который
# на всё отвечает 502 (так отвечал прокси VPN на 127.0.0.1; эталоны всех тестовых сайтов)
class Proxy502(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(502)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


psrv = HTTPServer(("127.0.0.1", 0), Proxy502)
srv2 = HTTPServer(("127.0.0.1", 0), Site)
for s_ in (psrv, srv2):
    threading.Thread(target=s_.serve_forever, daemon=True).start()
paddr = f"http://127.0.0.1:{psrv.server_address[1]}"
f = Fetcher("t")
from seocrawler.sysproxy import LocalDirect  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
f.opener = urllib.request.build_opener(LocalDirect({"http": paddr, "https": paddr}))
f.keep_alive = False
r = f.fetch(f"http://127.0.0.1:{srv2.server_address[1]}/")
if r.status != 200:
    bad.append(f"запасной путь загрузчика шлёт 127.0.0.1 через прокси: {r.status}")
try:   # обычный сайт - через прокси, как раньше
    code = urllib.request.build_opener(LocalDirect({"http": paddr})).open("http://site.example/", timeout=5).status
except urllib.error.HTTPError as e:
    code = e.code
if code != 502:
    bad.append(f"запасной путь загрузчика перестал брать прокси для обычного сайта: {code}")
psrv.shutdown()
srv2.shutdown()

if bad:
    print("ОШИБКИ:\n" + "\n".join(bad))
    sys.exit(1)
print("Прокси выключенного VPN: обход и службы идут напрямую - всё в порядке")
