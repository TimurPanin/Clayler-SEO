"""Разбор параметров командной строки crawl.py и запуск: обход сайта, отчёт, семантика, сравнение, списки."""
import argparse
import glob
import os
import sys
import time
import webbrowser

from seocrawler import competitors as COMP
from seocrawler import urls as U
from seocrawler.crawler import Config, Crawler
from seocrawler.crawler.common import JS_TABS_GENTLE, js_load, mask_to_regex

from .build import STATUS, build_report, status
from . import guard
from .extras import run_list, setup_js
from .history import _FOLDER_RX, resume_settings, run_compare
from .semantics_run import run_semantics


def build_safely(out_dir, open_browser, rebuild=False):
    """build_report, но памяти мало (memory.guard) или уже не хватило (MemoryError) - понятная подсказка и выход с
    кодом 3, а не трассировка посреди записи файлов (план на ночь 05.11.2026, пункт 9). Проверка в базе цела."""
    from seocrawler import memory
    try:
        build_report(out_dir, open_browser, rebuild=rebuild)
    except (memory.LowMemory, MemoryError) as e:
        free = getattr(e, "free", None)
        # трассировка держит данные сборки (база, проблемы, страницы) - отпускаем их до печати, иначе подсказка
        # сама может упасть с MemoryError (ревью кода 05.11.2026)
        e.__traceback__ = None
        del e
        import gc
        gc.collect()
        print(memory.build_stopped_text(free))
        status(step="Остановлено: мало памяти компьютера", done=True)
        sys.exit(3)


