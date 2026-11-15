"""Данные Яндекс Вебмастера для отчёта (нужен вход через Яндекс — seocrawler/accounts.py).

Загружается при сборке отчёта (и при «Обновить отчёт»), сохраняется в базу проверки (meta «webmaster»):
сводка (страниц в поиске, исключено, ИКС), проблемы, которые видит сам Яндекс (диагностика), страницы в поиске,
появившиеся и выпавшие страницы, что робот скачивал и с каким кодом, популярные запросы.
Проблемы из этих данных — analyze/checks/webmaster.py, сводка и запросы — раздел отчёта (report.py).
Если Яндекс не подключён или сайта нет в Вебмастере — тихо ничего не делает.
"""
import time
import urllib.parse
from urllib.parse import urlsplit

from . import accounts

MAX_IN_SEARCH = 20000   # страниц в поиске загружаем не больше (по 100 за запрос)
MAX_EVENTS = 2000
MAX_INDEXING = 2000


def _norm(host):
    host = (host or "").lower().split(":")[0]
    try:
        host = host.encode("idna").decode() if not host.isascii() else host
    except Exception:
        pass
    return host[4:] if host.startswith("www.") else host


def find_hosts(uid, start_url):
    """Сайты в Вебмастере для адреса проверки, лучший первым: тот же домен (www и без www — одно), сначала
    главное зеркало (данные о поиске Яндекс собирает только по нему), потом та же схема и www. В аккаунте может
    быть и http://, и https://timurpanin.ru - раньше бралась схема адреса проверки, даже если это не главное
    зеркало, и в «Семантике» было «Вебмастер не загружен», хотя он подключён."""
    sp = urlsplit(start_url)
    want = _norm(sp.hostname)
    found = []
    for h in accounts._api("yandex", f"/user/{uid}/hosts").get("hosts", []):
        if not h.get("verified"):
            continue
        u = urlsplit(h.get("ascii_host_url") or "")
        if _norm(u.hostname) != want:
            continue
        score = (not h.get("main_mirror")) * 4 + (u.scheme == sp.scheme) * 2 + \
            ((u.hostname or "").startswith("www.") == (sp.hostname or "").startswith("www."))
        found.append((score, h))
    return [h for _s, h in sorted(found, key=lambda x: -x[0])]


def find_host(uid, start_url):
    hosts = find_hosts(uid, start_url)
    return hosts[0] if hosts else None


def _pages(path, key, limit):
    out, off = [], 0
    while off < limit:
        sep = "&" if "?" in path else "?"
        part = accounts._api("yandex", f"{path}{sep}offset={off}&limit=100").get(key, [])
        out += part
        if len(part) < 100:
            break
        off += 100
    return out


QA_DAYS = 14        # мониторинг запросов Вебмастера отдаёт последние 2 недели, по дням
QA_MAX = 1500


def analytics(base, kind, limit=QA_MAX):
    """Мониторинг поисковых запросов Вебмастера (POST query-analytics/list), kind - "URL" или "QUERY".
    → [{"text": адрес или запрос, "other": самый частый запрос страницы или страница запроса, "shows", "clicks",
    "pos"}] за QA_DAYS дней: показы и клики - сумма по дням, место - среднее по дням с весом показов."""
    out, off = [], 0
    while off < limit:
        r = accounts._api("yandex", base + "/query-analytics/list",
                          {"offset": off, "limit": 500, "device_type_indicator": "ALL", "text_indicator": kind})
        part = r.get("text_indicator_to_statistics") or []
        for x in part:
            days = {}
            for s in x.get("statistics") or []:
                days.setdefault(s.get("date"), {})[s.get("field")] = s.get("value") or 0
            shows = sum(d.get("IMPRESSIONS", 0) for d in days.values())
            clicks = sum(d.get("CLICKS", 0) for d in days.values())
            w = [(d["POSITION"], d.get("IMPRESSIONS", 0)) for d in days.values() if d.get("POSITION")]
            pos = (sum(p * n for p, n in w) / sum(n for _p, n in w) if sum(n for _p, n in w)
                   else (sum(p for p, _n in w) / len(w) if w else None))
            out.append({"text": (x.get("text_indicator") or {}).get("value") or "",
                        "other": (x.get("popular_complementary_indicator") or {}).get("value") or "",
                        "shows": shows, "clicks": clicks, "pos": pos})
        if len(part) < 500:
            break
        off += 500
    return out


