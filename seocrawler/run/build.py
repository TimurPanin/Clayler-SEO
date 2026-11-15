"""Сборка отчёта из готового обхода: данные служб (Вебмастер, Search Console, Метрика и др.), сравнение с прошлой
проверкой, поиск проблем и все файлы отчёта. Здесь же - состояние сборки для окна программы (status.json)."""
import json
import os
import time
import webbrowser

import seocrawler.analyze as AN
from seocrawler import compare as CMP
from seocrawler import xlsx_report
from seocrawler.analyze import cached_analyze
from seocrawler.crawler import _plural
from seocrawler.report import PAGE_EXPORT, export_all, html_report
from seocrawler.storage import Store

from .history import later_crawl, previous_crawl, run_compare

# служебные поля загрузки Вебмастера, Search Console и Метрики - не данные (загрузка с одними ошибками - не данные)
NOT_DATA = {"host", "site", "fetched", "errors", "counter", "name", "not_loaded", "id"}

STATUS = {"path": "", "data": {}}
_STATUS_LOCK = __import__("threading").Lock()   # пишут сборка отчёта и замер ресурсов (memory.ON_SAMPLE)


def status(**kw):
    """Состояние для окна программы (status.json): шаг, папка, готово ли."""
    with _STATUS_LOCK:
        _status(kw)


def _status(kw):
    if STATUS["path"]:
        from seocrawler.crawler import write_status
        try:
            STATUS["data"] = json.load(open(STATUS["path"], encoding="utf-8"))
        except Exception:
            pass
        STATUS["data"].update(kw, updated=time.time())
        from seocrawler import memory
        if memory.LAST:
            STATUS["data"]["res"] = dict(memory.LAST)   # память и процессор - для окна
        write_status(STATUS["path"], STATUS["data"])


# версия расчёта здоровья в meta summary: 2 - с 15.10.2026 (проблема всего сайта - штраф, а не 0%);
# у старых отчётов без неё окно пишет «старый расчёт здоровья» (window/reports_list.py)
HEALTH_VERSION = 2


