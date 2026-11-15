"""Автотест того, что сделано для работы с клиентами и разделом «Где теряем клики» (без сети):
- метки у проблем (labels.py): «не ошибка» убирает проблему из отчёта и здоровья только этого сайта, «передано» и
  «ждёт проверки» на расчёт не влияют; /api/labels в окне;
- метка сайта «клиент / конкурент / тест» (reports_list.set_site_tag) в списке сайтов и через /api/site_tag;
- «Отчёт за месяц» (monthly.py): пара проверок одного режима, файл и копия в «для клиента», /api/monthly;
- «Где теряем клики» (lost_clicks.py): подставные данные Вебмастера, Search Console и Метрики дают действия
  «почините» (страница 404, на которую идут из поиска), «перепишите сниппет», «до тройки недалеко», «много отказов»;
  без данных раздел говорит, что подключить, а в отчёте для клиента его нет; мониторинг запросов Вебмастера
  (webmaster.analytics) складывает дни и считает место с весом показов.
Личные файлы (метки проблем.json, метки сайтов.json, отчёты) не трогаются: пути подменяются на временную папку.
Запуск: py -3 tests/проверить_клиентов.py (и из проверить_всё.py)."""
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
PORT, WPORT = 8802, 8803
B = f"http://127.0.0.1:{PORT}"

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


