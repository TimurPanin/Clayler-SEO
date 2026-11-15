"""Режимы «Только этот раздел» (crawl.py --only-section) и «Мой список адресов» (--only-urls) на тестовом сайте:
обходятся только страницы раздела или списка (плюс куда ведут их редиректы), в отчёте есть пояснение,
проблем про связи всего сайта (глубина, сироты) нет. Запуск: python tests/проверить_разделы.py (и из проверить_всё.py)."""
import csv
import glob
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = 8769
BASE = f"http://127.0.0.1:{PORT}"
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def wait_up(sec=15):
    for _ in range(sec * 10):
        try:
            urllib.request.urlopen(BASE + "/", timeout=1)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.1)
    return False


def crawl(tmp, args):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
               CLAYLER_REPORTS=tmp)
    before = set(glob.glob(os.path.join(tmp, "*")))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py")] + args + ["--no-open", "--delay", "0"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    new = sorted(set(glob.glob(os.path.join(tmp, "*"))) - before)
    if r.returncode != 0 or not new:
        fails.append("программа завершилась с ошибкой: " + (r.stdout + r.stderr)[-800:])
        return None, set(), []
    folder = new[-1]
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    pages = {u[len(BASE):] for (u,) in db.execute(
        "SELECT url FROM urls WHERE kind='page' AND internal=1 AND state='done'")}
    scope = db.execute("SELECT value FROM meta WHERE key='scope'").fetchone()
    db.close()
    with open(os.path.join(folder, "проблемы.csv"), encoding="utf-8-sig") as f:
        keys = [os.path.splitext(os.path.basename(row[-1]))[0] for row in list(csv.reader(f, delimiter=";"))[1:]]
    return folder, pages, (json.loads(scope[0]) if scope else None, keys)


def main():
    tmp = tempfile.mkdtemp(prefix="clayler-scope-")
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "testsite.py"), str(PORT)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_up():
            print(f"✗ разделы и список: тестовый сайт не запустился (порт {PORT} занят?)")
            sys.exit(1)
        # 1. Только раздел /catalog/
        folder, pages, info = crawl(tmp, [BASE + "/catalog/", "--only-section"])
        if folder:
            scope, keys = info
            check(scope == {"mode": "section", "prefix": f"127.0.0.1:{PORT}/catalog/"}, f"раздел: scope {scope}")
            check(pages and all(p.startswith("/catalog/") for p in pages), f"раздел: лишние страницы {sorted(pages)}")
            check("/catalog/item-3" in pages, f"раздел: не обошёл товары {sorted(pages)}")
            check(not {"deep", "one_inlink", "orphans"} & set(keys), f"раздел: проблемы всего сайта {keys}")
            rep = open(os.path.join(folder, "отчёт.html"), encoding="utf-8").read()
            check("Проверен только раздел" in rep, "раздел: нет пояснения в отчёте")
            check("Проверен только раздел" in open(os.path.join(folder, "аудит.html"), encoding="utf-8").read(),
                  "раздел: нет пояснения в аудите")
        # 1а. «Дообойти» раздела (--continue без --only-section, как из окна с другой формой): остаётся разделом
        if folder:
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
                       CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_NO_SITE_TECH="1",
                       CLAYLER_REPORTS=tmp)
            subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), BASE + "/catalog/", "--continue",
                            "--no-open", "--delay", "0"], env=env, capture_output=True, timeout=300)
            db = sqlite3.connect(os.path.join(folder, "crawl.db"))
            scope = json.loads((db.execute("SELECT value FROM meta WHERE key='scope'").fetchone() or ["null"])[0])
            again = {u[len(BASE):] for (u,) in db.execute(
                "SELECT url FROM urls WHERE kind='page' AND internal=1 AND state='done'")}
            db.close()
            check(scope == {"mode": "section", "prefix": f"127.0.0.1:{PORT}/catalog/"} and
                  all(p.startswith("/catalog/") for p in again),
                  f"«Дообойти» раздела стал проверкой всего сайта: {scope} {sorted(again)[:6]}")
        # 2. Свой список адресов: /old ведёт цепочкой редиректов /old2 → /new — их тоже открываем
        lst = os.path.join(tmp, "список.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write(f"{BASE}/old\n{BASE}/about\n\n{BASE}/missing ; {BASE}/about\nне адрес\n")
        folder, pages, info = crawl(tmp, ["--only-urls", lst])
        if folder:
            scope, keys = info
            check(scope == {"mode": "list", "count": 3}, f"список: scope {scope}")
            check(pages == {"/old", "/old2", "/new", "/about", "/missing"}, f"список: страницы {sorted(pages)}")
            check("4xx" in keys, f"список: нет ошибки 404 для /missing {keys}")
            rep = open(os.path.join(folder, "отчёт.html"), encoding="utf-8").read()
            check("Проверены только адреса из списка (3 шт.)" in rep, "список: нет пояснения в отчёте")
            check(os.path.exists(os.path.join(folder, "список_адресов.txt")), "список: не сохранён в папке проверки")
    finally:
        srv.terminate()
    if fails:
        print("✗ разделы и список:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ режимы «Только этот раздел» и «Мой список адресов»")


if __name__ == "__main__":
    main()