def build_report(out_dir, open_browser=True, compare_with=None, rebuild=False):
    """rebuild — «Обновить отчёт» из окна: сайт заново не обходится, в окне «Обновляю отчёт» и свой прогресс."""
    head = "Обновляю отчёт" if rebuild else "Собираю отчёт"

    def stage(text, a, b=None, parts=1):
        """Шаг сборки для окна: доля всей сборки от a до b (0..1); анализ внутри шага двигает полосу сам.
        parts — сколько анализов в шаге (сравнение анализирует прошлую и эту проверку): каждый — своя часть полосы."""
        status(step=f"{head}: {text}", out_dir=out_dir, report_frac=a)
        memory.guard()   # мало памяти - memory.LowMemory, сборку останавливаем сами (run/cli.build_safely)
        if b is None:
            AN.ON_PROGRESS = None
            return
        n = [0]

        def on(f):
            memory.guard()   # и посреди анализа - он идёт минутами (раз в 5 с, остальное - сравнение времени)
            if f == 0.0:
                n[0] = min(parts, n[0] + 1)
            lo = a + (b - a) * (n[0] - 1) / parts
            status(report_frac=round(lo + (b - a) / parts * f, 3))
        AN.ON_PROGRESS = on

    # память и процессор в окне - раз в 5 с, а не только при смене этапа: этап анализа идёт минутами
    from seocrawler import memory
    memory.ON_SAMPLE = status
    memory.ARMED[0] = True   # проверка памяти (memory.guard) - только во время сборки отчёта
    stage("проверяю орфографию", 0.0)
    store = Store(os.path.join(out_dir, "crawl.db"))
    try:  # копия сайта с www, обойденная старой версией: не считать каждую страницу дважды
        from seocrawler import mirror_copy
        mirror_copy.drop_from_store(store)
    except Exception as e:
        print("Убрать копию сайта из расчёта не получилось:", str(e)[:150])
    _fetch_extra(store, out_dir, stage)
    # Сравнение — после загрузки данных Вебмастера и Search Console: раньше оно шло первым, и новая проверка
    # анализировалась дважды (до и после загрузки), а на больших сайтах это минуты. Дальше анализ берётся из кеша.
    cmp_info = None
    prev = compare_with if compare_with is not None else previous_crawl(out_dir)
    if prev:
        try:
            stage("сравниваю с прошлой проверкой", 0.12, 0.62, parts=2)
            cmp_info = run_compare(prev, out_dir)
        except Exception as e:
            print("Сравнение с прошлой проверкой не получилось:", str(e)[:150])
    else:  # прошлую проверку удалили или убрали в архив: старое сравнение с ней уже не про этот отчёт
        for name in ("сравнение.html", "сравнение.csv"):
            try:
                os.remove(os.path.join(out_dir, name))
            except OSError:
                pass
    print("\nСобираю отчёт: ищу проблемы по всему сайту...")
    stage("ищу проблемы по всему сайту", 0.62 if cmp_info else 0.12, 0.62)
    issues, pages, summary = cached_analyze(store)
    summary["compare"] = cmp_info
    summary["buy_clicks"] = store.get_meta("buy_clicks", None)
    summary["consent_forms"] = store.get_meta("consent_forms", None)
    try:  # страна, на которую работает сайт: домен, телефоны, валюта, язык (seocrawler/country.py)
        from seocrawler import country
        summary["country"] = country.detect(store.db, store.get_meta("start", ""), store.get_meta("site_tech", None))
    except Exception as e:
        summary["country"] = None
        print("Страну сайта определить не удалось:", str(e)[:150])
    store.set_meta("compare", cmp_info)  # для окна и сообщения в Telegram: что исправлено и что сломалось
    store.set_meta("summary", dict({k: summary[k] for k in ("health", "pages", "crit", "warn", "note", "queue_left")},
                                   unchecked=summary.get("unchecked", False), country=summary.get("country"),
                                   hv=HEALTH_VERSION))
    store.commit()
    if cmp_info:
        try:  # здоровье по всем проверкам этого сайта — график в отчёте
            summary["history"] = CMP.history(out_dir)
        except Exception as e:
            print("История проверок не собрана:", str(e)[:150])
    if os.environ.get("CLAYLER_NO_PROBLEM_SHOTS") != "1" or store.get_meta("problem_shots"):
        try:  # несколько страниц с обведённой красным ошибкой — для отчёта клиенту
            from seocrawler import problem_shots
            stage("снимаю страницы с обведённой ошибкой", 0.62)
            summary["problem_shots"] = problem_shots.ensure(store, issues, out_dir)
        except Exception as e:
            print("Снимки с обведённой ошибкой не сделаны:", str(e)[:150])
    from seocrawler.audit import REPORT_META
    meta = {k: store.get_meta(k, "") for k in REPORT_META}
    try:  # что не проверено и почему: фильтры, лимит, robots.txt, вход, ошибки, страницы из поиска
        from seocrawler import coverage
        summary["coverage"] = coverage.collect(store, summary)
    except Exception as e:
        summary["coverage"] = None
        print("«Что не проверено и почему» не собрано:", str(e)[:150])
    stage("записываю таблицы", 0.62)
    export_all(store, issues, pages, out_dir)
    from seocrawler import suggest_out
    suggest_out.write_csvs(summary, out_dir)  # заголовки.csv, перелинковка.csv
    try:  # готовые robots.txt, sitemap.xml, редиректы, title — в «для клиента/файлы для разработчика»
        from seocrawler import fix_files
        stage("готовлю файлы для разработчика", 0.64)
        summary["fix_files"] = fix_files.write(store, issues, summary, out_dir)
    except Exception as e:
        summary["fix_files"] = []
        print("Файлы для разработчика не собраны:", str(e)[:150])
    try:  # смета и план работ для клиента: что сделать, кто, сколько часов (и денег, если указана ставка)
        from seocrawler import estimate
        stage("считаю смету и план работ", 0.65)
        summary["works"] = estimate.write(out_dir, meta, issues, pdf=os.environ.get("CLAYLER_NO_PDF") != "1")
    except Exception as e:
        summary["works"] = []
        print("Смета не собрана:", str(e)[:150])
    try:  # семантика, если её собирали: по каким запросам сайт может быть в поиске и что для этого сделать
        from seocrawler.semantics import client as sem_client
        from seocrawler import lost_clicks
        lc = summary.get("lost_clicks") or {}
        summary["semantics"] = sem_client.summary(out_dir, [lost_clicks.qkey(r["q"]) for r in lc.get("queries") or []])
        lost_clicks.bind_semantics(lc, (summary["semantics"] or {}).pop("bind", None))
    except Exception as e:
        summary["semantics"] = None
        print("Семантика в отчёт не попала:", str(e)[:150])
    if os.environ.get("CLAYLER_NO_PDF") != "1":  # картинка паутины с цифрой здоровья: обложка для Авито и Kwork
        try:
            from seocrawler import web_cover
            stage("рисую картинку паутины", 0.655)
            err = web_cover.write_png(out_dir, meta, summary)
            if err:
                print("Картинка паутины не нарисована:", err)
        except Exception as e:
            print("Картинка паутины не нарисована:", str(e)[:150])
    path, xlsx_note, client_dir = _write_reports(out_dir, meta, issues, pages, summary, stage)
    _print_done(summary, path, xlsx_note, client_dir, open_browser, cmp_info)
    if open_browser:
        try:
            webbrowser.open("file:///" + os.path.abspath(path).replace("\\", "/"))
        except Exception:
            pass
    return path


