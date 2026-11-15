"""Сообщить Яндексу, что страницы изменились: после правок поисковик узнаёт о них за дни, а не недели.

Два бесплатных способа:
- IndexNow — открытый протокол Яндекса и Bing: список адресов уходит одним запросом. Нужен ключ — файл <ключ>.txt
  в корне сайта (его один раз выкладывает разработчик), так Яндекс убеждается, что сайт ваш.
- Очередь переобхода Яндекс Вебмастера — через уже подключённый вход в Яндекс; лимит — несколько десятков
  адресов в день (Вебмастер сообщает, сколько осталось).
Какие адреса отправлять: программа сама находит страницы, у которых с прошлой проверки поменялись title,
description, H1, canonical, код ответа или индексируемость, и новые страницы."""
import json
import os
import re
import secrets
import sqlite3
import urllib.parse
import urllib.request
from urllib.parse import urlsplit

from . import accounts, sysproxy

KEY = "indexnow"
ENDPOINT = "https://yandex.com/indexnow"
FIELDS = [("status", "код ответа"), ("indexability", "индексируемость"), ("title", "title"), ("description", "description"),
          ("h1", "H1"), ("canonical", "canonical")]
_FOLDER_RX = re.compile(r"^(.*)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?$")
MAX = 1000


def _pages(folder):
    db = sqlite3.connect(f"file:{os.path.join(folder, 'crawl.db')}?mode=ro", uri=True)
    try:
        cols = ", ".join(f"p.{c}" for c, _ in FIELDS)
        rows = db.execute(f"SELECT p.url, {cols}, p.indexable, p.content_type FROM pages p JOIN urls u ON u.url=p.url "
                          "WHERE u.internal=1 AND u.kind='page'").fetchall()
        start = json.loads((db.execute("SELECT value FROM meta WHERE key='start'").fetchone() or ['""'])[0])
        done = (db.execute("SELECT value FROM meta WHERE key='finished_at'").fetchone() or [None])[0]
    finally:
        db.close()
    return start, bool(done), {r[0]: r for r in rows}


def previous(folder):
    """Прошлая законченная проверка того же сайта (по имени папки)."""
    folder = os.path.abspath(folder)
    m = _FOLDER_RX.match(os.path.basename(folder))
    if not m:
        return None
    parent = os.path.dirname(folder)
    for d in sorted(os.listdir(parent), reverse=True):
        mm = _FOLDER_RX.match(d)
        if mm and mm.group(1) == m.group(1) and d < os.path.basename(folder) and \
                os.path.exists(os.path.join(parent, d, "crawl.db")):
            try:
                if _pages(os.path.join(parent, d))[1]:
                    return os.path.join(parent, d)
            except sqlite3.Error:
                continue
    return None


def changed(folder):
    """[(адрес, что поменялось)] — рабочие страницы, изменившиеся с прошлой проверки, и новые. None — сравнивать не с чем."""
    prev = previous(folder)
    if not prev:
        return None, ""
    _s, _d, new = _pages(folder)
    _s, _d, old = _pages(prev)
    out = []
    for url, r in new.items():
        if r[1] != 200 or r[-2] != 1 or (r[-1] or "") not in ("text/html", "application/xhtml+xml"):
            continue  # отправлять имеет смысл только рабочие страницы, открытые для поиска
        o = old.get(url)
        if not o:
            out.append((url, "новая страница"))
            continue
        diff = [name for i, (_c, name) in enumerate(FIELDS, 1) if (o[i] or "") != (r[i] or "")]
        if diff:
            out.append((url, ", ".join(diff)))
    out.sort(key=lambda x: (x[1] == "новая страница", x[0]))
    return out[:MAX], os.path.basename(prev)


# ---------- IndexNow
def _host(site):
    return (urlsplit(site if "://" in site else "https://" + site).hostname or "").lower()


