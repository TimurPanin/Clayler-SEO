"""Автотест уведомлений окна и «Журнала» (window/events.py, applog.py, plain_errors.py). Без сети и без звука.
Проверяется: токены и пароли не попадают в журнал (ни известные из доступы.json, ни похожие на ключ),
обычные адреса и слова не портятся; ошибки - простыми словами с «что сделать»; уведомление о законченной
проверке, семантике и ошибке; колокольчик (прочитано, звук, очистить); журнал срезает старое;
плашки и колокольчик подключены на всех страницах окна, «Журнал» - в меню."""
import json
import os
import shutil
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="clayler-notify-")
os.environ["CLAYLER_JOURNAL_DIR"] = TMP
os.environ["CLAYLER_NO_SOUND"] = "1"
os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(TMP, "доступы.json")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seocrawler import applog  # noqa: E402
from seocrawler.plain_errors import explain  # noqa: E402
from seocrawler.window import events  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# ---- токены и пароли
SECRET = "Kj8sd7FhQw2LmZx9Pq"
with open(os.environ["CLAYLER_ACCOUNTS_FILE"], "w", encoding="utf-8") as f:
    json.dump({"direct": {"token": "plain:" + __import__("base64").b64encode(SECRET.encode()).decode(), "login": "timur"},
               "yandex": {"account": "timur@yandex.ru", "sites": ["franmeb.ru"]}}, f)
for raw, bad in [(f"Директ ответил: неверный токен {SECRET}", SECRET),
                 ("https://x.ru/cb?access_token=y0_AgAAAAB1234567890abcdefGHIJKLmnop&state=1", "y0_AgAAAAB"),
                 ("Authorization: OAuth AQAAAABBbbCCcc1234567890", "AQAAAABB"),
                 ("бот 1234567890:AAEhBP0av18bKvXzQWERTYUIOPasdfghjkl12 не ответил", "AAEhBP0av"),
                 ("password=hunter22 и дальше", "hunter22")]:
    check(bad not in applog.scrub(raw), f"секрет остался в журнале: {raw[:40]}")
for keep in ["https://gasprofservice.ru/kupit-gazovyy-kotel-v-moskve-nedorogo-2024/", "Ключ Директа сохранён",
             "timur@yandex.ru", "franmeb.ru"]:
    check(applog.scrub(keep) == keep, f"обычный текст испорчен: {keep}")
applog.write("action", f"Нажата кнопка «Сохранить ключ» token={SECRET}", "franmeb.ru")
with open(applog.path(), encoding="utf-8") as f:
    check(SECRET not in f.read(), "токен попал в файл журнала")

# ---- ошибки простыми словами
for raw, title in [("<urlopen error [Errno 11001] getaddrinfo failed>", "Сайт не найден"),
                   ("HTTP Error 403: Forbidden", "закрыл доступ"),
                   ("PermissionError: [WinError 32] being used by another process", "Файл занят"),
                   ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "HTTPS"),
                   ("TimeoutError: timed out", "долго не отвечает"),
                   ("OSError: [Errno 28] No space left on device", "кончилось место"),
                   ("KeyError: 'groups'", "Внутренняя ошибка")]:
    e = explain(raw)
    check(title in e["title"] and e["todo"] and e["detail"] == raw, f"ошибка не объяснена: {raw} -> {e}")
e = explain("Семантика для этой проверки ещё не собрана.")
check(e["title"] == "Семантика для этой проверки ещё не собрана." and not e["detail"], "понятный русский текст переписан")

# ---- уведомления о законченных задачах
REP = os.path.join(TMP, "отчёты")
folder = os.path.join(REP, "franmeb.ru_2026-10-16_10-00")
os.makedirs(folder)


class FakeJob:
    from_queue, was_stopped, site_down, competitors_report, semantics_dir = False, False, "", "", ""

    def __init__(self, **kw):
        self.started, self.lines, self.sites, self.site, self.out_dir = time.time() - 5, [], ["https://franmeb.ru/"], "", ""
        self.__dict__.update(kw)


with open(os.path.join(folder, "отчёт.html"), "w", encoding="utf-8") as f:
    f.write("<html></html>")
ev = events.job_finished(FakeJob(out_dir=folder), "check")
check(ev and ev["kind"] == "ok" and ev["title"] == "Отчёт готов: franmeb.ru" and ev["link"].startswith("/r/"),
      f"нет «Отчёт готов»: {ev}")
ev = events.job_finished(FakeJob(out_dir=folder), "rebuild")
check(ev and ev["title"] == "Отчёт обновлён: franmeb.ru", f"нет «Отчёт обновлён»: {ev}")
# сборку остановили из-за памяти, а отчёт.html уже свежий - не «Отчёт обновлён», а ошибка (ревью кода 05.11.2026)
from seocrawler import memory  # noqa: E402
ev = events.job_finished(FakeJob(out_dir=folder, lines=memory.build_stopped_text(900).strip().split("\n")), "rebuild")
check(ev and ev["kind"] == "err" and "не до конца" in ev["title"] and "памяти" in ev["title"].lower(),
      f"остановка сборки из-за памяти показана как успех: {ev}")
ev = events.job_finished(FakeJob(out_dir=folder, site_down="ошибка 502"), "check")
check(ev and ev["kind"] == "warn" and "неполный" in ev["title"], f"неполный отчёт не отмечен: {ev}")
with open(os.path.join(folder, "семантика.json"), "w", encoding="utf-8") as f:
    f.write("{}")
