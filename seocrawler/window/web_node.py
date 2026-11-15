"""Узел живой паутины в окне (/api/web_node): какая страница стоит за местом в паутине и её главная проблема.

Паутина декоративная: окно переводит узел в номер по ходу проверки (n-я готовая страница сайта), а красный
или жёлтый участок нити - в ближайший к этому месту адрес с ошибкой или переадресацией. Порядок - как адреса
записывались в базу (pages.rowid). Пока идёт проверка, проблема - по ответу страницы; когда отчёт готов -
самая важная проблема страницы из анализа отчёта (.анализ.pickle)."""
import os
import pickle
import sqlite3
import threading

from . import REPORTS
from ..fmt import plural as _plural

SEV = {"critical": (0, "crit"), "warning": (1, "warn"), "notice": (2, "note")}
_index = {}  # папка -> (время файла анализа, {адрес: [(важность, название проблемы)]})
_lock = threading.Lock()


def _db(folder):
    path = os.path.join(folder, "crawl.db")
    if not os.path.exists(path):
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def _page_at(db, n):
    """n-я (с 0) готовая страница сайта по порядку проверки; дальше последней - последняя."""
    q = ("SELECT p.rowid AS rid, p.* FROM pages p JOIN urls u ON u.url = p.url WHERE u.kind = 'page' AND u.internal = 1 "
         "ORDER BY p.rowid {} LIMIT 1 OFFSET ?")
    return db.execute(q.format(""), (max(0, n),)).fetchone() or db.execute(q.format("DESC"), (0,)).fetchone()


def _near(db, rid, bad):
    """Адрес с ошибкой (bad) или переадресацией, ближайший по порядку проверки к записи rid."""
    cond = "(status IS NULL OR status = 0 OR status >= 400)" if bad else "(status >= 300 AND status < 400)"
    a = db.execute(f"SELECT rowid AS rid, * FROM pages WHERE {cond} AND rowid <= ? ORDER BY rowid DESC LIMIT 1", (rid,)).fetchone()
    b = db.execute(f"SELECT rowid AS rid, * FROM pages WHERE {cond} AND rowid > ? ORDER BY rowid LIMIT 1", (rid,)).fetchone()
    if a is None or (b is not None and b["rid"] - rid < rid - a["rid"]):
        return b
    return a


def _quick(row):
    """Главная проблема по ответу страницы - пока отчёта нет."""
    st, err = row["status"], row["error"]
    if not st:
        return "crit", "Не открывается: " + (err or "сайт не ответил")
    if st >= 400:
        return "crit", f"Не открывается: ответ {st}" + (f" ({row['reason']})" if row["reason"] else "")
    if st >= 300:
        loc = row["location"] or ""
        return "warn", f"Переадресация {st}" + (f" на {loc}" if loc else "")
    keys = row.keys()
    if "indexable" in keys and row["indexable"] == 0 and (row["content_type"] or "").startswith("text/html"):
        return "warn", "Закрыта от поиска" + (f": {row['indexability']}" if row["indexability"] else "")
    if (row["content_type"] or "").startswith("text/html"):
        if not (row["title"] or "").strip():
            return "warn", "Нет заголовка title"
        if not (row["h1"] or "").strip():
            return "note", "Нет заголовка H1"
    if row["elapsed"] and row["elapsed"] > 3:
        return "note", f"Медленно отвечает: {row['elapsed']:.1f} с".replace(".", ",")
    return "ok", "По ответу страницы проблем не видно, полная проверка - в отчёте"


def _issues(folder):
    """Проблемы страниц из анализа готового отчёта: {адрес: [(важность, название, ключ)]}. Кешируется по времени файла."""
    path = os.path.join(folder, ".анализ.pickle")
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    with _lock:
        have = _index.get(folder)
        if have and have[0] == mt:
            return have[1]
    try:
        with open(path, "rb") as f:
            issues = pickle.load(f)["issues"]
    except Exception:
        return None
    idx = {}
    for i in issues:
        rank = SEV.get(i.severity, (3, "note"))[0]
        pc = i.page_col if isinstance(i.page_col, int) else -1
        for r in i.rows or []:
            cells = r if isinstance(r, (list, tuple)) else [r]
            for j, c in enumerate(cells):  # адрес страницы и, например, битая картинка или ссылка на ней
                if isinstance(c, str) and c.startswith("http"):
                    have = idx.setdefault(c, {})
                    # своя проблема страницы (адрес в колонке страницы) важнее, чем «на неё ссылаются»
                    k = (j != pc, rank)
                    if i.key not in have or k < have[i.key][0]:
                        have[i.key] = (k, i.title)
    for c, have in idx.items():
        idx[c] = [(k[1], t, key) for key, (k, t) in sorted(have.items(), key=lambda x: x[1][0])]
    with _lock:
        _index.clear()  # держим в памяти только одну проверку
        _index[folder] = (mt, idx)
    return idx


def lookup(name, kind, n, busy=()):
    folder = os.path.join(REPORTS, os.path.basename(name or ""))
    db = _db(folder)
    if db is None:
        return {"note": "Проверка ещё не началась"}
    try:
        page = _page_at(db, n)
        if page is None:
            return {"note": "Страница ещё не проверена"}
        row = page if kind == "page" else (_near(db, page["rid"], kind == "err") or page)
        where = ""
        if kind != "page" and row["url"] != page["url"]:
            src = db.execute("SELECT kind, internal, found_on FROM urls WHERE url = ?", (row["url"],)).fetchone()
            if src and src["found_on"] and not (src["kind"] == "page" and src["internal"]):
                what = "Картинка или файл" if src["kind"] == "resource" else "Ссылка на другой сайт" if not src["internal"] else "Адрес"
                where = f"{what} со страницы {src['found_on']}"
        sev, problem = _quick(row)
        keys = []
    finally:
        db.close()
    running = os.path.basename(folder) in set(busy)
    report = os.path.exists(os.path.join(folder, "отчёт.html")) and not running
    if report:
        found = (_issues(folder) or {}).get(row["url"])
        if found:
            rank, title, _k = found[0]
            sev = {0: "crit", 1: "warn"}.get(rank, "note")
            more = len(found) - 1
            problem = title + (f" (и ещё {more} {_plural(more, 'проблема', 'проблемы', 'проблем')})" if more else "")
            keys = [k for _r, _t, k in found]
        elif sev == "ok":
            problem = "Проблем у этой страницы не найдено"
    return {"url": row["url"], "sev": sev, "problem": problem, "where": where, "issues": keys,
            "report": f"/r/{os.path.basename(folder)}/отчёт.html" if report else ""}
