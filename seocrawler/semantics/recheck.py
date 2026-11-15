"""«После правок проверить снова»: заново скачать только страницы, которых касаются задачи семантики, без
полной проверки сайта, и отметить, что исправилось.

- Страницы с замечаниями (title, H1, описание, текст): каждое замечание проверяется заново тем же правилом,
  что и при сборе семантики (главный запрос в title и H1, «цена» в title, город, описание, слова в тексте,
  объём текста). Текст страницы берётся целиком, с меню и подвалом, поэтому проверка чуть мягче, чем при сборе.
- Страницы, которые мешают друг другу (только случаи с решением): «Оставить одну главной» — у остальных свои
  title и H1 и ссылка на главную; «Склеить» — с остальных 301-переадресация на главную; «Развести по смыслу» —
  у всех страниц разные title и H1.
Итог записывается в решения сайта (decisions.py, ключ «recheck») и показывается на странице «Семантика»."""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urldefrag

from . import decisions as D

THREADS = 4
MAX_PAGES = 400
MIN_WORDS = 150
BUY_RX = re.compile(r"купит|цен|стоимост|заказ|недорог", re.I)
STATE = {}   # сайт → {"running", "done", "total", "error"}
_lock = threading.Lock()


def status(host):
    return dict(STATE.get(D.site_key(host)) or {"running": False})


def targets(data):
    """Какие страницы перепроверять: с замечаниями и из случаев «мешают друг другу» с решением."""
    urls = []
    for g in data.get("groups") or []:
        if g.get("kind") == "page" and g.get("page") and (g.get("a") or {}).get("problems"):
            urls.append(g["page"])
    for c in data.get("cannibal") or []:
        if c.get("decision") and c["decision"] != "ok":
            urls += [p["url"] for p in c["pages"]]
    return list(dict.fromkeys(urls))[:MAX_PAGES]


def start(data, folder=""):
    """Запустить в фоне. data — семантика с наложенными решениями (decisions.apply), folder — папка проверки
    (оттуда страницы «до правок»). Возвращает текст ошибки или ""."""
    host = D.site_key(data.get("host"))
    urls = targets(data)
    if not urls:
        return "Перепроверять нечего: нет страниц с замечаниями и случаев с решением."
    with _lock:
        if (STATE.get(host) or {}).get("running"):
            return ""
        STATE[host] = {"running": True, "done": 0, "total": len(urls), "error": "", "started": D.now()}
    threading.Thread(target=_run, args=(data, host, urls, folder), daemon=True).start()
    return ""


def _fetch_all(site, urls, st):
    from ..fetcher import Fetcher, UA_PRESETS
    from ..parser import parse_html
    f = Fetcher(UA_PRESETS["chrome"], timeout=20, total_timeout=40)
    try:
        from .. import site_auth
        auth = site_auth.headers_for(site)
        if auth:
            f.host_headers.update(auth)
    except Exception:
        pass

    def one(u):
        info = {"url": u, "status": 0, "error": "", "location": "", "title": "", "h1": "", "description": "",
                "text": "", "words": 0, "links": set()}
        try:
            r = f.fetch(u)
            info["status"], info["error"] = r.status, r.error
            if r.location:
                info["location"] = _clean(urljoin(u, r.location))
            if r.status == 200 and r.is_html and r.body:
                p = parse_html(r.body, r.headers.get("content-type", ""))
                info.update(title=(p["titles"] or [""])[0], h1=(p["h1"] or [""])[0],
                            description=(p["descriptions"] or [""])[0], text=p["text"], words=p["content_words"],
                            links={_clean(urljoin(u, x.get("href") or "")) for x in p["links"]})
        except Exception as e:  # одна страница не должна ронять всю перепроверку
            info["error"] = str(e)[:150]
        st["done"] += 1
        return u, info
    with ThreadPoolExecutor(THREADS) as ex:
        out = dict(ex.map(one, urls))
    f.close()
    return out


def _clean(u):
    u = urldefrag(u or "")[0]
    return u[:-1] if u.endswith("/") and u.count("/") > 3 else u


def _same(u1, u2):
    from ..urls import same_page   # общее правило для адресов: http/https, www, слэш в конце, якорь
    return same_page(u1, u2)


