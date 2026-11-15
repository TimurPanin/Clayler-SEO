"""Обновления поиска и «Что просело» - вкладка «Обновления» на странице «Семантика» (window/semupd.py, page/semupd.js).

Откуда даты обновлений:
- Google: открытый список status.search.google.com/incidents.json, раздел «Ranking» (core, spam и другие
  обновления) - название, начало и конец раскатки. Google держит в списке около года, поэтому всё, что программа
  видела, копится в файле и не пропадает.
- Яндекс: общего списка нет. Даты обновления поисковой базы («апы») - точки истории «страниц в поиске» Вебмастера
  (search-urls/in-search/history): база одна на все сайты, поэтому годится любой подтверждённый сайт аккаунта.
  Тоже копятся в файле. Встряски выдачи, которые замечают SEO-трекеры (Pixel Tools, PR-CY, XTOOL), - ручной список:
  несколько известных дат вписаны (KNOWN), свои добавляются в окне. Чужие сайты программа не читает.
- По своему сайту, по дням: показы, клики и средняя позиция в Яндексе (Вебмастер search-queries/all/history),
  страниц в поиске и сколько появилось / выпало на каждом обновлении базы (in-search/history, events/history),
  клики, показы и позиция в Google (Search Console), визиты из поиска Яндекса и Google (Метрика).
«Что просело» (compare): те же источники за N дней до даты и N дней после - запросы и страницы входа, разложено
по группам семантики; просевшие страницы рядом с проблемами, которые нашла проверка (.анализ.pickle), и короткий
текст для клиента «почему меньше посетителей из поиска» со списком «что делаем / чего не делаем».
Файлы: «решения семантики/обновления поиска.json» (общие даты) и «решения семантики/<сайт> - обновления.json»."""
import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request

from .. import accounts, jsonfile, sysproxy

GOOGLE_URL = os.environ.get("CLAYLER_GOOGLE_STATUS") or "https://status.search.google.com/incidents.json"
DAYS = 365          # графики за год (Вебмастер сам отдаёт столько, сколько хранит)
FRESH = 12 * 3600   # общие даты и данные сайта обновляются не чаще раза в 12 часов
WINDOW = 28         # «до» и «после» - по 28 дней (меньше, если после даты прошло меньше)
LAG = 3             # последние дни у Google и Вебмастера ещё неполные

# Встряски выдачи Яндекса, которые заметили SEO-трекеры (их наблюдение, а не слова Яндекса)
KNOWN = [
    {"date": "2026-09-26", "name": "Pixel Tools: «Снижение влияния ПФ в услугах»", "src": "https://tools.pixelplus.ru/updates/yandex"},
    {"date": "2026-09-28", "name": "PR-CY: выдача изменилась на 16,5 %", "src": "https://pr-cy.ru/updates/"},
    {"date": "2026-10-05", "name": "XTOOL: выдача изменилась на 16 %", "src": "https://xtool.ru/updates-informer/"},
]

MONTHS = {"January": "январь", "February": "февраль", "March": "март", "April": "апрель", "May": "май", "June": "июнь",
          "July": "июль", "August": "август", "September": "сентябрь", "October": "октябрь", "November": "ноябрь",
          "December": "декабрь"}
KINDS = [("core", "Основное обновление Google (core update)"), ("spam", "Обновление Google против спама"),
         ("helpful content", "Обновление Google о полезном контенте"), ("review", "Обновление Google об обзорах"),
         ("discover", "Обновление Google Discover"), ("link", "Обновление Google о ссылках")]


def _say(*a):
    """Запись в журнал окна: консоль Windows может не уметь русские буквы - тогда молча."""
    try:
        print(*a)
    except Exception:
        pass


def _today():
    return datetime.date.today()


def _d(s):
    return datetime.date.fromisoformat(str(s)[:10])


def ru_date(s):
    return _d(s).strftime("%d.%m.%Y")


def google_name(en):
    """«May 2026 core update» → «Основное обновление Google (core update), май 2026»."""
    low = en.lower()
    kind = next((ru for k, ru in KINDS if k in low), "")
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", en)
    when = f"{MONTHS[m.group(1)]} {m.group(2)}" if m else ""
    if not kind:
        return en
    return kind + (", " + when if when else "")


# ---------- хранение

def _dir():
    from . import decisions
    return decisions.DIR


def _global_path():
    return os.path.join(_dir(), "обновления поиска.json")


def _site_path(host):
    from . import decisions
    return decisions.site_file(host, " - обновления")


_read = jsonfile.load


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    jsonfile.save(path, data, indent=1)


# ---------- общие даты: Google, базы Яндекса, встряски

