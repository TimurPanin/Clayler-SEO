"""Автотест проверок, данные для которых в тестах без интернета не получить: срок сертификата (нужен
сертификат, которому доверяет Windows), орфография (Яндекс.Спеллер), страницы, которые знает поиск (Вебмастер и
Search Console), фото с других сайтов выборкой (больше 1 000 фото), ссылки на внутренний адрес сервера (тестовый
сайт сам на 127.0.0.1), города (поддомены и переключатель на JavaScript).
Тестовый сайт tests/checksite.py проверяется программой, потом в его базу подставляются данные, которые обычно
приходят из сети, и проверки должны сработать - и не сработать без этих данных.
Запуск: py -3 tests/проверить_редкие_проверки.py (и из проверить_всё.py)."""
import glob
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = 8779
B = f"http://127.0.0.1:{PORT}"

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def main():
    tmp = tempfile.mkdtemp(prefix="clayler-rare-")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_REPORTS=tmp)
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "checksite.py"), str(PORT)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(B + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), B + "/", "--no-open", "--delay", "0",
                            "--no-exposed"], env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=400)
    finally:
        srv.kill()
    folders = sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*")))
    if r.returncode != 0 or not folders:
        print("✗ редкие проверки: тестовый сайт не проверился\n" + (r.stdout + r.stderr)[-1500:])
        sys.exit(1)

    os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
    from seocrawler.storage import Store
    from seocrawler.analyze import analyze
    store = Store(os.path.join(folders[-1], "crawl.db"))

    def keys():
        issues, _pages, _summary = analyze(store)
        return {i.key for i in issues}

    before = keys()
    for k in ("cert_expiry", "spelling", "search_orphans", "img_ext_sample", "private_host", "region_unlinked",
              "region_no_urls", "region_not_checked"):
        check(k not in before, f"{k} сработала без данных")

    # данные, которые обычно приходят из сети
    store.set_meta("cert", {"host": "127.0.0.1", "not_after": "Oct 25 12:00:00 2026 GMT", "days_left": 10})
    store.set_meta("spelling", {"errors": {"тестового": ["тестовый"]}})
    store.set_meta("search_urls", {"complete": True, "urls": {B + "/orphan": ["yandex", "google"]}})
    store.set_meta("ext_files_sample", {"cdn.example.ru": [1000, 250]})
    store.set_meta("regions_no_urls", ["Казань"])
    store.commit()
    got = keys()
    for k in ("cert_expiry", "spelling", "search_orphans", "img_ext_sample", "region_no_urls"):
        check(k in got, f"{k} не сработала на подставных данных")

    # раздел /sec/ как город, на который ведут ссылки только изнутри; потом - города найдены, но проверка без них
    store.set_meta("regions_no_urls", None)
    store.set_meta("regions", [{"city": "", "url": B + "/", "how": "основной сайт", "main": True},
                               {"city": "Казань", "url": B + "/sec/", "how": "ссылка на сайте", "main": False}])
    store.commit()
    check("region_unlinked" in keys(), "region_unlinked не сработала: на /sec/ ссылки только изнутри")
    store.set_meta("regions", [])
    store.set_meta("regions_seen", [{"city": "Казань", "url": B + "/sec/", "main": False}])
    store.commit()
    check("region_not_checked" in keys(), "region_not_checked не сработала")

    # сайт не на 127.0.0.1: ссылки на 127.0.0.1 - внутренний адрес сервера
    store.set_meta("start", "https://example.ru/")
    store.commit()
    check("private_host" in keys(), "private_host не сработала")

    if fails:
        print("✗ редкие проверки:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ редкие проверки: срок сертификата, орфография, страницы из поиска, фото выборкой, внутренний адрес, "
          "города - срабатывают на данных и молчат без них")


main()
