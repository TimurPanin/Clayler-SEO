"""Данные Google Search Console для отчёта (нужен вход через Google — seocrawler/accounts.py).

Загружается при сборке отчёта (и «Обновить отчёт»), сохраняется в базу проверки (meta «gsc»):
запросы и страницы с показами за 28 дней, sitemap, и проверка индекса (URL Inspection) для важных страниц —
в индексе ли, какую страницу Google считает основной. Проверка индекса у Google ограничена (2000 в день на сайт),
поэтому смотрим до INSPECT страниц. Проблемы — analyze/checks/search_console.py, раздел отчёта — report_html.
Если Google не подключён или сайта нет в Search Console — тихо ничего не делает.
"""
import datetime
import time
import urllib.parse
from urllib.parse import urlsplit

from . import accounts
from .fmt import plural
from .webmaster import _norm

INSPECT = 100          # страниц на проверку индекса за один отчёт
DAYS = 28


def find_site(start_url):
    """Ресурс Search Console для адреса: сначала «префикс URL» с той же схемой и хостом, потом доменный (sc-domain:)."""
    sp = urlsplit(start_url)
    want = _norm(sp.hostname)
    best = None
    for e in accounts._api("google", "/sites").get("siteEntry", []):
        if e.get("permissionLevel") == "siteUnverifiedUser":
            continue
        u = e.get("siteUrl") or ""
        if u.startswith("sc-domain:"):
            host, score = u[10:], 1
        else:
            p = urlsplit(u)
            if p.path not in ("", "/"):
                continue
            host = p.hostname or ""
            score = 2 + (p.scheme == sp.scheme) * 2 + ((p.hostname or "") == (sp.hostname or ""))
        if _norm(host) == want and (not best or score > best[0]):
            best = (score, u)
    return best[1] if best else None


def in_property(url, site):
    """Относится ли адрес к ресурсу Search Console (иначе Google не даст его проверить)."""
    if site.startswith("sc-domain:"):
        host = (urlsplit(url).hostname or "").lower()
        return host == site[10:] or host.endswith("." + site[10:])
    return url.startswith(site)


def _query(site, dims, limit):
    end = datetime.date.today() - datetime.timedelta(days=2)  # последние 2 дня у Google ещё неполные
    start = end - datetime.timedelta(days=DAYS - 1)
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims, "rowLimit": limit}
    path = f"/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query"
    return accounts._api("google", path, body).get("rows", []), f"{start:%d.%m} – {end:%d.%m.%Y}"


def fetch(start_url, inspect_urls=(), log=print):
    """Собрать данные Search Console. inspect_urls — важные страницы для проверки индекса. None, если нечего."""
    if not accounts._get("google").get("token"):
        return None
    try:
        site = find_site(start_url)
    except Exception as e:
        log("Search Console: не получилось получить список сайтов - " + str(e)[:150])
        return None
    if not site:
        log("Search Console: этого сайта нет среди ресурсов подключённого аккаунта Google - данные не добавлены.")
        return None
    out = {"site": site, "fetched": time.strftime("%d.%m.%Y %H:%M"), "errors": []}
    try:
        rows, out["period"] = _query(site, ["query"], 1000)
        out["queries"] = [{"q": r["keys"][0], "clicks": r.get("clicks", 0), "shows": r.get("impressions", 0),
                           "pos": r.get("position")} for r in rows]
        rows, _ = _query(site, ["page"], 25000)
        out["pages"] = [{"url": r["keys"][0], "clicks": r.get("clicks", 0), "shows": r.get("impressions", 0),
                         "pos": r.get("position")} for r in rows]
    except Exception as e:
        out["errors"].append("запросы: " + str(e)[:150])
    try:   # какая страница показывается по запросу - для «Где теряем клики»
        rows, _ = _query(site, ["query", "page"], 5000)
        out["qp"] = [{"q": r["keys"][0], "url": r["keys"][1], "shows": r.get("impressions", 0)} for r in rows]
    except Exception as e:
        out["errors"].append("страницы по запросам: " + str(e)[:150])
    try:
        out["sitemaps"] = accounts._api("google", f"/sites/{urllib.parse.quote(site, safe='')}/sitemaps").get("sitemap", [])
    except Exception as e:
        out["errors"].append("sitemap: " + str(e)[:150])
    ins = []
    mine = [u for u in inspect_urls if in_property(u, site)]
    if inspect_urls and not mine:  # ресурс http://, а сайт на https:// (или наоборот) — Google проверять не даст
        out["hint"] = (f"Страницы сайта открываются по адресам вида {urlsplit(inspect_urls[0]).scheme}://…, а ресурс в "
                       f"Search Console - {site}. Добавьте в Search Console ресурс с тем же началом адреса "
                       f"(или доменный ресурс) - тогда программа проверит, какие страницы в индексе.")
    for u in mine[:INSPECT]:
        try:
            r = accounts._api("google", accounts.PROVIDERS["google"]["inspect"],
                              {"inspectionUrl": u, "siteUrl": site, "languageCode": "ru"})
            ir = (r.get("inspectionResult") or {}).get("indexStatusResult") or {}
            ins.append({"url": u, "verdict": ir.get("verdict"), "coverage": ir.get("coverageState"),
                        "google_canonical": ir.get("googleCanonical"), "user_canonical": ir.get("userCanonical"),
                        "last_crawl": (ir.get("lastCrawlTime") or "")[:10]})
        except Exception as e:
            out["errors"].append("проверка индекса: " + str(e)[:150])
            break  # закончилась дневная норма или нет прав — остальные не пробуем
    out["inspect"] = ins
    log(f"Search Console: {site} - запросов {len(out.get('queries') or [])}, страниц с показами "
        f"{len(out.get('pages') or [])}, проверено в индексе {len(ins)}.")
    return out