def _retry(fn, tries=3):
    """Сеть оборвалась (WinError 10054 через VPN) - ещё раз через 2 и 5 секунд, а не сразу ошибка (15.10.2026)."""
    for i in range(tries):
        try:
            return fn()
        except (OSError, ValueError):
            if i == tries - 1:
                raise
            time.sleep((2, 5)[min(i, 1)])


def _fetch_google():
    req = urllib.request.Request(GOOGLE_URL, headers={"User-Agent": "Mozilla/5.0 ClaylerSEO"})
    with sysproxy.urlopen(req, timeout=30) as r:
        items = json.loads(r.read())
    out = {}
    for x in items:
        if x.get("service_name") != "Ranking" or not x.get("begin"):
            continue
        en = x.get("external_desc") or ""
        out[x.get("id") or en] = {"begin": x["begin"][:10], "end": (x.get("end") or "")[:10], "name": google_name(en),
                                  "en": en, "url": "https://status.search.google.com/" + (x.get("uri") or "")}
    return out


def _yandex_host():
    """(путь API сайта) любого подтверждённого сайта аккаунта - для дат обновления базы. None - Яндекс не подключён."""
    st = accounts._get("yandex")
    if not st.get("token"):
        return None
    uid = st.get("user_id") or accounts._api("yandex", "/user")["user_id"]
    for h in accounts._api("yandex", f"/user/{uid}/hosts").get("hosts", []):
        if h.get("verified"):
            base = f"/user/{uid}/hosts/{urllib.parse.quote(h['host_id'], safe='')}"
            try:
                accounts._api("yandex", base + "/summary")
                return base
            except Exception:
                continue   # сайт ещё не загружен в Вебмастер - следующий
    return None


def _history_points(r):
    return [(p["date"][:10], p.get("value")) for p in r.get("history") or [] if p.get("date")]


def refresh(force=False, log=None):
    """Обновить общие даты (раз в 12 часов). Возвращает файл общих дат."""
    g = _read(_global_path())
    now = time.time()
    changed = False
    if force or now - (g.get("google_at") or 0) > FRESH:
        try:
            items = _retry(_fetch_google)
            g.setdefault("google", {}).update(items)
            g["google_at"], g["google_err"] = now, ""
        except Exception as e:
            g["google_err"] = "Список обновлений Google не загрузился: " + str(e)[:150]
            g["google_at"] = now - FRESH + 3600   # повторить через час
        changed = True
    if force or now - (g.get("yandex_at") or 0) > FRESH:
        g["yandex_at"] = now
        try:
            base = _retry(_yandex_host)
            if base:
                frm = (_today() - datetime.timedelta(days=DAYS)).isoformat()
                pts = _history_points(_retry(lambda: accounts._api(
                    "yandex", base + f"/search-urls/in-search/history?date_from={frm}&date_to={_today().isoformat()}")))
                add_bases([d for d, _v in pts], g)
                g["yandex_err"] = ""
            else:
                g["yandex_err"] = "no_yandex"
        except Exception as e:
            # «The handshake operation timed out» (20.10.2026): связь оборвалась - повторить через час, а не через 12
            g["yandex_err"] = "Даты обновления базы Яндекса не загрузились: " + str(e)[:150]
            g["yandex_at"] = now - FRESH + 3600
        changed = True
    if changed:
        _write(_global_path(), g)
    return g


def add_bases(dates, g=None):
    """Запомнить даты обновления поисковой базы Яндекса (копятся, не теряются)."""
    save = g is None
    g = g if g is not None else _read(_global_path())
    have = set(g.get("yandex_bases") or [])
    have.update(d for d in dates if d)
    g["yandex_bases"] = sorted(have)
    if save:
        _write(_global_path(), g)


def manual_add(date, name, src=""):
    try:
        date = _d(date).isoformat()
    except ValueError:
        return "Дата не похожа на дату: нужно, например, 28.09.2026."
    name = (name or "").strip()[:200]
    if not name:
        return "Напишите, что это за встряска (например, «PR-CY: выдача изменилась на 15 %»)."
    g = _read(_global_path())
    g.setdefault("manual", []).append({"id": f"m{int(time.time() * 1000)}", "date": date, "name": name,
                                       "src": (src or "").strip()[:300]})
    _write(_global_path(), g)
    return ""


def manual_del(mid):
    g = _read(_global_path())
    if str(mid).startswith("k"):   # вписанная программой - прячем
        g["hidden"] = sorted(set(g.get("hidden") or []) | {str(mid)})
    else:
        g["manual"] = [m for m in g.get("manual") or [] if m.get("id") != mid]
    _write(_global_path(), g)