def fetch(start_url, log=print):
    """Собрать данные Вебмастера для сайта. Возвращает словарь или None (не подключено, сайта нет)."""
    st = accounts._get("yandex")
    if not st.get("token"):
        return None
    try:
        uid = st.get("user_id") or accounts._api("yandex", "/user")["user_id"]
        host = find_host(uid, start_url)
    except Exception as e:
        log("Яндекс Вебмастер: не получилось получить список сайтов - " + str(e)[:150])
        return None
    if not host:
        log("Яндекс Вебмастер: этого сайта нет среди подтверждённых в подключённом аккаунте - данные не добавлены.")
        return None
    base = f"/user/{uid}/hosts/{urllib.parse.quote(host['host_id'], safe='')}"
    out = {"host": host.get("unicode_host_url") or host.get("ascii_host_url"), "fetched": time.strftime("%d.%m.%Y %H:%M"),
           "errors": []}
    q = ("/search-queries/popular?order_by=TOTAL_SHOWS&query_indicator=TOTAL_SHOWS&query_indicator=TOTAL_CLICKS"
         "&query_indicator=AVG_SHOW_POSITION&query_indicator=AVG_CLICK_POSITION")
    jobs = [
        ("summary", lambda: accounts._api("yandex", base + "/summary")),
        ("problems", lambda: accounts._api("yandex", base + "/diagnostics").get("problems", {})),
        ("in_search", lambda: _pages(base + "/search-urls/in-search/samples", "samples", MAX_IN_SEARCH)),
        ("events", lambda: _pages(base + "/search-urls/events/samples", "samples", MAX_EVENTS)),
        ("indexing", lambda: _pages(base + "/indexing/samples", "samples", MAX_INDEXING)),
        ("queries", lambda: _pages(base + q, "queries", 500)),
        # «Где теряем клики» (analyze/checks/lost_clicks.py): показы, клики и место по страницам и по запросам
        # со страницей за 2 недели. Написано по документации API (query-analytics), на настоящем доступе не проверено
        ("qa_urls", lambda: analytics(base, "URL")),
        ("qa_queries", lambda: analytics(base, "QUERY")),
    ]
    for key, fn in jobs:
        try:
            out[key] = fn()
        except Exception as e:
            if "HOST_NOT_LOADED" in str(e):  # сайт недавно добавлен в Вебмастер — Яндекс ещё не собрал данные
                out["not_loaded"] = True
            else:
                out["errors"].append(f"{key}: {str(e)[:150]}")
    if out.get("not_loaded"):
        log("Яндекс Вебмастер: сайт недавно добавлен, Яндекс ещё не собрал по нему данные (обычно несколько дней).")
    n = len(out.get("in_search") or [])
    log(f"Яндекс Вебмастер: {out['host']} - страниц в поиске загружено {n}, запросов {len(out.get('queries') or [])}.")
    return out


