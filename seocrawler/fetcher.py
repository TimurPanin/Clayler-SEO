"""Загрузчик. Редиректы не проходит сам — каждый шаг записывается отдельно.
Ошибки без ответа различаются по типу: DNS, SSL, отказ, таймаут.
Соединение с сайтом держится открытым (keep-alive): следующий адрес того же сайта идёт по нему же,
без нового подключения и TLS. Если в Windows настроен прокси — загрузка идёт как раньше, через urllib."""
import collections
import os
import re
import http.client
import socket
import ssl
import threading
import time
import zlib
import urllib.request
from urllib.parse import urlsplit
import urllib.error
from dataclasses import dataclass, field
from urllib.parse import urlsplit

HTML_TYPES = ("text/html", "application/xhtml+xml")
REDIRECTS = (301, 302, 303, 307, 308)

UA_PRESETS = {
    "crawler": "Mozilla/5.0 (compatible; ClaylerSEO/1.0)",
    "googlebot": "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36 "
                 "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "yandexbot": "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "phone": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
}


@dataclass
class Response:
    url: str
    status: int = 0
    reason: str = ""
    error: str = ""          # тип ошибки, если ответа нет
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    elapsed: float = 0.0
    ttfb: float = 0.0        # время до ответа сервера (заголовки получены), без скачивания тела
    size: int = 0            # байт передано (до распаковки)
    truncated: bool = False
    size_measured: bool = False
    ssl_note: str = ""       # сертификат не прошёл проверку, но сайт ответил без проверки

    @property
    def retryable(self):
        return self.error.startswith(RETRYABLE)

    @property
    def content_type(self):
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def is_html(self):
        return self.content_type in HTML_TYPES

    @property
    def location(self):
        return self.headers.get("location", "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


RETRYABLE = ("Таймаут", "Соединение сброшено", "Ошибка соединения")
# имя сайта: буквы (и кириллица - «пример.рф» бывает ещё не в xn--), цифры, точка, дефис, подчёркивание или IPv6;
# пробел, скобки, кавычки и прочие знаки - адрес записан с ошибкой
_HOST_OK = re.compile(r"[\w.-]+|[0-9A-Fa-f:.]+")


def _classify(exc) -> str:
    r = getattr(exc, "reason", exc)
    if isinstance(r, str):
        r = exc
    if isinstance(r, socket.gaierror):
        return "DNS: домен не найден"
    if isinstance(r, ssl.SSLCertVerificationError):
        return "SSL: ошибка сертификата"
    if isinstance(r, (ssl.SSLEOFError, ssl.SSLZeroReturnError)):
        # оборвали на шаге https-рукопожатия (провайдер или защита сайта), а не ошибка настройки https:
        # повторяется, как обычный сброс (dog-comfort.kz 17.10.2026; причина - access_check.py)
        return "Соединение сброшено на шаге https"
    if isinstance(r, ssl.SSLError):
        return "SSL: ошибка соединения"
    if isinstance(r, (socket.timeout, TimeoutError)):
        return "Таймаут"
    if isinstance(r, ConnectionRefusedError):
        return "Соединение отклонено"
    if isinstance(r, ConnectionResetError):
        return "Соединение сброшено"
    return "Ошибка соединения: " + (str(r)[:80] or type(r).__name__)


class Fetcher:
    def __init__(self, user_agent: str, timeout: float = 15, max_bytes: int = 5_000_000,
                 extra_headers: dict = None, verify_ssl: bool = True,
                 total_timeout: float = 30, max_file_bytes: int = 10_000_000):
        self.user_agent = user_agent
        self.timeout = timeout            # сколько ждать каждый ответ сервера
        self.total_timeout = total_timeout  # сколько всего можно качать один адрес
        self.max_bytes = max_bytes        # HTML больше этого обрезается
        self.max_file_bytes = max_file_bytes  # картинки/файлы без указанного размера: докачиваем не больше
        self.extra_headers = extra_headers or {}
        self.host_headers = {}            # {хост: заголовки} — вход на закрытый сайт, только для этого хоста
        self.ssl_backend = "Python"
        ctx = None
        if verify_ssl:
            # truststore проверяет сертификаты средствами Windows/macOS, как браузер:
            # сам докачивает недостающие промежуточные сертификаты и видит сертификаты,
            # установленные в систему. Без него Python иногда ошибочно ругается на SSL.
            try:
                import truststore
                ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                self.ssl_backend = "система (truststore)"
            except Exception:
                ctx = None
        if ctx is None:
            ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        # прокси Windows, кроме прокси выключенного VPN (sysproxy.py): с ним не открывалась ни одна страница
        from .sysproxy import LocalDirect, live_proxies
        self._proxies = live_proxies()
        # Без cookies и Accept-Language — как Googlebot
        self.opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ctx), LocalDirect(self._proxies))
        self.ctx = ctx
        # CLAYLER_NO_KEEPALIVE=1 — по-старому: новое подключение на каждый адрес (на случай проблем с сайтом)
        self.keep_alive = os.environ.get("CLAYLER_NO_KEEPALIVE") != "1"
        self._local = threading.local()   # у каждого потока свои открытые соединения
        self._bypass = {}

    def fetch(self, url: str, read_body: bool = True, any_type: bool = False, peek: int = 0) -> Response:
        """read_body — читать тело HTML; any_type — читать тело любого типа (robots.txt, sitemap);
        peek — для картинок, стилей, скриптов: сколько первых байт прочитать (по ним узнаём размеры картинки).
        Если сервер не сообщил размер файла, файл докачивается целиком, чтобы узнать вес."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        headers.update(self.extra_headers)
        res = Response(url=url)
        host = urlsplit(url).hostname or ""
        if self.host_headers and host.lower() in self.host_headers:
            headers.update(self.host_headers[host.lower()])
        if not host or ".." in host or host.startswith(".") or any(len(p) > 63 for p in host.split(".")) \
                or not _HOST_OK.fullmatch(host):
            # ошибка в самом адресе (ntagil..site.ru; пробелы и скобки в имени сайта - ссылку записали криво,
            # reestr-719.ru: «http://Постановление 878 (https://…)»; раньше - английская «URL can't contain control
            # characters») — сервер тут ни при чём: не повторяем и не тормозим обход
            res.error = "Неправильный адрес: ошибка в имени сайта"
            return res
        t0 = time.perf_counter()
        conn = None
        guard = _GUARD.add(t0 + self.hard_timeout)
        try:
            raw, conn = self._open(url, headers, guard)
            res.ttfb = time.perf_counter() - t0
            res.status = raw.status if hasattr(raw, "status") else raw.code
            res.reason = getattr(raw, "reason", "") or ""
            res.headers = {k.lower(): v for k, v in raw.headers.items()}
            link_hdrs = raw.headers.get_all("Link") or []
            if link_hdrs:
                res.headers["link"] = ", ".join(link_hdrs)
            xr = raw.headers.get_all("X-Robots-Tag") or []
            if xr:
                res.headers["x-robots-tag"] = ", ".join(xr)
            sc = raw.headers.get_all("Set-Cookie") or []
            if sc:   # все cookie, по строке на каждую (security.cookie_problems), а не только последняя
                res.headers["set-cookie"] = "\n".join(sc)
            deadline = t0 + self.total_timeout
            want = any_type or (read_body and (res.content_type in HTML_TYPES or not res.content_type))
            full = False   # тело читаем целиком - битое сжатие тогда видно, а не тихая пустая страница
            if want and 200 <= res.status < 300 or (want and res.status >= 400):
                full = True
                data, late = _read(raw, self.max_bytes + 1, deadline)
                if len(data) > self.max_bytes:
                    data, res.truncated = data[: self.max_bytes], True
                if late:
                    # медленный сервер: не ждём бесконечно, адрес попадёт в отчёт как «не ответил»
                    res.error = f"Загрузка дольше {self.total_timeout:.0f} с - прервана"
            elif peek and 200 <= res.status < 300:
                data, late = _read(raw, peek, deadline)
                rest = _rest(res, conn, len(data))
                if not late and rest:
                    _read(raw, rest, deadline)  # небольшой файл дочитываем: соединение пригодится дальше
                elif not late and not res.headers.get("content-length") and len(data) == peek:
                    # размер неизвестен — докачиваем, чтобы узнать вес, но не больше лимита и не дольше срока
                    more, late = _read(raw, self.max_file_bytes, deadline)
                    data += more
                    res.size_measured = not late and len(more) < self.max_file_bytes
            else:
                data = raw.read(1)  # не качаем PDF и прочее целиком
                rest = _rest(res, conn, len(data))
                if rest and (rest <= 65536 or not 200 <= res.status < 300):
                    _read(raw, rest, deadline)  # короткий ответ (редирект) дочитываем: соединение пригодится дальше
            # сеть кончилась - снимаем запрос со сторожа сразу, до распаковки: иначе срок мог выйти уже у полностью
            # полученного ответа (ревью кода 04.11.2026)
            if _GUARD.done(guard):
                raise _HardDeadline()
            self._release(conn, raw)
            try:
                res.size = int(res.headers.get("content-length") or len(data) or 0)
            except ValueError:
                res.size = len(data)
            res.body, problem = _unpack(data, res.headers.get("content-encoding", ""))
            if full and problem == "big":
                res.truncated = True
            elif full and problem == "broken" and not res.error:
                if res.body:
                    res.truncated = True   # сжатые данные оборвались: страница разобрана по началу
                else:
                    res.error = UNPACK_ERROR
        except Exception as e:  # ответа нет вообще
            # сервер тянул ответ по капле дольше жёсткого срока - соединение закрыл _Guard (отсюда и обрыв)
            late = isinstance(e, _HardDeadline) or _GUARD.done(guard)
            res.error = f"Загрузка дольше {self.hard_timeout:.0f} с - прервана" if late else _classify(e)
            if conn is not None:
                conn.close()  # ответ оборвался на середине — это соединение дальше не годится
        res.elapsed = time.perf_counter() - t0
        return res

    @property
    def hard_timeout(self):
        """Жёсткий срок одного запроса (_Guard): сколько качать + сколько ждать ответа + запас 5 с. Законно медленный
        ответ укладывается в total_timeout + timeout (последний кусок тела начинают ждать до total_timeout, ждут не
        больше timeout) - запас, чтобы его не оборвать на самой границе."""
        return self.total_timeout + self.timeout + 5

    # ---------- соединения
    MAX_CONN = 6  # сколько открытых соединений держит один поток (свой сайт + несколько внешних)

    def _proxy_for(self, scheme, host):
        """Прокси из настроек Windows для этого адреса: (хост, порт), None — без прокси,
        "urllib" — прокси необычный (с паролем, SOCKS), пусть работает urllib, как раньше."""
        purl = self._proxies.get(scheme)
        if not purl:
            return None
        if host not in self._bypass:
            # свой компьютер - всегда напрямую, как в браузере: в исключениях прокси VPN Throne бывает только
            # «*.local», и запросы к 127.0.0.1 уходили в прокси с ответом 502 (автотесты, 28.10.2026)
            from .sysproxy import is_local
            if is_local(host):
                self._bypass[host] = True
                return None
            try:
                self._bypass[host] = bool(urllib.request.proxy_bypass(host))
            except Exception:
                self._bypass[host] = False
        if self._bypass[host]:
            return None
        pp = urlsplit(purl if "://" in purl else "http://" + purl)
        if pp.scheme != "http" or pp.username or not pp.hostname:
            return "urllib"
        return pp.hostname, pp.port or 80

    def _open(self, url, headers, guard=None):
        """Отправляет запрос. Возвращает (ответ, соединение); соединение None — запрос шёл через urllib.
        Через прокси — так же, как urllib: https через туннель CONNECT, http — полным адресом.
        guard - запись _GUARD этого запроса: соединение отдаём ей, чтобы закрыть по жёсткому сроку
        (у запроса через urllib жёсткого срока нет - только таймаут на каждый кусок)."""
        sp = urlsplit(url)
        proxy = self._proxy_for(sp.scheme, sp.hostname) if sp.scheme in ("http", "https") else "urllib"
        if not self.keep_alive or proxy == "urllib":
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                return self.opener.open(req, timeout=self.timeout), None
            except urllib.error.HTTPError as e:  # 3xx/4xx/5xx — это тоже ответ
                return e, None
        key = (sp.scheme, sp.hostname, sp.port)
        path = (sp.path or "/") + ("?" + sp.query if sp.query else "")
        if proxy and sp.scheme == "http":
            path = f"http://{sp.netloc.rsplit('@', 1)[-1]}{path}"
            headers = dict(headers, Host=sp.netloc.rsplit("@", 1)[-1])
        pool = getattr(self._local, "pool", None)
        if pool is None:
            pool = self._local.pool = collections.OrderedDict()
        for attempt in (0, 1):
            conn = pool.pop(key, None)
            reused = conn is not None and conn.sock is not None
            if conn is None:
                host, port = proxy or (sp.hostname, sp.port)
                if sp.scheme == "https":
                    conn = http.client.HTTPSConnection(host, port, timeout=self.timeout, context=self.ctx)
                    if proxy:
                        conn.set_tunnel(sp.hostname, sp.port or 443)
                else:
                    conn = http.client.HTTPConnection(host, port, timeout=self.timeout)
            pool[key] = conn
            while len(pool) > self.MAX_CONN:
                pool.popitem(last=False)[1].close()
            _GUARD.attach(guard, conn)
            try:
                conn.request("GET", path, headers=headers)
                return conn.getresponse(), conn
            except (ConnectionError, http.client.BadStatusLine, http.client.ImproperConnectionState) as e:
                pool.pop(key, None)
                conn.close()
                # сервер сам закрыл соединение, пока оно простаивало, — это не ошибка сайта: повторяем по новому.
                # Но если его закрыл жёсткий срок (_Guard) - не повторяем: новая попытка шла бы уже без срока
                if not reused or attempt or _GUARD.killed(guard):
                    raise e
            except Exception:
                pool.pop(key, None)
                conn.close()
                raise

    @staticmethod
    def _release(conn, raw):
        """Ответ прочитан целиком — соединение остаётся для следующего адреса; не целиком (PDF, картинка,
        прерванная загрузка) — закрываем, чтобы сервер не досылал остаток."""
        try:
            if conn is None:
                raw.close()
            elif not raw.isclosed():
                conn.close()
        except Exception:
            pass

    def close(self):
        """Закрыть соединения текущего потока."""
        pool = getattr(self._local, "pool", None)
        while pool:
            pool.popitem()[1].close()


class _Guard:
    """Жёсткий срок на один запрос (сколько качать + сколько ждать ответа + запас: 30 + 15 + 5 с, Fetcher.hard_timeout). Таймаут сокета срабатывает,
    только когда сервер молчит совсем, а срок total_timeout проверяется между кусками тела: сервер, который тянет
    по байту в секунду заголовки ответа, держал поток сколько угодно. В обходе такой адрес бросал сторож главного
    цикла, а перепроверка ошибок после обхода ждала его до конца (тест/проверить_сторож.py, 04.11.2026).
    Один поток на всю программу раз в 0,5 с закрывает соединения запросов, у которых вышел срок."""

    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}      # ключ -> [срок, соединение, закрыто ли сторожем]
        self.thread = None

    def add(self, deadline):
        key = object()
        with self.lock:
            self.items[key] = [deadline, None, False]
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True, name="fetch-guard")
                self.thread.start()
        return key

    def attach(self, key, conn):
        with self.lock:
            if key in self.items:
                self.items[key][1] = conn

    def done(self, key):
        """Запрос закончился. True - его прервал сторож. Второй вызов для того же запроса - False."""
        with self.lock:
            v = self.items.pop(key, None)
        return bool(v and v[2])

    def killed(self, key):
        """Прервал ли сторож этот запрос (запрос ещё не снят)."""
        with self.lock:
            v = self.items.get(key)
        return bool(v and v[2])

    def _run(self):
        while True:
            time.sleep(0.5)
            now = time.perf_counter()
            with self.lock:   # закрываем под замком: done() после этого точно видит «прервано»
                for v in self.items.values():
                    if not v[2] and v[0] < now and v[1] is not None:
                        v[2] = True
                        try:
                            if v[1].sock is not None:
                                v[1].sock.shutdown(socket.SHUT_RDWR)   # будит поток, ждущий в recv
                        except OSError:
                            pass


_GUARD = _Guard()


class _HardDeadline(Exception):
    """Ответ прочитан, но сторож уже закрыл соединение по жёсткому сроку (Fetcher.fetch)."""


REST_MAX = 256 * 1024  # сколько недочитанного ответа дочитываем, чтобы не открывать новое соединение


def _rest(res, conn, got):
    """Сколько байт ответа осталось дочитать, если это стоит сделать (0 — не стоит). Недочитанный ответ
    закрывает соединение, и следующий адрес открывает новое (через VPN — заметно дольше): на torrefacto.ru
    так открывалось новое соединение на каждую картинку. Дочитать 200 КБ быстрее, чем подключиться заново."""
    cl = res.headers.get("content-length", "")
    if conn is None or not cl.isdigit():
        return 0
    left = int(cl) - got
    return left if 0 < left <= REST_MAX else 0


def _read(raw, n, deadline):
    """Читает до n байт небольшими кусками. Возвращает (данные, опоздали?) — если общий срок вышел,
    чтение прерывается: иначе сервер, отдающий файл по капле, держит поток часами
    (таймаут в 15 с срабатывает только когда сервер молчит совсем)."""
    buf = bytearray()
    read1 = getattr(raw, "read1", None)
    while len(buf) < n:
        if time.perf_counter() > deadline:
            return bytes(buf), True
        want = min(65536, n - len(buf))
        chunk = read1(want) if read1 else raw.read(want)
        if not chunk:
            break
        buf += chunk
    return bytes(buf), False


UNPACK_MAX = 50_000_000   # больше стольких байт после распаковки не держим: 5 МБ сжатого HTML бывают и 500 МБ текста
UNPACK_ERROR = "Ответ сжат с ошибкой - не распаковался"


def _decompress(data: bytes, enc: str) -> bytes:
    return _unpack(data, enc)[0]


def _unpack(data: bytes, enc: str, limit: int = None):
    """Распаковка gzip/deflate кусками, не больше limit байт. Возвращает (данные, беда): "" - в порядке, "big" -
    распакованное больше limit (обрезано), "broken" - сжатые данные оборваны или испорчены (что успели распаковать).
    Раньше gzip.decompress распаковывал целиком без предела, а испорченный ответ молча становился пустым
    (ревизия кода 03.11.2026)."""
    limit = UNPACK_MAX if limit is None else limit
    enc = (enc or "").lower()
    if "gzip" in enc:
        modes = (16 + zlib.MAX_WBITS,)
    elif "deflate" in enc:
        modes = (zlib.MAX_WBITS, -zlib.MAX_WBITS)   # deflate с заголовком zlib и без него
    else:
        return data, ""
    if not data:
        return b"", ""
    best = b""
    for wbits in modes:
        out, d, src, pos, members = bytearray(), zlib.decompressobj(wbits), data, 0, 0
        try:
            while pos < len(src):
                out += d.decompress(src[pos:pos + 65536], limit + 1 - len(out))
                pos += 65536
                if len(out) > limit:
                    return bytes(out[:limit]), "big"
                if d.eof:
                    members += 1
                    src, pos = d.unused_data + src[pos:], 0
                    if wbits < 0 or "gzip" not in enc or not src.strip(b"\0"):
                        return bytes(out), ""
                    d = zlib.decompressobj(wbits)   # несколько gzip подряд - как gzip.decompress
            out += d.flush()
            return bytes(out[:limit]), "" if d.eof else "broken"
        except zlib.error:
            if members:
                return bytes(out), ""   # мусор после целого архива - сам ответ цел
            best = max(best, bytes(out), key=len)
    return best, "broken"
