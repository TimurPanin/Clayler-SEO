"""Весь отчёт одним файлом Excel: сводка, список проблем с объяснениями, все страницы
и отдельная вкладка на каждую проблему. Нужен модуль openpyxl (ставится bat-файлом)."""
import re

from .analyze import SEV_RU, CRIT, WARN, NOTE
from .fmt import num, when_range
from .analyze.health import ABOUT as HEALTH_ABOUT
from .report import health_parts_text, seen_as_text as _seen_as

MAX_CELL = 32000          # Excel не хранит в ячейке больше 32 767 символов
MAX_ROWS = 1_000_000      # и больше ~1 млн строк на листе
# Лист одной проблемы - не больше стольких строк: на dom-primer.ru у проблем были
# сотни тысяч строк («браузеру не велено запоминать файлы» - 408 тыс.), Excel весил 118 МБ и собирался 10+ минут.
# Столько строк никто не читает; над таблицей - пометка, сколько всего. Число в списке проблем - полное.
MAX_ISSUE_ROWS = 50_000


def full_list_where(n_rows, excel="таблицей Excel"):
    """Где клиенту взять полный список проблемы: в Excel - если он туда целиком помещается (не больше MAX_ISSUE_ROWS
    строк на листе), иначе «по запросу», как на самом листе Excel."""
    return f"Полный список можно получить {excel}." if n_rows <= MAX_ISSUE_ROWS else "Полный список - по запросу."

SEV_FILL = {CRIT: "F8D7D3", WARN: "FCE0C4", NOTE: "FFF3BF"}   # красный, оранжевый, жёлтый - как в отчёте
SEV_ORDER = {CRIT: 0, WARN: 1, NOTE: 2}


def available():
    try:
        import openpyxl  # noqa: F401
        return True
    except Exception:
        return False


def _clean(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return v
    s = str(v)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)  # символы, которые Excel не принимает
    if s[:1] in ("=", "+", "-", "@") and not s[1:2].isdigit():
        s = "'" + s  # чтобы текст не превратился в формулу
    return s[:MAX_CELL]


def _sheet_name(n, title, used):
    # в Excel имя листа не длиннее 31 знака — режем по целому слову («Битые ссылки где именно», не «… испр»)
    base = re.sub(r"[\[\]:*?/\\']", "", f"{n:02d} {title}")
    if len(base) > 31:
        words = base[:32].split(" ")[:-1]
        # без висящего предлога и незакрытой скобки: «Ссылки на адреса с», «Нет описания (meta»
        while len(words) > 2 and (len(words[-1]) <= 2 or " ".join(words).count("(") > " ".join(words).count(")")):
            words.pop()
        base = " ".join(words).rstrip(" ,-(«")
    base = base[:31].strip()
    name, k = base, 2
    while name.lower() in used:
        name = base[:28] + f"_{k}"
        k += 1
    used.add(name.lower())
    return name