def key_for(site):
    """Ключ IndexNow для сайта (создаётся один раз и запоминается)."""
    host = _host(site)
    keys = accounts._get(KEY)
    if not keys.get(host):
        accounts._put(KEY, **{host: secrets.token_hex(16)})
        keys = accounts._get(KEY)
    return keys[host]


def key_status(site):
    """Выложен ли файл ключа на сайте: {"key", "file", "url", "ok", "error"}."""
    sp = urlsplit(site if "://" in site else "https://" + site)
    key = key_for(site)
    url = f"{sp.scheme or 'https'}://{sp.netloc}/{key}.txt"
    out = {"key": key, "file": f"{key}.txt", "url": url, "ok": False, "error": ""}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ClaylerSEO/1.0)"})
        with sysproxy.urlopen(req, timeout=15) as r:
            out["ok"] = key in r.read(2000).decode("utf-8", "replace")
            if not out["ok"]:
                out["error"] = "Файл открывается, но в нём нет ключа."
    except Exception as e:
        out["error"] = "Файл не найден на сайте: " + str(e)[:120]
    return out


def send_indexnow(site, urls):
    """Отправить адреса в IndexNow (Яндекс передаёт их и Bing). Возвращает текст результата; ошибка — RuntimeError."""
    st = key_status(site)
    if not st["ok"]:
        raise RuntimeError(f"Сначала выложите файл {st['file']} в корень сайта. " + st["error"])
    host = urlsplit(st["url"]).netloc
    urls = [u for u in urls if urlsplit(u).netloc == host][:10000]
    if not urls:
        raise RuntimeError("Нет адресов этого сайта для отправки.")
    body = json.dumps({"host": host, "key": st["key"], "keyLocation": st["url"], "urlList": urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with sysproxy.urlopen(req, timeout=30) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        msg = {400: "неправильный запрос", 403: "ключ не подошёл (файл ключа не найден или в нём другой ключ)",
               422: "адреса не относятся к этому сайту", 429: "слишком часто - попробуйте позже"}.get(e.code, "")
        raise RuntimeError(f"IndexNow ответил {e.code}" + (f": {msg}" if msg else ""))
    return f"Отправлено в IndexNow: {len(urls)} адресов (ответ {code}). Яндекс обойдёт их в ближайшие дни."


# ---------- очередь переобхода Вебмастера
def _wm_host(site):
    from .webmaster import find_host
    st = accounts._get("yandex")
    if not st.get("token"):
        raise RuntimeError("Не подключён вход в Яндекс (значок «Яндекс» вверху окна).")
    uid = st.get("user_id") or accounts._api("yandex", "/user")["user_id"]
    host = find_host(uid, site)
    if not host:
        raise RuntimeError("Этого сайта нет среди подтверждённых в подключённом Вебмастере.")
    return f"/user/{uid}/hosts/{urllib.parse.quote(host['host_id'], safe='')}"


def send_webmaster(site, urls):
    """Поставить адреса в очередь переобхода Вебмастера — сколько позволяет дневной лимит."""
    base = _wm_host(site)
    try:
        left = accounts._api("yandex", base + "/recrawl/quota").get("quota_remainder")
    except Exception:
        left = None
    sent, err = 0, ""
    for u in urls[: left if isinstance(left, int) else len(urls)]:
        try:
            accounts._api("yandex", base + "/recrawl/queue", {"url": u})
            sent += 1
        except Exception as e:
            err = str(e)[:200]
            if "scope" in err.lower() or "403" in err:
                err = ("у приложения на oauth.yandex.ru нет права webmaster:verify (оно нужно для переобхода) - добавьте "
                       "его, потом в программе «Отключить» и «Войти через Яндекс» заново")
            break
    rest = len(urls) - sent
    msg = f"В очередь переобхода Вебмастера: {sent} адресов."
    if rest and not err:
        msg += f" Ещё {rest} не поместились в дневной лимит - отправьте завтра или через IndexNow."
    if err:
        msg += " Остановился: " + err
    return msg