def indexed(x):
    """В индексе ли страница по ответу проверки: verdict PASS (у старых данных — по тексту coverage)."""
    return x.get("verdict") == "PASS" if x.get("verdict") else x.get("coverage") in COVERAGE_OK


# Состояния индекса из URL Inspection. Просим по-русски (languageCode=ru); если Google ответил по-английски — переводим
COVERAGE_OK = ("Submitted and indexed", "Indexed, not submitted in sitemap", "Страница отправлена и проиндексирована",
               "Страница проиндексирована, но её нет в файле Sitemap")
COVERAGE = {
    "Crawled - currently not indexed": "просканирована, но пока не проиндексирована",
    "Discovered - currently not indexed": "обнаружена, но ещё не просканирована",
    "Page with redirect": "страница с переадресацией",
    "Not found (404)": "не найдена (404)",
    "Soft 404": "ложная 404 (пустая страница с кодом 200)",
    "Excluded by ‘noindex’ tag": "исключена тегом noindex",
    "Blocked by robots.txt": "заблокирована в robots.txt",
    "Duplicate without user-selected canonical": "дубль, основная страница не указана",
    "Duplicate, Google chose different canonical than user": "дубль: Google выбрал другую основную страницу",
    "Alternate page with proper canonical tag": "альтернативная страница с правильным canonical",
    "Server error (5xx)": "ошибка сервера (5xx)",
    "URL is unknown to Google": "Google не знает об этой странице",
}


# «Где теряем клики»: показы и клики за 28 дней настоящие (Search Console), кликабельность места - средняя (оценка)
NEAR_FROM, NEAR_TO, TARGET = 4, 20, 3   # запросы на 4-20 месте: сколько кликов дало бы 3-е место
NEAR_MIN_SHOWS = 10                     # показов за 28 дней: меньше - случайность
LOW_CTR_MAX_POS, LOW_CTR_MIN_SHOWS = 3, 50   # на 1-3 месте, но кликают меньше половины обычного - плохой сниппет
LOST_NOTE = ("Оценка: показы за 28 дней из Search Console, умноженные на среднюю кликабельность места (у 1-го места "
             "около 28 % кликов, у 3-го 10 %, у 10-го 2 %), минус клики, которые уже есть. У каждого запроса своя "
             "кликабельность (реклама, карты, ответы прямо в выдаче), поэтому числа примерные.")


def _page_by_query(g):
    best = {}
    for r in g.get("qp") or []:
        if r["q"] not in best or r["shows"] > best[r["q"]][1]:
            best[r["q"]] = (r["url"], r["shows"])
    return {q: u for q, (u, _) in best.items()}