def events(g=None):
    """Все отметки для графиков: [{kind: google|yandex|base, date, end, name, url, id}] по дате."""
    g = g if g is not None else _read(_global_path())
    out = []
    for gid, x in (g.get("google") or {}).items():
        out.append({"kind": "google", "id": gid, "date": x["begin"], "end": x.get("end") or "", "name": x["name"],
                    "en": x.get("en") or "", "url": x.get("url") or ""})
    hidden = set(g.get("hidden") or [])
    for i, k in enumerate(KNOWN):
        if f"k{i}" not in hidden:
            out.append({"kind": "yandex", "id": f"k{i}", "date": k["date"], "name": k["name"], "url": k["src"], "known": True})
    for m in g.get("manual") or []:
        out.append({"kind": "yandex", "id": m["id"], "date": m["date"], "name": m["name"], "url": m.get("src") or ""})
    for d in g.get("yandex_bases") or []:
        out.append({"kind": "base", "date": d, "name": "Яндекс обновил поисковую базу"})
    out.sort(key=lambda e: e["date"])
    return out


def default_date(evs, today=None):
    """Дата для «Что просело» по умолчанию: последнее обновление Google или встряска Яндекса, после которой прошло
    хотя бы 3 полных дня данных. Обычные обновления базы Яндекса идут каждые несколько дней - их не берём."""
    last = (today or _today()) - datetime.timedelta(days=LAG + 3)
    for e in reversed(evs):
        if e["kind"] in ("google", "yandex") and _d(e["date"]) <= last:
            return e["date"]
    return (last - datetime.timedelta(days=WINDOW - 3)).isoformat()


# ---------- данные сайта по дням

def _api_r(*a):
    """Запрос к Вебмастеру или Search Console с повтором, если оборвалась связь (не при ответе с ошибкой)."""
    return _retry(lambda: accounts._api(*a))


def _wm_base(start_url):
    from ..webmaster import find_host
    st = accounts._get("yandex")
    if not st.get("token"):
        return None, "not_connected"
    uid = st.get("user_id") or accounts._api("yandex", "/user")["user_id"]
    host = find_host(uid, start_url)
    if not host:
        return None, "no_access"
    return f"/user/{uid}/hosts/{urllib.parse.quote(host['host_id'], safe='')}", "ok"


def _gsc_site(start_url):
    from ..search_console import find_site
    if not accounts._get("google").get("token"):
        return None, "not_connected"
    site = find_site(start_url)
    return (site, "ok") if site else (None, "no_access")


def _gsc(site, body):
    path = f"/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query"
    return _api_r("google", path, body).get("rows", [])


def _counter(start_url):
    from .. import metrika
    if not accounts._get("yandex").get("token"):
        return None, "not_connected"
    c = metrika.find_counter(start_url)
    return (c["id"], "ok") if c else (None, "no_access")


def _metrika(cid, d1, d2, dims, limit=10000):
    from .. import metrika
    return _retry(lambda: metrika._get("/stat/v1/data", ids=cid, metrics="ym:s:visits", dimensions=dims, filters=metrika.ORGANIC,
                        date1=d1, date2=d2, limit=limit, accuracy="full")).get("data", [])


def _engine(dim):
    v = (dim.get("id") or dim.get("name") or "").lower()
    return "yandex" if "yandex" in v or "яндекс" in v else "google" if "google" in v else "other"


def _err(e):
    s = str(e)
    return "no_data" if "HOST_NOT_LOADED" in s else "error: " + s[:200]


