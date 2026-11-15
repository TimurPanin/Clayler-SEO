"""Запросы из файлов для семантики: выгрузки, которые человек скачал сам (бесплатно) и добавил на странице «Семантика».
- Частотность: Вордстат (новый и старый вид), Key Collector, любые «запрос + число» - спрос в месяц.
- Статистика сайта: выгрузки Вебмастера («Запросы») и Search Console - показы, клики, позиция, страница.
Хранится на сайт в папке «решения семантики» (рядом с решениями), поэтому не теряется при новой проверке.
При сборе семантики запросы из файлов добавляются к подсказкам (источник «из файла»), частотность - в поле freq."""
import csv
import io
import os
import re
import time

from . import decisions
from .. import jsonfile

MAX_ROWS = 50000
MAX_LEN = 120
# колонки по заголовку (в нижнем регистре, ищется подстрока); порядок важен: «частота показов» - частотность
COLS = [("q", ("запрос", "фраза", "ключ", "query", "keyword", "запросы", "keys")),
        ("freq", ("частот", "число запросов", "wordstat", "[ws]", "[yw]", "volume", "спрос", "frequency", "базов", "ws")),
        ("clicks", ("клик", "click", "переход")),
        ("shows", ("показ", "impression")),
        ("pos", ("позиц", "position", "место")),
        ("page", ("url", "страниц", "page", "адрес", "landing"))]
SKIP = ("ctr", "доля", "%")


def _path(host):
    return decisions.site_file(host, " - запросы из файлов")


def load(host):
    d = jsonfile.load(_path(host))
    d.setdefault("files", [])
    return d


def _save(host, d):
    decisions.save_site_file(host, " - запросы из файлов", d, indent=1)