# Как Яндекс называет проблемы сайта (диагностика) — по-русски
PROBLEMS = {
    "CONNECTION_FAILED": "Робот не может подключиться к серверу",
    "CONNECT_FAILED": "Робот не может подключиться к серверу",
    "VIDEOHOST_OFFER_FAILED": "Не принято предложение видеохостинга",
    "DNS_ERROR": "Ошибка DNS: домен не открывается",
    "DISALLOWED_IN_ROBOTS": "Сайт закрыт от индексации в robots.txt",
    "MAIN_PAGE_ERROR": "Главная страница отдаёт ошибку",
    "THREATS": "Угрозы безопасности (вирусы, взлом)",
    "SSL_CERTIFICATE_ERROR": "Ошибка сертификата HTTPS",
    "URL_ALERT_4XX": "Много страниц с ошибкой 4xx",
    "URL_ALERT_5XX": "Много страниц с ошибкой 5xx",
    "SLOW_AVG_RESPONSE_TIME": "Сервер долго отвечает",
    "SOFT_404": "Несуществующие страницы отдают код 200 вместо 404",
    "DUPLICATE_PAGES": "Страницы-дубли",
    "DUPLICATE_CONTENT_ATTRS": "Одинаковые title и description",
    "DOCUMENTS_MISSING_TITLE": "Страницы без title",
    "DOCUMENTS_MISSING_DESCRIPTION": "Страницы без description",
    "INSIGNIFICANT_CGI_PARAMETER": "Незначащие параметры в адресах создают дубли (нужен Clean-param)",
    "ERROR_IN_ROBOTS_TXT": "Ошибки в robots.txt",
    "NO_ROBOTS_TXT": "Нет robots.txt",
    "ERRORS_IN_SITEMAPS": "Ошибки в sitemap",
    "NO_SITEMAPS": "Нет sitemap",
    "NO_SITEMAP_MODIFICATIONS": "Sitemap давно не обновлялся",
    "MAIN_MIRROR_IS_NOT_HTTPS": "Главное зеркало сайта - не HTTPS",
    "MAIN_PAGE_REDIRECTS": "Главная страница перенаправляет на другой адрес",
    "FAVICON_ERROR": "Ошибка фавиконки",
    "FAVICON_PROBLEM": "Проблема с фавиконкой",
    "BIG_FAVICON_ABSENT": "Нет фавиконки большого размера",
    "NO_METRIKA_COUNTER": "Не установлен счётчик Метрики",
    "NO_METRIKA_COUNTER_BINDING": "Счётчик Метрики не связан с Вебмастером",
    "NO_METRIKA_COUNTER_CRAWL_ENABLED": "Обход по счётчику Метрики выключен",
    "NO_REGIONS": "Не указан регион сайта",
    "NOT_IN_SPRAV": "Организации нет в Яндекс Бизнесе (Справочнике)",
    "NOT_MOBILE_FRIENDLY": "Сайт не оптимизирован для мобильных",
    "TOO_MANY_DOMAINS_ON_SEARCH": "В поиске слишком много поддоменов",
    "NON_WORKING_VIDEO": "Не работает видео на страницах",
}
SEVERITY = {"FATAL": "фатальная", "CRITICAL": "критичная", "POSSIBLE_PROBLEM": "возможная проблема",
            "RECOMMENDATION": "рекомендация"}

# Почему страница исключена из поиска
EXCLUDED = {
    "HTTP_ERROR": "страница отдаёт ошибку", "NOT_CANONICAL": "не основная (canonical на другую)",
    "DUPLICATE": "дубль другой страницы", "LOW_QUALITY": "недостаточно качественная",
    "META_NO_INDEX": "закрыта noindex", "ROBOTS_TXT_ERROR": "закрыта в robots.txt",
    "ROBOTS_HOST_ERROR": "закрыта в robots.txt", "REDIRECT_NOTSEARCHABLE": "перенаправляет на другую",
    "REDIRECT_SEARCHABLE": "перенаправляет (в поиске - конечная)", "CLEAN_PARAMS": "убрана по Clean-param",
    "NOT_MAIN_MIRROR": "не главное зеркало", "PARSER_ERROR": "робот не смог разобрать страницу",
    "NOTHING_FOUND": "не нашлось ничего полезного", "HOST_ERROR": "сайт не отвечал",
    "CONNECTION_ERROR": "не удалось подключиться", "BAD_QUALITY": "недостаточно качественная",
    "OTHER": "другая причина", "NOT_SUPPORTED": "формат не поддерживается",
}