ev = events.job_finished(FakeJob(semantics_dir=folder), "semantics")
check(ev and ev["kind"] == "ok" and ev["title"] == "Семантика собрана: franmeb.ru" and ev["link"].startswith("/semantics?f="),
      f"нет «Семантика собрана»: {ev}")
ev = events.job_finished(FakeJob(sites=["https://nosuch.ru/"], lines=["Начинаю", "Ошибка: <urlopen error [Errno 11001] getaddrinfo failed>"]),
                         "check")
check(ev and ev["kind"] == "err" and "Сайт не найден" in ev["title"] and ev["todo"] and "getaddrinfo" in ev["detail"]
      and ev["site"] == "nosuch.ru", f"ошибка проверки не простыми словами: {ev}")
check(events.job_finished(FakeJob(from_queue=True, out_dir=folder), "check") is None, "очередь: лишнее уведомление на каждый сайт")
ev = events.job_finished(FakeJob(out_dir=folder, was_stopped=True), "check")
check(ev and ev["kind"] == "info" and ev["title"].startswith("Остановлено"), f"остановка: {ev}")
# «Остановить» во время «Обновить отчёт»: crawl.py --report файла «стоп» не читает, процесс прерывается сразу (23.10.2026)
import subprocess  # noqa: E402
from seocrawler.window.job import Job  # noqa: E402
j = Job()
j.active, j.rebuild, j.stop_file = True, True, os.path.join(TMP, ".stop-test")
j.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
j.stop()
try:
    j.proc.wait(10)
except subprocess.TimeoutExpired:
    j.proc.kill()
    check(False, "«Остановить» не прервал «Обновить отчёт»")
check(j.was_stopped, "прерванное «Обновить отчёт» не отмечено как остановленное")
ev = events.job_finished(FakeJob(out_dir=folder, was_stopped=True), "rebuild")
check(ev and ev["title"].startswith("Остановлено") and "ещё раз" in ev["text"], f"остановка «Обновить отчёт»: {ev}")
check(events.error("Traceback\nValueError: x") and events.error("Traceback\nValueError: x") is None,
      "одинаковая ошибка повторяется чаще раза в минуту")
ev = events.from_telegram("⚠️ Очередь: <b>site.ru</b> пропущен - сайт ответил кодом 503.\nИду дальше.")
check(ev and ev["kind"] == "warn" and ev["title"] == "Очередь: site.ru пропущен - сайт ответил кодом 503.", f"Telegram-текст: {ev}")

# ---- колокольчик
st = events.since(0)
check(len(st["items"]) >= 8 and st["seen"] == 0, "уведомления не копятся")
check(events.since(st["items"][-2]["id"])["items"] == st["items"][-1:], "новые после ?after= не те")
st = events.update(seen=st["last"], sound=False)
check(st["seen"] == st["last"] and st["sound"] is False, "прочитано / звук не сохраняются")
with open(os.path.join(TMP, "уведомления.json"), encoding="utf-8") as f:
    check(json.load(f)["sound"] is False, "звук не записан в файл")
check(events.update(clear=True)["items"] == [], "«Очистить» не очищает")

# ---- журнал: записи, виды, срезание старого
items = applog.read(100)
check(any(r["kind"] == "error" and "Сайт не найден" in r["text"] and "getaddrinfo" in r["detail"] for r in items),
      "ошибка не в журнале с «Подробнее»")
check(any(r["kind"] == "event" and r["text"].startswith("Отчёт готов") for r in items), "уведомление не в журнале")
check(all(r["kind"] == "action" for r in applog.read(100, "action")), "фильтр по виду")
check(applog.read(100, q="nosuch.ru") and all("nosuch.ru" in (r["text"] + r["site"]) for r in applog.read(100, q="nosuch.ru")), "поиск")
old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 40 * 86400))
with open(applog.path(), encoding="utf-8") as f:
    cur = f.read()
with open(applog.path(), "w", encoding="utf-8") as f:
    f.write(f"{old} | Действие | old.ru | старое\n" + cur)
applog._writes = 0
applog.write("info", "новое")
check(not applog.read(1000, q="old.ru"), "записи старше 30 дней не срезаются")
check(applog.read(1)[0]["text"] == "новое", "после срезания пропала новая запись")

# ---- страницы окна
PAGE = os.path.join(ROOT, "seocrawler", "window", "page")
for name in ("index.html", "semantics.html", "dictionary.html"):
    with open(os.path.join(PAGE, name), encoding="utf-8") as f:
        html = f.read()
    check("/page/notify.js" in html and "/page/notify.css" in html, f"{name}: нет плашек и колокольчика")
with open(os.path.join(PAGE, "index.html"), encoding="utf-8") as f:
    html = f.read()
check('data-view="log"' in html and "/page/journal.js" in html, "главная: нет вкладки «Журнал»")
with open(os.path.join(PAGE, "side.js"), encoding="utf-8") as f:
    side = f.read()
# меню рисует side.js (21.10.2026): на других страницах пункт - ссылка '/#' + экран главной
check("item('log', 'log', 'Журнал')" in side and "'/#' + v" in side, "меню других страниц: нет «Журнала»")
with open(os.path.join(PAGE, "notify.js"), encoding="utf-8") as f:
    js = f.read()
check(".value" not in js.replace("el.value && el.type === 'button' && el.value", "").replace("s.value", ""),
      "notify.js читает то, что введено в поля")

shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("УВЕДОМЛЕНИЯ И ЖУРНАЛ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Уведомления окна, «Журнал» и ошибки простыми словами: всё в порядке")