def _n(s):
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def check_group(g, page, city):
    """Замечания группы: какие исправлены, какие остались."""
    from . import norm, core, keys, _covers
    a = g.get("a") or {}
    gcore = core(norm(g["name"])) or core(norm(a.get("main") or ""))

    def has(s):
        return bool(s) and bool(gcore) and _covers(core(norm(s)), gcore)
    page_keys = set()
    for t in set(re.findall(r"[a-zа-я0-9]+", norm(" ".join((page["title"], page["h1"], page["description"], page["text"]))))):
        page_keys |= keys(t)

    def words_in(ws):
        miss = [w for w in ws if not keys(_n(w)) & page_keys]
        return not miss, miss
    fixed, left = [], []
    for p in a.get("problems") or []:
        ok, note = None, ""
        if p.startswith("В title нет главного запроса"):
            ok = has(page["title"])
        elif p.startswith("В title нет «купить»") or p.startswith("В title нет «цена»"):
            ok = bool(BUY_RX.search(page["title"]))
        elif p.startswith("В title нет города"):
            ok = bool(city) and _n(city)[:-1] in _n(page["title"])
        elif p.startswith("В H1 нет главного запроса"):
            ok = has(page["h1"])
        elif p.startswith("Нет описания"):
            ok = bool(page["description"].strip())
        elif p.startswith("В описании (description) нет главного запроса"):
            ok = has(page["description"])
        elif p.startswith("Главный запрос"):
            ok = has(page["text"])
        elif p.startswith("В тексте нет слов"):
            ok, miss = words_in(a.get("missing") or [])
            note = "ещё нет: " + ", ".join(miss) if miss else ""
        elif p.startswith("У конкурента в тексте есть слова"):
            ok, miss = words_in(a.get("lsi") or [])
            note = "ещё нет: " + ", ".join(miss) if miss else ""
        elif p.startswith("Мало текста"):
            ok = page["words"] >= MIN_WORDS
            note = f"сейчас {page['words']} слов"
        elif p.startswith("Текста в"):
            m = re.search(r"против (\d+)", p)
            ok = bool(m) and page["words"] * 2 >= int(m.group(1))
            note = f"сейчас {page['words']} слов"
        (fixed if ok else left).append({"problem": p, "note": note, "auto": ok is not None})
    return {"page": g["page"], "fixed": fixed, "left": left}


def check_case(c, pages):
    """Случай «мешают друг другу» по принятому решению: исправлено ли."""
    ch, main = c.get("decision"), c["main"]
    others = [p["url"] for p in c["pages"] if p["url"] != main]
    notes = []
    mp = pages.get(main) or {}
    if ch == "main":
        from . import norm, core, _covers
        gc = core(norm(c.get("title") or ""))   # запросы главной: название группы или одинаковый H1/title
        for u in others:
            p = pages.get(u) or {}
            if p.get("status") != 200:
                notes.append(f"{D._short(u)}: страница не открылась ({p.get('status') or p.get('error') or 'нет ответа'})")
                continue
            for what in ("title", "h1"):
                if gc and p.get(what) and _covers(core(norm(p[what])), gc):
                    notes.append(f"{D._short(u)}: в {'title' if what == 'title' else 'H1'} всё ещё «{c.get('title')}»")
            if _n(p["title"]) and _n(p["title"]) == _n(mp.get("title")):
                notes.append(f"{D._short(u)}: title такой же, как у главной")
            if _n(p["h1"]) and _n(p["h1"]) == _n(mp.get("h1")):
                notes.append(f"{D._short(u)}: H1 такой же, как у главной")
            if not any(_same(x, main) for x in p["links"]):
                notes.append(f"{D._short(u)}: нет ссылки на главную {D._short(main)}")
    elif ch == "merge":
        for u in others:
            p = pages.get(u) or {}
            if p.get("status") in (301, 308) and _same(p.get("location"), main):
                continue
            if p.get("status") in (302, 303, 307) and _same(p.get("location"), main):
                notes.append(f"{D._short(u)}: переадресация временная ({p['status']}), нужна 301")
            elif p.get("status") in (301, 302, 303, 307, 308):
                notes.append(f"{D._short(u)}: переадресация ведёт не на главную, а на {D._short(p.get('location'))}")
            else:
                notes.append(f"{D._short(u)}: переадресации нет, страница отвечает {p.get('status') or p.get('error') or 'ошибкой'}")
    elif ch == "split":
        got = [(u, pages.get(u) or {}) for u in [p["url"] for p in c["pages"]]]
        for what in ("title", "h1"):
            seen = {}
            for u, p in got:
                v = _n(p.get(what))
                if v:
                    seen.setdefault(v, []).append(u)
            for v, us in seen.items():
                if len(us) > 1:
                    notes.append(f"{'Title' if what == 'title' else 'H1'} всё ещё одинаковый у " + ", ".join(D._short(u) for u in us))
    return {"fixed": not notes, "notes": notes}


