"""Семантика в Excel (группы с их страницами, все запросы, отсеянное) и в JSON — для страницы в окне и бота."""
import json
import os

from ..xlsx_report import _clean
from .. import jsonfile
from ..fmt import num as _num
from . import labels as L

JSON_NAME = "семантика.json"
XLSX_NAME = "семантика.xlsx"
PRIO_KIND = {1: "page", 2: "create", 3: "absent", 4: "manual"}


def _place(r):
    """Средняя позиция сайта по запросу: лучшая из Вебмастера и Search Console, с одним знаком; 0 — нет данных."""
    ps = [x.get("pos") for x in (r.get("wm") or {}, r.get("gsc") or {}, r.get("imp") or {}) if x.get("pos")]
    return round(min(ps), 1) if ps else 0


def _sum(r, k):
    """Показы или клики: Вебмастер + Search Console, а если их нет - из выгрузки в файле (чтобы не считать дважды)."""
    v = ((r.get("wm") or {}).get(k) or 0) + ((r.get("gsc") or {}).get(k) or 0)
    return v or (r.get("imp") or {}).get(k) or 0


COMMERCIAL = ("Покупка", "Услуга")
ARTICLES_MAX = 60


def page_type(qs, Q):
    """Под какую страницу группа: «page» — страница товара или услуги (купить, цена, записаться), «article» —
    статья (как, что такое, почему), «both» — нужны обе: страница и статья, которая на неё ведёт."""
    info = sum(1 for q in qs if Q[q]["intent"] == "Информация" and not Q[q]["check"])
    comm = sum(1 for q in qs if Q[q]["intent"] in COMMERCIAL and not Q[q]["check"])
    if info >= 3 and comm >= 3 and info * 3 >= comm:
        return "both", info, comm
    if info >= 3 and info >= 1.5 * comm:
        return "article", info, comm
    return "page", info, comm


def article_plan(sem):
    """План статей для блога: информационные запросы групп («как выбрать…», «что такое…»). Одна тема — одна
    статья со ссылкой на страницу группы (или на ближайшую, если страницы ещё нет)."""
    Q = sem["queries"]
    out = []
    for g in sem["groups"]:
        if g["prio"] == 4:
            continue
        qs = sorted((q for q in g["queries"] if Q[q]["intent"] == "Информация" and not Q[q]["check"]),
                    key=lambda q: -Q[q]["score"])
        if len(qs) < 2:
            continue
        title = min(qs[:5], key=lambda q: (len(q.split()) < 3, -Q[q]["score"], len(q)))
        out.append({"title": title[:1].upper() + title[1:], "group": g["name"], "link": g["page"] or g["near"],
                    "queries": qs[:10], "n": len(qs), "score": sum(Q[q]["score"] for q in qs[:10])})
    out.sort(key=lambda a: -a["score"])
    return out[:ARTICLES_MAX]


