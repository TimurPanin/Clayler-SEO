"""Один процесс на одну папку проверки, и проверка не остаётся без окна (run/guard.py, 31.10.2026: после закрытия окна
сборка отчёта thehome.ru осталась работать, и «Продолжить прошлую проверку» пошла по той же папке параллельно).
Проверяем: пока идёт проверка, вторая с «Продолжить» и «Обновить отчёт» по этой папке не начинаются; окно (здесь -
процесс-родитель) закрыли - проверка завершается сама; старая метка от упавшего процесса папку не держит.
Свой медленный сайт, без сети. Запуск: py -3 тест/проверить_одну_папку.py (и из проверить_всё.py)."""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seocrawler.run import guard  # noqa: E402

PORT = 8784
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
            time.sleep(0.3)   # медленный сайт: проверка идёт, пока мы запускаем вторую
            n = int(m.group(1) or 0)
            body = (f"<html><head><title>Страница {n}</title></head><body><h1>Страница {n}</h1>"
                    + "".join(f'<a href="/p{n * 3 + k}/">ссылка</a>' for k in range(1, 4)) + "</body></html>").encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def crawl_cmd(*extra):
    return [sys.executable, os.path.join(ROOT, "crawl.py"), SITE, "--no-open", "--delay", "0", "--max-pages", "400",
            "--no-images", "--no-external", "--no-sitemap", "--no-search-urls", "--no-exposed", *extra]


def wait_for(cond, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.3)
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="clayler_one_folder_")
    env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_PARENT_CHECK="1",
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    first = parent = None
    try:
        # 1. идёт проверка - вторая по той же папке не начинается
        first = subprocess.Popen(crawl_cmd(), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        check(wait_for(lambda: glob.glob(os.path.join(tmp, "*", guard.LOCK)), 30), "метка «папка занята» не появилась")
        folder = os.path.dirname((glob.glob(os.path.join(tmp, "*", guard.LOCK)) or [""])[0])
        second = subprocess.run(crawl_cmd("--continue"), env=env, capture_output=True, text=True, timeout=60,
                                encoding="utf-8", errors="replace")
        check(second.returncode == 2, f"вторая проверка по занятой папке: код {second.returncode}, ждали 2")
        check("уже работает другой процесс" in second.stdout, "нет понятного сообщения о занятой папке")
        rep = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), "--report", folder, "--no-open"],
                             env=env, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
        check(rep.returncode == 2, f"«Обновить отчёт» по занятой папке: код {rep.returncode}, ждали 2")
        check(guard.busy(folder), "окно не видит, что папка занята")
        first.kill()
        first.wait(30)

        # 2. старая метка (процесс упал) папку не держит
        os.utime(os.path.join(folder, guard.LOCK), (time.time() - guard.STALE - 10,) * 2)
        check(not guard.busy(folder), "метка упавшего процесса держит папку")

        # 3. окно закрыли - проверка завершается сама (родитель запускает её с --stop-file, как окно)
        stop = os.path.join(tmp, ".stop-test")
        starter = ("import subprocess, sys, time; p = subprocess.Popen(sys.argv[1:]); print(p.pid, flush=True); "
                   "time.sleep(600)")
        parent = subprocess.Popen([sys.executable, "-c", starter] + crawl_cmd("--continue", "--stop-file", stop),
                                  env=env, stdout=subprocess.PIPE, text=True)
        child = int(parent.stdout.readline().strip() or 0)
        check(wait_for(lambda: guard.holder(folder) == child, 30), "продолжение после упавшего процесса не заняло папку")
        parent.kill()   # «закрыли окно»
        parent.wait(30)
        check(wait_for(lambda: not guard._alive(child), 30), "проверка осталась работать без окна")
    finally:
        for p in (first, parent):
            if p and p.poll() is None:
                p.kill()
        srv.shutdown()
    if fails:
        print("✗ одна папка - один процесс:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ одна папка - один процесс: вторая проверка и «Обновить отчёт» ждут, проверка без окна закрывается, "
          "старая метка не мешает")


if __name__ == "__main__":
    main()