def positions(g):
    """Сколько запросов на каком месте в Google: [(подпись, запросов, показов)]."""
    out = [["на 1-3 месте", 0, 0], ["на 4-10 месте", 0, 0], ["на 11-20 месте", 0, 0], ["дальше 20-го места", 0, 0]]
    for q in g.get("queries") or []:
        if q.get("pos") is None:
            continue
        p = round(q["pos"])
        k = 0 if p <= 3 else 1 if p <= 10 else 2 if p <= 20 else 3
        out[k][1] += 1
        out[k][2] += q["shows"]
    return [tuple(x) for x in out]


def lost(g):
    """Где теряем клики в Google. → (рядом с тройкой, плохой сниппет): строки
    [запрос, страница, место, показы, клики, сколько ещё кликов за 28 дней], по убыванию последнего."""
    from .semantics.bukvarix import ctr
    page = _page_by_query(g)
    near, snip = [], []
    for q in g.get("queries") or []:
        pos, shows, clicks = q.get("pos"), q.get("shows") or 0, q.get("clicks") or 0
        if pos is None:
            continue
        row = [q["q"], page.get(q["q"], ""), round(pos, 1), round(shows), round(clicks)]
        if NEAR_FROM <= round(pos) <= NEAR_TO and shows >= NEAR_MIN_SHOWS:
            more = round(shows * ctr(TARGET) - clicks)
            if more >= 1:
                near.append(row + [more])
        elif round(pos) <= LOW_CTR_MAX_POS and shows >= LOW_CTR_MIN_SHOWS and clicks < shows * ctr(pos) / 2:
            more = round(shows * ctr(pos) - clicks)
            if more >= 1:
                snip.append(row + [more])
    return sorted(near, key=lambda r: -r[5]), sorted(snip, key=lambda r: -r[5])


def report_html(g, esc):
    """Раздел отчёта «Google Search Console»: клики, показы, позиции, популярные запросы и где теряем клики за 28 дней."""
    if not g:
        return ""
    num = lambda x: f"{round(x):,}".replace(",", " ")
    pages = g.get("pages") or []
    ok = sum(1 for x in g.get("inspect") or [] if indexed(x))
    cards = "".join(f'<div class="card"><b class="big">{v}</b><span>{t}</span></div>' for v, t in (
        (num(sum(p["clicks"] for p in pages)), "кликов из Google за 28 дней"),
        (num(sum(p["shows"] for p in pages)), "показов в Google за 28 дней"),
        (f"{ok} из {len(g.get('inspect') or [])}" if g.get("inspect") else "-",
         "важных страниц в индексе Google (выборочная проверка)")))
    rows = "".join(f'<tr><td>{esc(q["q"])}</td><td>{num(q["shows"])}</td><td>{num(q["clicks"])}</td>'
                   f'<td>{"-" if q.get("pos") is None else format(q["pos"], ".1f")}</td></tr>'
                   for q in sorted(g.get("queries") or [], key=lambda q: -q["clicks"])[:50])
    table = (f'<div class="card"><h3>Популярные запросы в Google</h3><div class="tw" style="margin:0"><table><thead><tr>'
             f'<th>Запрос</th><th>Показы</th><th>Клики</th><th>Средняя позиция</th></tr></thead><tbody>{rows}'
             f'</tbody></table></div></div>') if rows else ""
    pos = positions(g)
    if any(n for _t, n, _s in pos):
        tr = "".join(f'<tr><td>{t[:1].upper() + t[1:]}</td><td>{num(n)}</td><td>{num(s)}</td></tr>' for t, n, s in pos)
        table = (f'<div class="card"><h3>Места в Google</h3><p class="mut">Сколько запросов сайта на каком месте в '
                 f'Google в среднем за 28 дней и сколько у них показов.</p><div class="tw" style="margin:0"><table><thead>'
                 f'<tr><th>Место</th><th>Запросов</th><th>Показов</th></tr></thead><tbody>{tr}</tbody></table></div></div>'
                 + table)
    near, snip = lost(g)

    def lost_table(title, why, rs):
        if not rs:
            return ""
        tr = "".join(f'<tr><td>{esc(r[0])}</td><td class="u">{esc(r[1]) or "-"}</td><td>{r[2]:.1f}</td>'
                     f'<td>{num(r[3])}</td><td>{num(r[4])}</td><td><b>+{num(r[5])}</b></td></tr>' for r in rs[:30])
        more = sum(r[5] for r in rs)
        return (f'<div class="card"><h3>{title}: ≈ +{num(more)} {plural(more, "клик", "клика", "кликов")} за 28 дней</h3>'
                f'<p class="mut">{why}</p><div class="tw" style="margin:0"><table><thead><tr><th>Запрос</th>'
                f'<th>Страница в Google</th><th>Место</th><th>Показы</th><th>Клики</th><th>Ещё кликов</th></tr></thead>'
                f'<tbody>{tr}</tbody></table></div></div>')
    table += lost_table("Где теряем клики: до первой тройки недалеко",
                        f"Запросы, где сайт в Google на {NEAR_FROM}-{NEAR_TO} месте и его уже показывают. «Ещё кликов» - "
                        f"сколько дало бы {TARGET}-е место. Начните сверху: усильте страницу текстом под запрос, "
                        "поправьте title и H1, поставьте на неё ссылки с других страниц. " + LOST_NOTE, near)
    table += lost_table("Где теряем клики: место высокое, а кликают мало",
                        f"Сайт на 1-{LOW_CTR_MAX_POS} месте, но кликают меньше половины обычного. Обычно виноват "
                        "сниппет: title и description не отвечают на запрос или не цепляют. " + LOST_NOTE, snip)
    err =(f'<p class="mut">Не всё загрузилось: {esc("; ".join(g["errors"]))}</p>') if g.get("errors") else ""
    if g.get("hint"):
        err += f'<p class="mut">{esc(g["hint"])}</p>'
    return (f'<h2 class="sec">Google Search Console</h2><p class="mut" style="margin:0">Данные Google для '
            f'{esc(g.get("site"))} за {esc(g.get("period") or "28 дней")}, загружены {esc(g.get("fetched"))}. '
            f'Проблемы из них - в разделе «Найденные проблемы», группа «Google Search Console».</p>'
            f'<div class="grid" style="margin-top:12px">{cards}</div>{table}{err}')