def to_data(sem):
    """Компактный вид для страницы «Семантика»: группы с запросами (запросы — списками, чтобы файл был небольшим)."""
    Q = sem["queries"]
    groups = []
    for g in sem["groups"]:
        qs = sorted(g["queries"], key=lambda q: (bool(Q[q]["check"]), -Q[q]["score"]))
        pt, n_info, n_comm = page_type(g["queries"], Q)
        groups.append({
            "ptype": pt, "info": n_info, "comm": n_comm,
            "name": g["name"], "todo": g["todo"], "kind": PRIO_KIND[g["prio"]], "page": g["page"], "near": g["near"],
            "score": g["score"], "rivals": [u for urls in g["rivals"].values() for u in urls[:1]],
            "products": len(g.get("products") or []), "a": g.get("audit"), "f": g.get("filters") or [],
            "faq": g.get("faq") or [],
            "lv": g.get("level") or 9,   # уровень маски: 1 - главная и меню, 2 - разделы, 3 - подразделы (masks.py)
            # запрос, уточнение, намерение, оценка, место Яндекс, место Google, показы Вебмастер/SC, проверить,
            # место сайта в поиске (лучшее из Вебмастера и Search Console, 0 — нет данных),
            # страница, которую Google показывает по запросу (Search Console), переходы из поиска,
            # частотность в месяц (из файла: Вордстат, Key Collector; 0 - нет),
            # место в Яндексе (Вебмастер) и в Google (Search Console) порознь, 0 - нет данных (дерево сайта)
            "q": [[q, Q[q]["extra"], Q[q]["intent"], Q[q]["score"], Q[q]["y"] or 0, Q[q]["g"] or 0, _sum(Q[q], "shows"),
                   Q[q]["check"], _place(Q[q]), (Q[q]["gsc"] or {}).get("page") or (Q[q].get("imp") or {}).get("page") or "",
                   _sum(Q[q], "clicks"), (Q[q].get("imp") or {}).get("freq") or 0,
                   round((Q[q]["wm"] or {}).get("pos") or 0, 1), round((Q[q]["gsc"] or {}).get("pos") or 0, 1)]
                  for q in qs]})
    reasons = {}
    for q, why, _src in sem["dropped"]:
        reasons.setdefault(why.split(":")[0], []).append(q)
    return {"site": sem["site"], "host": sem["host"], "city": sem["city"], "competitors": sem["competitors"],
            "made": sem["made"], "seconds": sem["seconds"], "wm": sem["wm"], "gsc": sem["gsc"],
            "total": len(Q), "dropped": {k: sorted(v) for k, v in reasons.items()}, "groups": groups,
            # каких слов нет на сайтах - для кнопки «Это про нас» в «Отсеяно» (окно)
            "foreign": {q: why.split(":", 1)[1].strip() for q, why, _s in sem["dropped"] if why.startswith("слов нет на сайтах:")},
            "deep": sem.get("deep", False), "cannibal": sem.get("cannibal") or [],
            "geo": sem.get("geo") or {"checks": [], "faq_pages": []}, "real": sem.get("real") or {}, "articles": article_plan(sem),
            "light": sem.get("light") or [], "new_site": sem.get("new_site"), "masks": sem.get("masks")}


def write_json(path, sem):
    jsonfile.save(path, to_data(sem), separators=(",", ":"))