def _fetch_extra(store, out_dir, stage):
    """Дочитать то, чего нет в базе обхода: орфография, движок и хостинг, безопасность, цены и формы, снимки
    телефона, данные Вебмастера, Search Console и Метрики. Каждое - один раз на проверку, сбой не мешает отчёту."""
    if os.environ.get("CLAYLER_NO_SPELLER") != "1":  # автотесты не ходят в интернет
        from seocrawler import speller
        speller.ensure(store)
    if os.environ.get("CLAYLER_NO_SITE_TECH") != "1":  # на чём сделан сайт и где размещён — один раз на проверку
        try:
            from seocrawler import site_tech
            stage("определяю движок и хостинг сайта", 0.03)
            site_tech.ensure(store)
        except Exception as e:
            print("Движок и хостинг не определены -", str(e)[:150])
    if os.environ.get("CLAYLER_NO_SECURITY") != "1":  # заголовки защиты и служебные файлы — один раз на проверку
        try:
            from seocrawler import security
            stage("проверяю безопасность сайта", 0.05)
            security.ensure(store)
        except Exception as e:
            print("Проверка безопасности не сделана -", str(e)[:150])
    if os.environ.get("CLAYLER_NO_SHOP") != "1":  # цены, кнопки, формы — у старых проверок дочитываем выборку страниц
        try:
            from seocrawler import shop
            stage("читаю цены, кнопки и формы на страницах", 0.055)
            shop.ensure(store)
            from seocrawler import buy_clicks
            stage("нажимаю кнопки покупки и заявки (формы не отправляются)", 0.057)
            buy_clicks.ensure(store, out_dir)
        except Exception as e:
            print("«Что мешает покупать»: страницы не дочитаны -", str(e)[:150])
        try:  # согласие на персональные данные в формах и виджетах (в браузере, формы не отправляются)
            from seocrawler import consent_forms
            stage("проверяю согласие на персональные данные в формах и виджетах", 0.0575)
            consent_forms.ensure(store, out_dir)
        except Exception as e:
            print("Согласие в формах не проверено -", str(e)[:150])
    # чего обход не открыл: закрытые цели редиректов, текст страниц из sitemap, нет ли sitemap
    from seocrawler import reread
    for text, frac, step in (("смотрю, куда ведут редиректы на закрытые адреса", 0.0577, reread.ensure_redirect_ends),
                             ("дочитываю страницы из sitemap без заголовка", 0.0578, reread.ensure_sitemap_blocks),
                             ("проверяю, есть ли на сайте sitemap", 0.0578, reread.ensure_sitemap_absent)):
        try:
            stage(text, frac)
            step(store)
        except Exception as e:   # дополнение, как соседние шаги: отчёт важнее, причина остаётся в журнале
            print(f"Не получилось ({text}) -", str(e)[:150])
    try:  # снимки телефона - у старых проверок и там, где обход их не сделал
        from seocrawler import mobile_view
        if not store.get_meta("mobile_view", None) or not os.path.isdir(os.path.join(out_dir, mobile_view.DIR)):
            stage("смотрю страницы на телефоне и делаю снимки", 0.058)
        mobile_view.ensure(store, out_dir)
    except Exception as e:
        print("Снимки телефона не сделаны -", str(e)[:150])
    if os.environ.get("CLAYLER_NO_USER_SETTINGS") != "1":  # данные Яндекс Вебмастера, если вход подключён
        # У прошлой проверки (есть проверка этого сайта новее) уже загруженные данные не заменяются сегодняшними:
        # иначе «Обновить отчёт» старой проверки показывал бы поиск и визиты не за её время, а сравнение и отчёт
        # за месяц - одни и те же цифры у старой и новой проверки. Если данных у неё не было - загружаются.
        old = later_crawl(out_dir) is not None
        # оставляем только настоящие данные: загрузка, где были одни ошибки, у старой проверки повторяется
        def keep(key):
            got = store.get_meta(key, None)
            return old and isinstance(got, dict) and any(
                v for k, v in got.items() if k not in NOT_DATA)
        try:
            from seocrawler import webmaster
            if keep("webmaster"):
                print("Яндекс Вебмастер: у прошлой проверки оставлены данные на день её проверки.")
            else:
                stage("загружаю данные Яндекс Вебмастера", 0.06)
                wm = webmaster.fetch(store.get_meta("start", ""))
                if wm:
                    store.set_meta("webmaster", wm)
                    store.commit()
        except Exception as e:
            print("Яндекс Вебмастер: данные не загружены -", str(e)[:150])
        try:  # данные Google Search Console, если вход подключён; проверка индекса — для страниц ближе к главной
            from seocrawler import search_console
            if keep("gsc"):
                print("Search Console: у прошлой проверки оставлены данные на день её проверки.")
            else:
                stage("загружаю данные Google Search Console", 0.08)
                imp = [r[0] for r in store.db.execute(
                    "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE p.status=200 AND p.indexable=1 "
                    "AND u.internal=1 ORDER BY u.depth, p.url LIMIT ?", (search_console.INSPECT,))]
                g = search_console.fetch(store.get_meta("start", ""), imp)
                if g:
                    store.set_meta("gsc", g)
                    store.commit()
        except Exception as e:
            print("Search Console: данные не загружены -", str(e)[:150])
        try:  # Яндекс Метрика — тот же вход через Яндекс
            from seocrawler import metrika
            if keep("metrika"):
                print("Яндекс Метрика: у прошлой проверки оставлены данные на день её проверки.")
            else:
                stage("загружаю данные Яндекс Метрики", 0.10)
                ym = metrika.fetch(store.get_meta("start", ""))
                if ym:
                    store.set_meta("metrika", ym)
                    store.commit()
        except Exception as e:
            print("Яндекс Метрика: данные не загружены -", str(e)[:150])