def _baseline(folder, urls):
    """Те же страницы, какими они были при проверке сайта (crawl.db): «до правок». Сравнение с ними честнее:
    исправленным считается только то, что тем же правилом было не так тогда и так сейчас."""
    import os
    import sqlite3
    import zlib
    out = {}
    try:
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    except sqlite3.Error:
        return out
    try:
        for u in urls:
            r = db.execute("SELECT status, location, title, h1, description, content_words, blocks FROM pages WHERE url=?",
                           (u,)).fetchone()
            if not r:
                continue
            text = ""
            if r[6]:
                try:
                    text = " ".join(zlib.decompress(r[6]).decode("utf-8").split("\n"))
                except Exception:
                    pass
            links = {_clean(x) for (x,) in db.execute(
                "SELECT d.s FROM link_rows l JOIN strs s ON s.id = l.src JOIN strs d ON d.id = l.dst "
                "WHERE s.s = ? AND l.kind = 'a'", (u,))}
            out[u] = {"url": u, "status": r[0] or 0, "error": "", "location": _clean(r[1] or ""), "title": r[2] or "",
                      "h1": r[3] or "", "description": r[4] or "", "text": text, "words": r[5] or 0, "links": links}
    except sqlite3.Error:
        pass
    db.close()
    return out


def _run(data, host, urls, folder=""):
    st = STATE[host]
    try:
        pages = _fetch_all(data.get("site") or "https://" + host, urls, st)
        before = _baseline(folder, urls) if folder else {}
        groups, cases = {}, {}
        for g in data.get("groups") or []:
            if g.get("kind") == "page" and g.get("page") in pages and (g.get("a") or {}).get("problems"):
                p = pages[g["page"]]
                if p["status"] != 200:
                    groups[g["name"]] = {"page": g["page"], "fixed": [], "left": [], "manual": [], "error":
                                         f"страница не открылась ({p['status'] or p['error'] or 'нет ответа'})"}
                    continue
                r = check_group(g, p, data.get("city"))
                # замечание, которое этим правилом не видно и на странице «до правок», проверить точно нельзя
                b = before.get(g["page"])
                was_ok = {x["problem"] for x in check_group(g, b, data.get("city"))["fixed"]} if b else set()
                r["manual"] = [x for x in r["fixed"] + r["left"] if x["problem"] in was_ok or not x["auto"]]
                r["fixed"] = [x for x in r["fixed"] if x not in r["manual"]]
                r["left"] = [x for x in r["left"] if x not in r["manual"]]
                groups[g["name"]] = r
        for c in data.get("cannibal") or []:
            if c.get("decision") and c["decision"] != "ok":
                r = check_case(c, pages)
                if r["fixed"] and before and all(p["url"] in before for p in c["pages"]) and check_case(c, before)["fixed"]:
                    r.update(fixed=False, manual=True, notes=["Программа не видит разницы с тем, что было до правок: "
                                                              "проверьте сами по задаче."])
                cases[c["key"]] = r
        n_prob = sum(len(r["fixed"]) + len(r["left"]) for r in groups.values())
        res = {"at": D.now(), "pages": len(pages), "groups": groups, "cannibal": cases,
               "summary": {"pages": len(pages),
                           "groups_total": len(groups), "groups_fixed": sum(1 for r in groups.values() if r["fixed"] and not r["left"] and not r.get("error")),
                           "problems_total": n_prob, "problems_fixed": sum(len(r["fixed"]) for r in groups.values()),
                           "problems_manual": sum(len(r.get("manual") or []) for r in groups.values()),
                           "cases_total": len(cases), "cases_fixed": sum(1 for r in cases.values() if r["fixed"])}}
        D.update(host, lambda d: d.__setitem__("recheck", res))
    except Exception as e:
        st["error"] = "Перепроверка не получилась: " + str(e)[:200]
    finally:
        st["running"] = False
        st["finished"] = time.time()
