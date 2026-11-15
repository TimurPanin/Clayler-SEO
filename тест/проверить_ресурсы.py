"""Память и процессор проверки в окне (seocrawler/memory.Sampler, 01.11.2026): своя память программы, память её
дочерних процессов (браузер для JavaScript), свободная память компьютера, загрузка процессора; проверка, запущенная
как из окна (--status-file), кладёт их в файл состояния, окно показывает строкой в карточке проверки.
Без сети. Запуск: py -3 тест/проверить_ресурсы.py (и из проверить_всё.py)."""
import json
import os
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

PORT = 8786
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        time.sleep(0.2)
        n = self.path.strip("/")[1:] if self.path.startswith("/p") else "0"
        n = int(n) if n.isdigit() else 0
        body = (f"<html><head><title>Страница {n}</title></head><body><h1>{n}</h1>"
                + (f'<a href="/p{n + 1}/">дальше</a>' if n < 40 else "") + "</body></html>").encode()
        self.send_response(200 if self.path == "/" or self.path.startswith("/p") else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    # 1. замер: своя память, дочерний процесс python на ~300 МБ, процессор со второго замера
    child = subprocess.Popen([sys.executable, "-c", "x = bytearray(300 * 2**20); import time; time.sleep(30)"])
    try:
        time.sleep(3)
        s = memory.Sampler()
        a = s.sample()
        end = time.time() + 1
        while time.time() < end:
            sum(i * i for i in range(5000))
        b = s.sample()
    finally:
        child.kill()
    check(a.get("free_mb"), f"свободная память не узнана: {a}")
    if os.name == "nt":
        # дочерний python (как процесс расчёта на нескольких ядрах) - это сама программа, а не браузер
        check(a.get("prog_mb", 0) >= 250, f"память дочернего процесса python не посчитана в программу: {a}")
        check(a.get("browser_mb", 0) < 100, f"дочерний python посчитан как браузер: {a}")
        check(b.get("cpu") is not None and b.get("prog_cpu", 0) > 0, f"процессор не замерен: {b}")

    # 2. проверка, запущенная как из окна, пишет замер в файл состояния
    tmp = tempfile.mkdtemp(prefix="clayler_res_")
    status = os.path.join(tmp, ".status-test.json")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SPEED_LAB="1", PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "crawl.py"), f"http://127.0.0.1:{PORT}/", "--no-open",
                          "--delay", "0", "--threads", "1", "--no-images", "--no-external", "--no-sitemap",
                          "--no-search-urls", "--no-exposed", "--status-file", status],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen = None
    try:
        end = time.time() + 120
        while time.time() < end and p.poll() is None and not seen:
            try:
                res = json.load(open(status, encoding="utf-8")).get("res") or {}
                if res.get("free_mb") and (os.name != "nt" or res.get("prog_mb")):
                    seen = res
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
    finally:
        p.wait(300)
        srv.shutdown()
    check(seen, "в файле состояния проверки нет памяти и процессора (res)")

    # 2б. «Обновить отчёт»: замер обновляется сам раз в несколько секунд, а не только при смене этапа
    import glob
    folder = (sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*"))) or [""])[-1]
    status2 = os.path.join(tmp, ".status-report.json")
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "crawl.py"), "--report", folder, "--no-open",
                          "--status-file", status2], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen2 = None
    try:
        end = time.time() + 120
        while time.time() < end and p.poll() is None and not seen2:
            try:
                seen2 = (json.load(open(status2, encoding="utf-8")).get("res") or {}).get("free_mb")
            except (OSError, ValueError):
                pass
            time.sleep(0.3)
    finally:
        p.wait(300)
    check(seen2, "при сборке отчёта в файле состояния нет памяти и процессора (res)")

    # 3. окно показывает строку
    page = os.path.join(ROOT, "seocrawler", "window", "page")
    check('id="resLine"' in open(os.path.join(page, "index.html"), encoding="utf-8").read(), "в карточке нет строки ресурсов")
    js = open(os.path.join(page, "app.js"), encoding="utf-8").read()
    check("function resText" in js and "$('resLine')" in js, "окно не выводит строку ресурсов")
    job = open(os.path.join(ROOT, "seocrawler", "window", "job.py"), encoding="utf-8").read()
    check('"res": (st or {}).get("res")' in job, "окно не передаёт ресурсы из файла состояния")
    if fails:
        print("✗ ресурсы проверки:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ ресурсы проверки: память программы и браузера, свободно, процессор - в файле состояния и в окне "
          f"(пример: {seen})")


if __name__ == "__main__":
    main()