TEXT = "Кухни и шкафы на заказ по вашим размерам, замер и доставка бесплатно. " * 8
PAGES = {"/": ("Мебель на заказ - фабрика", '<a href="/a">Кухни</a> <a href="/b">Шкафы</a> <a href="/c">Спальни</a> '
                                             '<a href="/missing">Старый раздел</a>'),
         "/a": ("Кухни на заказ", ""), "/b": ("Шкафы", ""), "/c": ("Спальни на заказ в городе", "")}


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path not in PAGES:
            body, code = b"<html><body><h1>404</h1></body></html>", 404
        else:
            title, extra = PAGES[path]
            body = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title></head><body>'
                    f'<h1>{title}</h1><p>{TEXT}</p>{extra}</body></html>').encode()
            code = 200
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def api(method, path, data=None):
    req = urllib.request.Request(f"http://127.0.0.1:{WPORT}{path}", method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main():
    tmp = tempfile.mkdtemp(prefix="clayler-clients-")
    reports = os.path.join(tmp, "reports")
    os.makedirs(reports)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_REPORTS=reports)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), B + "/", "--no-open", "--delay", "0",
                            "--no-exposed", "--no-external"], env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=400)
    finally:
        srv.shutdown()
    folders = sorted(glob.glob(os.path.join(reports, f"127.0.0.1_{PORT}_*")))
    if r.returncode != 0 or not folders:
        print("✗ клиенты: тестовый сайт не проверился\n" + (r.stdout + r.stderr)[-1500:])
        sys.exit(1)
    new = folders[-1]

    from seocrawler import jsonfile, labels, lost_clicks, monthly, webmaster
    from seocrawler.window import reports_list as RL
    from seocrawler.storage import Store
    from seocrawler.analyze import analyze

    # ---- метки у проблем: подменённый файл, а не «метки проблем.json» пользователя
    lab_file = os.path.join(tmp, "метки проблем.json")
    labels.FILE = lab_file
    labels._all = lambda: (jsonfile.load(lab_file) if os.path.exists(lab_file) else None) or {}
    store = Store(os.path.join(new, "crawl.db"))
    issues, _p, summary = analyze(store)
    keys = {i.key for i in issues}
    check(issues, "на тестовом сайте нет ни одной проблемы")
    victim = next(i for i in issues)
    check(labels.put(B + "/", victim.key, "wrong") == "Нет такой метки.", "неизвестная метка принята")
    check(labels.put("", victim.key, "sent") != "", "метка без сайта принята")
    check(labels.put("http://www.127.0.0.1:%d/" % PORT, victim.key, "not_error") == "", "метка не поставилась")
    check(labels.not_errors(B + "/") == {victim.key}, "www и без www - разные сайты для меток")
    issues2, _p, summary2 = analyze(store)
    check(victim.key not in {i.key for i in issues2}, "«не ошибка» не убрала проблему из отчёта")
    check([x["key"] for x in summary2.get("labels_hidden") or []] == [victim.key], "убранная проблема не в списке")
    check(summary2["health"] >= summary["health"], f"здоровье упало после «не ошибка»: {summary['health']} → {summary2['health']}")
    check(labels.not_errors("other-site.ru") == set(), "метка одного сайта видна у другого")
    labels.put(B + "/", victim.key, "sent")
    issues3, _p, summary3 = analyze(store)
    check(victim.key in {i.key for i in issues3} and summary3["health"] == summary["health"],
          "«передано разработчику» повлияло на отчёт или здоровье")
    labels.put(B + "/", victim.key, "")
    check(labels.load(B + "/") == {} and not (jsonfile.load(lab_file) or {}), "снятая метка осталась в файле")
    store.db.close()

    # ---- вторая (старая) проверка для отчёта за месяц: копия базы, законченная на 30 дней раньше
    old = os.path.join(reports, os.path.basename(new).replace(f"_{PORT}_", f"_{PORT}_0"))
    os.makedirs(old)
    for f in glob.glob(os.path.join(new, "crawl.db*")):
        shutil.copy(f, old)
    db = sqlite3.connect(os.path.join(old, "crawl.db"))
    fin = json.loads(db.execute("SELECT value FROM meta WHERE key='finished_at'").fetchone()[0])
    st = json.loads(db.execute("SELECT value FROM meta WHERE key='started_at'").fetchone()[0])
    import datetime as dt
    back = lambda s: (dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S") - dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE meta SET value=? WHERE key='finished_at'", (json.dumps(back(fin)),))
    db.execute("UPDATE meta SET value=? WHERE key='started_at'", (json.dumps(back(st)),))
    db.execute("UPDATE pages SET title='' WHERE url LIKE '%/c'")   # в прошлый раз у /c не было title
    db.commit()
    db.close()

    RL.REPORTS, RL.ARCHIVE = reports, os.path.join(tmp, "archive")
    RL.TAGS = os.path.join(tmp, "метки сайтов.json")
    RL._CACHE.clear()
    key = RL.site_key(B + "/")
    o, n = monthly.pick(key)
    check(o and n and os.path.normpath(o) == os.path.normpath(old) and os.path.normpath(n) == os.path.normpath(new),
          f"отчёт за месяц выбрал не те проверки: {o}, {n}")
    check(monthly.pick("нет-такого.ru") == (None, None), "отчёт за месяц для сайта без проверок")
    rel, err = monthly.build(key)
    path = os.path.join(reports, rel) if rel else ""
    doc = open(path, encoding="utf-8").read() if path and os.path.exists(path) else ""
    check(not err and "Отчёт о сайте за месяц" in doc, f"отчёт за месяц не собрался: {err}")
    check("—" not in doc and "рограмм" not in doc, "длинное тире или «программа» в отчёте за месяц")
    if os.path.isdir(os.path.join(new, "для клиента")):
        check(glob.glob(os.path.join(new, "для клиента", "*отчёт за месяц.html")), "нет копии в «для клиента»")
        from seocrawler import client_folder
        client_folder.fill(new, B + "/")   # «Обновить отчёт» заново заполняет папку - отчёт за месяц остаётся
        check(glob.glob(os.path.join(new, "для клиента", "*отчёт за месяц.html")),
              "«Обновить отчёт» стёр отчёт за месяц из «для клиента»")
    else:
        check(False, "у проверки нет папки «для клиента»")

    # ---- метка сайта
    check(RL.set_site_tag(B + "/", "boss") == "Нет такой метки.", "неизвестная метка сайта принята")
    check(RL.set_site_tag("", "client") != "", "метка без сайта принята")
    check(RL.set_site_tag(B + "/", "client") == "", "метка сайта не поставилась")
    g = next((x for x in RL.list_reports()["sites"] if x["key"] == key), {})
    check(g.get("tag") == "client", f"в списке сайтов нет метки «клиент»: {g.get('tag')}")
    RL.set_site_tag(key, "")
    check(RL.site_tags() == {}, "метка сайта не снялась")

    # ---- то же через окно программы (сервер в этом же процессе - пути уже подменены)
    from seocrawler.window.server import H
    w = ThreadingHTTPServer(("127.0.0.1", WPORT), H)
    threading.Thread(target=w.serve_forever, daemon=True).start()
    try:
        check(api("POST", "/api/site_tag", {"key": key, "tag": "rival"}) == {"ok": True}, "/api/site_tag")
        check(RL.site_tags().get(key) == "rival", "метка из окна не записалась")
        check(api("POST", "/api/labels", {"site": B + "/", "key": victim.key, "state": "wait"}) == {"ok": True},
              "/api/labels (POST)")
        got = api("GET", "/api/labels?site=" + key)
        check(got.get("labels", {}).get(victim.key, {}).get("state") == "wait" and "wait" in got.get("states", {}),
              f"/api/labels (GET): {got}")
        m = api("POST", "/api/monthly", {"key": key})
        check(m.get("ok") and "/r/" in m.get("url", ""), f"/api/monthly: {m}")
    finally:
        w.shutdown()

    # ---- «PDF для витрины» и «Видео обхода» у проверки в архиве: папку ищут и в «reports/archive»
    from seocrawler.window import server as SRV

    class Fake:
        sent = None

        def send(self, code, body, *a):
            self.sent = (code, body)
    arch = os.path.join(RL.ARCHIVE, os.path.basename(old) + "_арх")
    shutil.copytree(old, arch)
    was, SRV.REPORTS = SRV.REPORTS, reports
    try:
        fk = Fake()
        got = SRV.H.ready_folder(fk, {"folder": os.path.basename(arch)})
        check(got and os.path.normpath(got) == os.path.normpath(arch) and fk.sent is None,
              f"проверка в архиве не нашлась для «PDF для витрины»: {got} {fk.sent}")
        check(SRV.H.ready_folder(fk, {"folder": "../" + os.path.basename(new)}) and
              SRV.H.ready_folder(fk, {"folder": "нет-такой"}) is None, "имя папки с путём или несуществующее")
    finally:
        SRV.REPORTS = was
        shutil.rmtree(arch, ignore_errors=True)

    # ---- «Где теряем клики»
    store = Store(os.path.join(new, "crawl.db"))
    store.set_meta("webmaster", {"host": B, "fetched": "21.10.2026", "qa_urls": [{"text": B + "/a", "shows": 1400, "clicks": 10, "pos": 2.0}],
                                 "qa_queries": [{"text": "кухни на заказ", "other": B + "/a", "shows": 1400,
                                                 "clicks": 10, "pos": 2.0}]})
    store.set_meta("gsc", {"site": B + "/", "fetched": "21.10.2026", "pages": [{"url": B + "/b", "shows": 560, "clicks": 5, "pos": 8.0},
                                     {"url": B + "/missing", "shows": 100, "clicks": 28, "pos": 3.0}],
                           "queries": [{"q": "шкафы купить", "shows": 560, "clicks": 5, "pos": 8.0}],
                           "qp": [{"q": "шкафы купить", "url": B + "/b", "shows": 560}]})
    store.set_meta("metrika", {"counter": 1, "fetched": "21.10.2026", "landing": [{"url": B + "/c", "visits": 100, "bounce": 60},
                                           {"url": "https://other-site.ru/x", "visits": 500, "bounce": 90}]})
    store.commit()
    lc = analyze(store)[2].get("lost_clicks") or {}
    kinds = {a["kind"]: a for a in lc.get("actions") or []}
    check(set(kinds) == {"broken", "snip", "near", "bounce"}, f"действия «Где теряем клики»: {sorted(kinds)} {lc.get('error')}")
    check(kinds.get("broken", {}).get("url", "").endswith("/missing"), "«почините» не про страницу 404")
    check(kinds.get("snip", {}).get("url", "").endswith("/a"), "«перепишите сниппет» не про /a")
    check(kinds.get("near", {}).get("url", "").endswith("/b"), "«до тройки недалеко» не про /b")
    check(not any("other-site" in r["url"] for r in lc.get("pages") or []), "страница чужого сайта из Метрики в таблице")
    check(lc.get("sources") == ["Яндекс Вебмастер", "Google Search Console", "Яндекс Метрика"], f"источники: {lc.get('sources')}")
    html = lost_clicks.html_block(lc)
    check("Где теряем клики" in html and "4 главных действия" in html, "раздел «Где теряем клики» в отчёте")
    check("—" not in html, "длинное тире в «Где теряем клики»")
    store.set_meta("webmaster", None)
    store.set_meta("gsc", None)
    store.set_meta("metrika", None)
    store.commit()
    lc = analyze(store)[2].get("lost_clicks") or {}
    check(lc.get("sources") == [] and len(lc.get("missing") or []) == 3, f"без данных: {lc}")
    check("Нет данных" in lost_clicks.html_block(lc) and lost_clicks.html_block(lc, client=True) == "",
          "без данных: подсказка оператору или лишний раздел у клиента")
    store.db.close()

    # мониторинг запросов Вебмастера: два дня одного адреса, место с весом показов
    calls = []

    def fake_api(who, url, body):
        calls.append(body)
        if body["offset"]:
            return {"text_indicator_to_statistics": []}
        return {"text_indicator_to_statistics": [
            {"text_indicator": {"value": "/a"}, "popular_complementary_indicator": {"value": "кухни"},
             "statistics": [{"date": "d1", "field": "IMPRESSIONS", "value": 30}, {"date": "d1", "field": "CLICKS", "value": 3},
                            {"date": "d1", "field": "POSITION", "value": 2.0},
                            {"date": "d2", "field": "IMPRESSIONS", "value": 10}, {"date": "d2", "field": "POSITION", "value": 6.0}]}]}
    real = webmaster.accounts._api
    webmaster.accounts._api = fake_api
    try:
        got = webmaster.analytics("/base", "URL")
    finally:
        webmaster.accounts._api = real
    check(got == [{"text": "/a", "other": "кухни", "shows": 40, "clicks": 3, "pos": 3.0}],
          f"мониторинг запросов Вебмастера: {got}")
    check(calls and calls[0]["text_indicator"] == "URL", "мониторинг запросов: не тот вид запроса")

    if fails:
        print("✗ клиенты и «Где теряем клики»:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ клиенты и «Где теряем клики»: метки проблем и сайтов, отчёт за месяц, окно (/api/labels, site_tag, "
          "monthly), 4 вида действий из Вебмастера, Search Console и Метрики, без данных - подсказка")


main()