def report_html(wm, esc):
    """Раздел отчёта «Яндекс Вебмастер»: сводка и популярные запросы. esc — экранирование HTML."""
    if not wm:
        return ""
    s = wm.get("summary") or {}
    num = lambda x: "-" if x is None else f"{x:,}".replace(",", " ")
    # сводка Вебмастера обновляется с задержкой: «0 в поиске», а в списке страниц в поиске уже есть адреса
    in_search = s.get("searchable_pages_count")
    seen = len(wm.get("in_search") or [])
    lag = in_search is not None and seen > in_search
    cards = "".join(f'<div class="card"><b class="big">{num(v)}</b><span>{t}</span></div>' for v, t in (
        (max(in_search, seen) if lag else in_search,
         "страниц в поиске Яндекса" + (" (по списку страниц в поиске, сводка Яндекса ещё не обновилась)" if lag else "")),
        (s.get("excluded_pages_count"), "страниц исключено из поиска"),
        (s.get("sqi"), "ИКС - индекс качества сайта")))
    rows = []
    for q in (wm.get("queries") or [])[:50]:
        ind = q.get("indicators") or {}
        pos = ind.get("AVG_SHOW_POSITION")
        rows.append(f'<tr><td>{esc(q.get("query_text"))}</td><td>{num(ind.get("TOTAL_SHOWS"))}</td>'
                    f'<td>{num(ind.get("TOTAL_CLICKS"))}</td><td>{"-" if pos is None else f"{pos:.1f}"}</td></tr>')
    table = (f'<div class="card"><h3>Популярные запросы за неделю</h3><div class="tw" style="margin:0"><table><thead><tr>'
             f'<th>Запрос</th><th>Показы</th><th>Клики</th><th>Средняя позиция</th></tr></thead><tbody>{"".join(rows)}'
             f'</tbody></table></div></div>') if rows else ""
    err = (f'<p class="mut">Не всё загрузилось: {esc("; ".join(wm["errors"]))}</p>') if wm.get("errors") else ""
    if wm.get("not_loaded"):
        err += ('<p class="mut">Сайт недавно добавлен в Вебмастер: Яндекс ещё не собрал по нему данные о поиске '
                '(обычно несколько дней). Пересоберите отчёт позже - «Ещё → Обновить отчёт».</p>')
    return (f'<h2 class="sec">Яндекс Вебмастер</h2><p class="mut" style="margin:0">Данные самого Яндекса для '
            f'{esc(wm.get("host"))} на {esc(wm.get("fetched"))}. Проблемы из них - в разделе «Найденные проблемы», '
            f'группа «Яндекс Вебмастер».</p><div class="grid" style="margin-top:12px">{cards}</div>{table}{err}')


def queries_for_semantics(start_url, log=print):
    """Только популярные запросы (для семантики, если в проверке их нет): (состояние, запросы).
    Состояние: ok, not_connected (вход через Яндекс не подключён), no_access (сайта нет среди подтверждённых
    в аккаунте: клиент не дал доступ), no_data (Яндекс ещё не собрал), error."""
    st = accounts._get("yandex")
    if not st.get("token"):
        return "not_connected", []
    try:
        uid = st.get("user_id") or accounts._api("yandex", "/user")["user_id"]
        hosts = find_hosts(uid, start_url)
    except Exception as e:
        log("Яндекс Вебмастер: запросы не загружены - " + str(e)[:150])
        return accounts.fail_state(e), []
    if not hosts:
        return "no_access", []
    state = "no_data"
    q = ("/search-queries/popular?order_by=TOTAL_SHOWS&query_indicator=TOTAL_SHOWS&query_indicator=TOTAL_CLICKS"
         "&query_indicator=AVG_SHOW_POSITION&query_indicator=AVG_CLICK_POSITION")
    for host in hosts:   # у первого пусто (не то зеркало, ещё не собран) - пробуем следующий: http и https
        try:
            base = f"/user/{uid}/hosts/{urllib.parse.quote(host['host_id'], safe='')}"
            rows = _pages(base + q, "queries", 500)
        except Exception as e:
            if "HOST_NOT_LOADED" not in str(e):
                log("Яндекс Вебмастер: запросы не загружены - " + str(e)[:150])
                state = accounts.fail_state(e)
            continue
        if rows:
            return "ok", rows
    return state, []


def known_urls(start_url, log=print):
    """Адреса страниц, которые Яндекс показывает в поиске (для обхода: страницы без ссылок на сайте).
    (состояние, [адреса]). Состояния — как у queries_for_semantics."""
    st = accounts._get("yandex")
    if not st.get("token"):
        return "not_connected", []
    try:
        uid = st.get("user_id") or accounts._api("yandex", "/user")["user_id"]
        host = find_host(uid, start_url)
        if not host:
            return "no_access", []
        base = f"/user/{uid}/hosts/{urllib.parse.quote(host['host_id'], safe='')}"
        rows = _pages(base + "/search-urls/in-search/samples", "samples", MAX_IN_SEARCH)
    except Exception as e:
        if "HOST_NOT_LOADED" in str(e):
            return "no_data", []
        log("Яндекс Вебмастер: адреса страниц в поиске не загружены - " + str(e)[:150])
        return "error", []
    urls = [s["url"] for s in rows if s.get("url")]
    return ("ok" if urls else "no_data"), urls
