"""Прокси Windows от выключенного VPN: в настройках остался адрес (127.0.0.1:2080), а прокси уже не отвечает.
urlopen здесь в таком случае повторяет запрос напрямую. Раньше без VPN не работали подсказки и «Подключения»:
«WinError 10061 … actively refused it» (Throne). С ревизии так же ходят все запросы
к службам (Telegram, орфография, Букварикс, Директ, обновления поиска…), а обход сайта (fetcher.py) берёт
прокси через live_proxies: мёртвый прокси при старте проверки не используется."""
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


def is_local(host):
    """Свой компьютер: туда всегда напрямую, как в браузере (в исключениях прокси VPN бывает только «*.local»).
    127.x.x.x, localhost и *.localhost (копии страниц в окне - show.localhost), ::1 - но не сайт «127.ru»."""
    h = (host or "").lower().strip("[]")
    return h in ("localhost", "::1") or h.endswith(".localhost") or bool(re.fullmatch(r"127(?:\.\d{1,3}){3}", h))


class LocalDirect(urllib.request.ProxyHandler):
    """Прокси для urllib, но свой компьютер - напрямую. Без этого запасной путь загрузчика (fetcher.opener: проверка
    ответа 304, прокси с паролем, CLAYLER_NO_KEEPALIVE) слал 127.0.0.1 в прокси VPN и получал 502."""

    def proxy_open(self, req, proxy, type):
        if is_local(urllib.parse.urlsplit(req.full_url).hostname):
            return None   # дальше обычный обработчик - напрямую
        return super().proxy_open(req, proxy, type)


def _direct(req, timeout, context=None):
    """Тот же запрос без прокси."""
    handlers = [urllib.request.ProxyHandler({})]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers).open(req, timeout=timeout)


def urlopen(req, timeout, context=None):
    if isinstance(req, str):
        req = urllib.request.Request(req)
    if is_local(urllib.parse.urlsplit(req.full_url).hostname):
        return _direct(req, timeout, context)
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=context)
    except urllib.error.URLError as e:
        if isinstance(e, urllib.error.HTTPError) or not isinstance(e.reason, ConnectionRefusedError):
            raise
        if not urllib.request.getproxies().get(urllib.parse.urlsplit(req.full_url).scheme):
            raise
        # новый запрос: старый уже помечен «через прокси» (set_proxy) и снова пошёл бы туда
        again = urllib.request.Request(req.full_url, data=req.data, headers=dict(req.header_items()),
                                       method=req.get_method())
        return _direct(again, timeout, context)


_DEAD = {}   # {(хост, порт): (когда проверяли, мёртв ли)}


def _dead(purl):
    """Прокси на этом компьютере (127.0.0.1, localhost) отказывает в подключении: VPN выключен.
    Чужие адреса не проверяем: там отказ может быть временным, а соединение - долгим."""
    sp = urllib.parse.urlsplit(purl if "://" in purl else "http://" + purl)
    host, port = (sp.hostname or "").lower(), sp.port or 80
    if not is_local(host):
        return False
    t, dead = _DEAD.get((host, port), (0, False))
    if time.time() - t > 30:
        try:   # Windows отказывает в подключении к закрытому порту не сразу, а примерно через 2 секунды
            socket.create_connection((host, port), timeout=4).close()
            dead = False
        except ConnectionRefusedError:
            dead = True
        except OSError:
            dead = False
        _DEAD[(host, port)] = (time.time(), dead)
    return dead


def live_proxies():
    """getproxies() без прокси выключенного VPN."""
    try:
        got = urllib.request.getproxies()
    except Exception:
        return {}
    return {k: v for k, v in got.items() if k == "no" or not _dead(v)}
