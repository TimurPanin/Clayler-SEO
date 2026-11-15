"""Сбор семантики из готовой проверки (crawl.py --semantics): файлы семантики, ТЗ, дерево сайта, Excel."""
import os
import webbrowser

from seocrawler import xlsx_report


def run_semantics(folder, competitors, region="", open_file=False, deep=False, rival_hosts=(), stop_file="", light=False):
    from seocrawler import semantics
    from seocrawler.semantics import export as SX
    competitors = [c for c in competitors if os.path.exists(os.path.join(c, "crawl.db"))]
    try:
        sem = semantics.build(folder, competitors, log=print, region=region or None, deep=deep, rival_hosts=rival_hosts,
                              stop=(lambda: os.path.exists(stop_file)) if stop_file else None, light=light)
    except semantics.Stopped:
        print("Сбор семантики остановлен. Прежняя семантика сайта не тронута.")
        return None
    SX.write_json(os.path.join(folder, SX.JSON_NAME), sem)
    try:  # ТЗ копирайтеру на все новые страницы и страницы с замечаниями — одним файлом Word
        from seocrawler.semantics import brief_docx
        tz = brief_docx.write(folder, SX.load(folder))
        if tz:
            print("ТЗ копирайтеру: " + tz)
    except Exception as e:
        print("ТЗ копирайтеру не собрано:", str(e)[:150])
    path = os.path.join(folder, SX.XLSX_NAME)
    from seocrawler.semantics import decisions, newsite, plan, tree
    data = plan.enrich(decisions.apply(SX.load(folder), folder), folder)
    try:   # пары «похоже на синонимы» - сразу в «Словарь → Ждут подтверждения» (там их не надо ждать)
        from seocrawler.semantics import synonyms
        n = synonyms.save_pairs(folder, data)
        if n:
            print(f"Пар «похоже на синонимы»: {n} - ждут в «Словарь → Ждут подтверждения».")
    except Exception as e:
        print("Пары синонимов не найдены:", str(e)[:150])
    if sem.get("new_site"):   # новый сайт: структура будущего сайта страницей для клиента
        structure = newsite.structure(data)
        page = newsite.write_client(folder, data)
        if page:
            print(f"Структура сайта: страниц {structure['pages']}, статей в блог {len(structure['blog'])} - {page}")
    t = None
    try:   # дерево сайта и карта признаков: страница и первый лист Excel
        page, t = tree.write(folder, data)
        if page:
            print(f"Дерево сайта: карт признаков {t['maps']} - {page}")
    except Exception as e:
        print("Дерево сайта не собрано:", str(e)[:150])
    if xlsx_report.available():
        from seocrawler.semantics.xlsx_dec import brands_of
        SX.write_xlsx(path, sem, tree=t, brands=brands_of(data, folder))
    else:
        print("Excel-файл не собран: нет модуля openpyxl (его ставит «Clayler SEO.bat»).")
    print(f"Семантика готова: {path}")
    if open_file:
        os.startfile(path) if hasattr(os, "startfile") else webbrowser.open("file:///" + path)
    return path