def main():
    ap = argparse.ArgumentParser(description="SEO-краулер: обход сайта и отчёт об ошибках.")
    ap.add_argument("url", nargs="?", help="адрес сайта, например https://example.ru")
    ap.add_argument("--max-pages", type=int, default=10000, help="сколько страниц сайта обойти (10000)")
    ap.add_argument("--threads", type=int, default=4, help="одновременных запросов (4)")
    ap.add_argument("--delay", type=float, default=0.2, help="пауза между запросами, сек (0.2)")
    ap.add_argument("--depth", type=int, default=50, help="максимальная глубина (50)")
    ap.add_argument("--ua", default="crawler", help="User-Agent: crawler, googlebot, yandexbot, chrome или своя строка")
    ap.add_argument("--robots", default="googlebot", choices=["googlebot", "yandex"],
                    help="чьи правила robots.txt соблюдать (googlebot)")
    ap.add_argument("--ignore-robots", action="store_true", help="не соблюдать robots.txt")
    ap.add_argument("--no-clean-param", action="store_true", help="не применять Clean-param")
    ap.add_argument("--max-params", type=int, default=3, help="не обходить URL с большим числом параметров (3)")
    ap.add_argument("--follow-nofollow", action="store_true", help="переходить по nofollow-ссылкам")
    ap.add_argument("--subdomains", action="store_true", help="обходить поддомены как свой сайт")
    ap.add_argument("--regions", action="store_true",
                    help="сайт с городами: найти городские версии по переключателю города и проверить их вместе")
    ap.add_argument("--no-external", action="store_true", help="не проверять внешние ссылки")
    ap.add_argument("--no-images", action="store_true", help="не проверять картинки")
    ap.add_argument("--no-sitemap", action="store_true", help="не читать sitemap.xml")
    ap.add_argument("--no-search-urls", action="store_true",
                    help="не брать адреса страниц из Яндекс Вебмастера и Google Search Console")
    ap.add_argument("--crawl-sitemap", action="store_true", help="обходить и адреса из sitemap")
    ap.add_argument("--exclude", action="append", default=[], help="регулярное выражение для исключения URL")
    ap.add_argument("--skip-mask", action="append", default=[], metavar="МАСКА",
                    help="не обходить адреса по маске: * - любые символы, например /filter/ или *?sort=*")
    ap.add_argument("--only-section", action="store_true",
                    help="только этот раздел: обходить адреса, начинающиеся с указанного (site.ru/catalog/)")
    ap.add_argument("--only-urls", metavar="ФАЙЛ",
                    help="полная проверка только адресов из файла (по одному в строке), без обхода по ссылкам")
    ap.add_argument("--js", action="store_true", help="выполнять JavaScript во встроенном браузере (медленнее)")
    ap.add_argument("--setup-js", action="store_true", help="только установить всё нужное для режима JavaScript")
    ap.add_argument("--js-tabs", type=int, default=0,
                    help="сколько страниц рендерить одновременно (6, на бережной скорости 3)")
    ap.add_argument("--js-wait", type=float, default=5.0, help="сколько секунд ждать скрипты на странице (5)")
    ap.add_argument("--no-exposed", action="store_true",
                    help="не искать открытые служебные файлы (.git, .env, бэкапы) - для сайтов конкурентов")
    ap.add_argument("--insecure", action="store_true", help="не проверять SSL-сертификат")
    ap.add_argument("--continue", dest="resume", action="store_true", help="продолжить последний обход этого сайта")
    ap.add_argument("--report", metavar="ПАПКА", help="только пересобрать отчёт из готового обхода")
    ap.add_argument("--competitors", nargs="+", metavar="ПАПКА",
                    help="сравнить сайты: первая папка - ваш сайт, остальные - конкуренты")
    ap.add_argument("--semantics", nargs="+", metavar="ПАПКА",
                    help="собрать семантику: первая папка - свой сайт, остальные - конкуренты")
    ap.add_argument("--rival-hosts", nargs="*", default=[], metavar="САЙТ",
                    help="семантика: конкуренты по адресу, без проверки (разделы из меню главной)")
    ap.add_argument("--deep", action="store_true", help="семантика подробно: ещё «раздел + буква» (дольше)")
    ap.add_argument("--light", action="store_true",
                    help="семантика быстро (очередь сайтов): только главная и разделы, без подразделов и карточек")
    ap.add_argument("--masks", metavar="ПАПКА", help="предложить маски семантики по проверке (для страницы «Семантика»)")
    ap.add_argument("--region", default="", help="город для семантики (по умолчанию - из заголовков сайта)")
    ap.add_argument("--compare", nargs=2, metavar=("СТАРАЯ", "НОВАЯ"), help="сравнить две папки проверок")
    ap.add_argument("--list", metavar="ФАЙЛ", help="проверить только адреса из файла (по одному в строке)")
    ap.add_argument("--old", metavar="ПАПКА", help="переезд: взять адреса из этой проверки и сравнить с тем, что было")
    ap.add_argument("--new-host", default="", help="переезд на новый домен: проверять старые адреса на нём")
    ap.add_argument("--stop-file", default="", help=argparse.SUPPRESS)
    ap.add_argument("--status-file", default="", help=argparse.SUPPRESS)
    ap.add_argument("--no-open", action="store_true", help="не открывать отчёт в браузере")
    a = ap.parse_args()
    if a.stop_file or a.status_file:   # запустило окно программы: закроют окно - закрываемся и мы (run/guard.py)
        guard.watch_parent()
        from seocrawler import memory   # память и процессор проверки - в окно, через файл состояния
        memory.start_sampling()

    if a.list or a.old:
        run_list(a)
        return
    if a.competitors:
        dirs = [d for d in a.competitors if os.path.exists(os.path.join(d, "crawl.db"))]
        if len(dirs) < 2:
            print("Для сравнения нужно минимум две законченные проверки.")
            return
        print("Сравниваю сайты: " + ", ".join(os.path.basename(d) for d in dirs))
        sites = [COMP.site_metrics(d) for d in dirs]
        path = os.path.join(dirs[0], "конкуренты.html")
        COMP.write_report(path, sites)
        print(f"Сравнение с конкурентами готово: {path}")
        if not a.no_open:
            webbrowser.open("file:///" + os.path.abspath(path).replace("\\", "/"))
        return
    if a.masks:   # маски семантики из проверки - отдельной программой, окно не ждёт (semantics/masks.py)
        from seocrawler.semantics import masks
        masks.propose(a.masks)
        return
    if a.semantics:
        run_semantics(a.semantics[0], a.semantics[1:], a.region, not a.no_open, a.deep, a.rival_hosts, a.stop_file,
                      light=a.light)
        return
    if a.compare:
        info = run_compare(*a.compare)
        print(f"Исправлено: {info['fixed']}, новых: {info['added']}. Файл: {os.path.join(a.compare[1], 'сравнение.html')}")
        return
    if a.report:
        if not guard.claim(a.report, "отчёт"):
            sys.exit(2)
        STATUS["path"] = a.status_file
        build_safely(a.report, not a.no_open, rebuild=True)
        return
    if a.setup_js:
        sys.exit(0 if setup_js() else 1)
    only_urls = []
    if a.only_urls:
        from seocrawler.crawler.common import read_url_list
        only_urls = read_url_list(a.only_urls)
        if not only_urls:
            print("В списке нет адресов: нужны полные адреса, начинающиеся с http:// или https://")
            sys.exit(1)
        a.url = a.url or only_urls[0]
        a.max_pages = max(a.max_pages, 2 * len(only_urls))  # редиректы со списка тоже страницы
    if not a.url:
        a.url = input("Адрес сайта (например, https://example.ru): ").strip()
    if not a.url:
        return
    if "://" not in a.url:
        a.url = "https://" + a.url
    start = U.normalize(a.url)
    if not start:
        print("Не понял адрес:", a.url)
        return
    # имя папки: домен, а если адрес с портом — домен_порт (иначе разные сайты на одном домене перепутаются)
    from urllib.parse import urlsplit
    host = urlsplit(start).netloc.replace(":", "_")
    from seocrawler.window import REPORTS as reports   # автотесты пишут в свою папку (CLAYLER_REPORTS)
    os.makedirs(reports, exist_ok=True)

    out_dir = None
    if a.resume:
        old = sorted(d for d in glob.glob(os.path.join(reports, host + "_*"))
                     if (_FOLDER_RX.match(os.path.basename(d)) or [None, None])[1] == host)
        if old:
            out_dir = old[-1]
            print("Продолжаю прошлую проверку этого сайта. Папка:", out_dir)
        else:
            print("Прошлых проверок этого сайта не нашёл - начинаю новую.")
    if not out_dir:
        base_dir = os.path.join(reports, f"{host}_{time.strftime('%Y-%m-%d_%H-%M-%S')}")
        out_dir, n = base_dir, 2
        while os.path.exists(out_dir):  # две проверки в одну секунду
            out_dir, n = f"{base_dir}_{n}", n + 1
        os.makedirs(out_dir)
    if not guard.claim(out_dir, "проверка"):   # прошлая проверка этой папки ещё работает (например, без окна)
        sys.exit(2)

    list_file = ""
    if only_urls:  # список хранится в папке проверки: из неё его читает и «Продолжить прошлую проверку»
        list_file = os.path.join(out_dir, "список_адресов.txt")
    # «Дообойти» продолжает ту же проверку (resume_settings): её список не заменяем списком из формы окна
    if list_file and not (a.resume and os.path.exists(os.path.join(out_dir, "crawl.db"))):
        with open(list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(only_urls) + "\n")
    threads, js_tabs = max(1, a.threads), JS_TABS_GENTLE
    if a.js:
        js_tabs, threads = js_load(max(0.0, a.delay), threads, a.js_tabs)
    cfg = Config(
        start_url=start, max_pages=a.max_pages, max_depth=a.depth, threads=threads,
        delay=max(0.0, a.delay), user_agent=a.ua, robots_for=a.robots, respect_robots=not a.ignore_robots,
        use_clean_param=not a.no_clean_param, max_params=a.max_params, follow_nofollow=a.follow_nofollow,
        crawl_subdomains=a.subdomains, regions=a.regions, check_external=not a.no_external, check_resources=not a.no_images,
        use_sitemap=not a.no_sitemap, use_search_urls=not a.no_search_urls, crawl_sitemap=a.crawl_sitemap,
        exclude=a.exclude + [mask_to_regex(m) for m in a.skip_mask], skip_masks=a.skip_mask,
        section=start if a.only_section and not only_urls else "", url_list=list_file,
        verify_ssl=not a.insecure, stop_file=a.stop_file, status_file=a.status_file, render_js=a.js,
        render_tabs=js_tabs, render_wait=max(0.5, a.js_wait),
        check_exposed=not a.no_exposed,
    )
    if a.resume and os.path.exists(os.path.join(out_dir, "crawl.db")):
        resume_settings(cfg, out_dir)
    start = cfg.start_url
    print(f"Сайт: {start}")
    if cfg.url_list:
        resumed = a.resume and os.path.exists(os.path.join(out_dir, "crawl.db"))   # список - прежний
        print(f"Проверяю только адреса из списка{f': {len(only_urls)}' if only_urls and not resumed else ''} "
              "(по ссылкам на другие страницы не иду)")
    elif cfg.section:
        print("Проверяю только раздел: адреса, которые начинаются с " + start)
    print(f"Лимит: {a.max_pages} страниц сайта (картинки и внешние ссылки в лимит не входят)")
    print("Режим: " + ("с JavaScript (страницы открываются во встроенном браузере)" if cfg.render_js
                       else "без JavaScript (только HTML от сервера)"))
    print(f"Результаты сохраняются в папку: {out_dir}")
    print("Остановить можно в любой момент: Ctrl+C. Всё проверенное сохранится, и отчёт соберётся.")
    STATUS["path"] = a.status_file
    status(site=start, out_dir=out_dir, step="Запускаю", done=False)
    crawler = Crawler(cfg, os.path.join(out_dir, "crawl.db"))
    crawler._st.update(site=start, out_dir=out_dir, done=False)
    try:
        crawler.run()
    except KeyboardInterrupt:
        print("\nОстановлено. Собираю отчёт из того, что успел проверить.")
        crawler.store.commit()
    crawler.store.db.close()
    if getattr(crawler, "low_mem", None) is not None:
        # сборка отчёта сама берёт много памяти (база thehome.ru на 6 ГБ - до 8 ГБ): сейчас она бы упала
        print("\nОтчёт сейчас не собираю: памяти мало. Когда освободится - продолжите проверку (отчёт соберётся в "
              "конце) или нажмите «⋯ → Обновить отчёт».")
        status(step="Остановлено: мало памяти компьютера", done=True)
        return
    build_safely(out_dir, not a.no_open)
    status(step="Готово", done=True)