def fetch_series(start_url, log=None):
    """Данные сайта по дням из Вебмастера, Search Console и Метрики за год. Что не подключено - пусто с причиной."""
    to = _today()
    frm = to - datetime.timedelta(days=DAYS)
    out = {"fetched": time.strftime("%d.%m.%Y %H:%M"), "at": time.time(), "status": {}}
    # Яндекс Вебмастер
    try:
        base, st = _wm_base(start_url)
        out["status"]["wm"] = st
        if base:
            rng = f"date_from={frm.isoformat()}&date_to={to.isoformat()}"
            r = _api_r("yandex", base + "/search-queries/all/history?query_indicator=TOTAL_SHOWS&query_indicator="
                              "TOTAL_CLICKS&query_indicator=AVG_SHOW_POSITION&" + rng).get("indicators") or {}
            pick = lambda k: [[p["date"][:10], p.get("value") or 0] for p in r.get(k) or []]
            wm = {"shows": pick("TOTAL_SHOWS"), "clicks": pick("TOTAL_CLICKS"),
                  "pos": [x for x in pick("AVG_SHOW_POSITION") if x[1]]}
            wm["in_search"] = [list(p) for p in _history_points(
                _api_r("yandex", base + "/search-urls/in-search/history?" + rng))]
            ev = _api_r("yandex", base + "/search-urls/events/history?" + rng).get("indicators") or {}
            wm["appeared"] = [[p["date"][:10], p.get("value") or 0] for p in ev.get("APPEARED_IN_SEARCH") or []]
            wm["removed"] = [[p["date"][:10], p.get("value") or 0] for p in ev.get("REMOVED_FROM_SEARCH") or []]
            add_bases([d for d, _v in wm["in_search"]])
            out["wm"] = wm
    except Exception as e:
        out["status"]["wm"] = _err(e)
    # Google Search Console
    try:
        site, st = _gsc_site(start_url)
        out["status"]["gsc"] = st
        if site:
            rows = _gsc(site, {"startDate": frm.isoformat(), "endDate": to.isoformat(), "dimensions": ["date"],
                               "rowLimit": 1000})
            rows.sort(key=lambda r: r["keys"][0])
            out["gsc"] = {"clicks": [[r["keys"][0], r.get("clicks", 0)] for r in rows],
                          "shows": [[r["keys"][0], r.get("impressions", 0)] for r in rows],
                          "pos": [[r["keys"][0], round(r["position"], 1)] for r in rows if r.get("position")]}
    except Exception as e:
        out["status"]["gsc"] = _err(e)
    # Яндекс Метрика: визиты из поиска по дням, Яндекс и Google порознь
    try:
        cid, st = _counter(start_url)
        out["status"]["metrika"] = st
        if cid:
            days = {}
            for r in _metrika(cid, frm.isoformat(), "yesterday", "ym:s:date,ym:s:lastSearchEngineRoot"):
                d = (r["dimensions"][0].get("name") or "")[:10]
                e = _engine(r["dimensions"][1])
                days.setdefault(d, {"yandex": 0, "google": 0, "other": 0})[e] += r["metrics"][0]
            ks = sorted(days)
            out["metrika"] = {e: [[d, round(days[d][e])] for d in ks] for e in ("yandex", "google")}
    except Exception as e:
        out["status"]["metrika"] = _err(e)
    (log or _say)(f"Обновления поиска: данные сайта по дням - Вебмастер {out['status'].get('wm')}, "
        f"Search Console {out['status'].get('gsc')}, Метрика {out['status'].get('metrika')}.")
    return out


# ---------- «Что просело»

def windows(date, today=None):
    """(до: начало, конец), (после: начало, конец), дней - по N дней до даты и с даты. Ошибка - текст."""
    d = _d(date)
    last = (today or _today()) - datetime.timedelta(days=LAG)
    n = min(WINDOW, (last - d).days + 1)
    if n < 3:
        return None, None, 0, (f"После {ru_date(date)} прошло слишком мало дней: поисковики ещё не отдали данные. "
                               f"Сравнить можно, когда пройдёт хотя бы {LAG + 3} дня.")
    one = datetime.timedelta(days=1)
    return (d - n * one, d - one), (d, d + (n - 1) * one), n, ""


def _wm_queries(base, a, b):
    from ..webmaster import _pages
    q = ("/search-queries/popular?order_by=TOTAL_SHOWS&query_indicator=TOTAL_SHOWS&query_indicator=TOTAL_CLICKS"
         f"&query_indicator=AVG_SHOW_POSITION&date_from={a.isoformat()}&date_to={b.isoformat()}")
    out = {}
    for r in _pages(base + q, "queries", 3000):
        ind = r.get("indicators") or {}
        out[(r.get("query_text") or "").lower().strip()] = {
            "clicks": ind.get("TOTAL_CLICKS") or 0, "shows": ind.get("TOTAL_SHOWS") or 0, "pos": ind.get("AVG_SHOW_POSITION")}
    return out


def _gsc_dim(site, dim, a, b):
    rows = _gsc(site, {"startDate": a.isoformat(), "endDate": b.isoformat(), "dimensions": [dim], "rowLimit": 25000})
    return {(r["keys"][0].lower().strip() if dim == "query" else r["keys"][0]):
            {"clicks": r.get("clicks", 0), "shows": r.get("impressions", 0), "pos": r.get("position")} for r in rows}


def _metrika_pages(cid, a, b):
    out = {}
    for r in _metrika(cid, a.isoformat(), b.isoformat(), "ym:s:startURL,ym:s:lastSearchEngineRoot"):
        u = r["dimensions"][0].get("name") or ""
        out.setdefault(u, {"yandex": 0, "google": 0, "other": 0})[_engine(r["dimensions"][1])] += r["metrics"][0]
    return out


