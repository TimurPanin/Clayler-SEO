"""Наблюдение за сайтами, пока окно программы открыто: проверка по расписанию раз в неделю и мониторинг каждый час.

Мониторинг — лёгкая проверка без обхода: главная и до 9 самых важных страниц (на них больше всего ссылок внутри
сайта, по последней проверке) открываются с кодом 200 и не дольше 10 с, главная не закрыта noindex, robots.txt не
закрывает сайт целиком, SSL-сертификату осталось больше 14 дней. Если что-то сломалось — через 30 секунд ещё раз
(чтобы не тревожить из-за случайного сбоя), и только потом сообщение в Telegram. Когда починилось — тоже сообщение.

Список сайтов - «наблюдение.json» в папке «data» (в git не попадает).
"""
import os
import re
import socket
import sqlite3
import ssl
import threading
import time
import urllib.robotparser
from urllib.parse import urljoin, urlsplit

from . import jsonfile, paths

FILE = os.environ.get("CLAYLER_WATCH_FILE") or paths.data("наблюдение.json")
DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONITOR_EVERY = 60 * 60
SLOW_SECONDS = 10
CERT_DAYS = 14

_lock = threading.Lock()


# ---------- список сайтов ----------

def _load():
    return jsonfile.load(FILE)


def _save(data):
    jsonfile.save(FILE, data, indent=1)


def norm_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    p = urlsplit(url)
    if not p.hostname or "." not in p.hostname:
        return ""
    return f"{p.scheme}://{p.netloc.lower()}/"


def _key(url):
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def sites():
    return _load().get("sites", [])


def find(url):
    k = _key(norm_url(url) or url)
    return next((s for s in sites() if _key(s["url"]) == k), None)


def update(url, **fields):
    """Добавить сайт (если его нет) и поменять поля. None — убрать поле."""
    u = norm_url(url)
    if not u:
        return None, "Не понял адрес сайта."
    with _lock:
        data = _load()
        lst = data.setdefault("sites", [])
        cur = next((s for s in lst if _key(s["url"]) == _key(u)), None)
        if cur is None:
            cur = {"url": u, "monitor": False, "weekly": None, "pages": 10000}
            lst.append(cur)
        for k, v in fields.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        _save(data)
    return cur, ""


def remove(url):
    k = _key(norm_url(url) or url)
    with _lock:
        data = _load()
        before = len(data.get("sites", []))
        data["sites"] = [s for s in data.get("sites", []) if _key(s["url"]) != k]
        data.get("mon", {}).pop(k, None)
        _save(data)
    return "" if len(data["sites"]) < before else "Такого сайта в наблюдении нет."


def parse_weekly(text):
    """«пн 09:00» → {"day": 0, "time": "09:00"}; «выкл» → None. Возвращает (значение, ошибка)."""
    t = (text or "").strip().lower()
    if t in ("", "выкл", "нет", "off", "-"):
        return None, ""
    m = re.match(r"^(пн|вт|ср|чт|пт|сб|вс)\w*\s+(\d{1,2})[:.](\d{2})$", t)
    if not m or int(m.group(2)) > 23 or int(m.group(3)) > 59:
        return None, "Напишите день и время, например: пн 09:00"
    return {"day": DAYS.index(m.group(1)), "time": f"{int(m.group(2)):02d}:{m.group(3)}"}, ""


def weekly_text(w):
    return f"{DAYS[w['day']]} {w['time']}" if w else "выкл"


def mon_state(url):
    return _load().get("mon", {}).get(_key(url)) or {}


def _set_mon(url, state):
    with _lock:
        data = _load()
        data.setdefault("mon", {})[_key(url)] = state
        _save(data)


# ---------- проверка по расписанию ----------

def due(now=None):
    """Сайты, которым пора на проверку по расписанию (день и время наступили, сегодня ещё не запускали)."""
    now = now or time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    out = []
    for s in sites():
        w = s.get("weekly")
        if w and now.tm_wday == w["day"] and time.strftime("%H:%M", now) >= w["time"] and s.get("last_run") != today:
            out.append(s)
    return out


def mark_run(url):
    update(url, last_run=time.strftime("%Y-%m-%d"))


# ---------- мониторинг ----------

def important_pages(url, reports, n=9):
    """До n страниц, на которые больше всего ссылок внутри сайта, — по последней проверке этого сайта."""
    from .window.reports_list import list_checks
    for c in list_checks(reports):
        if c["key"] != _key(url):
            continue
        if c["folder"] in _pages_cache:  # на большом сайте запрос идёт ~20 с — считаем раз на проверку
            return _pages_cache[c["folder"]]
        db = os.path.join(reports, c["folder"], "crawl.db")
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            try:
                rows = con.execute("""
                    SELECT p.url FROM pages p JOIN urls u ON u.url = p.url
                    JOIN strs d ON d.s = p.url JOIN link_rows l ON l.dst = d.id AND l.internal = 1
                    WHERE u.internal = 1 AND u.kind = 'page' AND p.status = 200 AND p.content_type LIKE 'text/html%'
                    GROUP BY p.url ORDER BY COUNT(DISTINCT l.src) DESC LIMIT ?""", (n + 1,)).fetchall()
            finally:
                con.close()
        except Exception:
            continue
        main = norm_url(url)
        _pages_cache[c["folder"]] = [r[0] for r in rows if r[0] != main][:n]
        return _pages_cache[c["folder"]]
    return []


_pages_cache = {}


