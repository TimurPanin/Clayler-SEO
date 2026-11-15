"""Автотест надёжности загрузки (ревизия кода, без интернета, тестовый сервер на 127.0.0.1):
- распаковка gzip/deflate с пределом: обычный, испорченный, оборванный, «бомба» (мало сжатого - много текста),
  несколько gzip подряд, мусор после архива; загрузчик ставит «обрезано» или ошибку, а не тихую пустую страницу;
- Retry-After числом и датой (RFC 9110), прошлая дата, мусор;
- пауза между запросами: «Стоп» прерывает ожидание; пауза, о которой попросил сервер (429/503), задерживает
  и потоки, уже занявшие очередь;
- work после «Стоп» не делает ни одного запроса;
- упавшая часть разбора HTML видна в parse_errors, остальной разбор работает.
Запуск: py -3 tests/проверить_надёжность_загрузки.py (и из проверить_всё.py)."""
import email.utils
import gzip
import os
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import fetcher as F  # noqa: E402
from seocrawler import parser as P  # noqa: E402
from seocrawler.crawler.common import RateLimiter, retry_after  # noqa: E402
from seocrawler.crawler.page import PageMixin, STOPPED  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


HTML = ("<html><head><title>Страница</title></head><body><h1>Заголовок</h1>"
        + "<p>текст страницы</p>" * 2000 + "</body></html>").encode("utf-8")
GZ = gzip.compress(HTML)