def query_pages(start_url, log=print):
    """Какую страницу Google показывает по запросу (для семантики): {запрос: адрес} - по наибольшим показам."""
    try:
        site = find_site(start_url) if accounts._get("google").get("token") else None
        if not site:
            return {}
        rows, _period = _query(site, ["query", "page"], 5000)
    except Exception as e:
        log("Search Console: страницы по запросам не загружены - " + str(e)[:150])
        return {}
    best = {}
    for r in rows:
        q, page = r["keys"][0], r["keys"][1]
        if q not in best or r.get("impressions", 0) > best[q][1]:
            best[q] = (page, r.get("impressions", 0))
    return {q: p for q, (p, _) in best.items()}


def queries_for_semantics(start_url, log=print):
    """Только запросы за 28 дней (для семантики, если в проверке их нет): (состояние, [{q, clicks, shows, pos}]).
    Состояния — как у webmaster.queries_for_semantics."""
    if not accounts._get("google").get("token"):
        return "not_connected", []
    try:
        site = find_site(start_url)
        if not site:
            return "no_access", []
        rows, _period = _query(site, ["query"], 1000)
    except Exception as e:
        log("Search Console: запросы не загружены - " + str(e)[:150])
        return accounts.fail_state(e), []
    out = [{"q": r["keys"][0], "clicks": r.get("clicks", 0), "shows": r.get("impressions", 0), "pos": r.get("position")}
           for r in rows]
    return ("ok" if out else "no_data"), out


def known_urls(start_url, log=print):
    """Адреса страниц, которые Google показывал в поиске за 28 дней (для обхода: страницы без ссылок на сайте).
    (состояние, [адреса]). Состояния — как у webmaster.queries_for_semantics."""
    if not accounts._get("google").get("token"):
        return "not_connected", []
    try:
        site = find_site(start_url)
        if not site:
            return "no_access", []
        rows, _period = _query(site, ["page"], 25000)
    except Exception as e:
        log("Search Console: адреса страниц не загружены - " + str(e)[:150])
        return "error", []
    urls = [r["keys"][0] for r in rows if r.get("keys")]
    return ("ok" if urls else "no_data"), urls