def _fetch(fetcher, url, hops=5):
    """Загрузить с переходом по редиректам. Возвращает (ответ, конечный адрес)."""
    for _ in range(hops):
        r = fetcher.fetch(url)
        if r.status in (301, 302, 303, 307, 308) and r.location:
            url = urljoin(url, r.location)
            continue
        return r, url
    return r, url


def _cert_days(host, port=443):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            na = ss.getpeercert().get("notAfter")
    return int((ssl.cert_time_to_seconds(na) - time.time()) // 86400) if na else None


def _page_problem(fetcher, u, is_main):
    r, final = _fetch(fetcher, u)
    if r.error:
        return f"{u} - не открывается: {r.error}"
    if r.status != 200:
        return f"{u} - отвечает {r.status}" + (f" (после редиректа на {final})" if final != u else "")
    if r.elapsed > SLOW_SECONDS:
        return f"{u} - открывается {r.elapsed:.0f} с"
    if is_main:
        body = r.body[:300000].decode("utf-8", "replace").lower()
        if re.search(r"<meta[^>]+name=[\"']?robots[\"']?[^>]+noindex", body) or \
                "noindex" in r.headers.get("x-robots-tag", "").lower():
            return f"{u} - главная закрыта от поиска (noindex)"
    return ""


def check_site(url, reports, fetcher=None):
    """Список проблем сайта сейчас (пустой — всё в порядке)."""
    from .fetcher import Fetcher, UA_PRESETS
    fetcher = fetcher or Fetcher(UA_PRESETS["crawler"], timeout=20, total_timeout=30)
    main = norm_url(url)
    pages = [main] + [p for p in important_pages(url, reports) if p != main]
    problems = []
    page_errs = [_page_problem(fetcher, u, i == 0) for i, u in enumerate(pages)]
    reasons = {p.split(" - ", 1)[1] for p in page_errs if p}
    if len(pages) > 1 and all(page_errs) and len(reasons) == 1:
        # у всех страниц одна и та же беда — одной строкой, а не десятью
        problems.append(f"сайт {reasons.pop()} (все {len(pages)} проверенные страницы)")
    else:
        problems += [p for p in page_errs if p]
    # robots.txt: не закрыт ли сайт целиком
    try:
        r = fetcher.fetch(urljoin(main, "/robots.txt"), any_type=True)
        if r.status == 200:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(r.body.decode("utf-8", "replace").splitlines())
            closed = [bot for bot in ("Yandex", "Googlebot") if not rp.can_fetch(bot, main)]
            if closed:
                problems.append("robots.txt закрывает сайт для " + " и ".join(closed))
    except Exception:
        pass
    host = urlsplit(main).hostname
    if main.startswith("https://"):
        try:
            days = _cert_days(host)
            if days is not None and days < CERT_DAYS:
                problems.append(f"SSL-сертификат " + (f"закончится через {days} дн." if days >= 0 else "уже закончился"))
        except ssl.SSLCertVerificationError as e:
            why = str(e.verify_message or e)
            why = ("выдан на другой адрес" if "mismatch" in why.lower() else
                   "просрочен" if "expired" in why.lower() else why[:80])
            # страницы с той же ошибкой сертификата отдельно не перечисляем
            problems = [p for p in problems if "SSL: ошибка сертификата" not in p]
            problems.insert(0, f"SSL-сертификат не проходит проверку ({why}) - браузер покажет посетителям "
                               "предупреждение «подключение не защищено»")
        except Exception:
            pass  # не соединились — это уже покажет проверка главной
    return problems, len(pages)


def monitor(url, reports, fetcher=None, pause=30):
    """Проверить сайт; при проблемах — перепроверить через pause секунд. Возвращает (новое состояние, сообщение
    для Telegram или "")."""
    problems, n = check_site(url, reports, fetcher)
    if problems and pause:
        time.sleep(pause)
        again, n = check_site(url, reports, fetcher)
        problems = [p for p in problems if p in again] or again  # тревожим только тем, что повторилось
    old = mon_state(url)
    now = time.strftime("%d.%m %H:%M")
    same = old and old.get("ok") == (not problems)  # «с какого времени так» — меняется, только когда сменилось
    state = {"ok": not problems, "problems": problems, "checked": now, "t": time.time(), "pages": n,
             "since": old.get("since", now) if same else now}
    _set_mon(url, state)
    msg = ""
    was_bad = old.get("ok") is False
    new = [p for p in problems if p not in (old.get("problems") or [])]
    if problems and new:
        msg = f"🚨 {url} - что-то сломалось:\n" + "\n".join("• " + p for p in problems)
    elif not problems and was_bad:
        msg = f"✅ {url} снова в порядке (проблема была с {old.get('since', '-')})."
    return state, msg


# ---------- фоновый поток ----------

def start(job, start_check, send, reports):
    """start_check(url, pages) — запустить проверку (возвращает ошибку или ""); send(text, url=None) — в Telegram."""
    def loop():
        while True:
            try:
                if not job.running:
                    for s in due():
                        err = start_check(s["url"], s.get("pages") or 10000)
                        if err and job.running:
                            break   # другая проверка успела начаться (очередь, окно): эта - в следующий раз, не пропадает
                        mark_run(s["url"])
                        if err:
                            send(f"⚠️ Проверка по расписанию {s['url']} не запустилась: {err}")
                        else:
                            send(f"🗓 Запустил проверку по расписанию: {s['url']}")
                        break  # по одной: следующая — когда эта закончится
                for s in sites():
                    if s.get("monitor") and time.time() - (mon_state(s["url"]).get("t") or 0) > MONITOR_EVERY:
                        _state, msg = monitor(s["url"], reports)
                        if msg:
                            send(msg, s["url"])  # с кнопками «Перепроверить» / «Не следить»
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()