def write_xlsx(path, meta, issues, pages, summary, page_export):
    """Таблица уходит и клиенту (папка «для клиента»): тексты — как в отчёте для клиента, служебные проблемы скрыты.
    Пишется потоком (write_only): строки сразу уходят в файл, а не копятся в памяти - на dom-primer.ru
    (77 тыс. страниц, миллионы строк) обычный режим собирал Excel 10+ минут и брал гигабайты. Оформление то же:
    шапка, закреплённая строка, фильтры, ширина колонок, цвет важности, ссылки на листы, перенос строк."""
    from .client_report import HIDE, client_text
    issues = [i for i in issues if i.key not in HIDE]
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook(write_only=True)
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="EDEBE6")
    wrap = Alignment(wrap_text=True, vertical="top")
    top = Alignment(vertical="top")
    link_font = Font(color="1F4FBF", underline="single")

    def cell(ws, value, font=None, fill=None, alignment=None, hyperlink=None):
        c = WriteOnlyCell(ws, value=value)
        if font is not None:
            c.font = font
        if fill is not None:
            c.fill = fill
        if alignment is not None:
            c.alignment = alignment
        if hyperlink:
            c.hyperlink = hyperlink
        return c

    def header_row(ws, cols):
        return [cell(ws, c, bold, head_fill, wrap) for c in cols]

    def widths(ws, ws_widths):
        for i, w in enumerate(ws_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    def auto_widths(cols, rows):
        return [max(10, min(70, max([len(str(name))] + [min(len(str(r[i] if i < len(r) else "")), 80)
                                                        for r in rows[:300]]) + 2))
                for i, name in enumerate(cols)]

    # ---------- Сводка
    ws = wb.create_sheet("Сводка")
    widths(ws, [44, 70])
    rows = [
        ("Сайт", meta.get("start", "")),
        ("Проверка", when_range(meta.get("started_at"), meta.get("finished_at"))),
        ("Режим", "с JavaScript" if summary.get("render_js") else "без JavaScript"),
        ("Как проверяли", _seen_as(summary)),
        ("Здоровье сайта", f'{summary["health"]}% (доля страниц без критичных проблем и предупреждений; проблема всего сайта снимает 5-10%, '
                            f'все вместе не больше 30%). ' + HEALTH_ABOUT),
        *([("Здоровье по частям", health_parts_text(summary))] if health_parts_text(summary) else []),
        ("Страниц сайта проверено", summary["pages"]),
        ("Из них могут попасть в поиск", summary["indexable"]),
        ("Всего адресов проверено", summary["checked"]),
        ("Страниц без проблем", summary["pages_clean"]),
        ("Страниц только с предупреждениями", summary["pages_warn_only"]),
        ("Страниц с критичными проблемами", summary["pages_crit"]),
        ("Видов критичных проблем", summary["crit"]),
        ("Видов предупреждений", summary["warn"]),
        ("Видов замечаний", summary["note"]),
        ("Цвет строк на листе «Проблемы»", "красный - критично, оранжевый - предупреждение, жёлтый - замечание"),
    ]
    if summary.get("queue_left"):
        rows.append(("Внимание", f'Сайт проверен не полностью: ещё {summary["queue_left"]} страниц не проверены'))
    ws.append([cell(ws, "SEO-аудит сайта", Font(bold=True, size=14))])
    ws.append([])
    left = Alignment(horizontal="left")
    for k, v in rows:
        ws.append([cell(ws, k, bold), cell(ws, _clean(v), alignment=left)])
    ws.append([])
    ws.append([cell(ws, "Как читать", bold),
               cell(ws, "Вкладка «Проблемы» - всё найденное с объяснениями. Нажмите на название проблемы, "
                        "чтобы перейти к её списку адресов. Вкладка «Страницы» - все страницы сайта с их данными, "
                        "по любой колонке можно фильтровать.", alignment=wrap)])
    from . import coverage
    cov = summary.get("coverage")
    if cov:  # что не проверено и почему
        ws.append([])
        ws.append([cell(ws, coverage.HEAD, Font(bold=True, size=12)), cell(ws, coverage.intro(cov), alignment=wrap)])
        for what, n, why in coverage.xlsx_rows(cov):
            ws.append([cell(ws, f"{what}: {n}" if n != "" else what, alignment=wrap), cell(ws, why, alignment=wrap)])

    # ---------- Проблемы (со ссылками на вкладки)
    wp = wb.create_sheet("Проблемы")
    cols = ["Важность", "Раздел", "Проблема", "Количество", "Что это значит", "Что сделать"]
    widths(wp, [15, 16, 50, 11, 70, 70])
    wp.freeze_panes = "A2"
    wp.append(header_row(wp, cols))
    used = {"сводка", "проблемы", "страницы", "готовые заголовки", "перелинковка"}
    issue_sheets = []
    for n, i in enumerate(issues, 1):
        name = _sheet_name(n, client_text(i.title), used)
        issue_sheets.append((i, name))
        fill = PatternFill("solid", fgColor=SEV_FILL[i.severity])   # строка целиком цветом важности
        vals = [SEV_RU[i.severity], i.category, client_text(i.title), i.sitewide or i.count, client_text(i.why),
                client_text(i.fix)]
        wp.append([cell(wp, v, link_font if c == 2 else None, fill, wrap, f"#'{name}'!A1" if c == 2 else None)
                   for c, v in enumerate(vals)])
    wp.auto_filter.ref = f"A1:F{1 + len(issues)}"

    # ---------- Страницы
    wpg = wb.create_sheet("Страницы")
    pcols = [h for _, h in page_export]
    prows = [[p.get(k) for k, _ in page_export] for p in sorted(pages, key=lambda p: ((p["depth"] or 0), p["url"]))]
    widths(wpg, auto_widths(pcols, prows))
    wpg.freeze_panes = "A2"
    wpg.append(header_row(wpg, pcols))
    for r in prows[:MAX_ROWS]:
        wpg.append([_clean(v) for v in r])
    wpg.auto_filter.ref = f"A1:{get_column_letter(len(pcols))}{1 + min(len(prows), MAX_ROWS)}"
    prows = None

    # ---------- Готовые заголовки и план перелинковки
    from . import suggest_out
    for title, cols, rows, ws_widths in (
            ("Готовые заголовки", suggest_out.META_COLS, suggest_out.meta_rows(summary),
             [45, 30, 35, 45, 40, 55, 30, 40, 12, 22, 18]),
            ("Перелинковка", suggest_out.LINK_COLS, suggest_out.link_rows(summary),
             [45, 35, 40, 10, 10, 10, 45, 35, 35, 35])):
        if not rows:
            continue
        ws_ = wb.create_sheet(title)
        widths(ws_, ws_widths)
        ws_.freeze_panes = "A2"
        ws_.append(header_row(ws_, cols))
        for k, r in enumerate(rows[:MAX_ROWS]):
            vals = [_clean(v) for v in r]
            ws_.append([cell(ws_, v, alignment=wrap) for v in vals] if k < 2999 else vals)
        ws_.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{1 + min(len(rows), MAX_ROWS)}"

    # ---------- Вкладка на каждую проблему
    for i, name in issue_sheets:
        wi = wb.create_sheet(name)
        wi.sheet_properties.tabColor = SEV_FILL[i.severity]
        rows = i.rows[:MAX_ISSUE_ROWS]
        w = auto_widths(i.columns, i.rows)
        w[0] = max(w[0], 60)
        widths(wi, w)
        hr = 6   # строка шапки таблицы: 1-3 - что за проблема, 4 - ссылка назад, 5 - пусто или «показаны первые …»
        wi.freeze_panes = f"A{hr + 1}"
        wi.append([cell(wi, f"{SEV_RU[i.severity]}: {client_text(i.title)}", Font(bold=True, size=12))])
        wi.append([f"Что это значит. {client_text(i.why)}"])
        wi.append([f"Что сделать. {client_text(i.fix)}"])
        wi.append([cell(wi, "← к списку проблем", link_font, hyperlink="#'Проблемы'!A1")])
        if len(i.rows) > len(rows):
            wi.append([cell(wi, f"Показаны первые {num(len(rows))} строк из {num(len(i.rows))} - этого достаточно, "
                                "чтобы понять, что и где исправлять. Полный список - по запросу.", Font(italic=True))])
        else:
            wi.append([])
        wi.append([cell(wi, c, bold, head_fill) for c in i.columns])
        for k, r in enumerate(rows):
            vals = [_clean(v) for v in r]
            if k < 2000:
                wi.append([cell(wi, v, alignment=wrap if isinstance(v, str) and "\n" in v else top) for v in vals])
            else:
                wi.append(vals)
        wi.auto_filter.ref = f"A{hr}:{get_column_letter(len(i.columns))}{hr + len(rows)}"
    wb.save(path)