def _write_reports(out_dir, meta, issues, pages, summary, stage):
    """Все файлы отчёта: отчёт.html, для клиента, аудит (HTML, Word, PDF), экспресс, Excel, папка «для клиента»,
    карточка сайта, «Бренды и прочие». Возвращает (путь к отчёт.html, путь к отчёт.xlsx или "", папка для клиента)."""
    path = os.path.join(out_dir, "отчёт.html")
    stage("собираю отчёт.html", 0.66)
    html_report(path, meta, issues, pages, summary)
    stage("собираю отчёт для клиента", 0.72)
    try:  # тот же отчёт для клиента: один файл, без служебных советов, с вашими контактами
        from seocrawler import client_report
        client_report.write(out_dir, meta, issues, pages, summary)
    except Exception as e:
        print("Отчёт для клиента не собран:", str(e)[:150])
    try:
        from seocrawler.audit import write_audit, write_audit_docx
        stage("собираю аудит и файл Word", 0.76)
        write_audit(os.path.join(out_dir, "аудит.html"), meta, issues, summary)
        write_audit_docx(os.path.join(out_dir, "аудит.docx"), meta, issues, summary)
    except Exception as e:
        print("Не удалось собрать аудит.html:", str(e)[:150])
    try:  # экспресс-аудит на один лист — для потенциального клиента
        from seocrawler import express
        stage("собираю экспресс-аудит", 0.82)
        express.write(os.path.join(out_dir, "экспресс.html"), meta, issues, summary)
        if os.environ.get("CLAYLER_NO_PDF") != "1":
            from seocrawler.pdf import html_to_pdf
            err = html_to_pdf(os.path.join(out_dir, "экспресс.html"), os.path.join(out_dir, "экспресс.pdf"))
            if err:
                print("Экспресс-аудит в PDF не собран:", err)
    except Exception as e:
        print("Экспресс-аудит не собран:", str(e)[:150])
    if os.environ.get("CLAYLER_NO_PDF") != "1":  # PDF для клиента: примеры адресов — в приложении внутри файла
        try:
            from seocrawler.audit import write_audit
            from seocrawler.pdf import html_to_pdf
            stage("собираю аудит в PDF", 0.88)
            tmp = os.path.join(out_dir, ".аудит_для_pdf.html")
            write_audit(tmp, meta, issues, summary, for_pdf=True)
            err = html_to_pdf(tmp, os.path.join(out_dir, "аудит.pdf"))
            os.remove(tmp)
            if err:
                print("Аудит в PDF не собран:", err)
        except Exception as e:
            print("Аудит в PDF не собран:", str(e)[:150])
    xlsx_note = ""
    if xlsx_report.available():
        try:
            stage("собираю отчёт.xlsx", 0.94)
            xlsx_report.write_xlsx(os.path.join(out_dir, "отчёт.xlsx"), meta, issues, pages, summary, PAGE_EXPORT)
            xlsx_note = os.path.join(out_dir, "отчёт.xlsx")
        except PermissionError:
            print("Не удалось записать отчёт.xlsx - наверное, он открыт в Excel. Закройте его и соберите отчёт заново.")
        except Exception as e:
            print("Не удалось собрать отчёт.xlsx:", str(e)[:150])
    else:
        print("Excel-файл не собран: нет модуля openpyxl (его ставит «Запустить аудит.bat»).")
    client_dir = ""
    try:  # три файла для отправки клиенту — отдельной папкой с понятными именами
        from seocrawler import client_folder
        client_dir, busy = client_folder.fill(out_dir, meta.get("start", ""), check=True)
        for name in busy:
            print(f"Не удалось обновить «{name}» в папке «{client_folder.DIR}» - наверное, он открыт. "
                  "Закройте его и нажмите «Обновить отчёт».")
    except Exception as e:
        print("Папка для клиента не собрана:", str(e)[:150])
    try:  # карточка сайта: всё главное на одной странице - последней, чтобы видеть все готовые файлы
        from seocrawler import site_card
        site_card.write(out_dir, meta, issues, summary)
    except Exception as e:
        print("Карточка сайта не собрана:", str(e)[:150])
    try:  # общая таблица «Бренды и прочие»: бренды и свойства товаров с сайта - в лист его ниши
        from seocrawler import catalog
        xl = catalog.update(out_dir)
        if xl:
            print(f"Бренды и свойства сайта добавлены в общую таблицу: {xl}")
    except Exception as e:
        print("Таблица «Бренды и прочие» не обновлена:", str(e)[:150])
    return path, xlsx_note, client_dir


