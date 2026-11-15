"""Почему сайт не открывается: понятная причина вместо «Соединение сброшено» или «403».

Было (dog-comfort.kz 17.10.2026): напрямую через провайдера соединение сбрасывалось на шаге https-рукопожатия
(в curl ошибка 35, в браузере «Connection was reset»), через VPN проходило. Кроме того, сайт отдавал 403 всему,
что не похоже на браузер (программа представлялась «ClaylerSEO/1.0»), а браузеру Chrome - 200. В отчёте и окне
было только «Соединение сброшено» и «403», без причины и без того, что делать.

diagnose(url) идёт по шагам, как браузер: адрес (DNS) → подключение к серверу → защищённое подключение (https,
TLS-рукопожатие, 3 попытки) → ответ программе и ответ браузеру Chrome. Итог - словарь:
  kind    dns | tcp | tls_reset | tls_flaky | tls_error | dropped | bots_blocked | blocked | ok
  title   что случилось («Соединение режут по дороге», «Сайт не пускает программы»), todo - что сделать,
  detail  технические подробности по шагам (для «Подробнее» и журнала).
Если в Windows включён прокси (так работают многие VPN-программы), подключение идёт через него, как у браузера;
прокси с паролем или SOCKS - шаги подключения пропускаются, остаются ответы программе и браузеру."""
import socket
import ssl
import time
import urllib.request
from urllib.parse import urlsplit

TIMEOUT = 10
TRIES = 3                      # сколько раз пробовать https-рукопожатие
BOT_CODES = (401, 403, 406, 429, 503)

TEXT = {
    "dns": ("Сайт не найден по этому адресу",
            "Проверьте адрес на опечатки и откройте его в браузере. Если не открывается и там, домен не работает "
            "или не продлён."),
    "tcp": ("Сервер сайта не принимает подключение",
            "Сервер не отвечает совсем: сайт выключен или закрыт для вашей сети. Откройте сайт в браузере; если "
            "в браузере открывается, а программа - нет, попробуйте через VPN."),
    "tls_reset": ("Соединение режут по дороге",
                  "Сервер найден, подключиться к нему можно, но на шаге защищённого подключения (https) соединение "
                  "обрывают. Так бывает, когда сайт блокирует провайдер или защита сайта не пускает ваш адрес. "
                  "Попробуйте проверить через VPN."),
    "tls_flaky": ("Соединение обрывают через раз",
                  "Защищённое подключение (https) то проходит, то обрывается. Это провайдер или защита сайта. "
                  "Программа сама идёт медленнее; если обрывов много, проверьте через VPN."),
    "dropped": ("Сайт обрывает соединение без ответа",
                "Подключиться к сайту можно, но на запрос он обрывает соединение и ничего не отвечает - и программе, "
                "и браузеру Chrome. Обычно это защита сайта от частых запросов или блокировка вашего адреса: "
                "попробуйте позже или через VPN."),
    "tls_error": ("Ошибка защищённого подключения (https) на сайте",
                  "Откройте сайт в браузере. Если браузер тоже пишет об ошибке, https на сайте настроен неверно: "
                  "это стоит отметить в аудите."),
    "bots_blocked": ("Сайт не пускает программы",
                     "Браузеру сайт отвечает нормально, а программам - отказом. Проверяйте сайт как браузер Chrome "
                     "(«Проверять как» в дополнительных настройках)."),
    "blocked": ("Сайт закрыт и для браузера",
                "Отказ получает и программа, и браузер Chrome. Сайт может быть закрыт для вашей страны или адреса "
                "(попробуйте через VPN) или требует входа (раздел «Закрытые сайты»)."),
    "ok": ("Сайт открывается", ""),
}


def _ua(name):
    from .fetcher import UA_PRESETS
    return UA_PRESETS.get(name, name)


def _proxy(scheme, host):
    """Прокси из настроек Windows для адреса: (хост, порт), "other" - необычный (с паролем, SOCKS), None - без прокси."""
    from .sysproxy import live_proxies   # как обход (fetcher.py): прокси выключенного VPN не считается
    try:
        purl = live_proxies().get(scheme)
        if not purl or urllib.request.proxy_bypass(host):
            return None
    except Exception:
        return None
    pp = urlsplit(purl if "://" in purl else "http://" + purl)
    if pp.scheme != "http" or pp.username or not pp.hostname:
        return "other"
    return pp.hostname, pp.port or 80


def _connect(host, port, timeout, proxy=None):
    """Подключение к серверу напрямую или туннелем через прокси Windows (CONNECT), как у браузера."""
    if not proxy:
        return socket.create_connection((host, port), timeout=timeout)
    sock = socket.create_connection(proxy, timeout=timeout)
    try:
        sock.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode("ascii"))
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        first = data.split(b"\r\n", 1)[0].decode("latin-1")
        if " 200" not in first:
            raise ConnectionRefusedError(f"прокси {proxy[0]}:{proxy[1]} не подключился к сайту: {first or 'нет ответа'}")
        return sock
    except BaseException:
        sock.close()
        raise


def _handshake(host, port, timeout, proxy=None):
    """Одна попытка: подключиться и пройти TLS-рукопожатие. (что вышло, подробности):
    ok | tcp | dns | reset (оборвали или замолчали на рукопожатии) | error (другая ошибка TLS)."""
    try:
        sock = _connect(host, port, timeout, proxy)
    except socket.gaierror as e:
        return "dns", f"DNS: {e}"
    except OSError as e:
        return "tcp", f"подключение к {host}:{port}: {type(e).__name__} {e}"[:200]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False          # сертификат здесь не важен: смотрим, дают ли вообще пройти рукопожатие
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with ctx.wrap_socket(sock, server_hostname=host):
            return "ok", "рукопожатие https прошло"
    except (ConnectionResetError, ConnectionAbortedError, ssl.SSLEOFError, ssl.SSLZeroReturnError,
            socket.timeout, TimeoutError, BrokenPipeError) as e:
        return "reset", f"рукопожатие https: {type(e).__name__} {e}"[:200]
    except ssl.SSLError as e:
        return "error", f"рукопожатие https: {e}"[:200]
    except OSError as e:
        return "reset", f"рукопожатие https: {type(e).__name__} {e}"[:200]
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _code(r):
    return r.status or 0


