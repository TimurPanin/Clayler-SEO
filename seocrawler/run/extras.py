"""Проверка списка адресов и переезда (crawl.py --list, --old) и подготовка режима JavaScript (--setup-js)."""
import os
import sys
import time
import webbrowser


def run_list(a):
    """Проверка списка адресов (--list) или переезда (--old): результат - в папке «reports/списки»."""
    from seocrawler import urllist
    from urllib.parse import urlsplit
    old = None
    if a.old:
        start, old = urllist.from_check(a.old)
        urls = list(old)
        title = "Проверка переезда: " + (urlsplit(start).netloc or os.path.basename(a.old)) +                 (" → " + a.new_host if a.new_host else "")
        print(f"Переезд: беру {len(urls)} адресов из проверки {os.path.basename(a.old)}"
              + (f" и проверяю их на {a.new_host}" if a.new_host else ""))
    else:
        with open(a.list, encoding="utf-8-sig", errors="replace") as f:
            urls = urllist.read_list(f.read())
        title = "Проверка списка адресов"
        print(f"Проверяю список: {len(urls)} адресов")
    if not urls:
        print("Адресов для проверки нет: нужны полные адреса, начинающиеся с http:// или https://")
        return
    from seocrawler.window import REPORTS as reports   # автотесты пишут в свою папку (CLAYLER_REPORTS)
    host = (urlsplit(urllist._swap_host(urls[0], a.new_host)).netloc or "список").replace(":", "_")
    base = os.path.join(reports, "списки", f"{'переезд' if a.old else 'список'}_{host}_{time.strftime('%Y-%m-%d_%H-%M-%S')}")
    auth = None
    try:
        from seocrawler import site_auth
        auth = site_auth.headers_for(urls[0] if not a.new_host else urllist._swap_host(urls[0], a.new_host))
    except Exception:
        pass
    urllist.run(urls, base, old=old, new_host=a.new_host, ua=a.ua, threads=max(1, a.threads), delay=max(0.0, a.delay),
                stop_file=a.stop_file, title=title, auth=auth)
    print("Результат проверки списка: " + base + ".html")
    if not a.no_open:
        webbrowser.open("file:///" + os.path.abspath(base + ".html").replace("\\", "/"))


def setup_js():
    """Готовит встроенный браузер: ставит модуль playwright и скачивает Chromium. Он нужен для проверки с JavaScript,
    снимков страниц с обведённой ошибкой, вида на телефоне, скорости и кнопок покупки. Возвращает True, если
    браузер запускается. Его зовут «Clayler SEO.bat» при первом запуске и окно, когда включили JavaScript."""
    import subprocess

    def can_launch():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                p.chromium.launch(headless=True).close()
            return True, ""
        except Exception as e:
            return False, str(e).strip().splitlines()[0][:200] if str(e).strip() else type(e).__name__

    try:
        import playwright  # noqa: F401
    except Exception:
        print("Устанавливаю модуль playwright для работы с браузером (один раз, нужен интернет)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                            "playwright"])
        if r.returncode != 0:
            print("Не получилось установить playwright. Программа будет работать без снимков страниц"
                  " и проверки с JavaScript.")
            return False
    ok, err = can_launch()
    if ok:
        print("Встроенный браузер готов: снимки страниц и проверка с JavaScript работают.")
        return True
    print("Скачиваю встроенный браузер Chromium (один раз, около 150-200 МБ)...")
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    ok, err = can_launch()
    if ok:
        print("Готово: браузер Chromium установлен и запускается.")
        return True
    print("Браузер не запускается: " + err)
    print("Программа будет работать без снимков страниц и проверки с JavaScript.")
    return False
