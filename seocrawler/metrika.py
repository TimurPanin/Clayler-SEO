"""Данные Яндекс Метрики для отчёта (тот же вход через Яндекс, доступ metrika:read — seocrawler/accounts.py).

Загружается при сборке отчёта, сохраняется в базу проверки (meta «metrika») за 30 дней до вчера:
визиты всего и из поиска, отказы, доля телефонов, поисковые системы, страницы входа из поиска (визиты, отказы).
Проблемы — analyze/checks/metrika.py (посетители из поиска попадают на неработающие страницы; страницы входа
с высокими отказами), раздел отчёта — report_html. Счётчик ищется по домену сайта среди доступных аккаунту
(свои и гостевой доступ). Нет входа или счётчика — тихо ничего не делает.
"""
import time
import urllib.parse
from urllib.parse import urlsplit

from . import accounts
from .webmaster import _norm

ORGANIC = "ym:s:lastTrafficSource=='organic'"


def _get(path, **q):
    base = accounts.PROVIDERS["yandex"]["metrika"]
    return accounts._api("yandex", base + path + ("?" + urllib.parse.urlencode(q, doseq=True) if q else ""))


def find_counter(start_url):
    want = _norm(urlsplit(start_url).hostname)
    best = None
    for c in _get("/management/v1/counters", per_page=1000).get("counters", []):
        sites = [c.get("site") or ""] + [m for m in c.get("mirrors") or []] + \
                [(c.get("site2") or {}).get("site") or ""]
        hosts = {_norm(urlsplit(s if "://" in s else "http://" + s).hostname) for s in sites if s}
        if want in hosts and c.get("status") != "Deleted":
            if not best or (c.get("code_status") == "CS_OK") > (best.get("code_status") == "CS_OK"):
                best = c
    return best


def _data(cid, metrics, dims=None, filters=None, limit=100, sort=None):
    q = {"ids": cid, "metrics": metrics, "date1": "30daysAgo", "date2": "yesterday", "limit": limit,
         "accuracy": "full"}
    if dims:
        q["dimensions"] = dims
    if filters:
        q["filters"] = filters
    if sort:
        q["sort"] = sort
    return _get("/stat/v1/data", **q)


def fetch(start_url, log=print):
    if not accounts._get("yandex").get("token"):
        return None
    try:
        c = find_counter(start_url)
    except Exception as e:
        msg = str(e)
        if "403" in msg or "scope" in msg.lower():
            log("Яндекс Метрика: нет доступа - в приложении на oauth.yandex.ru нужен доступ metrika:read, "
                "потом «Отключить» и «Войти через Яндекс» заново.")
        else:
            log("Яндекс Метрика: не получилось получить список счётчиков - " + msg[:150])
        return None
    if not c:
        log("Яндекс Метрика: счётчика этого сайта нет среди доступных подключённому аккаунту - данные не добавлены.")
        return None
    cid = c["id"]
    out = {"counter": cid, "name": c.get("name") or c.get("site"), "fetched": time.strftime("%d.%m.%Y %H:%M"),
           "errors": []}
    try:
        t = _data(cid, "ym:s:visits,ym:s:bounceRate,ym:s:users").get("totals") or [0, 0, 0]
        s = _data(cid, "ym:s:visits,ym:s:bounceRate", filters=ORGANIC).get("totals") or [0, 0]
        out.update(visits=t[0], bounce=t[1], users=t[2], search_visits=s[0], search_bounce=s[1])
        d = _data(cid, "ym:s:visits", dims="ym:s:deviceCategory")
        out["devices"] = {r["dimensions"][0].get("name") or "?": r["metrics"][0] for r in d.get("data", [])}
        e = _data(cid, "ym:s:visits,ym:s:bounceRate", dims="ym:s:lastSearchEngineRoot", filters=ORGANIC)
        out["engines"] = [{"name": r["dimensions"][0].get("name") or "?", "visits": r["metrics"][0],
                           "bounce": r["metrics"][1]} for r in e.get("data", [])]
        lp = _data(cid, "ym:s:visits,ym:s:bounceRate", dims="ym:s:startURL", filters=ORGANIC, limit=5000,
                   sort="-ym:s:visits")
        out["landing"] = [{"url": r["dimensions"][0].get("name") or "", "visits": r["metrics"][0],
                           "bounce": r["metrics"][1]} for r in lp.get("data", [])]
    except Exception as e:
        out["errors"].append(str(e)[:200])
    log(f"Яндекс Метрика: счётчик {cid} - визитов за 30 дней {round(out.get('visits') or 0)}, "
        f"из поиска {round(out.get('search_visits') or 0)}, страниц входа из поиска {len(out.get('landing') or [])}.")
    return out


def report_html(m, esc):
    """Раздел отчёта «Яндекс Метрика»: посещаемость за 30 дней, поиск, телефоны, страницы входа из поиска."""
    if not m:
        return ""
    num = lambda x: "-" if x is None else f"{round(x):,}".replace(",", " ")
    dev = m.get("devices") or {}
    total_dev = sum(dev.values()) or 0
    phone = sum(v for k, v in dev.items() if k.lower() in ("смартфоны", "smartphones", "планшеты", "tablets"))
    cards = "".join(f'<div class="card"><b class="big">{v}</b><span>{t}</span></div>' for v, t in (
        (num(m.get("visits")), "визитов за 30 дней"),
        (num(m.get("search_visits")), "из них из поиска" + (
            f" ({round(100 * m['search_visits'] / m['visits'])}%)" if m.get("visits") else "")),
        (f"{round(100 * phone / total_dev)}%" if total_dev else "-", "визитов с телефонов и планшетов"),
        (f"{m['search_bounce']:.0f}%" if m.get("search_bounce") is not None else "-", "отказов у посетителей из поиска")))
    eng = ", ".join(f"{esc(e['name'])} - {num(e['visits'])}" for e in m.get("engines") or [])
    rows = "".join(f'<tr><td>{esc(x["url"])}</td><td>{num(x["visits"])}</td><td>{x["bounce"]:.0f}%</td></tr>'
                   for x in (m.get("landing") or [])[:30])
    table = (f'<div class="card"><h3>Страницы, на которые приходят из поиска</h3><div class="tw" style="margin:0"><table>'
             f'<thead><tr><th>Страница</th><th>Визитов</th><th>Отказы</th></tr></thead><tbody>{rows}</tbody></table>'
             f'</div></div>') if rows else ""
    err = (f'<p class="mut">Не всё загрузилось: {esc("; ".join(m["errors"]))}</p>') if m.get("errors") else ""
    return (f'<h2 class="sec">Яндекс Метрика</h2><p class="mut" style="margin:0">Счётчик {esc(m.get("counter"))} '
            f'({esc(m.get("name"))}), последние 30 дней, загружено {esc(m.get("fetched"))}.'
            + (f" Из поиска: {eng}." if eng else "") + '</p>'
            f'<div class="grid" style="margin-top:12px">{cards}</div>{table}{err}')