def _num(v):
    """«1 234», «1,234», «12,5», 1234.0 → число; не число - None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("\xa0", "").replace(" ", "").replace("%", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _query(v):
    """Запрос без операторов Вордстата («+», «!», кавычки, скобки), в нижнем регистре."""
    s = str(v or "").strip().lower().replace("ё", "е")
    if re.match(r"(https?:|www\.)", s):
        return ""
    s = re.sub(r"[+!\"«»\[\]()]", " ", s)
    s = re.sub(r"\s-\S+", " ", s)             # минус-слова Вордстата
    s = re.sub(r"\s+", " ", s).strip()
    if not s or len(s) > MAX_LEN or not re.search(r"[a-zа-я]", s):
        return ""
    return s


def _table(name, raw):
    """Файл → список таблиц (список строк-списков)."""
    ext = os.path.splitext(name.lower())[1]
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        out = [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
        wb.close()
        return out
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("не получилось прочитать текст файла")
    lines = [x for x in text.splitlines() if x.strip()]
    sample = "\n".join(lines[:20])
    delim = max(("\t", ";", ","), key=lambda d: sum(x.count(d) for x in lines[:20]))
    if not any(delim in x for x in lines[:20]):       # просто список запросов, по одному в строке
        return [[[x] for x in lines]]
    return [list(csv.reader(io.StringIO(text), delimiter=delim))] if sample else [[]]


def _header(rows):
    """Строка заголовка (в первых 15: та, где узнано больше колонок) и номера колонок."""
    best = (None, None)
    for i, r in enumerate(rows[:15]):
        cells = [str(c or "").strip().lower() for c in r]
        cols = {}
        for j, c in enumerate(cells):
            if not c or any(s in c for s in SKIP):
                continue
            for key, words in COLS:
                if key not in cols and any(w in c for w in words):
                    cols[key] = j
                    break
        if "q" in cols:
            _freq_cols(cells, cols)
        if "q" in cols and (best[1] is None or len(cols) > len(best[1])):
            best = (i, cols)
    return best


def _freq_kind(c):
    """Какая частотность Вордстата в столбце: «!» - точная (форма слова), кавычки - фразовая, иначе базовая (с хвостами)."""
    if "!" in c or "точн" in c:
        return "exact"
    if '"' in c or "«" in c or "кавыч" in c or "фразов" in c:
        return "phrase"
    return "base"


def _freq_cols(cells, cols):
    """Key Collector, Арсёнкин (arsenkin.ru: «WS», «"WS"», «"!WS"»), Букварикс дают по нескольку частотностей.
    Раньше бралась первая - обычно базовая, с хвостами, в разы больше. Программа везде считает частоту фразы в
    кавычках (как Вордстат через Директ), поэтому: фразовая, если есть, потом точная, потом базовая (freq_b)."""
    found = {}
    for j, c in enumerate(cells):
        if not c or any(s in c for s in SKIP) or j in (cols.get("q"), cols.get("page")):
            continue
        if any(w in c for w in COLS[1][1]) and not any(w in c for w in ("клик", "click", "показ", "позиц")):
            k = _freq_kind(c)
            if k == "base" and "base" in found and "phrase" not in found:
                k = "phrase"   # CSV снял кавычки: «"Частотность" [YW]» читается как «Частотность [YW]» - второй такой
            found.setdefault(k, j)
    if not found:
        return
    best = found.get("phrase", found.get("exact", found.get("base")))
    cols["freq"] = best
    name = {"phrase": "в кавычках", "exact": "точная", "base": "базовая, с хвостами"}
    cols["_freq_col"] = name[next(k for k, j in found.items() if j == best)] + f", столбец «{cells[best]}»"
    if "base" in found and found["base"] != best:
        cols["freq_b"] = found["base"]


def parse(name, raw):
    """(строки {q, freq, shows, clicks, pos, page}, вид: «freq» - частотность, «stats» - статистика сайта, «list»)."""
    best = None
    tables = [t for t in _table(name, raw) if t]
    heads = [_header(t) for t in tables]
    with_head = any(c is not None for _, c in heads)
    for rows, (i, cols) in zip(tables, heads):
        if cols is None and with_head:   # в файле есть лист с заголовком «Запрос» - остальные листы не про запросы
            continue
        if cols is None:                 # без заголовка: запрос в первой колонке, число - во второй
            i, cols = -1, {"q": 0}
            if any(len(r) > 1 and _num(r[1]) is not None for r in rows[:20]):
                cols["freq"] = 1
        stats = "pos" in cols or "clicks" in cols
        if not stats and "shows" in cols and "freq" not in cols:   # Вордстат: «Показов в месяц» - частотность
            cols["freq"] = cols.pop("shows")
        out = {}
        for r in rows[i + 1:]:
            if len(out) >= MAX_ROWS:
                break
            get = lambda k: r[cols[k]] if k in cols and cols[k] < len(r) else None  # noqa: E731
            q = _query(get("q"))
            if not q:
                continue
            row = {"q": q}
            for k in ("freq", "freq_b", "shows", "clicks", "pos"):
                v = _num(get(k))
                if v is not None:
                    row[k] = round(v, 1) if k == "pos" else int(v)
            p = str(get("page") or "").strip()
            if p.startswith(("http", "/")):   # путь «/kotly/» - адрес этого сайта (rows), раньше терялся (24.10.2026)
                row["page"] = p
            old = out.get(q)
            if not old or (row.get("freq") or row.get("shows") or 0) > (old.get("freq") or old.get("shows") or 0):
                out[q] = row
        kind = "stats" if stats else ("freq" if "freq" in cols else "list")
        if out and (not best or len(out) > len(best[0])):
            best = (list(out.values()), kind, cols.get("_freq_col") or "")
    if not best:
        raise ValueError("в файле не нашлось колонки с запросами")
    return best[0], best[1]


def freq_column(name, raw):
    """Из какого столбца взята частотность (для подписи у файла)."""
    try:
        tables = [t for t in _table(name, raw) if t]
    except Exception:
        return ""
    for rows in tables:
        i, cols = _header(rows)
        if cols and cols.get("_freq_col"):
            return cols["_freq_col"]
    return ""


KIND = {"freq": "частотность", "stats": "показы и места сайта", "list": "список запросов"}


def add_file(host, name, raw):
    rows, kind = parse(name, raw)
    def put(d):
        d["files"] = [f for f in d["files"] if f["name"] != name]
        d["files"].append({"name": name, "kind": kind, "n": len(rows), "at": time.strftime("%d.%m.%Y %H:%M"), "rows": rows})
    col = freq_column(name, raw) if kind == "freq" else ""
    d = load(host)
    put(d)
    if col:
        d["files"][-1]["col"] = col
    _save(host, d)
    return {"name": name, "kind": kind, "label": KIND[kind] + (f" ({col})" if col else ""), "n": len(rows)}


def remove_file(host, name):
    d = load(host)
    d["files"] = [f for f in d["files"] if f["name"] != name]
    _save(host, d)


def listing(host):
    return [{"name": f["name"], "kind": f["kind"], "label": KIND.get(f["kind"], "") + (f" ({f['col']})" if f.get("col") else ""),
             "n": f["n"], "at": f["at"]}
            for f in load(host)["files"]]


def rows(host):
    """Все запросы из файлов сайта: {запрос: {freq, shows, clicks, pos, page}} - по каждому полю наибольшее
    (позиция - лучшая), страница - из файла с самыми большими показами."""
    out = {}
    for f in load(host)["files"]:
        for r in f["rows"]:
            o = out.setdefault(r["q"], {})
            for k in ("freq", "freq_b", "shows", "clicks"):
                if r.get(k) is not None:
                    o[k] = max(o.get(k) or 0, r[k])
            if r.get("pos"):
                o["pos"] = min(o.get("pos") or 1e9, r["pos"])
            if r.get("page") and (r.get("shows") or 0) >= o.get("_ps", -1):
                p = r["page"]   # в выгрузке бывает только путь «/kotly/» - тогда адрес этого сайта
                o["page"], o["_ps"] = (f"https://{host}{p}" if p.startswith("/") else p), r.get("shows") or 0
    for o in out.values():
        o.pop("_ps", None)
    return out
