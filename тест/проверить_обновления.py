"""Проверка вкладки «Обновления» (semantics/updates.py) на поддельных Яндексе, Google и странице статуса Google:
даты обновлений Google по-русски, даты обновлений базы Яндекса копятся, свои встряски добавляются и убираются,
данные сайта по дням, «Что просело» по группам и страницам с проблемами проверки, текст для клиента.
Запуск: python тест/проверить_обновления.py (вызывается и из проверить_всё.py)."""
import datetime
import json
import os
import pickle
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

TODAY = datetime.date.today()
D = TODAY - datetime.timedelta(days=30)          # начало обновления Google
BASES = [(TODAY - datetime.timedelta(days=n)).isoformat() for n in (40, 33, 26, 19, 12, 5)]


def day(n):
    return (TODAY - datetime.timedelta(days=n)).isoformat()


def after(s):
    return s >= D.isoformat()


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

    def do_GET(self):
        sp = urlsplit(self.path)
        p, q = unquote(sp.path), {k: v[0] for k, v in parse_qs(sp.query).items()}
        if p == "/incidents.json":
            return self.out([
                {"id": "c1", "service_name": "Ranking", "begin": D.isoformat() + "T16:00:00+00:00",
                 "end": (D + datetime.timedelta(days=12)).isoformat() + "T10:00:00+00:00",
                 "external_desc": "May 2026 core update", "uri": "incidents/c1"},
                {"id": "s1", "service_name": "Serving", "begin": day(50) + "T00:00:00+00:00", "external_desc": "Serving issue"},
                {"id": "p1", "service_name": "Ranking", "begin": day(4) + "T00:00:00+00:00", "external_desc": "September 2026 spam update"}])
        if p == "/v4/user/7/hosts":
            return self.out({"hosts": [{"host_id": "https:site.ru:443", "verified": True, "ascii_host_url": "https://site.ru/",
                                        "unicode_host_url": "https://site.ru/"}]})
        base = "/v4/user/7/hosts/https:site.ru:443"
        if p == base + "/summary":
            return self.out({"searchable_pages_count": 10})
        if p == base + "/search-urls/in-search/history":
            return self.out({"history": [{"date": d + "T10:00:00.000+03:00", "value": 100 - i} for i, d in enumerate(BASES)]})
        if p == base + "/search-urls/events/history":
            return self.out({"indicators": {"APPEARED_IN_SEARCH": [{"date": d + "T10:00:00.000+03:00", "value": 2} for d in BASES],
                                            "REMOVED_FROM_SEARCH": [{"date": d + "T10:00:00.000+03:00", "value": 3} for d in BASES]}})
        if p == base + "/search-queries/all/history":
            pts = [day(n) for n in range(120, 0, -1)]
            return self.out({"indicators": {
                "TOTAL_SHOWS": [{"date": d + "T00:00:00.000+03:00", "value": 100.0} for d in pts],
                "TOTAL_CLICKS": [{"date": d + "T00:00:00.000+03:00", "value": 10.0} for d in pts],
                "AVG_SHOW_POSITION": [{"date": d + "T00:00:00.000+03:00", "value": 5.0} for d in pts]}})
        if p == base + "/search-queries/popular":
            if int(q.get("offset") or 0):
                return self.out({"queries": []})
            return self.out({"queries": [
                {"query_text": "Котел газовый", "indicators": {"TOTAL_SHOWS": 300, "TOTAL_CLICKS": 30, "AVG_SHOW_POSITION": 4.0}},
                {"query_text": "бойлер", "indicators": {"TOTAL_SHOWS": 100, "TOTAL_CLICKS": 10, "AVG_SHOW_POSITION": 6.0}}]})
        if p == "/webmasters/v3/sites":
            return self.out({"siteEntry": [{"siteUrl": "sc-domain:site.ru", "permissionLevel": "siteOwner"}]})
        if p == "/management/v1/counters":
            return self.out({"counters": [{"id": 55, "site": "site.ru", "status": "Active", "code_status": "CS_OK"}]})
        if p == "/stat/v1/data":
            dims = q["dimensions"]
            Y, G = {"id": "yandex", "name": "Яндекс"}, {"id": "google", "name": "Google"}
            if dims.startswith("ym:s:date"):
                rows = []
                for n in range(120, 0, -1):
                    d = day(n)
                    rows += [{"dimensions": [{"name": d}, Y], "metrics": [20]},
                             {"dimensions": [{"name": d}, G], "metrics": [8 if after(d) else 20]}]
                return self.out({"data": rows})
            a = after(q["date1"])
            return self.out({"data": [
                {"dimensions": [{"name": "https://site.ru/kotly/"}, G], "metrics": [40 if a else 200]},
                {"dimensions": [{"name": "https://site.ru/kotly/"}, Y], "metrics": [300]},
                {"dimensions": [{"name": "https://site.ru/boilers/"}, G], "metrics": [50]}]})
        return self.out({"error": p}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        p = urlsplit(self.path).path
        if p.endswith("/searchAnalytics/query"):
            dim = body["dimensions"][0]
            a = after(body["startDate"])
            if dim == "date":
                rows = [{"keys": [day(n)], "clicks": 6 if after(day(n)) else 15, "impressions": 200,
                         "position": 7.5 if after(day(n)) else 3.2} for n in range(120, 2, -1)]
                return self.out({"rows": rows})
            if dim == "query":
                return self.out({"rows": [
                    {"keys": ["котел газовый"], "clicks": 60 if a else 200, "impressions": 2000, "position": 8.0 if a else 3.0},
                    {"keys": ["бойлер"], "clicks": 50, "impressions": 500, "position": 5.0}]})
            return self.out({"rows": [
                {"keys": ["https://site.ru/kotly/"], "clicks": 60 if a else 200, "impressions": 2000, "position": 8.0 if a else 3.0},
                {"keys": ["https://site.ru/boilers/"], "clicks": 50, "impressions": 500, "position": 5.0}]})
        return self.out({"error": p}, 404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="clayler-upd-")
    port = srv.server_port
    os.environ["CLAYLER_OAUTH_TEST"] = f"http://127.0.0.1:{port}"
    os.environ["CLAYLER_GOOGLE_STATUS"] = f"http://127.0.0.1:{port}/incidents.json"
    os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(tmp, "доступы.json")
    os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(tmp, "решения")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from seocrawler import accounts as A
    with open(A.FILE, "w", encoding="utf-8") as f:
        json.dump({"yandex": {"token": A.seal("YA"), "user_id": 7, "expires": 9e9},
                   "google": {"token": A.seal("G"), "expires": 9e9},
                   "google_sites": []}, f)
    from seocrawler.semantics import updates as U
    from seocrawler.analyze.common import Issue, CRIT
    bad = []

    def check(ok, what):
        if not ok:
            bad.append(what)

    # общие даты
    g = U.refresh(force=True, log=lambda *a: None)
    ev = U.events(g)
    goo = [e for e in ev if e["kind"] == "google"]
    check(len(goo) == 2, f"Google: должно быть 2 обновления раздела Ranking, а не {len(goo)}")
    check(any(e["name"] == "Основное обновление Google (core update), май 2026" for e in goo), "название core update не по-русски")
    check(U.google_name("September 2026 spam update") == "Обновление Google против спама, сентябрь 2026", "название spam update")
    check(g.get("yandex_bases") == BASES, f"даты базы Яндекса не те: {g.get('yandex_bases')}")
    U.add_bases(["2020-01-01"])
    check("2020-01-01" in U._read(U._global_path())["yandex_bases"], "даты базы Яндекса не копятся")
    dd = U.default_date([{"kind": "google", "date": D.isoformat()}, {"kind": "base", "date": day(8)}, {"kind": "google", "date": day(3)}])
    check(dd == D.isoformat(), f"дата по умолчанию {dd}, а не начало обновления, после которого есть данные")
    check(U.manual_add("31.02.2026", "x") != "", "неверная дата принята")
    check(U.manual_add(day(10), "PR-CY: встряска") == "", "своя встряска не добавилась")
    mine = [e for e in U.events() if e["name"] == "PR-CY: встряска"]
    check(len(mine) == 1, "своей встряски нет в списке")
    U.manual_del(mine[0]["id"])
    U.manual_del("k0")
    names = [e["name"] for e in U.events()]
    check("PR-CY: встряска" not in names and U.KNOWN[0]["name"] not in names, "встряска не убралась")

    # 21.10.2026: обрыв связи - повтор, прошлые графики не стираются, сетевая «ошибка» в «Подключениях» снимается
    tries = []

    def flaky():
        tries.append(1)
        if len(tries) < 3:
            raise OSError("[WinError 10054] Удалённый хост принудительно разорвал подключение")
        return "ok"
    real_sleep = U.time.sleep
    U.time.sleep = lambda s: None
    try:
        check(U._retry(flaky) == "ok" and len(tries) == 3, "обрыв связи: нет повтора")
    finally:
        U.time.sleep = real_sleep
    old = {"wm": {"shows": [[day(5), 1]]}, "gsc": {"x": 1}, "fetched": "2026-10-20"}
    kept = U._keep_old({"status": {"wm": "error: The handshake operation timed out", "gsc": "ok"}, "gsc": {"x": 2}}, old)
    check(kept.get("wm") == old["wm"] and kept.get("old", {}).get("wm") == "2026-10-20" and kept["gsc"] == {"x": 2},
          f"неудачная загрузка стёрла прошлый график или подменила удачный: {kept}")
    A._put("google", error="The handshake operation timed out")
    A._api("google", "/sites")
    check(not A._get("google").get("error"), "сетевая «ошибка» Google не снялась после удачного запроса")

    # данные по дням
    data = {"host": "site.ru", "site": "https://site.ru/",
            "groups": [{"name": "Котлы", "page": "https://site.ru/kotly/", "q": [["котел газовый"]]},
                       {"name": "Бойлеры", "page": "https://site.ru/boilers/", "q": [["бойлер"]]}]}
    full = os.path.join(tmp, "проверка")
    os.makedirs(full)
    iss = Issue("no_desc", CRIT, "Мета", "Страницы без description", "", "", ["Страница"], [["https://www.site.ru/kotly"]])
    with open(os.path.join(full, ".анализ.pickle"), "wb") as f:
        pickle.dump({"issues": [iss], "pages": [], "summary": {}}, f)
    b = U.build(data, full, load=True, log=lambda *a: None)
    s = b["series"]
    check(s["status"] == {"wm": "ok", "gsc": "ok", "metrika": "ok"}, f"источники: {s['status']}")
    s.setdefault("wm", {"clicks": [], "removed": [[0, 0]]}); s.setdefault("gsc", {"clicks": [], "pos": [[0, 0]]})
    s.setdefault("metrika", {"google": [[0, 0]], "yandex": [[0, 0]]})
    check(len(s["wm"]["clicks"]) == 120 and s["wm"]["removed"][0][1] == 3, "Вебмастер по дням не загрузился")
    check(len(s["gsc"]["clicks"]) == 118 and s["gsc"]["pos"][0][1] == 3.2, "Search Console по дням не загрузилась")
    check(s["metrika"]["google"][-1][1] == 8 and s["metrika"]["yandex"][-1][1] == 20, "Метрика по дням: Яндекс и Google порознь")

    # «Что просело»
    r, err = U.compare(data, full, D.isoformat(), data["site"], log=lambda *a: None)
    check(not err, "сравнение не сделалось: " + err)
    if r:
        check(r["days"] == 28 and r["after"][0] == D.isoformat(), f"окна сравнения: {r['before']} {r['after']}")
        check(r["total"]["google"]["pct"] == -64 and r["total"]["yandex"]["pct"] == 0, f"итоги: {r['total']}")
        kot = next(x for x in r["groups"] if x["name"] == "Котлы")
        check(kot["fell"] and kot["eng"]["google"]["pos"] == [3.0, 8.0], f"группа «Котлы» должна просесть: {kot}")
        check(not next(x for x in r["groups"] if x["name"] == "Бойлеры")["fell"], "«Бойлеры» не просели")
        check([p["url"] for p in r["pages"]] == ["https://site.ru/kotly/"], f"просевшие страницы: {r['pages']}")
        check(r["pages"] and r["pages"][0]["problems"] == ["Страницы без description"] and r["pages"][0]["groups"] == ["Котлы"],
              "у просевшей страницы нет проблемы проверки или группы")
        check(any(e["kind"] == "google" for e in r["near"]), "обновление Google рядом с датой не найдено")
        v = r["verdict"]
        check(v["fell"] and "Просел только поиск Google" in v["lines"][0], f"вывод: {v['lines']}")
        check("Что делаем:" in v["client"] and "Чего не делаем во время обновления:" in v["client"]
              and "Основное обновление Google (core update), май 2026" in v["client"] and "котлы" in v["client"], "текст для клиента")
        check("—" not in v["client"] and "топ" not in v["client"].lower(), "в тексте клиента длинное тире или «топ»")
        check(U.build(data, full)["compare"]["date"] == D.isoformat(), "разбор не запомнился")
    _r, err = U.compare(data, full, day(1), data["site"], log=lambda *a: None)
    check("слишком мало дней" in err, "дата без данных после неё должна давать понятную ошибку")
    srv.shutdown()
    if bad:
        print("ОШИБКИ:\n- " + "\n- ".join(bad))
        sys.exit(1)
    print("Обновления поиска: всё в порядке")


if __name__ == "__main__":
    main()
