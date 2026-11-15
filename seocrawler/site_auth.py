"""Закрытые тестовые сайты: логин и пароль (HTTP Basic — окошко браузера «Вход») и/или cookie для входа.
Хранятся зашифрованными средствами Windows в «доступы.json» (как ключи Яндекса и Google), по каждому сайту отдельно.
Отправляются только этому сайту (тот же домен, с www и без) — ни картинкам на других сайтах, ни внешним ссылкам."""
import base64
from urllib.parse import urlsplit

from . import accounts

KEY = "site_auth"


def _host(url_or_host):
    h = (urlsplit(url_or_host).hostname if "://" in (url_or_host or "") else (url_or_host or "").split("/")[0].split(":")[0]) or ""
    h = h.lower()
    return h[4:] if h.startswith("www.") else h


def _all():
    return accounts._get(KEY)


def sites():
    """Для окна: какие сайты с доступом сохранены (без самих паролей)."""
    out = []
    for host, d in sorted(_all().items()):
        out.append({"host": host, "user": accounts.unseal(d["user"]) if d.get("user") else "",
                    "has_password": bool(d.get("password")), "has_cookie": bool(d.get("cookie"))})
    return out


def save(site, user="", password="", cookie=""):
    host = _host(site)
    if not host or "." not in host and host != "localhost" and not host.replace(".", "").isdigit():
        return "Укажите адрес сайта, например test.site.ru."
    if not (user or cookie):
        return "Нужны логин и пароль или cookie."
    cur = _all().get(host) or {}
    rec = {}
    if user:
        rec["user"] = accounts.seal(user)
        rec["password"] = accounts.seal(password) if password else cur.get("password", "")
    if cookie:
        rec["cookie"] = accounts.seal(cookie.strip())
    accounts._put(KEY, **{host: rec})
    return ""


def remove(site):
    accounts._put(KEY, **{_host(site): None})
    return ""


def headers_for(url):
    """{хост: заголовки} для этого сайта (с www и без) или None, если доступа нет."""
    host = _host(url)
    d = _all().get(host)
    if not d:
        return None
    h = {}
    if d.get("user"):
        pair = accounts.unseal(d["user"]) + ":" + (accounts.unseal(d["password"]) if d.get("password") else "")
        h["Authorization"] = "Basic " + base64.b64encode(pair.encode("utf-8")).decode()
    if d.get("cookie"):
        h["Cookie"] = accounts.unseal(d["cookie"])
    return {host: h, "www." + host: h} if h else None


def login_headers(url: str, log=print) -> dict:
    """Заголовки входа для обхода и дочитывания: {хост: заголовки} или {}. Одно поведение на всех: файл доступов
    испорчен
    или ключ не расшифровался - строка в журнале и работа без входа, а не тишина (иначе видна только страница входа)."""
    try:
        return headers_for(url) or {}
    except (OSError, ValueError, KeyError, TypeError) as e:
        log(f"Данные входа на сайт не прочитались, проверяю без входа: {e}")
        return {}