def load(folder):
    try:
        with open(os.path.join(folder, JSON_NAME), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    from .. import direct   # точная частотность Вордстата из Директа - в колонку «Спрос»
    from . import forms     # «группа безопасности» и «группы безопасности» - одна строка
    from . import synonyms  # «бойлер …» и «водонагреватель …» - в одной группе (словарь ниши)
    from . import masks     # стоп-слова клиента - сразу в «Отсеяно», и Вордстат на них не тратится
    from .words import refine_intents   # «Сравнение» и «Навигация» и у семантики, собранной раньше
    return direct.apply(masks.drop_stopped(synonyms.apply(forms.merge(refine_intents(data)))))


def summary(data, prio=False):
    """Счётчики для итога: сколько групп по видам действий (prio - группы сбора, у них вид по g["prio"])."""
    out = {k: 0 for k in PRIO_KIND.values()}
    for g in data["groups"]:
        out[PRIO_KIND.get(g["prio"], "manual") if prio else g["kind"]] += 1
    return out

PRIO_FILL = {1: "E2F0D9", 2: "FBEBC8", 3: "EDEBE6", 4: "EDEBE6"}
HOW = [
    ("Что это", "Семантика сайта: какие запросы ищут люди по товарам и услугам сайта и какая страница должна по ним "
                "показываться в поиске. Одна группа - одна страница."),
    ("Откуда запросы", "Разделы вашего сайта и сайтов конкурентов → подсказки Яндекса и Google по каждому разделу "
                       "(то, что люди набирают в поиске) → запросы из Вебмастера и Search Console, если вход подключён."),
    ("Вкладка «Группы»", "Главная. У группы - страница сайта и что с ней делать: «" + L.KIND["page"][0] + "» ("
                         + L.KIND["page"][1] + "), «" + L.KIND["create"][0] + "» (" + L.KIND["create"][1] + "), «"
                         + L.KIND["absent"][0] + "» (" + L.KIND["absent"][1] + "). Сначала - самые востребованные."),
    ("Вкладка «Запросы»", "Все запросы: группа, уточнение (что добавлено к названию раздела: бренд, размер, «для "
                          "частного дома»), намерение (купить, услуга, узнать, сравнить, найти сам сайт), место в подсказках."),
    ("Оценка спроса, баллы", "Примерная, по месту в подсказках: первая подсказка Яндекса - 10 баллов, десятая - 1, так же Google. "
                      "Это не число показов в месяц: точную частотность даёт только Яндекс Вордстат."),
    ("Колонка «Проверить»", "В запросе есть слова, которых нет ни на одной странице ваших сайтов и сайтов конкурентов - "
                            "возможно, запрос про другое («группа безопасности на высоте»). Посмотреть глазами."),
    ("Вкладка «Отсеяно»", "Что убрано и почему: другой город, название конкурента, «скачать», «своими руками», "
                          "не по теме. Если что-то убрано зря, можно вернуть вручную."),
]


def write_xlsx(path, sem, structure=None, tree=None, brands=None, visibility=None):
    """tree - дерево сайта (tree.build): первым листом «Дерево сайта» (у нового сайта - «Структура сайта») и лист
    «Признаки». structure - новый сайт без дерева (newsite.structure): первым листом «Структура сайта».
    brands - бренды (brands.build): листы «Бренды» и «Бренды по категориям».
    visibility - Букварикс (bukvarix.build): листы «Видимость» и «Видимость - запросы»."""
    b = _Book()
    _sheet_how(b, sem)
    if tree:
        from .tree import write_sheets
        write_sheets(b.wb, tree, "Структура сайта" if tree["new"] else "Дерево сайта", first=True)
        b.wb.active = 0
    elif structure:
        _sheet_structure(b, structure)
    _sheet_groups(b, sem)
    if any(g.get("land") for g in sem["groups"]):   # с решениями (plan.enrich): какая страница под группу
        _sheet_landing(b, sem)
    _sheet_queries(b, sem)
    _sheet_tz(b, sem)
    _sheet_articles(b, sem)
    _sheet_filters(b, sem)
    _sheet_geo(b, sem)
    _sheet_cannibal(b, sem)
    if brands and brands.get("brands"):
        _sheet_brands(b, brands)
    if visibility and visibility.get("domains"):
        _sheet_visibility(b, visibility)
    quick = (visibility or {}).get("quick") or {}
    if quick.get("rows"):
        _sheet_quick(b, quick)
    if (quick.get("ads") or {}).get("rows"):
        _sheet_ads(b, quick)
    ws = b.sheet("Отсеяно", ["Запрос", "Почему убран", "Откуда"], [60, 44, 30])
    for q, why, src in sorted(sem["dropped"], key=lambda x: (x[1], x[0])):
        ws.append([_clean(q), _clean(why), src])
    b.wb.save(path)


class _Book:
    """Книга Excel и общие приёмы листов семантики: шапка, ссылка, заливка."""

    def __init__(self):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        self.PatternFill = PatternFill
        self.wb = Workbook()
        self.bold = Font(bold=True)
        self.head_fill = PatternFill("solid", fgColor="EDEBE6")
        self.wrap = Alignment(wrap_text=True, vertical="top")
        self.link_font = Font(color="1F4FBF", underline="single")

    def fill(self, color):
        return self.PatternFill("solid", fgColor=color)

    def sheet(self, title, cols, widths, index=None):
        """Новый лист с шапкой: жирная, с заливкой, закреплена, с фильтром; ширина колонок."""
        from openpyxl.utils import get_column_letter
        ws = self.wb.create_sheet(title, index)
        ws.append(cols)
        for i, w in enumerate(widths, 1):
            c = ws.cell(row=1, column=i)
            c.font, c.fill, c.alignment = self.bold, self.head_fill, self.wrap
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"
        return ws

    def link(self, ws, row, col, url):
        if url:
            c = ws.cell(row=row, column=col)
            c.hyperlink, c.font = url, self.link_font

    def wrap_cells(self, ws, cols, row=None):
        for col in cols:
            ws.cell(row=row or ws.max_row, column=col).alignment = self.wrap


def _append_clean(ws, row):
    """Строка в лист: текст - через _clean (без длинных тире и прямых кавычек), числа как есть."""
    ws.append([_clean(x) if isinstance(x, str) else x for x in row])


def _sheet_how(b, sem):
    Q = sem["queries"]
    ws = b.wb.active
    ws.title = "Как читать"
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 110
    head = [("Сайт", sem["site"]), ("Город", sem["city"] or "не определён - подсказки по всей России"),
            ("Конкуренты", ", ".join(sem["competitors"]) or "нет"), ("Собрано", sem["made"]),
            ("Итого", f'{_num(len(Q))} {L.plural(len(Q), "query")} в {_num(len(sem["groups"]))} '
                      f'{"группе" if len(sem["groups"]) % 10 == 1 and len(sem["groups"]) % 100 != 11 else "группах"}, '
                      f'отсеяно {_num(len(sem["dropped"]))}'),
            ("Группы", "; ".join(L.count(k, n) for k, n in summary(sem, prio=True).items() if n)),
            ("Вебмастер и Search Console", ", ".join(x for x, ok in (("Вебмастер", sem["wm"]), ("Search Console",
             sem["gsc"])) if ok) or "запросов из них нет (нет доступа к сайту или данных)"), ("", "")]
    for a, txt in head + HOW:
        ws.append([a, txt])
        ws.cell(row=ws.max_row, column=1).font = b.bold
        ws.cell(row=ws.max_row, column=2).alignment = b.wrap


def _sheet_structure(b, structure):
    from .newsite import rows as ns_rows
    ws = b.sheet("Структура сайта", ["Что", "Страница", "Адрес", "H1", "Title", "Главные запросы", "Спрос", "У конкурентов"],
                 [16, 40, 40, 40, 56, 70, 10, 36], index=0)
    lvl_fill = {"Главная": "E2F0D9", "Раздел": "E2F0D9", "Подраздел": "F3F8EE", "Портфолио": "FBEBC8",
                "Статья в блог": "FBEBC8", L.KIND["absent"][0]: "EDEBE6"}
    for r in ns_rows(structure):
        ws.append([r[0], r[1][:len(r[1]) - len(r[1].lstrip())] + _clean(r[1].lstrip()), r[2], _clean(r[3]), _clean(r[4]),
                   _clean(r[5]), r[6], r[7]])
        ws.cell(row=ws.max_row, column=1).fill = b.fill(lvl_fill.get(r[0], "FFFFFF"))
        ws.cell(row=ws.max_row, column=6).alignment = b.wrap
    b.wb.active = 0


def _sheet_groups(b, sem):
    Q = sem["queries"]
    ws = b.sheet("Группы", ["Группа", "Что делать", "Страница на сайте", "Запросов", "Оценка спроса, баллы", "Главные запросы",
                            "Ближайшая страница / пример товара", "У конкурентов"], [34, 44, 50, 10, 10, 70, 50, 50])
    for g in sem["groups"]:
        top = sorted((q for q in g["queries"] if not Q[q]["check"]), key=lambda q: -Q[q]["score"])
        rivals = "; ".join(u for urls in g["rivals"].values() for u in urls[:1])
        ws.append([_clean(g["name"]), _clean(g["todo"]), g["page"], len(g["queries"]), g["score"],
                   _clean(", ".join(top[:8])), g["near"], _clean(rivals)])
        r = ws.max_row
        b.link(ws, r, 3, g["page"])
        b.link(ws, r, 7, g["near"])
        ws.cell(row=r, column=2).fill = b.fill(PRIO_FILL[g["prio"]])
        b.wrap_cells(ws, (2, 6), r)


def _sheet_landing(b, sem):
    Q = sem["queries"]
    ws = b.sheet("Запрос → страница", ["Группа", "Главный запрос", "Запросов", "Оценка спроса, баллы", "Страница", "Что с ней",
                                       "Новая страница: H1", "Новая страница: title"], [34, 34, 10, 10, 56, 22, 34, 50])
    fill = {"ok": "E2F0D9", "fix": "FBEBC8", "wrong": "F8D7D3", "create": "F8D7D3", "absent": "EDEBE6", "manual": "EDEBE6"}
    for g in sem["groups"]:
        land = g.get("land") or {}
        if not land or land["st"] == "manual":
            continue
        top = max((q for q in g["queries"] if not Q[q]["check"]), key=lambda q: Q[q]["score"], default="")
        ws.append([_clean(g["name"]), _clean((g.get("audit") or {}).get("main") or top), len(g["queries"]), g["score"],
                   land["url"], land["label"] + (" (новый адрес)" if land["new"] else ""),
                   _clean(land["h1"]) if land["new"] else "", _clean(land["title"]) if land["new"] else ""])
        r = ws.max_row
        b.link(ws, r, 5, "" if land["new"] else land["url"])
        ws.cell(row=r, column=6).fill = b.fill(fill[land["st"]])


def _sheet_queries(b, sem):
    Q = sem["queries"]
    ws = b.sheet("Запросы", ["Запрос", "Группа", "Уточнение", "Намерение", "Страница на сайте", "Оценка спроса, баллы",
                             "Место в подсказках Яндекса", "Место в подсказках Google", "Показы в Вебмастере",
                             "Показы в Search Console", "Откуда", "Проверить", "Частотность в месяц (из файла)"],
                 [48, 30, 26, 12, 44, 10, 12, 12, 12, 12, 30, 40, 14])
    for g in sem["groups"]:
        for q in sorted(g["queries"], key=lambda q: (bool(Q[q]["check"]), -Q[q]["score"])):
            r = Q[q]
            ws.append([_clean(q), _clean(g["name"]), _clean(r["extra"]), r["intent"], g["page"] or g["near"],
                       r["score"], r["y"] or "", r["g"] or "", (r["wm"] or {}).get("shows") or "",
                       (r["gsc"] or {}).get("shows") or "", ", ".join(sorted(r["src"])), _clean(r["check"]),
                       (r.get("imp") or {}).get("freq") or ""])


def _sheet_tz(b, sem):
    ws = b.sheet("ТЗ на страницы", ["Группа", "Страница", "Главный запрос", "Что поправить", "Title сейчас",
                                    "Предлагаемый title", "H1 сейчас", "Предлагаемый H1", "Предлагаемое описание",
                                    "Слов на странице", "Слова из текста конкурента", "Объём текста", "Подзаголовки H2"],
                 [28, 44, 30, 60, 40, 44, 30, 30, 50, 10, 40, 36, 60])
    for g in sem["groups"]:
        a = g.get("audit")
        if not a or not (a["problems"] or a.get("new")):
            continue
        now = a.get("now") or {}
        todo = "Новая страница: " + g["todo"] if a.get("new") else "\n".join("• " + p for p in a["problems"])
        tz = g.get("tz") or {}
        ws.append([_clean(g["name"]), g["page"] or (g.get("land") or {}).get("url") or "", _clean(a["main"]), _clean(todo),
                   _clean(now.get("title")), _clean(a["title"]), _clean(now.get("h1")), _clean(a["h1"]),
                   _clean(a["description"]), now.get("words", ""), _clean(", ".join(a.get("lsi") or [])),
                   _clean((tz.get("volume") or {}).get("text") or ""), _clean("; ".join(tz.get("h2") or []))])
        r = ws.max_row
        b.link(ws, r, 2, g["page"])
        b.wrap_cells(ws, (4, 5, 6, 9, 12, 13), r)


def _sheet_articles(b, sem):
    ws = b.sheet("План статей", ["Тема статьи", "Группа", "Куда ссылаться из статьи", "Запросов", "Запросы"],
                 [50, 34, 50, 10, 90])
    for a in article_plan(sem):
        ws.append([_clean(a["title"]), _clean(a["group"]), a["link"], a["n"], _clean(", ".join(a["queries"]))])
        b.link(ws, ws.max_row, 3, a["link"])
        for c in ws[ws.max_row]:
            c.alignment = b.wrap


def _sheet_filters(b, sem):
    ws = b.sheet("Страницы-фильтры", ["Группа", "Страница-фильтр", "Запросов", "Товаров на сайте", "Совет",
                                      "Пример товара", "Примеры запросов"], [30, 40, 10, 10, 34, 50, 70])
    rows = [(g, f) for g in sem["groups"] for f in g.get("filters") or []]
    for g, f in sorted(rows, key=lambda x: -x[1]["queries"]):
        advice = ("Создать страницу-фильтр" if f["products"] >= 3 else
                  f"Товаров мало ({f['products']}) - сначала расширить ассортимент" if f["products"] else
                  "Таких товаров на сайте нет")
        ws.append([_clean(g["name"]), _clean(f["name"]), f["queries"], f["products"], advice, f["example"],
                   _clean(", ".join(f["sample"]))])
        b.link(ws, ws.max_row, 6, f["example"])


def _sheet_geo(b, sem):
    ws = b.sheet("GEO и вопросы", ["Что", "Страница", "Результат", "Что сделать"], [40, 44, 60, 70])
    geo = sem.get("geo") or {}
    for c in geo.get("checks") or []:
        ws.append([("✓ " if c["ok"] else "✗ " if c["ok"] is False else "? ") + c["name"], "", _clean(c["text"]),
                   _clean(c["fix"])])
        ws.cell(row=ws.max_row, column=1).font = b.bold
        b.wrap_cells(ws, (3, 4))
    faq_pages = set(geo.get("faq_pages") or [])
    for g in sem["groups"]:
        if not g.get("faq"):
            continue
        page = g["page"] or ""
        note = ("на странице уже есть разметка FAQPage" if page in faq_pages else
                "добавить блок «вопрос - ответ» с короткими ответами и разметкой FAQPage")
        ws.append([f"Вопросы: {_clean(g['name'])}", page, _clean("\n".join(g["faq"])), note])
        b.link(ws, ws.max_row, 2, page)
        ws.cell(row=ws.max_row, column=3).alignment = b.wrap


def _sheet_cannibal(b, sem):
    ws = b.sheet("Мешают друг другу", ["Что не так", "Страница", "H1", "Title", "Её группа", "Ссылок на неё", "Совет",
                                       "Решение и задача разработчику"], [40, 50, 34, 44, 28, 10, 50, 70])
    for c in sem.get("cannibal") or []:
        for i, p in enumerate(c["pages"]):
            advice = ("Оставить главной (на неё больше всего ссылок)" if p["url"] == c["main"] else
                      f"Сделать свои title и H1 - по группе «{p['group']}»" if p["group"] else
                      "Сделать свои title и H1 или убрать дубль")
            dec = ""   # решение человека (decisions.py): только в «семантика с решениями.xlsx»
            if i == 0 and c.get("decision"):
                from .decisions import CHOICES
                dec = CHOICES[c["decision"]][0] + (": " + c["task"] if c.get("task") else "")
            ws.append([_clean(c["why"]) if i == 0 else "", p["url"], _clean(p["h1"]), _clean(p["title"]),
                       _clean(p["group"]), p["links"], advice, _clean(dec)])
            b.link(ws, ws.max_row, 2, p["url"])


def _sheet_brands(b, brands):
    from .brands import ALONE, ST_BRAND, ST_CELL, rows as brand_rows
    from .tree import FILL
    b_rows, c_rows = brand_rows(brands)
    dem = "Спрос в месяц" if brands.get("freq") else "Оценка спроса, баллы"
    st_fill = {v: FILL[k] for d in (ST_CELL, ST_BRAND) for k, v in d.items()}   # цвета как в дереве сайта
    ws = b.sheet("Бренды", ["Бренд", dem, "Запросов", "Как пишут (запросов)", "Что сделать", "Страница бренда у вас",
                            "У конкурентов", "Товаров у вас", "Примеры запросов", "Вид", "Модели в запросах"],
                 [24, 12, 10, 44, 18, 44, 24, 10, 70, 26, 40])
    for r in b_rows:
        _append_clean(ws, r)
        ws.cell(row=ws.max_row, column=5).fill = b.fill(st_fill.get(r[4], "FFFFFF"))
        b.link(ws, ws.max_row, 6, r[5])
    ws = b.sheet("Бренды по категориям", ["Бренд", "Категория", dem, "Запросов", "Что с ней", "Страница у вас",
                                          "У конкурентов", "Примеры запросов"], [24, 34, 12, 10, 22, 50, 24, 70])
    for r in c_rows:
        _append_clean(ws, r)
        ws.cell(row=ws.max_row, column=5).fill = b.fill(st_fill.get(r[4], "EDEBE6"))
        b.link(ws, ws.max_row, 6, r[5])
    ws.append([])
    ws.append(["", f"«{ALONE}» - запросы с брендом без категории: «baxi уфа», «бакси официальный сайт»."])


def _sheet_visibility(b, visibility):
    from .bukvarix import xlsx_rows
    g_rows, q_rows, note = xlsx_rows(visibility)
    good, warn = b.fill("D9EAD3"), b.fill("FCEFC2")
    ws = b.sheet("Видимость", ["Группа", "Что с группой", "Страница", "Сайт виден по запросам", "Из них в первой десятке",
                               "Есть у конкурентов, нет у вас", "Спрос того, чего нет, в месяц", "Чего нет (примеры)"],
                 [34, 18, 44, 12, 12, 14, 14, 80])
    for r in g_rows:
        _append_clean(ws, r)
        b.link(ws, ws.max_row, 3, r[2])
        if r[5]:
            ws.cell(row=ws.max_row, column=6).fill = warn
        if r[3]:
            ws.cell(row=ws.max_row, column=4).fill = good
    ws.append([])
    for line in note:
        ws.append(["", line])
    ws = b.sheet("Видимость - запросы", ["Запрос", "Группа", "Ваш сайт", "Место вашего сайта (Букварикс)",
                                         "Место по Вебмастеру", "Конкуренты и их места", "!Частотность в месяц",
                                         "Частотность в месяц"], [50, 34, 22, 12, 12, 40, 12, 12])
    for r in q_rows:
        _append_clean(ws, r)
        ws.cell(row=ws.max_row, column=3).fill = good if r[3] else warn if r[2].startswith("нет") else b.head_fill


def _sheet_quick(b, quick):
    from .bukvarix import quick_xlsx
    rows, note = quick_xlsx(quick)
    ws = b.sheet("Быстрые победы", ["Группа", "Страница", "Запрос", "Место сейчас", "Откуда место", "Частота в месяц",
                                    "Откуда частота", "Посетителей сейчас, примерно", "Недополучаете в месяц, примерно",
                                    "В рекламе стоили бы, ₽ в месяц"], [30, 40, 44, 10, 12, 11, 30, 13, 15, 14])
    warn = b.fill("FCEFC2")
    for r in rows:
        _append_clean(ws, r)
        b.link(ws, ws.max_row, 2, r[1])
        ws.cell(row=ws.max_row, column=9).fill = warn
    ws.append([])
    for line in note:
        ws.append(["", line])


def _sheet_ads(b, quick):
    from .bukvarix import ads_xlsx
    rows, note = ads_xlsx(quick)
    ws = b.sheet("Стоимость в рекламе", ["Запрос", "Группа", "Место сейчас", "Частота в месяц", "Откуда частота",
                                         "Посетителей в месяц, примерно", "Цена клика в рекламе, ₽",
                                         "В рекламе стоили бы, ₽ в месяц"], [44, 30, 10, 11, 30, 13, 12, 14])
    for r in rows:
        _append_clean(ws, r)
    ws.append([])
    for line in note:
        ws.append(["", line])