def _fine(r):
    return bool(r.status) and r.status < 400


def _what(r):
    return f"код {r.status}" if r.status else (r.error or "нет ответа")


def diagnose(url, ua="crawler", verify_ssl=True, timeout=TIMEOUT, headers=None, tries=TRIES, fetch=None):
    """Причина, по которой адрес не открывается (см. описание модуля). headers - вход на закрытый сайт.
    fetch(url, ua_name) -> Response - для автотестов; по умолчанию программа сама загружает адрес."""
    sp = urlsplit(url)
    host, scheme = sp.hostname or "", sp.scheme or "https"
    port = sp.port or (443 if scheme == "https" else 80)
    steps, out = [], {"kind": "ok", "url": url, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    proxy = _proxy(scheme, host)

    def done(kind, **kw):
        out.update(kw, kind=kind)
        out["title"], out["todo"] = TEXT[kind]
        if proxy and proxy != "other" and kind in ("tls_reset", "tls_flaky", "tcp", "dropped"):
            # VPN-программа в режиме прокси: часть сайтов она может пускать мимо VPN
            out["todo"] += (" В Windows включён прокси (так работают многие VPN-программы): возможно, этот сайт идёт "
                            "мимо VPN - включите VPN для всех сайтов или выберите другой сервер.")
        out["detail"] = "; ".join(steps)
        return out

    if proxy != "other":
        if proxy:
            steps.append(f"через прокси Windows {proxy[0]}:{proxy[1]}")
        if scheme == "https":
            res = [_handshake(host, port, timeout, proxy) for _ in range(max(1, tries))]
            kinds = [k for k, _ in res]
            steps.append(f"https-рукопожатие: прошло {kinds.count('ok')} из {len(kinds)}")
            steps.extend(sorted({d for k, d in res if k != "ok"}))
            if kinds[0] == "dns":
                return done("dns")
            if all(k == "tcp" for k in kinds):
                return done("tcp")
            bad = sum(1 for k in kinds if k in ("reset", "tcp"))
            if "error" in kinds and "ok" not in kinds:
                return done("tls_error")
            if bad == len(kinds):
                return done("tls_reset", tries=len(kinds), failed=bad)
            out.update(tries=len(kinds), failed=bad)
        else:
            try:
                _connect(host, port, timeout, proxy).close()
                steps.append("подключение есть")
            except socket.gaierror as e:
                steps.append(f"DNS: {e}")
                return done("dns")
            except OSError as e:
                steps.append(f"подключение: {type(e).__name__} {e}"[:200])
                return done("tcp")
    else:
        steps.append("через прокси Windows с паролем или SOCKS: подключение не проверяю")

    if fetch is None:
        from .fetcher import Fetcher

        def fetch(u, who):
            f = Fetcher(_ua(who), timeout=timeout, verify_ssl=verify_ssl, total_timeout=timeout * 2)
            if headers:
                f.host_headers[host.lower()] = headers
            if who == "chrome":
                f.extra_headers = {"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
            return f.fetch(u, read_body=False)
    prog = fetch(url, ua)
    chrome = fetch(url, "chrome") if ua != "chrome" else prog
    steps.append(f"программе: {_what(prog)}; браузеру Chrome: {_what(chrome)}")
    out.update(program=_code(prog) or prog.error, browser=_code(chrome) or chrome.error)
    if not _fine(prog) and _fine(chrome) and (_code(prog) in BOT_CODES or not prog.status or _code(prog) >= 400):
        return done("bots_blocked")
    if not _fine(prog) and not _fine(chrome) and _code(chrome) in BOT_CODES:
        return done("blocked")
    if out.get("failed"):
        return done("tls_flaky")
    if _fine(prog):
        return done("ok")
    if not prog.status and not chrome.status:
        # ответа нет ни программе, ни браузеру, а рукопожатие проходит: обрывают уже сам запрос
        if (prog.error or "").startswith("SSL") and not prog.retryable:
            return done("tls_error")
        return done("dropped")
    return done("ok")


def line(d):
    """Строка в журнал проверки: «Сайт не открывается: <что случилось>. <что сделать> (подробности)»."""
    if not d or d.get("kind") == "ok":
        return ""
    head = "Сайт не пускает программы" if d["kind"] == "bots_blocked" else "Сайт не открывается"
    return f"{head}: {d['title'][0].lower() + d['title'][1:]}. {d['todo']} ({d.get('detail', '')})"


def short(d):
    """Коротко для «сайт перестал отвечать (...)»: «соединение режут по дороге на шаге https, попробуйте через VPN»."""
    k = (d or {}).get("kind")
    return {"tls_reset": "соединение режут по дороге на шаге https (провайдер или защита сайта), попробуйте через VPN",
            "tls_flaky": "соединение обрывают через раз на шаге https (провайдер или защита сайта)",
            "bots_blocked": "сайт не пускает программы, браузеру отвечает",
            "blocked": "сайт закрыт и для браузера",
            "dropped": "сайт обрывает соединение без ответа (защита от частых запросов или блокировка адреса)",
            "tcp": "сервер не принимает подключение",
            "dns": "домен не находится"}.get(k, "")
