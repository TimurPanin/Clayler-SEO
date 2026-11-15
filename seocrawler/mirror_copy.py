"""Копия сайта на соседнем адресе (с www или без), которая открывается сама, без редиректа на главный.
22.10.2026: на lancentre.ru одна ссылка с главной вела на www.lancentre.ru, и программа обошла копию целиком -
18 234 страницы вместо 9 115, все числа в отчёте вдвое, а «одинаковый title» - почти сплошь пары «страница и
её копия на www». Теперь страницы копии не открываются (обход), а в готовых проверках убираются из расчёта
при «Обновить отчёт»: строки переносятся в таблицы mirror_bak_*, ничего не стирается насовсем.
Сама копия - проблема «Вариант адреса сайта открывается без редиректа» (analyze/checks/mirrors.py), ссылки на
неё - «Ссылки на копию сайта»."""
from urllib.parse import urlsplit

SKIP = "Копия сайта: открывается без редиректа, страницы копии не проверялись"
TABLES = (("images", "page"), ("resources", "page"), ("img_display", "page"), ("param_links", "src"))


def twin_host(mirrors):
    """Хост копии (www.site.ru для site.ru и наоборот), если она открылась сама с кодом 200. Иначе ''."""
    if not mirrors or not mirrors.get("main"):
        return ""
    main = urlsplit(mirrors["main"])
    host = (main.hostname or "").lower()
    twin = host[4:] if host.startswith("www.") else "www." + host
    for m in mirrors.get("variants") or []:
        v = urlsplit(m.get("variant") or "")
        ch = m.get("chain") or []
        if (v.hostname or "").lower() == twin and v.scheme == main.scheme and ch and ch[0][1] == 200:
            return twin
    return ""


def is_twin(url, twin):
    return bool(twin) and (urlsplit(url).hostname or "").lower() == twin


def drop_from_store(store, log=print):
    """Готовая проверка, где копия уже обойдена: страницы копии - в «не проверялись» (как при новом обходе),
    их данные - в таблицы mirror_bak_*. Повторный вызов ничего не делает."""
    db = store.db
    twin = twin_host(store.get_meta("mirrors", None))
    if not twin:
        return 0
    like = (f"http://{twin}/%", f"https://{twin}/%", f"http://{twin}", f"https://{twin}")
    host_sql = "(url LIKE ? OR url LIKE ? OR url = ? OR url = ?)"
    urls = [r[0] for r in db.execute(f"SELECT url FROM urls WHERE kind='page' AND {host_sql} AND "
                                     "(state<>'skipped' OR skip_reason IS NOT ?)", (*like, SKIP))]
    if not urls:
        return 0
    db.execute("CREATE TEMP TABLE IF NOT EXISTS mc_urls (url TEXT PRIMARY KEY)")
    db.execute("DELETE FROM mc_urls")
    db.executemany("INSERT OR IGNORE INTO mc_urls VALUES (?)", [(u,) for u in urls])
    db.execute("CREATE TABLE IF NOT EXISTS mirror_bak_pages AS SELECT * FROM pages WHERE 0")
    db.execute("INSERT INTO mirror_bak_pages SELECT * FROM pages WHERE url IN (SELECT url FROM mc_urls)")
    db.execute("DELETE FROM pages WHERE url IN (SELECT url FROM mc_urls)")
    for t, col in TABLES:
        db.execute(f"CREATE TABLE IF NOT EXISTS mirror_bak_{t} AS SELECT * FROM {t} WHERE 0")
        db.execute(f"INSERT INTO mirror_bak_{t} SELECT * FROM {t} WHERE {col} IN (SELECT url FROM mc_urls)")
        db.execute(f"DELETE FROM {t} WHERE {col} IN (SELECT url FROM mc_urls)")
    if store.legacy_links:
        db.execute("CREATE TABLE IF NOT EXISTS mirror_bak_links AS SELECT * FROM links WHERE 0")
        db.execute("INSERT INTO mirror_bak_links SELECT * FROM links WHERE src IN (SELECT url FROM mc_urls)")
        db.execute("DELETE FROM links WHERE src IN (SELECT url FROM mc_urls)")
    else:
        ids = "SELECT id FROM strs WHERE s IN (SELECT url FROM mc_urls)"
        db.execute("CREATE TABLE IF NOT EXISTS mirror_bak_link_rows AS SELECT * FROM link_rows WHERE 0")
        db.execute(f"INSERT INTO mirror_bak_link_rows SELECT * FROM link_rows WHERE src IN ({ids})")
        db.execute(f"DELETE FROM link_rows WHERE src IN ({ids})")
    db.execute("UPDATE urls SET state='skipped', skip_reason=? WHERE kind='page' AND url IN (SELECT url FROM mc_urls)",
               (SKIP,))
    old = store.get_meta("mirror_dropped", None) or {}
    store.set_meta("mirror_dropped", {"host": twin, "pages": old.get("pages", 0) + len(urls)})
    store.commit()
    log(f"Копия сайта {twin} открывается без редиректа: её страницы ({len(urls)}) убраны из расчёта, "
        "чтобы не считать каждую страницу дважды.")
    return len(urls)
