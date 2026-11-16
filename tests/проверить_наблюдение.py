"""Проверка наблюдения (seocrawler/watch.py) и команд бота: расписание раз в неделю, мониторинг на маленьком
тестовом сайте (сломалась страница → тревога, починилась → «снова в порядке», noindex на главной, robots.txt
закрыл сайт), команды /check /stop /watch /weekly /sites.
Запуск: python tests/проверить_наблюдение.py (вызывается и из проверить_всё.py)."""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SITE = {"/": (200, "<html><head><title>Главная</title></head><body>ok</body></html>"),
        "/robots.txt": (200, "User-agent: *\nDisallow: /admin/\n")}


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        code, body = SITE.get(self.path, (404, "нет"))
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain" if self.path.endswith(".txt") else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class FakeJob:
    def __init__(self):
        self.running, self.stopped = False, False

    def status(self):
        return {"running": self.running, "site": "", "step": "", "progress": None, "elapsed": 0, "idle": 0,
                "idle_note": ""}

    def stop(self):
        self.stopped = True


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="clayler-watch-")
    os.environ["CLAYLER_WATCH_FILE"] = os.path.join(tmp, "наблюдение.json")
    os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(tmp, "доступы.json")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from seocrawler import telegram, watch

    fails = []

    def check(cond, what):
        if not cond:
            fails.append(what)

    # расписание
    check(watch.parse_weekly("Пн 9:05") == ({"day": 0, "time": "09:05"}, ""), "«Пн 9:05» не понят")
    check(watch.parse_weekly("выкл") == (None, ""), "«выкл» не понят")
    check(watch.parse_weekly("завтра")[1], "ерунда принята за расписание")
    watch.update("site.ru", weekly={"day": 2, "time": "10:00"})
    wed_9 = time.strptime("2026-09-30 09:59", "%Y-%m-%d %H:%M")  # среда
    wed_10 = time.strptime("2026-09-30 10:01", "%Y-%m-%d %H:%M")
    check(not watch.due(wed_9) and [s["url"] for s in watch.due(wed_10)] == ["https://site.ru/"], "расписание")
    watch.update("site.ru", last_run="2026-09-30")
    check(not watch.due(wed_10), "в тот же день запускается второй раз")
    check(watch.find("www.site.ru")["url"] == "https://site.ru/", "www и без www - не один сайт")
    check(watch.remove("site.ru") == "" and not watch.sites(), "не убрался")

    # мониторинг
    url = f"http://127.0.0.1:{srv.server_port}/"
    watch.update(url, monitor=True)
    state, msg = watch.monitor(url, tmp, pause=0)
    check(state["ok"] and not msg, "исправный сайт - тревога: " + msg)
    SITE["/"] = (500, "ошибка")
    state, msg = watch.monitor(url, tmp, pause=0)
    check(not state["ok"] and msg.startswith("🚨") and "отвечает 500" in msg, "не заметил 500 на главной: " + msg)
    _state, msg = watch.monitor(url, tmp, pause=0)
    check(not msg, "повторная тревога о той же проблеме")
    SITE["/"] = (200, '<html><head><meta name="robots" content="noindex"></head></html>')
    state, msg = watch.monitor(url, tmp, pause=0)
    check("noindex" in msg, "не заметил noindex на главной: " + msg)
    SITE["/"] = (200, "<html>ok</html>")
    SITE["/robots.txt"] = (200, "User-agent: *\nDisallow: /\n")
    state, msg = watch.monitor(url, tmp, pause=0)
    check("robots.txt закрывает сайт" in msg, "не заметил закрытый robots.txt: " + msg)
    SITE["/robots.txt"] = (200, "User-agent: *\nDisallow:\n")
    state, msg = watch.monitor(url, tmp, pause=0)
    check(state["ok"] and msg.startswith("✅"), "не сообщил, что починилось: " + msg)

    # команды бота
    started = []
    telegram._starter = lambda u, p: started.append((u, p)) or ""
    job = FakeJob()
    ans = telegram._answer("/check vigas.su 2000", job)
    check(started == [("https://vigas.su/", 2000)] and "Запустил" in ans, "/check: " + ans)
    telegram._starter = lambda u, p: "Проверка уже идёт."
    check("Не запустил" in telegram._answer("/check vigas.su", job), "/check, когда проверка уже идёт")
    check("ничего не проверяется" in telegram._answer("/stop", job) and not job.stopped, "/stop без проверки")
    job.running = True
    telegram._answer("/stop@clayler_bot", job)
    check(job.stopped, "/stop не остановил")
    check("Слежу" in telegram._answer("/watch gasmasterservis.ru", job), "/watch")
    check("пн 09:00" in telegram._answer("/weekly gasmasterservis.ru пн 9:00", job), "/weekly")
    s = watch.find("gasmasterservis.ru")
    check(s and s["monitor"] and s["weekly"] == {"day": 0, "time": "09:00"}, "/watch + /weekly не сохранились")
    txt = telegram._answer("/sites", job)
    check("gasmasterservis.ru" in txt and "пн 09:00" in txt, "/sites: " + txt)
    telegram._answer("/unwatch gasmasterservis.ru", job)
    check(watch.find("gasmasterservis.ru")["monitor"] is False, "/unwatch при расписании должен оставить расписание")
    telegram._answer("/weekly gasmasterservis.ru выкл", job)
    check(watch.find("gasmasterservis.ru") is None, "без мониторинга и расписания сайт должен убраться")
    check("/check" in telegram._answer("/help", job), "/help")

    # кнопки
    r = telegram._answer("clayler-test.ru", job)
    datas = [d for row in r.buttons for _t, d in row]
    check("Что сделать" in r and "watch:clayler-test.ru" in datas and "again:clayler-test.ru" in datas,
          "адрес сайта сообщением - нет кнопок: " + str(datas))
    check("Пришлите адрес" in telegram._answer("▶️ Проверить сайт", job), "кнопка меню «Проверить сайт»")
    check("ничего не проверяется" in telegram._answer("📊 Что идёт", FakeJob()), "кнопка меню «Что идёт»")
    telegram._on_button("watch:clayler-test.ru", job)
    check(watch.find("clayler-test.ru")["monitor"], "кнопка «Следить»")
    telegram._on_button("weekly:clayler-test.ru", job)
    check(watch.find("clayler-test.ru")["weekly"] == {"day": 0, "time": "09:00"}, "кнопка «Раз в неделю»")
    started.clear()
    telegram._starter = lambda u, p: started.append((u, p)) or ""
    telegram._on_button("again:clayler-test.ru", job)
    check(started == [("https://clayler-test.ru/", 10000)], "кнопка «Проверить ещё раз»: " + str(started))
    check("нет" in telegram._on_button("pdf:clayler-test.ru", job), "кнопка PDF без отчёта")
    sb = telegram.sites_text()
    check(any(d == "unwatch:clayler-test.ru" for row in sb.buttons for _t, d in row), "кнопки в списке сайтов")
    telegram._on_button("unwatch:clayler-test.ru", job)
    telegram._on_button("noweekly:clayler-test.ru", job)
    check(watch.find("clayler-test.ru") is None, "кнопки «Не следить» + «Отменить расписание»")
    check(all(len(d.encode()) <= 64 for row in telegram.result_buttons("https://" + "x" * 70 + ".ru/") for _t, d in row),
          "данные кнопки длиннее 64 байт")

    srv.shutdown()
    if fails:
        print("✗ наблюдение: " + "; ".join(fails))
        sys.exit(1)
    print("✓ наблюдение: расписание, мониторинг, команды бота")


if __name__ == "__main__":
    main()