def fetch_compare(start_url, date, today=None, log=None):
    """Сырые данные «до» и «после» из всех подключённых источников."""
    before, after, n, err = windows(date, today)
    if err:
        return None, err
    raw = {"date": _d(date).isoformat(), "days": n, "before": [before[0].isoformat(), before[1].isoformat()],
           "after": [after[0].isoformat(), after[1].isoformat()], "status": {}}
    try:
        base, st = _wm_base(start_url)
        raw["status"]["wm"] = st
        if base:
            raw["wm"] = [_wm_queries(base, *before), _wm_queries(base, *after)]
    except Exception as e:
        raw["status"]["wm"] = _err(e)
    try:
        site, st = _gsc_site(start_url)
        raw["status"]["gsc"] = st
        if site:
            raw["gsc_q"] = [_gsc_dim(site, "query", *before), _gsc_dim(site, "query", *after)]
            raw["gsc_p"] = [_gsc_dim(site, "page", *before), _gsc_dim(site, "page", *after)]
    except Exception as e:
        raw["status"]["gsc"] = _err(e)
    try:
        cid, st = _counter(start_url)
        raw["status"]["metrika"] = st
        if cid:
            raw["metrika"] = [_metrika_pages(cid, *before), _metrika_pages(cid, *after)]
    except Exception as e:
        raw["status"]["metrika"] = _err(e)
    if not any(k in raw for k in ("wm", "gsc_q", "metrika")):
        return None, ("Сравнивать не с чем: для этого сайта нет доступа ни к Вебмастеру, ни к Search Console, ни к Метрике. "
                      "Подключите их в «Настройках» (вход через Яндекс и Google) или попросите у клиента гостевой доступ.")
    return raw, ""


