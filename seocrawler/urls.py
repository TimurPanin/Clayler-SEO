"""Нормализация URL и работа с параметрами.

Правило: приводим к единому виду только то, что точно не меняет страницу
(регистр схемы и домена, якорь #, порт по умолчанию, порядок параметров,
кодирование символов). /page и /page/ НЕ склеиваем — это находка для аудита.
"""
from urllib.parse import urlsplit, urlunsplit, urljoin, parse_qsl, urlencode, quote, unquote, unquote_plus
import re

# Параметры, которые почти никогда не меняют содержимое страницы
TRACKING_PARAMS = {
    "gclid", "yclid", "fbclid", "msclkid", "dclid", "_openstat", "from",
    "sessionid", "session_id", "sid", "phpsessid", "jsessionid", "ysclid",
    "_ga", "_gl", "mc_cid", "mc_eid", "etext", "roistat",
}
TRACKING_PREFIXES = ("utm_", "openstat")

_SAFE_PATH = "/:@!$&'()*+,;=-._~%"
_SAFE_QUERY = "/:@!$'()*+,;=-._~%?"


def is_tracking_param(name: str) -> bool:
    n = name.lower()
    return n in TRACKING_PARAMS or n.startswith(TRACKING_PREFIXES)


def _requote(part: str, safe: str) -> str:
    # %D0%BA и «к» — одно и то же: раскодируем и кодируем обратно единообразно
    return quote(unquote(part), safe=safe)


def is_relative(raw: str) -> bool:
    """Ссылка считается от текущей страницы: `otzyvy`, `blog/`, `../x`. Не «/x», не «?page=2», не «#якорь», не
    «tel:...»."""
    raw = (raw or "").strip()
    return bool(raw) and raw[0] not in "/?#" and ":" not in raw.split("/", 1)[0]


def normalize(url: str, base: str = None, sort_params: bool = True):
    """Возвращает нормализованный абсолютный URL или None, если это не http(s)."""
    if base:
        url = urljoin(base, url.strip())
    url = url.strip()
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    scheme = p.scheme.lower()
    if scheme not in ("http", "https"):
        return None
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return None
    try:
        host = host.encode("idna").decode("ascii")  # кириллические домены -> xn--
    except UnicodeError:
        pass   # имя не переводится в xn--: оставляем как есть, запрос сам покажет понятную ошибку
    try:
        port = p.port
    except ValueError:
        return None
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = _requote(p.path or "/", _SAFE_PATH)
    path = _resolve_dots(path)
    query = p.query
    if query:
        pairs = _split_query(query)
        if sort_params:
            pairs = sorted(pairs)
        query = _join_query(pairs)
    return urlunsplit((scheme, netloc, path, query, ""))  # якорь отбрасываем


def _split_query(query: str):
    """Параметры как (имя, значение, без_знака_равно). «?v123» остаётся «?v123», а не «?v123=»:
    сервер может понимать их по-разному, и так адрес совпадает с тем, что стоит на сайте."""
    out = []
    for part in query.split("&"):
        if part:
            k, eq, v = part.partition("=")
            out.append((unquote_plus(k), unquote_plus(v), not eq))
    return out


def _join_query(pairs) -> str:
    q = lambda s: quote(s, safe="/:@!$'()*,;-._~")
    return "&".join(q(k) if bare else f"{q(k)}={q(v)}" for k, v, bare in pairs)


def _resolve_dots(path: str) -> str:
    if "/." not in path:
        return path
    out = []
    for seg in path.split("/"):
        if seg == "..":
            if len(out) > 1:
                out.pop()
        elif seg != ".":
            out.append(seg)
    res = "/".join(out)
    if path.endswith(("/.", "/..")):
        res += "/"
    return res or "/"


def strip_params(url: str, clean_param_rules=None):
    """Убирает трекинговые параметры и параметры из Clean-param.

    Возвращает (очищенный_url, список_удалённых_параметров).
    clean_param_rules — список (set_параметров, префикс_пути) из robots.txt Яндекса.
    """
    p = urlsplit(url)
    if not p.query:
        return url, []
    pairs = _split_query(p.query)
    removed, kept = [], []
    for k, v, bare in pairs:
        drop = is_tracking_param(k)
        if not drop and clean_param_rules:
            for names, prefix in clean_param_rules:
                if k in names and (not prefix or p.path.startswith(prefix)):
                    drop = True
                    break
        (removed if drop else kept).append((k, v, bare) if not drop else k)
    if not removed:
        return url, []
    query = _join_query(kept)
    return urlunsplit((p.scheme, p.netloc, p.path, query, "")), removed


def param_count(url: str) -> int:
    q = urlsplit(url).query
    return len(parse_qsl(q, keep_blank_values=True)) if q else 0


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def site_key(url):
    """Один сайт - одна карточка: www.site.ru и site.ru вместе (окно, метки проблем, сравнение)."""
    host = (urlsplit(url).hostname or url or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, root_host: str, include_subdomains: bool) -> bool:
    h = host_of(url)
    root = root_host[4:] if root_host.startswith("www.") else root_host
    if h in (root_host, root, "www." + root):
        return True
    if isinstance(include_subdomains, (set, frozenset)):  # только названные поддомены (городские версии сайта)
        return h in include_subdomains
    return include_subdomains and h.endswith("." + root)


_REPEAT_RE = re.compile(r"(/[^/]+/[^/]+)\1\1")


def has_repetitive_path(url: str) -> bool:
    """Ловушка относительных ссылок: /a/b/a/b/a/b/..."""
    path = urlsplit(url).path
    segs = [s for s in path.split("/") if s]
    if len(segs) >= 3 and any(segs.count(x) >= 3 for x in set(segs)):
        return True
    return bool(_REPEAT_RE.search(path))


FILE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".bmp", ".ico", ".tif", ".tiff",
            ".zip", ".rar", ".7z", ".mp4", ".mp3", ".avi", ".mov", ".webm", ".woff", ".woff2", ".ttf")


def is_file_url(url: str) -> bool:
    """Адрес явно ведёт на файл (картинку, архив, видео), а не на страницу. PDF считаем документом-страницей,
    как Screaming Frog: в нём бывают ссылки и текст."""
    return urlsplit(url).path.lower().endswith(FILE_EXT)


def page_key(url: str) -> str:
    """Ключ для сравнения адреса из файла (Вебмастер, Search Console, Key Collector, свои группы) с адресами обхода:
    без http/https, www, якоря, слэша в конце и меток (utm_ и т. п.); домен - в нижнем регистре, кириллица
    и %D0%BA - одинаково. Регистр пути важен: /Kotly/ и /kotly/ - разные страницы. Адрес без схемы («a.ru/x») -
    как https://a.ru/x. Пусто или не адрес - ""."""
    u = (url or "").strip()
    if not u:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "https://" + u.lstrip("/")
    n = normalize(u)
    if not n:
        return ""
    p = urlsplit(n)
    host = (p.netloc or "").removeprefix("www.")
    query = "&".join(x for x in p.query.split("&") if x and not is_tracking_param(x.split("=")[0]))
    return host + (p.path.rstrip("/") or "") + ("?" + query if query else "")


def same_page(a: str, b: str) -> bool:
    """Один и тот же адрес по правилу page_key."""
    ka, kb = page_key(a), page_key(b)
    return bool(ka) and ka == kb
