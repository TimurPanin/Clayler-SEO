"""Проверка сообщений в Telegram (seocrawler/telegram.py) на поддельном сервере Telegram: токен проверяется,
чат находится по первому сообщению боту, токен в файле зашифрован, сообщение об окончании проверки собирается
из папки отчёта (здоровье, время, главные проблемы), остановленная и неудачная проверки - свой заголовок.
Запуск: python тест/проверить_телеграм.py (вызывается и из проверить_всё.py)."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

SENT = []
FILES = []
STATE = {"updates": []}


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

    def handle_any(self):
        n = int(self.headers.get("Content-Length") or 0)
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        token, _, method = self.path[4:].partition("/")
        if token != "111:GOOD":
            return self.out({"ok": False, "error_code": 401, "description": "Unauthorized"}, 401)
        if method == "getMe":
            return self.out({"ok": True, "result": {"username": "clayler_test_bot"}})
        if method == "getUpdates":
            return self.out({"ok": True, "result": STATE["updates"]})
        if method == "sendMessage":
            SENT.append(f)
            return self.out({"ok": True, "result": {}})
        if method == "sendDocument":
            FILES.append(self.headers.get("Content-Type", ""))
            return self.out({"ok": True, "result": {}})
        if method == "setMyCommands":
            return self.out({"ok": True, "result": True})
        return self.out({"ok": False, "description": "Not Found"}, 404)

    do_GET = do_POST = handle_any


def make_check(base, name, site, health, stopped_report=False, started="2026-09-30 10:00:00", pdf=False):
    d = os.path.join(base, name)
    os.makedirs(d)
    con = sqlite3.connect(os.path.join(d, "crawl.db"))
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    meta = {"start": site, "work_seconds": 4800, "started_at": started,
            "summary": {"health": health, "html_ok": 812, "pages": 900, "crit": 2, "warn": 5}}
    con.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
    con.commit()
    con.close()
    if pdf:
        open(os.path.join(d, "аудит.pdf"), "wb").write(b"%PDF-1.4 test")
    if not stopped_report:
        open(os.path.join(d, "отчёт.html"), "w").close()
        with open(os.path.join(d, "проблемы.csv"), "w", encoding="utf-8-sig") as f:
            f.write("Важность;Раздел;Проблема;Количество\nКритично;Коды;Битые ссылки <404>;37\n"
                    "Предупреждение;Title;Длинный title;120\nЗамечание;Картинки;Нет alt;5\n"
                    "Замечание;Разное;Четвёртая;1\n")
    return d


class FakeJob:
    def __init__(self, sites, dirs, stopped=False, lines=()):
        self.sites, self.site, self.dirs = sites, sites[0], dirs
        self.out_dir = dirs[0] if dirs else ""
        self.started, self.finished = 1000.0, 1000.0 + 5400
        self.was_stopped, self.lines, self.competitors_report = stopped, list(lines), ""

    def add(self, line):
        self.lines.append(line)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="clayler-tg-")
    os.environ["CLAYLER_TELEGRAM_TEST"] = f"http://127.0.0.1:{srv.server_port}"
    os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(tmp, "доступы.json")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from seocrawler import telegram

    fails = []

    def check(cond, what):
        if not cond:
            fails.append(what)

    check("не узнал токен" in telegram.save_token("111:BAD"), "неверный токен не распознан")
    check(telegram.save_token("111:GOOD") == "", "верный токен не сохранился")
    st = telegram.status()
    check(st["has_token"] and st["bot"] == "@clayler_test_bot" and not st["ready"], "статус после токена")
    check("111:GOOD" not in open(os.environ["CLAYLER_ACCOUNTS_FILE"], encoding="utf-8").read(),
          "токен лежит в файле открытым текстом")
    check("не получил от вас сообщений" in telegram.find_chat(), "без сообщения боту чат «нашёлся»")
    STATE["updates"] = [{"message": {"chat": {"id": -5, "type": "group"}}},
                        {"message": {"chat": {"id": 42, "type": "private", "first_name": "Тимур"}}}]
    check(telegram.find_chat() == "" and telegram.status()["ready"], "чат не найден по сообщению")
    check(SENT and SENT[-1]["chat_id"] == "42", "пробное сообщение не ушло в личный чат")

    reports = os.path.join(tmp, "отчёты")
    make_check(reports, "www.site.ru_0", "https://www.site.ru/", 70, started="2026-09-20 10:00:00")
    mine = make_check(reports, "site.ru_1", "https://site.ru/", 78, pdf=True)
    comp = make_check(reports, "rival.ru_1", "https://rival.ru/", 64)
    telegram.notify_job(FakeJob(["https://site.ru/", "https://rival.ru/"], [mine, comp]))
    text = SENT[-1]["text"]
    for part in ("✅ Проверка закончена: https://site.ru/", "Здоровье: <b>78%</b> (было 70%, +8)",
                 "проверка шла 1 ч 20 мин", "Заняла: 1 ч 30 мин", "🔴 Битые ссылки &lt;404&gt; - 37",
                 "🟡 Длинный title - 120", "(конкурент)", "64%"):
        check(part in text, "в сообщении нет: " + part)
    check("Четвёртая" not in text and text.count("🔴") + text.count("🟡") + text.count("⚪") == 3,
          "главных проблем не 3")

    check(len(FILES) == 1 and "multipart/form-data" in FILES[0], "аудит PDF не приложен")
    kb = json.loads(SENT[-1].get("reply_markup") or "{}").get("inline_keyboard") or []
    check(any(b["callback_data"] == "xlsx:site.ru" for row in kb for b in row), "под итогом нет кнопок")
    telegram.notify_job(FakeJob(["https://site.ru/"], [mine]))
    one = SENT[-1]["text"]
    check(one.count("https://site.ru/") == 1 and "проверка шла" not in one, "у одного сайта повторы в сообщении")
    telegram.set_option("pdf", False)
    telegram.notify_job(FakeJob(["https://site.ru/"], [mine]))
    check(len(FILES) == 2, "PDF отправился, хотя галочка снята")

    class Running(FakeJob):
        def status(self):
            return {"running": True, "site": "https://site.ru/", "step": "Шаг 3 из 4: обход", "progress": [120, 10000],
                    "elapsed": 600, "idle": 0, "idle_note": ""}
    ans = telegram._answer("/status", Running(["https://site.ru/"], [mine]))
    check("Идёт проверка: https://site.ru/" in ans and "120 из 10000" in ans and "10 мин" in ans, "ответ на /status")
    check("/status" in telegram._answer("привет", None), "ответ на обычное сообщение")

    telegram.notify_job(FakeJob(["https://site.ru/"], [mine], stopped=True))
    check(SENT[-1]["text"].startswith("⏹ Проверка остановлена"), "остановленная проверка")
    bad = make_check(reports, "down.ru_1", "https://down.ru/", 0, stopped_report=True)
    telegram.notify_job(FakeJob(["https://down.ru/"], [bad], lines=["Ошибка: сайт не отвечает"]))
    check(SENT[-1]["text"].startswith("❌ Проверка не получилась") and "сайт не отвечает" in SENT[-1]["text"],
          "неудачная проверка")

    n = len(SENT)
    telegram.set_option("enabled", False)   # галочка «Сообщения в Telegram» в окне
    telegram.notify_job(FakeJob(["https://site.ru/"], [mine]))
    check(len(SENT) == n, "выключенные сообщения всё равно отправились")
    telegram.disconnect()
    check(not telegram.status()["has_token"], "«Отключить» не стёр токен")

    srv.shutdown()
    if fails:
        print("✗ Telegram: " + "; ".join(fails))
        sys.exit(1)
    print("✓ Telegram: токен, поиск чата, сообщение об окончании проверки - всё работает")


if __name__ == "__main__":
    main()
