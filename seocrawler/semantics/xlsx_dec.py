"""«Скачать Excel» с учётом решений человека: «семантика с решениями.xlsx» в папке проверки. Тот же вид, что
семантика.xlsx при сборе (export.write_xlsx), но группы — после решений (разделённые, с выбранной страницей),
убранные группы — во вкладке «Отсеяно», у мешающих страниц — решение и задача разработчику.
В семантика.json нет источников запросов и полных причин отсева, поэтому они берутся из семантика.xlsx сбора."""
import os

from . import export as SX
from .decisions import JUNK_REASON

FILE = "семантика с решениями.xlsx"
PRIO = {v: k for k, v in SX.PRIO_KIND.items()}


def _from_built(folder):
    """Из семантика.xlsx сбора: запрос → (откуда, показы Вебмастер, показы SC) и список отсеянного."""
    src, dropped = {}, []
    path = os.path.join(folder, SX.XLSX_NAME)
    if not os.path.exists(path):
        return src, dropped
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True)
        if "Запросы" in wb.sheetnames:
            for r in wb["Запросы"].iter_rows(min_row=2, values_only=True):
                if r and r[0]:
                    src[str(r[0])] = (r[10] or "", r[8] or None, r[9] or None)
        if "Отсеяно" in wb.sheetnames:
            dropped = [(str(r[0]), r[1] or "", r[2] or "") for r in wb["Отсеяно"].iter_rows(min_row=2, values_only=True)
                       if r and r[0]]
        wb.close()
    except Exception:
        pass
    return src, dropped


def write(folder, data):
    """data — семантика с наложенными решениями (decisions.apply). Возвращает путь к файлу."""
    src, dropped = _from_built(folder)
    Q, groups = {}, []
    for g in data["groups"]:
        qs = []
        for r in g.get("q") or []:
            s = src.get(r[0])
            Q[r[0]] = {"extra": r[1], "intent": r[2], "score": r[3], "y": r[4] or None, "g": r[5] or None,
                       "wm": {"shows": s[1]} if s and s[1] else ({"shows": r[6]} if r[6] and not s else None),
                       "gsc": {"shows": s[2]} if s and s[2] else None, "check": r[7],
                       "src": set(x.strip() for x in s[0].split(",") if x.strip()) if s else set(),
                       "imp": {"freq": r[11]} if len(r) > 11 and r[11] else None}
            qs.append(r[0])
        groups.append({"name": g["name"], "todo": g["todo"], "page": g.get("page") or "", "near": g.get("near") or "",
                       "score": g.get("score") or 0, "prio": PRIO.get(g["kind"], 4), "queries": qs,
                       "rivals": {"": g.get("rivals") or []}, "audit": g.get("a"), "filters": g.get("f") or [],
                       "faq": g.get("faq") or [], "land": g.get("land"), "tz": g.get("tz")})
    if not dropped:   # старый сбор без семантика.xlsx: причины без подробностей
        dropped = [(q, why, "") for why, qs in (data.get("dropped") or {}).items() if why != JUNK_REASON for q in qs]
    dropped += [(q, JUNK_REASON, "решение на странице «Семантика»") for q in (data.get("dropped") or {}).get(JUNK_REASON, [])]
    sem = {"site": data["site"], "city": data.get("city"), "competitors": data.get("competitors") or [],
           "made": data.get("made", "") + " (с решениями на странице «Семантика»)", "queries": Q, "groups": groups,
           "dropped": dropped, "wm": data.get("wm"), "gsc": data.get("gsc"), "geo": data.get("geo"),
           "cannibal": [c for c in data.get("cannibal") or [] if c.get("decision") != "ok"]}
    path = os.path.join(folder, FILE)
    from .tree import build as tree_build   # первым листом - дерево сайта (у нового сайта - его структура)
    SX.write_xlsx(path, sem, tree=tree_build(data, folder), brands=brands_of(data, folder),
                  visibility=visibility_of(data))
    return path


def brands_of(data, folder):
    """Бренды для листов Excel; не получилось - без них (Excel важнее)."""
    try:
        from .brands import build
        res = build(data, folder)
    except Exception:
        return None
    try:   # общая таблица «Бренды и прочие» (catalog.py): бренды и свойства этого сайта - в лист его ниши
        from .. import catalog
        catalog.update(folder, data, res)
    except Exception as e:
        print("Таблица «Бренды и прочие» не обновлена:", str(e)[:150])
    return res


def visibility_of(data):
    """Видимость из Букварикса (вкладка «Видимость») для листов Excel; не загружалась или ошибка - без них."""
    try:
        from .bukvarix import build
        v = build(data, data["host"])
        q = v.get("quick") or {}
        return v if v.get("domains") or q.get("rows") or (q.get("ads") or {}).get("rows") else None
    except Exception:
        return None
