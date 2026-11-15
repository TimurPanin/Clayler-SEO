"""Проверка входа в Вебмастер и Search Console (seocrawler/accounts.py) на поддельном сервере Яндекса/Google:
код → ключ, список сайтов, ключи в файле зашифрованы, чужая ссылка не принимается, ключ Google обновляется,
«Отключить» отзывает ключ. Запуск: python тест/проверить_вход.py (вызывается и из проверить_всё.py)."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

LOG = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def out(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"])).decode()
        path = urlsplit(self.path).path
        if self.headers.get("Content-Type") == "application/json":  # API Search Console
            body = json.loads(raw)
            LOG.append((path, body))
            if path == "/webmasters/v3/sites/https%3A%2F%2Fsite.ru%2F/searchAnalytics/query":
                if body["dimensions"] == ["query"]:
                    return self.out({"rows": [{"keys": ["купить"], "clicks": 7, "impressions": 100, "position": 4.5},
                                              {"keys": ["цена"], "clicks": 5, "impressions": 200, "position": 1.2},
                                              {"keys": ["редко"], "clicks": 0, "impressions": 5, "position": 6}]})
                if body["dimensions"] == ["query", "page"]:
                    return self.out({"rows": [{"keys": ["купить", "https://site.ru/"], "impressions": 30},
                                              {"keys": ["купить", "https://site.ru/kupit"], "impressions": 70}]})
                return self.out({"rows": [{"keys": ["https://site.ru/old"], "clicks": 3, "impressions": 50},
                                          {"keys": ["https://site.ru/"], "clicks": 4, "impressions": 50}]})
            if path.endswith("/query-analytics/list"):   # мониторинг запросов Вебмастера (с 21.10.2026)
                if body.get("offset"):
                    return self.out({"text_indicator_to_statistics": []})
                text = "https://site.ru/" if body.get("text_indicator") == "URL" else "купить"
                return self.out({"text_indicator_to_statistics": [
                    {"text_indicator": {"value": text}, "statistics": [
                        {"date": "2026-10-20", "field": "IMPRESSIONS", "value": 40},
                        {"date": "2026-10-20", "field": "CLICKS", "value": 4},
                        {"date": "2026-10-20", "field": "POSITION", "value": 3.5}]}]})
            if path == "/v1/urlInspection/index:inspect":
                r = {"https://site.ru/": {"verdict": "PASS", "coverageState": "Страница отправлена и проиндексирована", "googleCanonical": "https://site.ru/",
                                          "userCanonical": "https://site.ru/"},
                     "https://site.ru/new": {"verdict": "NEUTRAL", "coverageState": "Crawled - currently not indexed",
                                             "googleCanonical": "https://site.ru/", "userCanonical": "https://site.ru/new"}}
                return self.out({"inspectionResult": {"indexStatusResult": r[body["inspectionUrl"]]}})
            return self.out({}, 404)
        f = {k: v[0] for k, v in parse_qs(raw).items()}
        LOG.append((path, f))
        if path == "/token":
            if f.get("client_secret") != "СЕКРЕТ-1":
                return self.out({"error": "invalid_client"}, 400)
            if f["grant_type"] == "authorization_code":
                if f.get("code") != "КОД" or not f.get("code_verifier"):
                    return self.out({"error": "bad_verification_code"}, 400)
                # payload id_token: {"email": "me@example.com"}
                return self.out({"access_token": "KEY-1", "refresh_token": "REFRESH-1", "expires_in": 3600,
                                 "id_token": "x.eyJlbWFpbCI6Im1lQGV4YW1wbGUuY29tIn0.y"})
            if f["grant_type"] == "refresh_token" and f.get("refresh_token") == "REFRESH-1":
                return self.out({"access_token": "KEY-2", "expires_in": 3600})
            return self.out({"error": "invalid_grant"}, 400)
        return self.out({})  # отзыв ключа

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        LOG.append((self.path, auth))
        if not auth.endswith(("KEY-1", "KEY-2")):
            return self.out({"error": "unauthorized"}, 401)
        if self.path == "/v4/user":
            return self.out({"user_id": 77})
        if self.path.startswith("/management/v1/counters"):  # Метрика
            return self.out({"counters": [{"id": 5, "site": "other.ru", "status": "Active"},
                                          {"id": 9, "site": "www.site.ru", "status": "Active", "code_status": "CS_OK"}]})
        if self.path.startswith("/stat/v1/data"):
            q = parse_qs(urlsplit(self.path).query)
            if q["ids"] != ["9"] or q["date1"] != ["30daysAgo"]:
                return self.out({}, 400)
            dims, organic = q.get("dimensions", [""])[0], "filters" in q
            if dims == "ym:s:startURL":
                return self.out({"data": [
                    {"dimensions": [{"name": "https://site.ru/old"}], "metrics": [40, 10.0]},
                    {"dimensions": [{"name": "https://site.ru/"}], "metrics": [100, 50.0]}]})
            if dims == "ym:s:deviceCategory":
                return self.out({"data": [{"dimensions": [{"name": "Смартфоны"}], "metrics": [60]},
                                          {"dimensions": [{"name": "ПК"}], "metrics": [40]}]})
            if dims == "ym:s:lastSearchEngineRoot":
                return self.out({"data": [{"dimensions": [{"name": "Яндекс"}], "metrics": [140, 30.0]}]})
            return self.out({"totals": [140, 30.0] if organic else [200, 25.0, 150]})
        if self.path == "/v4/user/77/hosts":
            return self.out({"hosts": [{"unicode_host_url": "https://сайт.рф:443", "verified": True},
                                       {"ascii_host_url": "https://chuzhoi.ru:443", "verified": False},
                                       {"ascii_host_url": "http://www.site.ru:80", "host_id": "http:www.site.ru:80",
                                        "verified": True},
                                       {"ascii_host_url": "https://site.ru:443", "host_id": "https:site.ru:443",
                                        "verified": True}]})
        base = "/v4/user/77/hosts/https%3Asite.ru%3A443"
        path, _, qs = self.path.partition("?")
        off = int(parse_qs(qs).get("offset", ["0"])[0])
        if path == base + "/summary":
            return self.out({"searchable_pages_count": 3, "excluded_pages_count": 5, "sqi": 40})
        if path == base + "/diagnostics":
            return self.out({"problems": {"NO_SITEMAPS": {"severity": "POSSIBLE_PROBLEM", "state": "PRESENT"},
                                          "DNS_ERROR": {"severity": "FATAL", "state": "ABSENT"}}})
        if path == base + "/search-urls/in-search/samples":  # 3 страницы, отдаём по 2, чтобы проверить листание
            urls = ["https://site.ru/", "https://site.ru/old", "https://site.ru/%D0%BA"][off:]
            return self.out({"samples": [{"url": u} for u in urls[:2]]}) if "limit=100" in qs else self.out({}, 400)
        if path == base + "/search-urls/events/samples":
            return self.out({"samples": [{"url": "https://site.ru/gone", "event": "REMOVED_FROM_SEARCH",
                                          "excluded_url_status": "HTTP_ERROR", "event_date": "2026-09-20T00:00:00"}]})
        if path == base + "/indexing/samples":
            return self.out({"samples": []})
        if path == base + "/search-queries/popular":
            return self.out({"queries": [{"query_text": "купить", "indicators": {"TOTAL_SHOWS": 10.0,
                                                                                 "AVG_SHOW_POSITION": 3.25}}]})
        if self.path == "/webmasters/v3/sites":
            return self.out({"siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
                                           {"siteUrl": "sc-domain:site.ru", "permissionLevel": "siteFullUser"},
                                           {"siteUrl": "https://site.ru/", "permissionLevel": "siteFullUser"},
                                           {"siteUrl": "https://x.ru/", "permissionLevel": "siteUnverifiedUser"}]})
        if self.path == "/webmasters/v3/sites/https%3A%2F%2Fsite.ru%2F/sitemaps":
            return self.out({"sitemap": [{"path": "https://site.ru/sitemap.xml", "errors": "2", "warnings": "0"},
                                         {"path": "https://site.ru/ok.xml", "errors": "0", "warnings": "0"}]})
        return self.out({}, 404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="clayler-acc-")
    os.environ["CLAYLER_OAUTH_TEST"] = f"http://127.0.0.1:{srv.server_port}"
    os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(tmp, "доступы.json")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from seocrawler import accounts as A
    bad = []

    def check(ok, what):
        if not ok:
            bad.append(what)

    check(A.start("yandex", 8900)[1], "вход без приложения должен просить ClientID")
    check(A.save_app("yandex", "ID-Я", "") != "", "без секрета сохранять нельзя")
    for p in ("yandex", "google"):
        check(A.save_app(p, "ID-" + p, "СЕКРЕТ-1") == "", f"{p}: приложение не сохранилось")
        url, err = A.start(p, 8900)
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        check(q.get("code_challenge_method") == "S256" and q.get("redirect_uri") == f"http://127.0.0.1:8900/oauth/{p}",
              f"{p}: в ссылке входа нет PKCE или адреса возврата")
        check(A.finish(p, {"state": "чужое", "code": "КОД"}) != "", f"{p}: принята ссылка с чужим state")
        check(A.finish(p, {"state": q["state"], "code": "КОД"}) == "", f"{p}: вход не завершился")
        check(A.finish(p, {"state": q["state"], "code": "КОД"}) != "", f"{p}: одну ссылку можно использовать дважды")
    st = A.status(8900)
    check(st["yandex"]["connected"] and st["yandex"]["sites"] == ["http://www.site.ru:80", "https://site.ru:443", "https://сайт.рф:443"], "Вебмастер: не тот список сайтов")
    check(st["google"]["account"] == "me@example.com" and st["google"]["sites"] == ["https://site.ru/", "sc-domain:example.com", "sc-domain:site.ru"],
          "Search Console: не та почта или список сайтов")
    raw = open(os.environ["CLAYLER_ACCOUNTS_FILE"], encoding="utf-8").read()
    check(not any(s in raw for s in ("KEY-1", "СЕКРЕТ-1", "REFRESH-1")), "ключи лежат в файле открытым текстом")
    # данные Вебмастера для отчёта и проблемы из них
    from types import SimpleNamespace
    from seocrawler import webmaster as W
    from seocrawler.analyze.checks import webmaster as WC
    wm = W.fetch("https://site.ru/", log=lambda *a: None)
    check(wm and wm["summary"]["sqi"] == 40 and len(wm["in_search"]) == 2 and not wm["errors"]
          and wm.get("qa_urls") == [{"text": "https://site.ru/", "other": "", "shows": 40, "clicks": 4, "pos": 3.5}],
          f"Вебмастер: данные не загрузились или не тот сайт: {wm and wm.get('errors')}")
    check(W.fetch("https://other.ru/", log=lambda *a: None) is None, "Вебмастер: нашёлся сайт, которого нет")
    got = {}
    ctx = SimpleNamespace(store=SimpleNamespace(get_meta=lambda k, d=None: wm if k == "webmaster" else d),
                          status={"https://site.ru/": (200, None), "https://site.ru/old": (404, None),
                                  "https://site.ru/new": (200, None)},
                          indexable=[{"url": "https://site.ru/", "depth": 0}, {"url": "https://site.ru/new", "depth": 1}],
                          add=lambda key, sev, cat, title, why, fix, cols, rows, page_col=0: rows and got.update({key: rows}))
    WC.run(ctx)
    check(got.get("wm_index_broken") == [["https://site.ru/old", 404, ""]], "Вебмастер: не найдена 404 в поиске")
    check(got.get("wm_problems", [[""]])[0][0] == "Нет sitemap" and len(got["wm_problems"]) == 1,
          "Вебмастер: не те проблемы диагностики")
    check(got.get("wm_removed", [[0, 0]])[0][1] == "страница отдаёт ошибку", "Вебмастер: выпавшие страницы")
    check("wm_not_in_index" not in got, "Вебмастер: список «нет в поиске» при неполных данных")
    wm["in_search"].append({"url": "https://site.ru/%D0%BA"})
    got.clear()
    WC.run(ctx)
    check(got.get("wm_not_in_index") == [["https://site.ru/new", 1]], "Вебмастер: не найдена страница вне поиска")
    check("купить" in W.report_html(wm, str) and "3.2" in W.report_html(wm, str), "Вебмастер: раздел отчёта")
    # данные Search Console
    from seocrawler import search_console as G
    from seocrawler.analyze.checks import search_console as GC
    g = G.fetch("https://www.site.ru/", ["https://site.ru/", "https://site.ru/new"], log=lambda *a: None)
    check(g and g["site"] == "https://site.ru/" and len(g["pages"]) == 2 and len(g["inspect"]) == 2 and not g["errors"],
          f"Search Console: данные не загрузились или не тот ресурс: {g and g.get('errors')}")
    got.clear()
    ctx.store = SimpleNamespace(get_meta=lambda k, d=None: g if k == "gsc" else d)
    GC.run(ctx)
    check(got.get("gsc_index_broken") == [["https://site.ru/old", 404, 50, 3]], "Search Console: не найдена 404 в поиске")
    check(got.get("gsc_canonical_diff") == [["https://site.ru/new", "https://site.ru/new", "https://site.ru/"]],
          "Search Console: другой canonical у Google")
    check(got.get("gsc_not_indexed", [[0, 0]])[0][1] == "просканирована, но пока не проиндексирована",
          "Search Console: страница не в индексе")
    check(got.get("gsc_sitemap") == [["https://site.ru/sitemap.xml", 2, 0, ""]], "Search Console: ошибки sitemap")
    h = G.report_html(g, str)
    check("купить" in h and "4.5" in h and "1 из 2" in h, "Search Console: раздел отчёта")
    # где теряем клики: «купить» на 4-м месте (3-е место дало бы 10 кликов из 100 показов, есть 7), страница - с
    # наибольшими показами; «цена» на 1-м месте, кликов 5 из 200 при обычных 28 %; «редко» - мало показов
    check(got.get("gsc_near_top") == [["купить", "https://site.ru/kupit", 4.5, 100, 7, 3]],
          f"Search Console: до тройки недалеко: {got.get('gsc_near_top')}")
    check(got.get("gsc_low_ctr") == [["цена", "", 1.2, 200, 5, 51]], f"Search Console: мало кликов: {got.get('gsc_low_ctr')}")
    check(G.positions(g) == [("на 1-3 месте", 1, 200), ("на 4-10 месте", 2, 105), ("на 11-20 месте", 0, 0), ("дальше 20-го места", 0, 0)],
          f"Search Console: позиции: {G.positions(g)}")
    check("Где теряем клики: до первой тройки" in h and "≈ +51 клик за" in h and "<td>На 4-10 месте</td><td>2</td><td>105</td>" in h,
          "Search Console: «Где теряем клики» в разделе отчёта")
    # Яндекс Метрика
    from seocrawler import metrika as M
    from seocrawler.analyze.checks import metrika as MC
    m = M.fetch("https://site.ru/", log=lambda *a: None)
    check(m and m["counter"] == 9 and m["visits"] == 200 and m["search_visits"] == 140 and len(m["landing"]) == 2
          and not m["errors"], f"Метрика: данные не загрузились или не тот счётчик: {m and m.get('errors')}")
    got.clear()
    ctx.store = SimpleNamespace(get_meta=lambda k, d=None: m if k == "metrika" else ("https://site.ru/" if k == "start" else d))
    MC.run(ctx)
    check(got.get("metrika_broken_landing") == [["https://site.ru/old", 404, 40]], "Метрика: неработающая страница входа")
    check(got.get("metrika_bounce") == [["https://site.ru/", 100, "50%"]], "Метрика: отказы")
    h = M.report_html(m, str)
    check("70%" in h and "60%" in h and "Яндекс - 140" in h, "Метрика: раздел отчёта")
    # ключ Google истёк - должен обновиться сам
    data = json.loads(raw)
    data["google"]["expires"] = 0
    open(os.environ["CLAYLER_ACCOUNTS_FILE"], "w", encoding="utf-8").write(json.dumps(data))
    check(A.refresh_sites("google") == "" and LOG[-1][1] == "Bearer KEY-2", "ключ Google не обновился")
    # ключ отозван: в окне «вход истёк» и простые слова вместо «Token has been expired or revoked»
    A._put("google", error="Token has been expired or revoked.")
    g_st = A.status(8900)["google"]
    check(g_st["expired"] and g_st["error"].startswith("Вход истёк") and "Publish app" in g_st["error"]
          and not A.status(8900)["yandex"]["expired"], f"истёкший вход Google: {g_st['expired']} {g_st['error']}")
    # Google выдал ключ без галочки Search Console: понятный текст, «нет доступа к Search Console»
    A._put("google", error='Google Search Console ответил 403: {"message": "Request had insufficient authentication scopes."}')
    g_st = A.status(8900)["google"]
    check(g_st["expired"] and g_st["relogin"] == "нет доступа к Search Console" and "галочк" in g_st["error"],
          f"Google без доступа к Search Console: {g_st['relogin']} {g_st['error']}")
    # сразу после входа: Google вернул ключ без доступа к Search Console - предупреждаем на странице входа
    url, _e = A.start("google", 8900)
    st_ = parse_qs(urlsplit(url).query)["state"][0]
    real_post = A._post
    A._post = lambda u, f: {"access_token": "KEY-1", "expires_in": 3600, "scope": "openid email"}
    msg = A.finish("google", {"state": st_, "code": "КОД"})
    A._post = real_post
    check("галочк" in msg and A.status(8900)["google"]["relogin"] == "нет доступа к Search Console",
          f"вход без галочки Search Console не замечен: {msg}")
    for p in ("yandex", "google"):
        A.disconnect(p)
    st = A.status(8900)
    check(not st["yandex"]["connected"] and not st["google"]["connected"] and st["google"]["has_app"],
          "после «Отключить» остался ключ или пропало приложение")
    check(sum(1 for x in LOG if x[0] in ("/revoke_token", "/revoke")) == 2, "ключи не отозваны")
    # файл доступов испорчен: не стирается молча, а сохраняется копией рядом, и войти можно заново (28.10.2026)
    import glob
    with open(A.FILE, "w", encoding="utf-8") as f:
        f.write('{"google": {"secret": "x"}, "yandex": {"tok')   # оборван посреди записи
    sleep, A.time.sleep = A.time.sleep, lambda s: None
    try:
        A._put("yandex", account="кто-то")
    except RuntimeError as e:
        check(False, f"испорченный файл - тупик: {e}")
    finally:
        A.time.sleep = sleep
    copies = glob.glob(A.FILE + ".испорчен-*")
    check(len(copies) == 1 and '"google": {"secret": "x"}' in open(copies[0], encoding="utf-8").read(),
          f"копия испорченного файла: {copies}")
    with open(A.FILE, encoding="utf-8") as f:
        check(json.load(f).get("yandex", {}).get("account") == "кто-то", "после испорченного файла вход не записан")
    # файл занят (не открывается) - ничего не перезаписывается, понятная ошибка
    real_open, A.time.sleep = open, (lambda s: None)
    A.open = lambda *a, **k: (_ for _ in ()).throw(PermissionError("занят"))
    try:
        A._put("yandex", account="другой")
        check(False, "занятый файл доступов перезаписан")
    except RuntimeError:
        pass
    finally:
        del A.open
        A.time.sleep = sleep
    srv.shutdown()
    print(("✗ вход в Вебмастер/Search Console: " + "; ".join(bad)) if bad else "✓ вход в Вебмастер/Search Console")
    return not bad


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