def _print_done(summary, path, xlsx_note, client_dir, open_browser, cmp_info):
    """Итог в чёрное окно: здоровье, сколько проблем, где файлы, что сравнилось, что не проверено."""
    print("\n" + "=" * 60)
    print(f"  ГОТОВО. Здоровье сайта: {summary['health']}%")
    print(f"  (доля страниц без критичных проблем и предупреждений)")
    print("=" * 60)
    print(f"  Проверено страниц сайта: {summary['pages']}")
    print(f"  Найдено видов проблем: критичных - {summary['crit']}, "
          f"предупреждений - {summary['warn']}, замечаний - {summary['note']}")
    print(f"\n  Отчёт: {path}")
    if xlsx_note:
        print(f"  Для Excel: {xlsx_note}")
    if client_dir and os.path.isdir(client_dir):
        print(f"  Файлы для клиента: {client_dir}")
    if open_browser:
        print("  Сейчас он откроется в браузере. Начните с блока «С чего начать».")
    if cmp_info:
        print(f"\n  По сравнению с проверкой {cmp_info['old_finished']}: исправлено проблем - {cmp_info['fixed']}, "
              f"новых - {cmp_info['added']}. Подробно: сравнение.html")
    if summary["queue_left"]:
        n = summary["queue_left"]
        print(f"\n  Внимание: сайт проверен не полностью - ещё {n} "
              f"{_plural(n, 'страница ждёт', 'страницы ждут', 'страниц ждут')} проверки.")
        print("  Чтобы продолжить: запустите аудит снова, введите лимит побольше")
        print("  и на вопрос «Продолжить прошлую проверку?» ответьте «д».")
