"""Браузер для JavaScript не копит память (31.10.2026): Playwright на каждую страницу оставляет у себя служебные вызовы
без ответа и не удаляет их (thehome.ru: +80 МБ в минуту, через 17 часов MemoryError). renderer.Renderer запускает
браузер и Playwright заново каждые RECYCLE_EVERY страниц. Проверяем: перезапуски были, вызовов без ответа не
больше, чем за один круг, страницы открываются и после перезапуска, лишних процессов браузера не остаётся.
Свой маленький сайт, без сети. Запуск: py -3 тест/проверить_память_браузера.py (и из проверить_всё.py)."""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
EVERY, PAGES, PORT = 15, 50, 8783
os.environ["CLAYLER_RENDER_RECYCLE"] = str(EVERY)
from seocrawler import renderer as R  # noqa: E402

HTML = ("<html><head><title>Страница</title><script src='/a.js'></script></head><body><h1>Заголовок</h1>"
        + "".join(f"<img src='/i{i}.png' width=5 height=5>" for i in range(20))
        + "<p id=t></p><script>document.getElementById('t').textContent='добавил скрипт'</script>"
        + "</body></html>").encode("utf-8")
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body, ctype = (b"var x=1;", "application/javascript") if self.path.endswith(".js") else \
            (HTML, "text/html; charset=utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def children():
    """Сколько процессов запущено от этого (браузер, Playwright). None - посчитать нечем."""
    try:
        import psutil
        return len(psutil.Process().children(recursive=True))
    except Exception:
        return None


def kill_browser():
    """Убить процессы браузера Chromium, запущенные этим тестом (как если бы он упал). Сколько убито."""
    try:
        import psutil
        kids = [p for p in psutil.Process().children(recursive=True) if "chrom" in p.name().lower()]
        for p in kids:
            p.kill()
        psutil.wait_procs(kids, timeout=10)
        return len(kids)
    except Exception:
        return 0


def chromium_count():
    """Сколько процессов Chromium запущено от этого теста. None - посчитать нечем."""
    try:
        import psutil
        return sum(1 for p in psutil.Process().children(recursive=True) if "chrom" in p.name().lower())
    except Exception:
        return None


def main():
    ok, why = R.available()
    if not ok:
        print(f"- память браузера: пропущено ({why})")
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    r = R.Renderer("Mozilla/5.0", tabs=2, wait_seconds=1, timeout=20)
    try:
        if not r.start():
            print(f"- память браузера: пропущено (браузер не запустился: {r.start_error})")
            return
        procs, waiting = [], []
        for i in range(PAGES):
            res = r.render(f"http://127.0.0.1:{PORT}/p{i}", HTML)
            check(not res.error, f"страница {i}: {res.error}")
            check("добавил скрипт" in res.html, f"страница {i}: JavaScript не выполнился")
            if i % EVERY == EVERY - 1:
                procs.append(children())
                waiting.append(len(r.pw._impl_obj._connection._callbacks))
        check(r.restarts >= PAGES // EVERY - 1, f"перезапусков браузера {r.restarts}, ждали не меньше {PAGES // EVERY - 1}")
        # за один круг копится 3 вызова на страницу: больше - перезапуск их не выбросил
        check(max(waiting) <= EVERY * 3 + 10, f"вызовов Playwright без ответа копится: {waiting}")
        if procs and procs[0] is not None:
            check(max(procs) <= procs[0] + 2, f"процессов браузера после перезапусков стало больше: {procs}")
        # браузер умер посреди проверки (31.10.2026 thehome.ru: кончилась память) - запускается заново, страница
        # повторяется, а не пишется «не удалось отрендерить»
        killed = kill_browser()
        if killed:
            res = r.render(f"http://127.0.0.1:{PORT}/after-crash", HTML)
            check(not res.error and "добавил скрипт" in res.html,
                  f"после смерти браузера страница не открылась: {res.error or 'нет текста скрипта'}")
            check(r.revived >= 1, "смерть браузера не замечена (revived = 0)")
            res = r.render(f"http://127.0.0.1:{PORT}/after-crash-2", HTML)
            check(not res.error, f"следующая страница после перезапуска: {res.error}")
        # перезапуск прервали посередине (страница не дождалась ответа): взятые места вкладок возвращаются
        import asyncio

        async def cut_recycle():
            await r.sem.acquire()          # одна вкладка занята долгой страницей
            r.rendered = r.RECYCLE_EVERY
            t = asyncio.ensure_future(r._recycle())
            await asyncio.sleep(0.2)       # перезапуск взял свободные места и ждёт занятое
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            r.sem.release()
            return r.sem._value
        free = asyncio.run_coroutine_threadsafe(cut_recycle(), r.loop).result(30)
        check(free == r.tabs, f"после прерванного перезапуска свободных вкладок {free} из {r.tabs}")
        r.rendered = 0
        res = r.render(f"http://127.0.0.1:{PORT}/after-cancel", HTML)
        check(not res.error, f"после прерванного перезапуска страница не открылась: {res.error}")
        # браузер не запустился заново: JavaScript не выключается навсегда - новая попытка позже
        real = r._launch

        async def broken():
            raise RuntimeError("нет памяти")
        r._launch = broken
        r.rendered = r.RECYCLE_EVERY
        res = r.render(f"http://127.0.0.1:{PORT}/no-browser", HTML)
        check("не запустился заново" in res.error and not r.start_error,
              f"неудачный запуск браузера: {res.error!r}, start_error={r.start_error!r}")
        r._launch, r.retry_at = real, 0.0   # «прошла минута»
        res = r.render(f"http://127.0.0.1:{PORT}/browser-back", HTML)
        check(not res.error and "добавил скрипт" in res.html, f"после неудачного запуска браузер не вернулся: {res.error}")
        # браузер запустился, а вкладка нет: процессы Chromium закрываются сразу, а не висят до следующей попытки
        from playwright.async_api._generated import Browser
        real_ctx = Browser.new_context

        async def no_context(self, *a, **kw):
            raise RuntimeError("нет вкладки")
        Browser.new_context = no_context
        r.rendered = r.RECYCLE_EVERY
        res = r.render(f"http://127.0.0.1:{PORT}/no-context", HTML)
        left = chromium_count()
        Browser.new_context = real_ctx
        check("не запустился заново" in res.error, f"неудачная вкладка: {res.error!r}")
        if left is not None:
            check(left == 0, f"после неудачного запуска осталось процессов Chromium: {left}")
        r.retry_at = 0.0
        res = r.render(f"http://127.0.0.1:{PORT}/back-2", HTML)
        check(not res.error, f"после неудачной вкладки браузер не вернулся: {res.error}")
        # строки журнала: браузер не запустился заново, выключен, снова работает (crawler/page.js_state_note)
        from seocrawler.crawler.page import PageMixin

        class Fake(PageMixin):
            def __init__(self):
                self.renderer, self.lines = type("R", (), {"start_error": "", "launch_error": ""})(), []

            def log(self, m):
                self.lines.append(m)
        f = Fake()
        f.js_state_note()
        f.renderer.launch_error = "браузер не запустился заново: нет памяти"
        f.js_state_note()
        f.js_state_note()
        f.renderer.start_error = f.renderer.launch_error
        f.js_state_note()
        f.renderer.start_error = f.renderer.launch_error = ""
        f.js_state_note()
        check(len(f.lines) == 3 and "попробую снова" in f.lines[0] and "(нет памяти)" in f.lines[0]
              and "без JavaScript" in f.lines[1] and "снова работает" in f.lines[2], f"строки журнала: {f.lines}")
    finally:
        r.stop()
        srv.shutdown()
    if fails:
        print("✗ память браузера:\n   " + "\n   ".join(fails[:10]))
        sys.exit(1)
    print(f"✓ память браузера: {PAGES} страниц, перезапусков {r.restarts}, вызовы без ответа не копятся, "
          "лишних процессов нет")


if __name__ == "__main__":
    main()
