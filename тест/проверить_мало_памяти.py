"""Мало памяти компьютера - обход останавливается сам, а не падает с MemoryError (seocrawler/memory.py,
crawler/main_loop.low_memory; thehome.ru 31.10.2026 упал через 17 часов). Порог завышаем переменной
CLAYLER_MIN_FREE_MB: обход должен остановиться в первые секунды, написать в журнал почему и что делать, не собирать
отчёт (сборка сама берёт много памяти), а «Продолжить прошлую проверку» с нормальным порогом - доделать проверку.
Свой медленный сайт, без сети. Запуск: py -3 тест/проверить_мало_памяти.py (и из проверить_всё.py)."""
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seocrawler import memory  # noqa: E402

PORT = 8785
SITE = f"http://127.0.0.1:{PORT}/"
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        m = re.fullmatch(r"/(?:p(\d+)/)?", self.path)
        if self.path == "/robots.txt":
            body, ctype = b"", "text/plain"
        elif not m:   # служебные проверки программы (index.php, ?clayler=1 и др.) - такой страницы нет
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        else:
            time.sleep(0.05)
            n = int(m.group(1) or 0)
            links = "".join(f'<a href="/p{n * 2 + k}/">ссылка</a>' for k in (1, 2)) if n < 30 else ""
            body = f"<html><head><title>Страница {n}</title></head><body><h1>Страница {n}</h1>{links}</body></html>".encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(tmp, *extra, min_free=None):
    env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8",
               PYTHONUTF8="1")
    if min_free is not None:
        env["CLAYLER_MIN_FREE_MB"] = str(min_free)
    return subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), SITE, "--no-open", "--delay", "0",
                           "--no-images", "--no-external", "--no-sitemap", "--no-search-urls", "--no-exposed", *extra],
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def main():
    free = memory.free_mb()
    check(free is not None and free > 0, f"свободную память узнать не удалось: {free}")
    tmp = tempfile.mkdtemp(prefix="clayler_low_mem_")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = run(tmp, min_free=10 ** 9)   # «осталось меньше миллиона гигабайт» - всегда мало
        out = r.stdout + r.stderr
        folder = (sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*"))) or [""])[-1]
        check(r.returncode == 0, f"проверка при нехватке памяти завершилась с ошибкой {r.returncode}: {out[-500:]}")
        check("Памяти компьютера почти не осталось" in out, "в журнале нет сообщения о нехватке памяти")
        check("Продолжить прошлую проверку" in out, "в журнале нет подсказки, что делать дальше")
        check("мало памяти компьютера" in out, "итог обхода не говорит, что остановлен из-за памяти")
        check(not os.path.exists(os.path.join(folder, "отчёт.html")), "отчёт собирается, хотя памяти мало")
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
        done1 = db.execute("SELECT COUNT(*) FROM urls WHERE state='done' AND kind='page'").fetchone()[0]
        left = db.execute("SELECT COUNT(*) FROM urls WHERE state='queued' AND kind='page'").fetchone()[0]
        meta = db.execute("SELECT value FROM meta WHERE key='low_memory'").fetchone()
        db.close()
        check(left > 0, f"обход не остановился: в очереди {left} страниц")
        check(meta and "free_mb" in json.loads(meta[0]), "в базе нет отметки об остановке из-за памяти")

        r = run(tmp, "--continue")   # памяти хватает - доделываем
        db = sqlite3.connect(os.path.join(folder, "crawl.db"))
        done2 = db.execute("SELECT COUNT(*) FROM urls WHERE state='done' AND kind='page'").fetchone()[0]
        db.close()
        check(r.returncode == 0 and done2 > done1, f"продолжение не доделало обход: было {done1}, стало {done2}")
        check(os.path.exists(os.path.join(folder, "отчёт.html")), "после продолжения отчёт не собрался")

        # «Обновить отчёт», а памяти мало: сборка останавливается сама с подсказкой, без трассировки (memory.guard,
        # run/cli.build_safely; план на ночь 05.11.2026). Раньше сборка шла без присмотра до MemoryError
        env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
                   CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8",
                   PYTHONUTF8="1", CLAYLER_MIN_FREE_MB=str(10 ** 9))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), "--report", folder, "--no-open"], env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        out = r.stdout + r.stderr
        check(r.returncode == 3, f"сборка отчёта при нехватке памяти: код {r.returncode}, {out[-400:]}")
        check("Нехватка памяти" in out and "Обновить отчёт" in out, f"нет подсказки при сборке отчёта: {out[-400:]}")
        check("Traceback" not in out, f"сборка упала с трассировкой: {out[-600:]}")
        # и посреди анализа: прогресс анализа глушил любые ошибки - остановка по памяти должна пройти насквозь,
        # и шаг «except Exception - написать и идти дальше» её не глотает
        from seocrawler import analyze as AN

        def low(_f):
            raise memory.LowMemory(100)
        old, AN.ON_PROGRESS = AN.ON_PROGRESS, low
        try:
            try:
                AN._progress(0.5)
                check(False, "остановка по памяти потерялась в прогрессе анализа")
            except memory.LowMemory:
                pass
            try:
                try:
                    AN._progress(0.5)
                except Exception:
                    check(False, "остановку по памяти поймал «except Exception»")
            except memory.LowMemory:
                pass
        finally:
            AN.ON_PROGRESS = old
        # вне сборки отчёта (окно, «Семантика» тоже зовут анализ) проверка памяти молчит, в сборке - останавливает
        old_min, memory.MIN_FREE_MB = memory.MIN_FREE_MB, 10 ** 9
        try:
            memory.ARMED[0], memory._GUARD_AT[0] = False, 0.0
            memory.guard()
            memory.ARMED[0] = True
            try:
                memory.guard()
                check(False, "во время сборки отчёта проверка памяти не остановила")
            except memory.LowMemory:
                pass
        except memory.LowMemory:
            check(False, "проверка памяти остановила вне сборки отчёта")
        finally:
            memory.MIN_FREE_MB, memory.ARMED[0] = old_min, False
    finally:
        srv.shutdown()
    if fails:
        print("✗ мало памяти:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ мало памяти: обход останавливается сам с подсказкой, без отчёта, продолжение доделывает "
          f"(свободно сейчас {free} МБ)")


if __name__ == "__main__":
    main()