def _norm_url(u):
    sp = urllib.parse.urlsplit(u or "")
    host = (sp.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host + (sp.path.rstrip("/") or "/") + ("?" + sp.query if sp.query else "")


def page_problems(full):
    """{адрес без схемы и www: [(важность, проблема)]} из разбора проверки (.анализ.pickle). Нет разбора - {}."""
    import pickle
    from ..analyze.common import CRIT, WARN
    path = os.path.join(full or "", ".анализ.pickle")
    try:
        with open(path, "rb") as f:
            issues = pickle.load(f)["issues"]
    except Exception:
        return {}
    from .. import client_report
    out = {}
    rank = {CRIT: 0, WARN: 1}
    for iss in issues:
        if iss.page_col is None or iss.key in client_report.HIDE or iss.sitewide:
            continue
        title = client_report.client_text(iss.title)
        for row in iss.rows:
            try:
                cell = str(row[iss.page_col])
            except (IndexError, KeyError, TypeError):
                continue
            for u in cell.split("\n"):
                lst = out.setdefault(_norm_url(u), [])
                if all(t != title for _s, t in lst):
                    lst.append((rank.get(iss.severity, 2), title))
        for u in getattr(iss, "group_pages", ()):   # битые ссылки шаблона одной строкой - на всех своих страницах
            lst = out.setdefault(_norm_url(u), [])
            if all(t != title for _s, t in lst):
                lst.append((rank.get(iss.severity, 2), title))
    for lst in out.values():
        lst.sort()
    return out


def _pct(b, a):
    return None if not b else round((a - b) * 100 / b)


def _pos(rows):
    """Средняя позиция по показам."""
    s = sum(r["shows"] for r in rows if r.get("pos"))
    return round(sum(r["pos"] * r["shows"] for r in rows if r.get("pos")) / s, 1) if s else None


def analyze(data, raw, problems=None, evs=None):
    """Разбор «до / после» по группам семантики и страницам. data - семантика (export.load + решения)."""
    problems = problems or {}
    # запрос → группа
    qg = {}
    for i, g in enumerate(data.get("groups") or []):
        for r in g.get("q") or []:
            qg.setdefault(str(r[0]).lower().strip(), i)
    eng = {}
    if "wm" in raw:
        eng["yandex"] = raw["wm"]
    if "gsc_q" in raw:
        eng["google"] = raw["gsc_q"]
    # итоги по поисковикам: переходы из Вебмастера / Search Console, визиты из Метрики
    total = {}
    for e, (b, a) in eng.items():
        tb, ta = sum(x["clicks"] for x in b.values()), sum(x["clicks"] for x in a.values())
        total[e] = {"clicks": [round(tb), round(ta)], "shows": [round(sum(x["shows"] for x in b.values())),
                                                                round(sum(x["shows"] for x in a.values()))],
                    "pos": [_pos(b.values()), _pos(a.values())]}
    if "metrika" in raw:
        for e in ("yandex", "google"):
            v = [round(sum(p[e] for p in side.values())) for side in raw["metrika"]]
            total.setdefault(e, {})["visits"] = v
    for t in total.values():
        main = t.get("visits") or t.get("clicks") or [0, 0]
        t["pct"] = _pct(*main)
    # группы
    groups = {}
    for e, (b, a) in eng.items():
        for k, side in ((0, b), (1, a)):
            for q, x in side.items():
                gi = qg.get(q, -1)
                G = groups.setdefault(gi, {})
                E = G.setdefault(e, {"clicks": [0, 0], "shows": [0, 0], "rows": [[], []], "queries": {}})
                E["clicks"][k] += x["clicks"]
                E["shows"][k] += x["shows"]
                E["rows"][k].append(x)
                E["queries"].setdefault(q, [None, None])[k] = x
    pages_by_group = {}
    for i, g in enumerate(data.get("groups") or []):
        if g.get("page"):
            pages_by_group.setdefault(_norm_url(g["page"]), []).append(g["name"])
    mpages = {}
    if "metrika" in raw:
        for k, side in enumerate(raw["metrika"]):
            for u, v in side.items():
                mpages.setdefault(_norm_url(u), [{"yandex": 0, "google": 0}, {"yandex": 0, "google": 0}, u])
                for e in ("yandex", "google"):
                    mpages[_norm_url(u)][k][e] += v[e]
    out_groups = []
    for gi, G in groups.items():
        g = data["groups"][gi] if gi >= 0 else {"name": "Запросы вне групп семантики"}
        row = {"group": gi, "name": g["name"], "page": g.get("page") or "", "eng": {}, "loss": 0, "queries": []}
        for e, E in G.items():
            pb, pa = _pos(E["rows"][0]), _pos(E["rows"][1])
            row["eng"][e] = {"clicks": [round(E["clicks"][0]), round(E["clicks"][1])],
                             "shows": [round(E["shows"][0]), round(E["shows"][1])], "pos": [pb, pa]}
            row["loss"] += E["clicks"][0] - E["clicks"][1]
            for q, (xb, xa) in E["queries"].items():
                cb, ca = (xb or {}).get("clicks", 0), (xa or {}).get("clicks", 0)
                qb, qa = (xb or {}).get("pos"), (xa or {}).get("pos")
                worse = (qa or 100) - (qb or 100) if qb else 0
                if cb - ca >= 1 or worse >= 3:
                    row["queries"].append({"q": q, "e": e, "clicks": [round(cb), round(ca)],
                                           "pos": [qb and round(qb, 1), qa and round(qa, 1)]})
        row["queries"].sort(key=lambda r: (r["clicks"][1] - r["clicks"][0], -((r["pos"][1] or 100) - (r["pos"][0] or 100))))
        row["queries"] = row["queries"][:15]
        if g.get("page"):
            mp = mpages.get(_norm_url(g["page"]))
            if mp:
                row["visits"] = [round(mp[0]["yandex"] + mp[0]["google"]), round(mp[1]["yandex"] + mp[1]["google"])]
        allc = [sum(v["clicks"][k] for v in row["eng"].values()) for k in (0, 1)]
        posw = [p for v in row["eng"].values() for p in [v["pos"]] if p[0] and p[1]]
        row["fell"] = bool((allc[0] - allc[1] >= 2 and allc[1] <= allc[0] * 0.7)
                           or any(p[1] - p[0] >= 3 for p in posw)
                           or (row.get("visits") and row["visits"][0] - row["visits"][1] >= 3
                               and row["visits"][1] <= row["visits"][0] * 0.7))
        row["grew"] = bool(not row["fell"] and allc[1] - allc[0] >= 2 and allc[1] >= allc[0] * 1.3)
        row["loss"] = round(row["loss"])
        out_groups.append(row)
    out_groups.sort(key=lambda r: (not r["fell"], -r["loss"], r["name"]))
    # страницы: визиты из поиска (Метрика), иначе клики Google (Search Console)
    pages = {}
    for nu, (b, a, u) in mpages.items():
        pages[nu] = {"url": u, "yandex": [round(b["yandex"]), round(a["yandex"])], "google": [round(b["google"]), round(a["google"])],
                     "src": "visits"}
    if "gsc_p" in raw:
        for k, side in enumerate(raw["gsc_p"]):
            for u, x in side.items():
                P = pages.setdefault(_norm_url(u), {"url": u, "src": "clicks"})
                P.setdefault("gclicks", [0, 0])[k] += x["clicks"]
    out_pages = []
    for nu, P in pages.items():
        if P["src"] == "visits":
            b, a = P["yandex"][0] + P["google"][0], P["yandex"][1] + P["google"][1]
        else:
            b, a = P["gclicks"]
            P["google"] = [round(b), round(a)]
        loss = b - a
        if loss >= 3 and a <= b * 0.7:
            out_pages.append({"url": P["url"], "before": round(b), "after": round(a), "loss": round(loss),
                              "yandex": P.get("yandex"), "google": P.get("google"), "src": P["src"],
                              "groups": pages_by_group.get(nu, []),
                              "problems": [t for _s, t in problems.get(nu, [])][:6]})
    out_pages.sort(key=lambda p: -p["loss"])
    # обновления поиска рядом с датой
    near = []
    d0 = _d(raw["date"])
    for e in evs or []:
        a = _d(e["date"])
        z = _d(e["end"]) if e.get("end") else a
        if e["kind"] == "base":
            continue
        if a - datetime.timedelta(days=3) <= d0 <= z + datetime.timedelta(days=7) or d0 <= a <= _d(raw["after"][1]):
            near.append(e)
    bases = [e["date"] for e in evs or [] if e["kind"] == "base" and raw["after"][0] <= e["date"] <= raw["after"][1]]
    res = {"date": raw["date"], "days": raw["days"], "before": raw["before"], "after": raw["after"],
           "status": raw["status"], "total": total, "groups": out_groups[:300],
           "fell": sum(1 for g in out_groups if g["fell"]), "grew": sum(1 for g in out_groups if g["grew"]),
           "pages": out_pages[:100], "pages_more": max(0, len(out_pages) - 100), "near": near, "bases": bases,
           "made": time.strftime("%d.%m.%Y %H:%M"), "with_problems": bool(problems)}
    res["verdict"] = verdict(res)
    return res


DO = ["Ждём окончания обновления и ещё одну-две недели, ничего не переделывая на сайте: позиции часто частично "
      "возвращаются сами.",
      "Сравниваем «до» и «после» по группам запросов и смотрим конкурентов: если просели все сайты темы - дело в "
      "обновлении, если только наш - в самом сайте.",
      "Ищем общий признак у просевших страниц (мало своего текста, дубли, медленная загрузка, слабые коммерческие "
      "блоки) и исправляем его сразу на всех похожих страницах.",
      "Продолжаем плановую работу по аудиту: она не зависит от обновления."]
DONT = ["Не меняем массово заголовки, тексты и адреса страниц.",
        "Не удаляем и не склеиваем страницы.",
        "Не покупаем ссылки и не накручиваем поведенческие факторы.",
        "Не делаем выводов по двум-трём дням: во время обновления позиции скачут каждый день."]
ENG = {"yandex": "Яндекса", "google": "Google"}


def _pl(n, one, few, many):
    n = abs(int(n)) % 100
    return many if 11 <= n <= 14 else one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def _num(x):
    from ..fmt import num
    return num(round(x or 0))


def verdict(res):
    """Короткий вывод для оператора и текст для клиента."""
    T = res["total"]
    lines, client = [], []
    fell = {e: t for e, t in T.items() if t.get("pct") is not None and t["pct"] <= -15}
    for e, t in T.items():
        v = t.get("visits") or t.get("clicks")
        if not v:
            continue
        what = "посетителей" if t.get("visits") else "переходов"
        p = t.get("pct")
        ch = "без изменений" if p is None or abs(p) < 5 else (f"меньше на {-p} %" if p < 0 else f"больше на {p} %")
        client.append(f"Из {ENG[e]}: {what} было {_num(v[0])}, стало {_num(v[1])} ({ch}).")
    dn = f"{res['days']} {_pl(res['days'], 'день', 'дня', 'дней')}"
    period = (f"Сравнили {dn} до {ru_date(res['date'])} ({ru_date(res['before'][0])} - {ru_date(res['before'][1])}) "
              f"и {dn} после ({ru_date(res['after'][0])} - {ru_date(res['after'][1])}).")
    # рядом с датой - обновления того поисковика, который просел (просели оба или никто - все)
    near = [e for e in res["near"] if not fell or len(fell) > 1 or e["kind"] in fell]
    upd = []
    for e in near:
        if e["kind"] == "google":
            upd.append(f"{e['name']} ({ru_date(e['date'])}" + (f" - {ru_date(e['end'])})" if e.get("end") else ", ещё идёт)"))
        else:
            upd.append(f"встряска выдачи Яндекса {ru_date(e['date'])} (по наблюдению SEO-сервисов)")
    if not fell:
        head = "Заметного падения нет: посетителей из поиска примерно столько же или больше."
    elif len(fell) == len([t for t in T.values() if t.get("pct") is not None]) and len(fell) > 1:
        head = ("Просели оба поисковика сразу. Так бывает из-за сезона, проблем на самом сайте (страницы перестали "
                "открываться, сменились адреса) или совпавших обновлений.")
    else:
        e = next(iter(fell))
        other = [ENG[x] for x in T if x != e and T[x].get("pct") is not None]
        head = (f"Просел только поиск {ENG[e]}" + (f", из {', '.join(other)} посетителей примерно столько же" if other else "")
                + ". Значит, дело скорее в изменениях этого поисковика, чем в сайте.")
    lines.append(head)
    if upd:
        lines.append("В эти дни: " + "; ".join(upd) + ".")
    elif fell:
        lines.append("Известных обновлений поиска рядом с этой датой нет: стоит проверить сайт (доступность, "
                     "изменения на страницах) и сезон спроса.")
    if res["bases"]:
        n = len(res["bases"])
        lines.append(f"После даты Яндекс обновлял поисковую базу {n} {_pl(n, 'раз', 'раза', 'раз')}.")
    fg = [g for g in res["groups"] if g["fell"] and g["group"] >= 0]
    if fg:
        lines.append("Просели группы: " + ", ".join(f"«{g['name']}»" for g in fg[:5]) + (f" и ещё {len(fg) - 5}" if len(fg) > 5 else "") + ".")
    probs = [p for p in res["pages"] if p["problems"]]
    if probs:
        lines.append(f"На {len(probs)} из {len(res['pages'])} просевших страниц проверка нашла проблемы: их стоит "
                     f"исправить в первую очередь.")
    # текст для клиента
    t = [f"Почему изменилось число посетителей из поиска", "", period] + client + [""]
    if not fell:
        t.append("Заметного падения нет.")
    else:
        t.append(head)
        if upd:
            t.append("В эти дни поисковики обновляли выдачу: " + "; ".join(upd) + ". Такие обновления меняют "
                     "позиции у всех сайтов темы, а не только у нашего, и раскатываются одну-две недели.")
        if fg:
            t.append("Сильнее всего просели запросы про: " + ", ".join(g["name"].lower() for g in fg[:5]) + ".")
        if probs:
            t += ["", "На просевших страницах есть то, что стоит исправить:"]
            for p in probs[:5]:
                t.append(f"- {p['url']}: " + "; ".join(x[:1].lower() + x[1:] for x in p["problems"][:3]) + ".")
    t += ["", "Что делаем:"] + [f"- {x}" for x in DO] + ["", "Чего не делаем во время обновления:"] + [f"- {x}" for x in DONT]
    return {"lines": lines, "client": "\n".join(t), "fell": bool(fell)}


def compare(data, full, date, start_url, today=None, log=None):
    """«Что просело» на дату: загрузить, разобрать, запомнить. (результат, ошибка)."""
    g = refresh(log=log)
    raw, err = fetch_compare(start_url, date, today, log)
    if err:
        return None, err
    res = analyze(data, raw, page_problems(full), events(g))
    s = _read(_site_path(data["host"]))
    s["compare"] = res
    _write(_site_path(data["host"]), s)
    return res, ""


def _keep_old(new, old):
    """Источник не загрузился (сеть, VPN), а в прошлый раз загрузился - оставить прошлые данные графика и пометить,
    от какого числа они: раньше одна неудачная загрузка стирала графики и на экране было «не загружалось»."""
    for k in ("wm", "gsc", "metrika"):
        if str(new["status"].get(k, "")).startswith("error") and (old or {}).get(k):
            new[k] = old[k]
            new.setdefault("old", {})[k] = (old.get("old") or {}).get(k) or old.get("fetched") or ""
    return new


def build(data, full, load=False, log=None):
    """Всё для вкладки: отметки, данные сайта по дням (из файла; load - загрузить заново), последний разбор."""
    g = refresh(log=log) if load else _read(_global_path())
    s = _read(_site_path(data["host"]))
    if load:
        s["series"] = _keep_old(fetch_series(data["site"], log), s.get("series"))
        _write(_site_path(data["host"]), s)
        g = _read(_global_path())
    evs = events(g)
    stale = not s.get("series") or time.time() - (s["series"].get("at") or 0) > FRESH \
        or time.time() - (g.get("google_at") or 0) > FRESH
    return {"events": evs, "series": s.get("series"), "compare": s.get("compare"), "stale": stale,
            "default_date": default_date(evs), "google_err": g.get("google_err") or "",
            "yandex_err": "" if g.get("yandex_err") == "no_yandex" else (g.get("yandex_err") or ""),
            # прошлые даты есть - ошибка не красная, а тихая строка: на графиках всё видно, повтор через час
            "err_quiet": bool(g.get("google")),
            "yandex_quiet": bool(g.get("yandex_bases")),
            "do": DO, "dont": DONT}
