"""Поиск своего текста по готовой проверке — как Custom Search у Screaming Frog, но без повторного обхода.
Ищет в тексте страниц (то, что видит посетитель), в title/description/H1 или в адресах. Можно искать страницы,
где фразы НЕТ (например, нет нового телефона), и страницы без счётчика Метрики или Google Analytics."""
import csv
import json
import os
import re
import sqlite3
import zlib

MAX_ROWS = 1000
WHERE = {"text": "в тексте страницы", "meta": "в title, description и H1", "url": "в адресе страницы",
         "all": "везде"}
COUNTERS = {"no_ym": ("ym", "Яндекс Метрики"), "no_ga": ("ga", "Google Analytics"), "no_gtm": ("gtm", "Google Tag Manager")}


def _norm(s):
    return (s or "").lower().replace("ё", "е")


def _phrases(query, regex):
    out = []
    for line in (query or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if regex:
            try:
                out.append(re.compile(line, re.I))
            except re.error as e:
                raise ValueError(f"Ошибка в выражении «{line}»: {e}")
        else:
            out.append(re.compile(re.escape(_norm(" ".join(line.split()))).replace(r"\ ", r"\s+")))
    return out


def _snippet(text, m, width=70):
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if a else "") + text[a:m.start()] + "[" + text[m.start():m.end()] + "]" + text[m.end():b] + ("…" if b < len(text) else "")


def search(folder, query="", mode="has", where="text", regex=False):
    """mode: has — страницы, где фраза есть; none — где нет ни одной из фраз; no_ym / no_ga / no_gtm — без счётчика.
    Возвращает {"pages": всего проверено страниц, "found": сколько нашлось, "rows": [...], "csv": имя файла}."""
    db_path = os.path.join(folder, "crawl.db")
    if not os.path.exists(db_path):
        raise ValueError("Нет такой проверки.")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in db.execute("PRAGMA table_info(pages)")}
        if mode in COUNTERS:
            if "counters" not in cols or not db.execute("SELECT 1 FROM pages WHERE counters IS NOT NULL LIMIT 1").fetchone():
                raise ValueError("В этой проверке счётчики ещё не собирались: это умеет версия программы 7.1 и новее. "
                                 "Проверьте сайт заново.")
        elif not (query or "").strip():
            raise ValueError("Напишите, что искать.")
        if mode not in COUNTERS and where in ("text", "all") and "blocks" not in cols:
            raise ValueError("В этой проверке не сохранён текст страниц (старая версия программы). Проверьте сайт заново.")
        phrases = [] if mode in COUNTERS else _phrases(query, regex)
        sel = ["p.url", "p.title", "p.description", "p.h1"] + [f"p.{c}" if c in cols else "NULL"
                                                                for c in ("blocks", "counters")]
        q = (f"SELECT {', '.join(sel)} FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' "
             "AND p.status=200 AND p.content_type IN ('text/html','application/xhtml+xml') ORDER BY u.depth, p.url")
        total, rows = 0, []
        for url, title, desc, h1, blocks, ctr in db.execute(q):
            total += 1
            if mode in COUNTERS:
                have = json.loads(ctr) if ctr else None
                if have is None or have.get(COUNTERS[mode][0]):
                    continue
                other = ", ".join(f"{k}: {' '.join(v)}" for k, v in have.items())
                rows.append({"url": url, "title": title or "", "where": "", "n": 0,
                             "snippet": "есть другие: " + other if other else "счётчиков нет совсем"})
                continue
            fields = []
            if where in ("text", "all") and blocks:
                try:
                    fields.append(("текст", zlib.decompress(blocks).decode("utf-8").replace("\n", " · ")))
                except Exception:
                    pass
            if where in ("meta", "all"):
                fields += [("title", title or ""), ("description", desc or ""), ("H1", h1 or "")]
            if where in ("url", "all"):
                fields.append(("адрес", url))
            hits = []
            for name, text in fields:
                low = text if regex else _norm(text)
                for rx in phrases:
                    ms = list(rx.finditer(low))
                    if ms:
                        hits.append((name, len(ms), _snippet(text, ms[0])))
            if mode == "has" and hits:
                rows.append({"url": url, "title": title or "", "where": ", ".join(dict.fromkeys(h[0] for h in hits)),
                             "snippet": hits[0][2], "n": sum(h[1] for h in hits)})
            elif mode == "none" and not hits:
                rows.append({"url": url, "title": title or "", "where": "", "snippet": "", "n": 0})
    finally:
        db.close()
    name = "поиск.csv"
    try:
        with open(os.path.join(folder, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Адрес", "Title", "Где нашлось", "Сколько раз", "Фрагмент"])
            for r in rows:  # в файле — все найденные, на экране — первые MAX_ROWS
                w.writerow([r["url"], r["title"], r["where"], r["n"] or "", r["snippet"]])
    except OSError:
        name = ""
    return {"pages": total, "found": len(rows), "rows": rows[:MAX_ROWS], "csv": name, "limited": len(rows) > MAX_ROWS}