# ---------- распаковка
body, bad = F._unpack(GZ, "gzip")
check(body == HTML and bad == "", f"обычный gzip: {len(body)} {bad!r}")
body, bad = F._unpack(zlib.compress(HTML), "deflate")
check(body == HTML and bad == "", f"deflate с заголовком: {bad!r}")
co = zlib.compressobj(wbits=-zlib.MAX_WBITS)
body, bad = F._unpack(co.compress(HTML) + co.flush(), "deflate")
check(body == HTML and bad == "", f"deflate без заголовка: {bad!r}")
body, bad = F._unpack(GZ[: len(GZ) // 2], "gzip")
check(bad == "broken" and 0 < len(body) < len(HTML) and HTML.startswith(body), f"оборванный gzip: {len(body)} {bad!r}")
body, bad = F._unpack(GZ[:10] + b"\x00garbage" * 50, "gzip")
check(bad == "broken" and body == b"", f"испорченный gzip: {len(body)} {bad!r}")
bomb = gzip.compress(b"\0" * 3_000_000)
body, bad = F._unpack(bomb, "gzip", limit=1_000_000)
check(bad == "big" and len(body) == 1_000_000, f"бомба: {len(body)} {bad!r} (сжато {len(bomb)} байт)")
body, bad = F._unpack(gzip.compress(b"aaa") + gzip.compress(b"bbb"), "gzip")
check(body == b"aaabbb" and bad == "", f"два gzip подряд: {body!r} {bad!r}")
body, bad = F._unpack(gzip.compress(b"aaa") + b"garbage", "gzip")
check(body == b"aaa" and bad == "", f"мусор после gzip: {body!r} {bad!r}")
check(F._unpack(b"", "gzip") == (b"", "") and F._unpack(b"x", "") == (b"x", ""), "пустой ответ и без сжатия")
check(F._decompress(GZ, "gzip") == HTML, "_decompress (site_tech) как раньше")


# ---------- загрузчик на тестовом сервере
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # соединение остаётся открытым: загрузчик берёт его повторно (keep-alive)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/trickle":   # заголовки по байту: таймаут сокета не срабатывает никогда
            try:
                self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                for _ in range(60):
                    time.sleep(0.5)
                    self.wfile.write(b"a")
                    self.wfile.flush()
            except OSError:
                pass
            self.close_connection = True
            return
        data = {"/ok": GZ, "/cut": GZ[: len(GZ) // 2], "/broken": GZ[:10] + b"\x00" * 300,
                "/bomb": bomb}.get(self.path, b"")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
f = F.Fetcher("test")
r = f.fetch(base + "/ok")
check(r.body == HTML and not r.truncated and not r.error, f"/ok: {len(r.body)} {r.truncated} {r.error!r}")
r = f.fetch(base + "/cut")
check(r.truncated and r.body and not r.error, f"/cut - обрывок с пометкой «обрезано»: {len(r.body)} {r.truncated} {r.error!r}")
r = f.fetch(base + "/broken")
check(r.error == F.UNPACK_ERROR and not r.body, f"/broken - ошибка, а не пустая страница: {r.error!r}")
old = F.UNPACK_MAX
F.UNPACK_MAX = 1_000_000
r = f.fetch(base + "/bomb")
F.UNPACK_MAX = old
check(r.truncated and len(r.body) == 1_000_000 and not r.error, f"/bomb - не больше предела: {len(r.body)} {r.truncated}")
r = f.fetch(base + "/broken", read_body=False)
check(not r.error, f"без чтения тела битое сжатие не ошибка (картинки, редиректы): {r.error!r}")
t = time.monotonic()
r = F.Fetcher("test", timeout=1, total_timeout=1).fetch(base + "/trickle")
took = time.monotonic() - t
check(took < 9 and r.error.startswith("Загрузка дольше 7 с"), f"жёсткий срок 1 + 1 + 5 с на заголовки по капле: {took:.1f} с, {r.error!r}")
# то же по уже открытому соединению: обрыв от сторожа - не «сервер закрыл простаивавшее соединение», без повтора
# по новому соединению (там срока уже не было бы -)
g = F.Fetcher("test", timeout=1, total_timeout=1)
g.fetch(base + "/ok")
t = time.monotonic()
r = g.fetch(base + "/trickle")
took = time.monotonic() - t
check(took < 9 and r.error.startswith("Загрузка дольше 7 с"), f"жёсткий срок на открытом соединении: {took:.1f} с, {r.error!r}")
r = f.fetch(base + "/ok")
check(r.body == HTML and not r.error, f"после прерванного запроса загрузчик работает: {r.error!r}")
# ссылку записали криво - пробелы и скобки в имени сайта (reestr-719.ru): ошибка адреса, а не английская ошибка связи
for bad in ("http://xn-- 878 (https-2nja//reestr-719.ru/pp878/", "https://ex ample.ru/"):
    r = f.fetch(bad)
    check(r.error.startswith("Неправильный адрес"), f"кривое имя сайта {bad!r}: {r.error!r}")
srv.shutdown()

# ---------- Retry-After
check(retry_after("5") == 5 and retry_after("120") == 60 and retry_after("0") == 1, "Retry-After числом")
soon = email.utils.formatdate(time.time() + 30, usegmt=True)
check(28 <= retry_after(soon) <= 31, f"Retry-After датой: {retry_after(soon)} ({soon})")
check(retry_after(email.utils.formatdate(time.time() - 600, usegmt=True)) == 1, "Retry-After прошлой датой")
check(retry_after(email.utils.formatdate(time.time() + 86400, usegmt=True)) == 60, "Retry-After далёкой датой")
check(retry_after("скоро") == 10 and retry_after("") == 10 and retry_after(None) == 10, "Retry-After непонятный")

# ---------- пауза: «Стоп» и просьба сервера подождать
lim = RateLimiter(5.0)
lim.wait()
stop = threading.Event()
threading.Timer(0.3, stop.set).start()
t = time.monotonic()
ok = lim.wait(stop.is_set)
check(ok is False and time.monotonic() - t < 2.5, f"«Стоп» прерывает паузу 5 с: {ok}, {time.monotonic() - t:.1f} с")

lim = RateLimiter(0.3)
lim.wait()
went = []
th = threading.Thread(target=lambda: (lim.wait(), went.append(time.monotonic())))
t = time.monotonic()
th.start()
time.sleep(0.05)       # поток уже занял время (через 0,3 с) и спит
lim.backoff(1.5)       # тут сервер ответил 429
th.join(10)
check(went and went[0] - t >= 1.4, f"занявший очередь поток ждёт и паузу сервера: {went[0] - t if went else None:.2f} с")


# ---------- work() после «Стоп»
class NoNet:
    def fetch(self, *a, **kw):
        raise AssertionError("запрос после «Стоп»")


class Fake(PageMixin):
    def __init__(self):
        class C:
            retries = 2
        self.cfg, self.stop_flag, self.fetcher = C(), True, NoNet()
        self.limiter = self.res_limiter = RateLimiter(0.1)

    def limiter_for(self, *a):
        return self.limiter


try:
    r, parsed = Fake().work("http://127.0.0.1/x", True, "page")
    check(r.error == STOPPED and parsed is None, f"work после «Стоп»: {r.error!r}")
except AssertionError as e:
    fails.append(f"work: {e}")


# ---------- упавшая часть разбора HTML
class Boom(P._ShopFacts):
    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            raise KeyError("x")
        return super().handle_starttag(tag, attrs)


real = P._ShopFacts
P._ShopFacts = Boom
try:
    p = P.parse_html(HTML, "text/html; charset=utf-8")
finally:
    P._ShopFacts = real
check(p["parse_errors"] and "KeyError" in p["parse_errors"][0] and p["titles"] == ["Страница"]
      and p["h1"] == ["Заголовок"], f"сбой части разбора: {p['parse_errors']}, {p['titles']}, {p['h1']}")
check(P.parse_html(HTML)["parse_errors"] == [], "обычная страница без ошибок разбора")

# ---------- страница-обрывок (код 200 с ошибкой загрузки) не идёт в проверки как обычная (analyze/prepare.html_ok)
import tempfile  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from seocrawler.analyze import prepare  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

tmp = tempfile.mkdtemp(prefix="clayler_obryvok_")
st = Store(os.path.join(tmp, "crawl.db"))
for u, err in (("http://t.ru/", ""), ("http://t.ru/slow", "Загрузка дольше 30 с - прервана"),
               ("http://t.ru/gz", F.UNPACK_ERROR)):
    st.enqueue(u, 0, 1, "page", "")
    st.save_page({"url": u, "status": 200, "error": err, "content_type": "text/html", "indexable": 0 if err else 1})
st.commit()
ctx = SimpleNamespace(store=st)
prepare.run(ctx)
check([p["url"] for p in ctx.html_ok] == ["http://t.ru/"], f"обрывки в html_ok: {[p['url'] for p in ctx.html_ok]}")
st.db.close()

if fails:
    print("✗ надёжность загрузки:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ надёжность загрузки: распаковка с пределом, Retry-After датой, «Стоп» в паузе и повторах, ошибки разбора")
