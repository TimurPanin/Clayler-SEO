"""Отчёты: один HTML-файл и CSV для Excel (разделитель «;», UTF-8 с BOM)."""
import csv
import os
import re
from dataclasses import dataclass

from .analyze import SEV_RU, CRIT, WARN, NOTE
from .analyze.health import ABOUT as HEALTH_ABOUT
from .mobile_view import gallery_html, GALLERY_CSS
from . import duration as D
from .audit import regions_html, sections_html, scope_text
from . import buy_clicks, consent_forms, coverage, shop, sitemap_pic
from . import report_web
from .report_assets import REPORT_CSS, REPORT_CSS_INTRO, REPORT_CSS_TAIL, REPORT_JS
from . import report_weight
from .webmaster import report_html as wm_html
from .search_console import report_html as gsc_html
from .metrika import report_html as ym_html
from .extract import report_html as extract_html
from .speed_lab import report_html as sl_html, CSS as SL_CSS
from .site_tech import report_html as tech_html, _ru_date
from . import fix_files, labels, lost_clicks, lightbox, problem_shots, security, suggest_out, tablefs, web_cover
from .semantics import client as sem_client
from .fmt import esc as _e, num as _num, pretty_url, quote, when, when_range

PAGE_EXPORT = [
    ("url", "URL"), ("status", "Код"), ("error", "Ошибка"), ("indexability", "Индексируемость"),
    ("depth", "Глубина"), ("pagerank", "Внутренний PageRank"), ("inlinks", "Входящих ссылок (со страниц сайта)"),
    ("title", "Title"),
    ("title_len", "Длина title"), ("description", "Description"), ("desc_len", "Длина description"),
    ("h1", "H1"), ("h1_count", "Кол-во H1"), ("h2_count", "Кол-во H2"), ("canonical", "Canonical"),
    ("canonical_header", "Canonical (заголовок)"), ("meta_robots", "Meta robots"),
    ("x_robots", "X-Robots-Tag"), ("redirect_type", "Тип редиректа"), ("location", "Редирект на"),
    ("word_count", "Слов"), ("water", "Вода, %"), ("nausea", "Тошнота"), ("nausea_acad", "Тошнота академическая, %"), ("ttfb", "Время ответа сервера, с"), ("elapsed", "Время загрузки страницы, с"), ("size", "Размер, байт"),
    ("content_type", "Content-Type"), ("encoding", "Кодировка"), ("last_modified", "Last-Modified"),
    ("outlinks_internal", "Внутр. ссылок"), ("outlinks_external", "Внеш. ссылок"),
    ("images_no_alt", "Картинок без alt"), ("lang", "lang"), ("hreflang", "hreflang"),
    ("raw_title", "Title в исходном HTML (режим JS)"), ("raw_words", "Слов в исходном HTML (режим JS)"),
    ("js_only_links_count", "Ссылок только после JS"), ("js_redirect", "JS-редирект на"),
    ("js_time", "Время рендеринга, с"), ("js_error", "Ошибка рендеринга"),
]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if c is None else c for c in r])


def export_links(store, pages, out_dir):
    """ссылки.csv без сквозных ссылок; сквозные (меню, подвал — есть на 30% страниц и больше)
    — одной строкой каждая в ссылки_сквозные.csv. Иначе на большом сайте файл весит сотни мегабайт."""
    db = store.db
    n_pages = sum(1 for p in pages if p.get("status") == 200 and p.get("content_type") in ("text/html", "application/xhtml+xml"))
    threshold = max(20, int(n_pages * 0.3))
    status = {r[0]: (r[1], r[2]) for r in db.execute("SELECT url, status, error FROM pages")}
    if store.legacy_links:
        q = "SELECT dst, anchor, kind, COUNT(DISTINCT src) AS n FROM links GROUP BY dst, anchor, kind HAVING n>=?"
    else:
        q = """SELECT d.s, a.s, g.kind, g.n FROM (SELECT dst, anchor, kind, COUNT(DISTINCT src) AS n FROM link_rows
               GROUP BY dst, anchor, kind HAVING n>=?) g JOIN strs d ON d.id=g.dst LEFT JOIN strs a ON a.id=g.anchor"""
    sitewide = {(r[0], r[1] or "", r[2]): r[3] for r in db.execute(q, (threshold,))}
    rows = db.execute("SELECT src, dst, anchor, kind, nofollow, internal FROM links")

    def main_rows():
        for src, dst, anchor, kind, nofollow, internal in rows:
            if (dst, anchor or "", kind) in sitewide:
                continue
            st, err = status.get(dst, (None, None))
            yield [src, dst, anchor, kind, nofollow, internal, st, err]
    write_csv(os.path.join(out_dir, "ссылки.csv"),
              ["Откуда", "Куда", "Анкор", "Тип", "nofollow", "Внутренняя", "Код", "Ошибка"], main_rows())
    sw = sorted(sitewide.items(), key=lambda kv: -kv[1])
    write_csv(os.path.join(out_dir, "ссылки_сквозные.csv"),
              ["Куда", "Анкор", "Тип", "На скольких страницах", "Код", "Ошибка"],
              [[d, a, k, n, *status.get(d, (None, None))] for (d, a, k), n in sw])


def export_all(store, issues, pages, out_dir):
    lists = os.path.join(out_dir, "проблемы")
    os.makedirs(lists, exist_ok=True)
    keys = {i.key for i in issues}
    for f in os.listdir(lists):   # списки проблем, которых после «Обновить отчёт» больше нет (выключили, исправили)
        if os.path.splitext(f)[0] not in keys and f.endswith((".csv", ".html")):
            try:
                os.remove(os.path.join(lists, f))
            except OSError:
                pass
    for p in pages:
        p["title_len"] = len(p["title"]) if p.get("title") else ""
        p["desc_len"] = len(p["description"]) if p.get("description") else ""
    pages_sorted = sorted(pages, key=lambda p: ((p["depth"] or 0), p["url"]))
    write_csv(os.path.join(out_dir, "страницы.csv"), [h for _, h in PAGE_EXPORT],
              [[p.get(k) for k, _ in PAGE_EXPORT] for p in pages_sorted])
    export_links(store, pages, out_dir)
    write_csv(os.path.join(out_dir, "проблемы.csv"),
              ["Важность", "Раздел", "Проблема", "Количество", "Что это значит", "Что сделать", "Файл со списком"],
              [[SEV_RU[i.severity], i.category, i.title, i.sitewide or i.count, i.why, i.fix, f"проблемы/{i.key}.csv"] for i in issues])
    for i in issues:
        write_csv(os.path.join(out_dir, "проблемы", f"{i.key}.csv"), i.columns, i.rows)
    write_tasks(issues, out_dir)
    from . import extract
    extract.write_csv(extract.rules_of(store.get_meta("extract_rules")), pages, out_dir)


def write_tasks(issues, out_dir):
    """задачи.csv — задания для разработчика: одна проблема — одна строка, по порядку важности и пользы."""
    order = {CRIT: 0, WARN: 1, NOTE: 2}
    todo = [i for i in issues if i.severity in (CRIT, WARN)]
    todo.sort(key=lambda i: (order[i.severity], -(getattr(i, "gain", 0) or 0), -i.count))

    def example(i):
        for r in i.rows[:1]:
            for c in r:
                if isinstance(c, str) and c.startswith(("http://", "https://")):
                    return c.split("\n")[0]
        return ""
    write_csv(os.path.join(out_dir, "задачи.csv"),
              ["№", "Важность", "Задача", "Что сделать", "Сколько", "Прирост здоровья, %", "Пример", "Полный список"],
              [[n, SEV_RU[i.severity], i.title, i.fix, i.sitewide or i.count,
                (getattr(i, "gain", 0) or "") , example(i), f"проблемы/{i.key}.csv"] for n, i in enumerate(todo, 1)])


def seen_as_text(summary):
    """«Сайт проверялся …»: кем программа представлялась и чьи правила robots.txt соблюдала (выбор «Проверять как»)."""
    sa = summary.get("seen_as") or {}
    ua, rb = sa.get("user_agent") or "crawler", sa.get("robots_for") or "googlebot"
    ya = rb.startswith("yandex")
    how = {"yandexbot": "так, как его видит робот Яндекса", "googlebot": "так, как его видит робот Google",
           "chrome": "так, как его видит обычный посетитель в браузере"}.get(ua, "автоматической проверкой")   # не «программой»: текст попадает и клиенту
    if (ua == "yandexbot") != ya or ua not in ("yandexbot", "googlebot"):
        how += ", запреты robots.txt взяты " + ("для Яндекса" if ya else "для Google")
    return "Сайт проверялся " + how


def _clicks(n):
    """1 переход, 2 перехода, 5 переходов."""
    w = "переход" if n % 10 == 1 and n % 100 != 11 else \
        "перехода" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "переходов"
    return f"{n} {w}"


def _clicks_gen(n):
    """«дальше 1 перехода», «дальше 3 переходов»."""
    return f"{n} " + ("перехода" if n % 10 == 1 and n % 100 != 11 else "переходов")


DEPTH_TAIL = 10   # всё, что дальше, — одной строкой «10 переходов и больше»
DEPTH_SHOW = 100  # сколько адресов показывать по нажатию на строку


def depth_html(summary, pages, client=False):
    """Блок «Сколько переходов от главной»: понятный заголовок, пояснение, глубокие уровни подсвечены,
    хвост склеен, по нажатию на строку — список таких страниц (сначала самые важные по PageRank)."""
    from . import settings
    deep = settings.DEEP_CLICKS
    counts = {}
    for i in summary.get("by_depth") or []:
        if i["d"] is None:
            continue
        k = min(int(i["d"]), DEPTH_TAIL)
        counts[k] = counts.get(k, 0) + i["n"]
    if not counts:
        return ""
    urls = {}
    for pg in pages:
        if pg.get("status") == 200 and pg.get("depth") is not None:
            urls.setdefault(min(int(pg["depth"]), DEPTH_TAIL), []).append(pg)
    total = sum(counts.values())
    far = sum(n for k, n in counts.items() if k > deep)
    mx = max(counts.values())
    rows = []
    for k in sorted(counts):
        n = counts[k]
        label = "главная" if k == 0 else (f"{k} и больше" if k == DEPTH_TAIL else _clicks(k))
        cls = "" if k <= deep else (" far" if k < DEPTH_TAIL and k <= deep + 2 else " vfar")
        lst = sorted(urls.get(k, []), key=lambda pg: -(pg.get("pagerank") or 0))
        more = n - min(len(lst), DEPTH_SHOW)
        links = "".join(f'<li>{_cell(pg["url"])}</li>' for pg in lst[:DEPTH_SHOW])
        tail = (f'<p class="mut">и ещё {_num(more)}.' + ('' if client else ' Полный список: отчёт.xlsx или страницы.csv, '
                'столбец «Глубина».') + '</p>') if more > 0 and links else ""
        row = (f'<span class="bl">{_e(label)}</span><span class="bt"><span style="width:{max(2, 100 * n / mx):.0f}%"></span></span>'
               f'<span class="bn">{_num(n)}</span>')
        if links:
            rows.append(f'<details class="dp{cls}"><summary class="bar">{row}</summary><ol>{links}</ol>{tail}</details>')
        else:
            rows.append(f'<div class="bar dp{cls}">{row}</div>')
    if far:
        verdict = (f'<p class="dpv"><b>Дальше {_clicks_gen(deep)}: {_num(far)} из {_num(total)} страниц '
                   f'({100 * far / total:.0f}%).</b> Выделены цветом. Нажмите на строку, чтобы увидеть эти страницы. '
                   f'Важные из них стоит поднять ближе к главной: ссылкой из меню, каталога или с популярных страниц.</p>')
    else:
        verdict = f'<p class="dpv"><b>Все страницы не дальше {_clicks_gen(deep)} от главной.</b> Это хорошо.</p>'
    return (f'<div class="card"><h3>Сколько переходов от главной до страницы</h3>'
            f'<p class="mut dpx">Сколько раз нужно нажать на ссылку, начиная с главной, чтобы попасть на страницу. '
            f'Поисковики хуже находят и реже обходят глубокие страницы. Хорошо, когда страницы не дальше '
            f'{_clicks_gen(deep)}.</p>{"".join(rows)}{verdict}</div>')


# (до скольких секунд, подпись); цвет как у глубины: дольше порога «медленно» жёлтый, дольше двух порогов красный
SPEED_BUCKETS = [(0.5, "до 0,5 с"), (1, "0,5-1 с"), (2, "1-2 с"), (5, "2-5 с"), (None, "больше 5 с")]


def _sec(x):
    return f"{x:.2f}".replace(".", ",") + " с"


def speed_html(pages, client=False):
    """Блок «Как быстро отвечает сервер»: страницы по времени ответа полосками, как глубина,
    среднее и медиана; по нажатию на строку - страницы, сначала самые медленные. Время - замер при обходе, а у
    самых медленных, перемеренных после обхода по одной, - второй замер (как в проблеме «Сервер долго отвечает»:
    у reestr-primer при обходе медленными вышли 72% страниц, а повторно - единицы)."""
    from . import settings
    vals, re_n = [], 0
    for pg in pages:
        if pg.get("status") != 200 or pg.get("content_type") not in ("text/html", "application/xhtml+xml"):
            continue
        t = pg.get("ttfb") if pg.get("ttfb") is not None else pg.get("elapsed")
        if pg.get("ttfb_recheck") is not None:
            t, re_n = pg["ttfb_recheck"], re_n + 1
        if t is not None:
            vals.append((float(t), pg))
    if not vals:
        return ""
    vals.sort(key=lambda v: -v[0])
    groups = [[] for _ in SPEED_BUCKETS]
    for t, pg in vals:
        i = next(i for i, (hi, _) in enumerate(SPEED_BUCKETS) if hi is None or t <= hi)
        groups[i].append((t, pg))
    ts = sorted(t for t, _ in vals)
    n = len(ts)
    med = ts[n // 2] if n % 2 else (ts[n // 2 - 1] + ts[n // 2]) / 2
    avg = sum(ts) / n
    mx = max(len(g) for g in groups)
    rows = []
    slow_s = settings.SLOW_SECONDS
    for i, ((hi, label), g) in enumerate(zip(SPEED_BUCKETS, groups)):
        if not g:
            continue
        lo = SPEED_BUCKETS[i - 1][0] if i else 0
        cls = "" if lo < slow_s else (" far" if lo < 2 * slow_s else " vfar")
        links = "".join(f'<li>{_cell(pg["url"])} <span class="mut">{_sec(t)}</span></li>' for t, pg in g[:DEPTH_SHOW])
        more = len(g) - min(len(g), DEPTH_SHOW)
        tail = (f'<p class="mut">и ещё {_num(more)}.' + ('' if client else ' Полный список: отчёт.xlsx или страницы.csv, '
                'столбец «Время ответа сервера, с».') + '</p>') if more > 0 else ""
        row = (f'<span class="bl">{_e(label)}</span><span class="bt"><span style="width:{max(2, 100 * len(g) / mx):.0f}%">'
               f'</span></span><span class="bn">{_num(len(g))}</span>')
        rows.append(f'<details class="dp{cls}"><summary class="bar">{row}</summary><ol>{links}</ol>{tail}</details>')
    slow = sum(1 for t in ts if t > settings.SLOW_SECONDS)
    head = f'<p class="dpv"><b>Обычно {_sec(med)}, в среднем {_sec(avg)}.</b> '
    if slow:
        pct = 100 * slow / n
        head += (f'Дольше {settings.SLOW_SECONDS:g} с: {_num(slow)} из {_num(n)} страниц '
                 f'({"меньше 1" if pct < 1 else f"{pct:.0f}"}%), '
                 f'выделены цветом. Нажмите на строку, чтобы увидеть эти страницы.</p>')
    else:
        head += f'Все страницы ответили быстрее {settings.SLOW_SECONDS:g} с. Это хорошо.</p>'
    return (f'<div class="card"><h3>Как быстро отвечает сервер</h3>'
            f'<p class="mut dpx">Сколько секунд проходит от запроса страницы до ответа сервера (без скачивания самой '
            f'страницы). «Обычно» - у половины страниц быстрее, у половины медленнее. Замер сделан во время проверки, '
            f'когда сервер был дополнительно нагружен ею'
            + (f'; самые медленные страницы ({_num(re_n)}) перемерены второй раз после неё, по одной, и здесь взят '
               f'второй замер' if re_n else ', поэтому на деле обычно чуть быстрее')
            + f'. Хорошо, когда страницы отвечают быстрее {settings.SLOW_SECONDS:g} с.</p>{head}{"".join(rows)}</div>')


def _link(u):
    """Адрес в ячейке ссылкой. Скобки внутри - часть адреса (/divan-(seryy)/), «)» без пары и «.,» в конце - нет."""
    tail = ""
    while u and (u[-1] in ".," or (u[-1] == ")" and u.count("(") < u.count(")"))):
        u, tail = u[:-1], u[-1] + tail
    # текст - как в браузере (русские буквы вместо %D0%91…), ссылка - прежний адрес
    return f'<a href="{_e(u)}" target="_blank" rel="noopener">{_e(pretty_url(u))}</a>{_e(tail)}'


def _cell(v):
    s = "" if v is None else str(v)
    parts = s.split("\n")
    out = []
    for part in parts:
        if re.search(r"(?:^|[\s(])https?://", part):
            # ссылкой - только сами адреса: «https://a → https://b», «https://a - с 17 стр.; https://b…»,
            # «ссылки на страницах: 2 (например, https://a/)» (раньше ссылкой становилась вся строка вместе с
            # припиской и вела на несуществующий адрес, а адрес внутри текста не был ссылкой)
            bits = re.split(r"(?<![^\s(])(https?://[^\s;]+)", part)
            out.append("".join(_link(b) if i % 2 else _e(b) for i, b in enumerate(bits)))
        else:
            out.append(_e(part))
    return "<br>".join(out)


def anchors_html(summary):
    rows = summary.get("anchors") or []
    if not rows:
        return ""
    body = "".join(f'<tr><td>{_cell(u)}<div class="mut">{_e(name)}</div></td><td>{_num(n)}</td><td>{_num(t)}</td>'
                   f'<td>{_e(top)}</td></tr>' for u, name, n, t, top in rows)
    # пример - название страницы этого сайта: до 24.10.2026 у всех сайтов стояло «Газовые котлы»
    ex = next((name for _u, name, *_ in rows if name and 3 <= len(name) <= 40), "")
    ex = f" ({quote(ex)})" if ex else ""
    return (f'<h2 class="sec">Какими словами ссылаются на главные страницы</h2><div class="card"><p class="mut" '
            f'style="margin:0 0 8px">Страницы, на которые ведёт больше всего внутренних ссылок. Текст ссылки подсказывает '
            f'поисковику, о чём страница: лучше, когда в нём есть название раздела{_e(ex)}, а не «Каталог» '
            f'или «Подробнее». «Из текста» - ссылки не из меню и подвала: они весят больше.</p>'
            f'<div class="tw" style="margin:0"><table><thead><tr><th>Страница</th><th>Страниц ссылается</th>'
            f'<th>Из них из текста</th><th>Чаще всего ссылаются словами</th></tr></thead><tbody>{body}</tbody></table>'
            f'</div></div>')


SEV_LEGEND = ('<p class="sev-legend">Цвет показывает важность:<i style="background:var(--crit)"></i>красный - критично, '
              'исправлять первым<i style="background:var(--warn)"></i>оранжевый - предупреждение'
              '<i style="background:var(--note)"></i>жёлтый - замечание, для сведения</p>')


def _health_site(summary):
    """Какие проблемы всего сайта сняли проценты здоровья (summary["health_site"], с 15.10.2026)."""
    site = summary.get("health_site") or []
    if not site:
        return ""
    items = "; ".join(f'{_e(quote(x["title"]))} ({_e(x.get("why", ""))}, -{x["minus"]}%)' for x in site)
    return (f' Здесь {_num(summary.get("health_pages", 0))}% страниц без проблем, минус '
            f'{summary.get("health_penalty", 0)}% за проблемы всего сайта: {items}.')


def health_parts_text(summary):
    """«Техника 60%, контент 15%» - из чего сложилось здоровье (summary["health_parts"], с 24.10.2026)."""
    hp = summary.get("health_parts")
    if not hp or summary.get("unchecked"):
        return ""
    return f'техника {hp["tech"]}%, контент {hp["content"]}%'


def _health_parts(summary):
    t = health_parts_text(summary)
    if not t:
        return ""
    return (f'<p style="margin:0 0 8px"><b>По частям: {t}.</b> Техника - сервер, шаблон, ссылки, индексация, скорость '
            f'(правит разработчик). Контент - тексты, Title, Description, H1, alt картинок, карточки товаров и цены '
            f'(правит контент-менеджер). Общее здоровье не выше каждой из частей: страница считается без проблем, только '
            f'если у неё нет проблем ни в технике, ни в контенте.</p>')


def _estimate_block(summary):
    from . import estimate, settings
    return estimate.html_block(summary.get("works") or [], settings.HOUR_RATE)


def _compare_block(summary):
    from .compare import client_html  # compare сам берёт write_csv отсюда
    return client_html(summary.get("compare"), summary.get("history") or ())


def _issues_html(issues, show_rows, client, lab=None):
    """Список проблем по важности (раскрывающиеся строки) и до 5 некритичных-не-замечаний для «С чего начать»."""
    # больше 50 000 строк в Excel не помещается - «по запросу»; импорт здесь: xlsx_report сам импортирует report
    from .xlsx_report import full_list_where
    sev_color = {CRIT: "crit", WARN: "warn", NOTE: "note"}
    sev_intro = {
        CRIT: "Мешает посетителям или поисковикам прямо сейчас. Исправлять в первую очередь.",
        WARN: "Ухудшает сайт, но не ломает его. Исправлять после критичных.",
        NOTE: "Для сведения. Не ошибки, а места, которые стоит проверить глазами.",
    }
    parts, first = [], []
    for sev in (CRIT, WARN, NOTE):
        group = [i for i in issues if i.severity == sev]
        if not group:
            continue
        if not parts:   # что значит цвет - один раз, над списком проблем
            parts.append(SEV_LEGEND)
        parts.append(f'<h2 class="sev-h {sev_color[sev]}">{SEV_RU[sev]} <span>{len(group)}</span></h2>'
                     f'<p class="sev-intro">{sev_intro[sev]}</p>')
        for i in group:
            if sev != NOTE and len(first) < 5:
                first.append(i)
            head = "".join(f"<th>{_e(c)}</th>" for c in i.columns)
            n_show = 5 if i.sitewide else show_rows
            # «pg» - для SHOW_JS: колонка страницы проблемы или колонка «где показать» (show_col: пример страницы,
            # который не считается страницей с проблемой - например, у коммерческих факторов)
            pc = next((c for c in (i.page_col, i.show_col) if isinstance(c, int) and not isinstance(c, bool)), -1)
            pc = -1 if client else pc
            body = "".join("<tr>" + "".join(f'<td{" class=pg" if n == pc else ""}>{_cell(c)}</td>'
                                            for n, c in enumerate(r)) + "</tr>"
                           for r in i.rows[:n_show])
            if client:
                more = (f'<p class="more">Показаны первые {n_show} из {_num(i.count)}. '
                        f'{full_list_where(len(i.rows))}</p>') if i.count > n_show else ""
            else:
                more = (f'<p class="more">Показаны первые {n_show} из {_num(i.count)}. '
                        f'Полный список - в файле <code>проблемы/{i.key}.csv</code></p>') if i.count > n_show else \
                    f'<p class="more">Этот список для Excel: <code>проблемы/{i.key}.csv</code></p>'
            st = ((lab or {}).get(i.key) or {}).get("state", "")
            tag = f' <span class="lbl-tag">{_e(labels.STATES[st])}</span>' if st in ("sent", "wait") and not client else ""
            parts.append(
                f'<details class="issue {sev_color[sev]}" id="{i.key}" data-text="{_e((i.title + " " + i.category).lower())}">'
                f'<summary><span class="dot"></span><span class="cat">{_e(i.category)}</span>'
                f'<span class="it">{_e(i.title)}{tag}</span><span class="cnt">{_e(i.count_text)}</span></summary>'
                f'<div class="expl"><p><b>Что это значит.</b> {_e(i.why)}</p>'
                f'<p><b>Что сделать.</b> {_e(i.fix)}</p></div>' + ("" if client else _label_box(i.key, st)) +
                f'<div class="tw"><table><thead><tr>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>{more}</details>')
    return parts, first


def _label_box(key, state):
    """Выбор метки у проблемы (labels.py). Виден, только когда отчёт открыт из окна программы (LABELS_JS)."""
    opts = "".join(f'<option value="{k}"{" selected" if k == state else ""}>{_e(t)}</option>'
                   for k, t in [("", "без метки")] + list(labels.STATES.items()))
    return (f'<div class="lbl" data-key="{_e(key)}" data-was="{_e(state)}" hidden>Метка работы: <select>{opts}</select> '
            f'<span class="lbl-msg mut"></span></div>')


def _hidden_html(summary, client):
    """Проблемы с меткой «не ошибка»: в отчёте и здоровье их нет, но список виден, и метку можно снять."""
    rows = summary.get("labels_hidden") or []
    if client or not rows:
        return ""
    li = "".join(f'<li>{_e(r["title"])} <span class="mut">({_e(r["count"])})</span> {_label_box(r["key"], "not_error")}</li>'
                 for r in rows)
    return (f'<h2 class="sec">Отмечено «не ошибка» - {len(rows)}</h2><div class="card"><p class="mut" style="margin:0 0 8px">'
            f'Эти проблемы найдены, но вы отметили их «не ошибка» для этого сайта: в отчёт и здоровье они не входят. '
            f'Снимите метку, чтобы вернуть, и нажмите «⋯ → Обновить отчёт».</p><ul>{li}</ul></div>')


# метки работы у проблем: сохраняются через окно программы (/api/labels), в отчёте, открытом файлом, выбора нет
LABELS_JS = """(function(){if(!/^https?:$/.test(location.protocol))return;const site=document.body.dataset.site||'';
document.querySelectorAll('.lbl').forEach(b=>{b.hidden=false;const s=b.querySelector('select'),m=b.querySelector('.lbl-msg');
b.addEventListener('click',e=>e.stopPropagation());
s.onchange=()=>fetch('/api/labels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site:site,key:b.dataset.key,state:s.value})})
.then(r=>r.json()).then(j=>{m.textContent=j.error||((s.value==='not_error'||b.dataset.was==='not_error')?'Сохранено. Чтобы проблема ушла из отчёта и здоровья (или вернулась), нажмите в окне программы «⋯ → Обновить отчёт».':'Сохранено.')})
.catch(()=>{m.textContent='Не сохранилось: окно программы закрыто?'})})})();"""

# клик по адресу страницы сайта в строке проблемы (отчёт открыт из окна) - копия этой страницы, где обведено
# остальное из строки: ссылка, картинка, текст (window/highlight.py). Ctrl+клик и отчёт, открытый файлом, -
# обычный переход на сайт
SHOW_JS = """(function(){const FILE=location.protocol==='file:';
if(!/^https?:$/.test(location.protocol)&&!FILE)return;
const site=(document.body.dataset.site||'').replace(/^www\\./,'');if(!site)return;
const own=u=>{try{const h=new URL(u).hostname.replace(/^www\\./,'');return h===site||h.endsWith('.'+site)}catch(x){return false}};
// обычный клик и клик колёсиком (открыть в новой вкладке) - копия с обводкой; Ctrl+клик - настоящая страница
function open1(q,real){if(!FILE){window.open(q,'_blank');return}
// отчёт открыт файлом: копия - через окно программы (порт 8900-8919, первый, что отвечает), иначе настоящая страница;
// новое окно браузер не дал открыть - в этой же вкладке
const w=window.open('about:blank','_blank'),go2=u=>{if(w)w.location=u;else location.href=u};
(async()=>{for(let p=8900;p<=8919;p++){try{const r=await fetch('http://127.0.0.1:'+p+'/api/clayler');
if(r.ok&&(await r.json()).app==='clayler'){go2('http://127.0.0.1:'+p+q);return}}catch(x){}}go2(real)})()}
const go=e=>{
// «Ошибки на снимках страниц»: адрес под снимком - копия с той же разметкой, что на снимке
const sa=e.target.closest('.psh a[data-key]');
if(sa&&e.button<=1&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&!e.altKey&&own(sa.href)){e.preventDefault();
const cap=((sa.closest('figcaption')||{}).querySelector?sa.closest('figcaption').querySelector('b'):null);
open1('/api/show?url='+encodeURIComponent(sa.href)+'&key='+encodeURIComponent(sa.dataset.key)+'&t='+encodeURIComponent(cap?cap.textContent.slice(0,200):'')+'&shot=1&find=[]',sa.href);return}
const a=e.target.closest('.issue td a[href]');
if(!a||e.button>1||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||!own(a.href))return;
// ячейка с адресом и припиской («… - с 17 стр.») - не адрес страницы
if(/\\s/.test(decodeURIComponent(a.href))||/\\.(jpe?g|png|gif|webp|avif|svg|ico|bmp|pdf|docx?|xlsx?|pptx?|zip|rar|7z|mp4|webm|mp3|css|js|json|xml|txt)$/i.test(new URL(a.href).pathname))return;
const tr=a.closest('tr'),td=a.closest('td'),pg=tr.querySelector('td.pg');   // только колонка страницы, не куда ведёт ссылка
if(td!==(pg||[...tr.children].find(c=>[...c.querySelectorAll('a[href]')].some(x=>own(x.href)))))return;
// искать только то, что стоит на странице (ссылка, картинка, текст, заголовок), а не «Предлагаю», «Тег», числа
const ON_PAGE=/ссылк|внешний адрес|вариант адреса|чаще всего|куда|картинк|изображ|текст ссылки|заголов|\\bh[1-6]\\b|alt|слово|адрес в коде|форм|телефон|значение|нашлось/i;
// «[Р]ассмотрение (латинская Р)» - на странице само слово: убираем скобки-пометки (буква внутри - та, что на сайте)
const raw=t=>/\\((?:латинск|русск)[^)]*\\)\\s*$/i.test(t)?t.replace(/\\s*\\((?:латинск|русск)[^)]*\\)\\s*$/i,'').replace(/\\[(.)\\]/g,'$1'):t;
const heads=[...a.closest('table').querySelectorAll('thead th')].map(th=>th.textContent);
// адрес проблемы - цель ссылки (404, закрыт в robots.txt, одна входящая ссылка…), а в строке есть страница, где эта
// ссылка стоит («Где стоят ссылки», «Откуда», «Например, здесь»): открываем её и обводим ссылку
const col=[...tr.children].indexOf(td),WHERE=/где|откуда|например/i;let page=a.href;const find=[];
if(!WHERE.test(heads[col]||'')){const w=[...tr.children].find((c,n)=>n!==col&&WHERE.test(heads[n]||'')&&c.querySelector('a[href]'));
const wa=w&&[...w.querySelectorAll('a[href]')].find(x=>own(x.href)&&x.href!==a.href&&!/\\s/.test(decodeURIComponent(x.href)));
if(wa){page=wa.href;   // искать на той странице вариант адреса, если он в строке есть («Вариант адреса»), иначе сам адрес
const vi=heads.findIndex((h,n)=>/вариант/i.test(h)&&tr.children[n]&&tr.children[n].querySelector('a[href]')),va=vi>=0&&tr.children[vi].querySelector('a[href]');find.push(va?va.href:a.href)}}
const me=a.textContent.trim();
[...tr.children].forEach((c,n)=>{if(!ON_PAGE.test(heads[n]||''))return;
c.innerText.split('\\n').forEach(t=>{t=raw(t.trim());if(t&&t!==me&&t!=='-'&&!t.startsWith('<')&&!(/^[-+\\d\\s.,%:()]+(мс|с|мб|кб|%)?$/i.test(t)&&t.replace(/\\D/g,'').length<7)&&!find.includes(t))find.push(t)})});
// проблема в коде страницы (title, description, canonical, H1, robots…) - копия с открытой панелью «Что в коде»
const key=(a.closest('details.issue')||{}).id||'';
if(!find.length&&!/title|desc|canon|h1|noindex|robots_meta|og_|hreflang|lang|viewport|keywords|schema|tmpl_meta|js_|head_invalid|head_broken|html_multi|dup_ids|mixed_letters_meta|h2_missing|mobile_diff|mobile_wide|mobile_taps|mobile_small_text/.test(key))return;
e.preventDefault();const its=a.closest('details.issue')&&a.closest('details.issue').querySelector('summary .it');
const it=its&&its.firstChild?its.firstChild.textContent:'';   // название проблемы - в плашку копии
// строка отчёта («Что отличается: слов на странице; Компьютеру: 812; Телефону: 95») - в плашку копии
const det=[...tr.children].map((c,n)=>n===col?'':(heads[n]||'')+': '+c.innerText.trim().replace(/\\s+/g,' ')).filter(Boolean).join('; ').slice(0,400);
const q='/api/show?url='+encodeURIComponent(page)+'&key='+encodeURIComponent(key)+'&d='+encodeURIComponent(det)+'&t='+encodeURIComponent(it.trim().slice(0,200))+'&find='+encodeURIComponent(JSON.stringify(find.slice(0,12)));
open1(q,a.href)};
document.addEventListener('click',go,true);document.addEventListener('auxclick',e=>{if(e.button===1)go(e)},true);
document.addEventListener('mousedown',e=>{if(e.button===1&&e.target.closest('.issue td a[href], .psh a[data-key]'))e.preventDefault()},true)})();"""


def _notes_html(meta, summary, client):
    """Плашки над здоровьем: раздел или список, «предварительный аудит», сайт проверен не полностью, сравнение,
    с JavaScript или без, нет sitemap."""
    left = summary["queue_left"]
    notes = []
    if scope_text(meta.get("scope")):
        notes.append(f'<p class="infobox">{_e(scope_text(meta.get("scope")))}</p>')
    if client:
        notes.append(f'<div class="infobox intro"><p><b>Это предварительный аудит.</b> Здесь собрано всё, что нашла '
                     f'автоматическая проверка сайта: ошибки, замечания и готовые подсказки. Это черновой вариант - '
                     f'не всё из списка обязательно исправлять. Посмотрите, что для вас важно, и выберите, с чем '
                     f'работать дальше; объём и порядок работ обсудим отдельно.</p>'
                     f'<p>Начать лучше с блока «С чего начать»: там правки, которые дадут больше всего пользы. '
                     f'Нажмите на строку проблемы - откроется объяснение, что сделать, и список страниц, где она есть.</p>'
                     + (f'<p>Сайт большой, поэтому в этот раз проверены первые {_num(summary["pages"])} страниц; ещё '
                        f'{_num(left)} найденных страниц в проверку не вошли. На них могут быть и другие проблемы - '
                        f'полную проверку всего сайта можно сделать отдельно.</p>' if left else "") + '</div>')
    if left and not client:
        notes.append(f'<p class="warnbox"><b>Сайт проверен не полностью.</b> Программа остановилась на лимите: '
                     f'ещё {_num(left)} найденных страниц не проверены, поэтому часть проблем в отчёт не попала, '
                     f'а проверка «страниц-сирот» из sitemap пропущена. Чтобы проверить сайт до конца, запустите аудит '
                     f'ещё раз, введите лимит побольше и на вопрос о продолжении ответьте «д» - программа продолжит '
                     f'с того же места.</p>')
    cmp = summary.get("compare")
    if cmp:
        notes.append(f'<p class="infobox"><b>По сравнению с прошлой проверкой</b> ({_e(when(cmp["old_finished"]))}): '
                     f'исправлено проблем - <b>{cmp["fixed"]}</b>, появилось новых - <b>{cmp["added"]}</b>, '
                     f'здоровье {cmp["health_old"]}% → {cmp["health_new"]}%.'
                     + ('' if client else ' <a href="сравнение.html">Что именно изменилось →</a>') + '</p>')
    if client:
        if summary.get("render_js"):
            notes.append(f'<p class="infobox">{_e(seen_as_text(summary))}: каждая страница открывалась в '
                         'браузере, со всеми скриптами. Title, ссылки и текст в отчёте - такие, какими они становятся '
                         'после загрузки страницы.</p>')
    elif summary.get("render_js"):
        notes.append(f'<p class="infobox"><b>Проверка с JavaScript.</b> {_e(seen_as_text(summary))}. Каждая страница открывалась во встроенном браузере '
                     f'(отрендерено: {_num(summary.get("rendered", 0))}). Title, ссылки и текст в отчёте - такие, какими '
                     f'они стали после выполнения скриптов, как их видит поисковик. Что именно меняют скрипты, смотрите в разделе '
                     f'«JavaScript» среди проблем. Если его нет, значит, скрипты ничего важного не меняют.</p>')
    else:
        notes.append(f'<p class="infobox">{_e(seen_as_text(summary))}, без JavaScript: программа читала только HTML, который отдаёт сервер. '
                     'Если сайт сделан на React, Vue, Angular или часть меню и каталога подгружается скриптами, '
                     'запустите проверку ещё раз с JavaScript.</p>')
    if summary["sitemap_urls"] == 0 and not client:
        notes.append('<p class="infobox">Sitemap не найден, поэтому сравнение с sitemap не проводилось.</p>')
    if not client:
        notes.extend(_access_notes(meta))
    return notes


def _country_sub(summary):
    """«🇰🇿 Казахстан · » в строке под заголовком (флаг - картинкой, country.py); подробности - при наведении."""
    from . import country as C
    c = summary.get("country") or {}
    head, why = C.text(c)
    if not head:
        return ""
    tip = "Страна сайта по признакам с самого сайта: " + why if why else ""
    return f'<span title="{_e(tip)}" style="white-space:nowrap">{head}</span> · '


def _access_notes(meta):
    """Для оператора: сайт не пускал программы, главная не открывалась (crawler/access.py), сайт отвечал через раз
    (crawler/shaky.py)."""
    out = []
    acc = meta.get("access") or {}
    if meta.get("ua_switched"):
        out.append(f'<p class="infobox"><b>Сайт не пускает программы.</b> На запрос программы главная отвечала '
                   f'«{_e(acc.get("program"))}», браузеру Chrome - «{_e(acc.get("browser"))}». Поэтому сайт проверялся '
                   f'как браузер Chrome. Стоит проверить в Вебмастере и Search Console (проверка страницы), что '
                   f'роботов поисковиков сайт пускает.</p>')
    elif acc.get("kind") not in (None, "ok", "bots_blocked"):
        out.append(f'<p class="warnbox"><b>{_e(acc["title"])}.</b> {_e(acc["todo"])}</p>')
    sh = meta.get("shaky") or {}
    if sh.get("pauses"):
        why = meta.get("site_down") or ""
        out.append(f'<p class="warnbox"><b>Сайт отвечал через раз.</b> Программа ставила паузы ({sh["pauses"]}, всего '
                   f'{max(1, round(sh.get("seconds", 0) / 60))} мин), шла медленнее и проверила ещё раз адреса без ответа '
                   f'({_num(sh.get("repeated", 0))}).' + (f' Обход прекращён: {_e(why)}.' if why else '') + '</p>')
    return out


def _health_view(summary):
    """(класс цвета, слово, число) для здоровья сайта."""
    health = summary["health"]
    hcls, hword = (("good", "хорошо") if health >= 90 else ("mid", "есть что поправить") if health >= 70
                   else ("bad", "много проблем"))
    if summary.get("unchecked"):   # ни одна страница не открылась: оценивать нечего, а не 0%
        return hcls, "не удалось проверить: ни одна страница сайта не открылась", "-"
    return hcls, hword, f"{health}%"


def _bars(items, key, label):
    mx = max([i["n"] for i in items] or [1])
    return "".join(
        f'<div class="bar"><span class="bl">{_e(label(i[key]))}</span>'
        f'<span class="bt"><span style="width:{max(2, 100 * i["n"] / mx):.0f}%"></span></span>'
        f'<span class="bn">{i["n"]}</span></div>' for i in items)


def _code_label(s):
    """Подпись строки сводки «Что отвечают страницы»: у каждого кода, не только у пяти частых."""
    s = str(s)
    if not s.isdigit():
        return s   # «нет ответа»
    from .analyze.checks.codes import label   # те же смыслы, что в колонке «Что это значит» (codes.MEANING)
    return f"{s} {label(int(s))}"


@dataclass
class _ReportView:
    """Что отличает отчёт для клиента от отчёта оператора."""
    footer: str
    head_brand: str
    brand_css: str
    title: str
    h1: str
    health_note: str
    sub_when: str


def _client_view(meta):
    from . import brand
    who = brand.contacts_line()
    finished = _e(_ru_date((meta.get("finished_at") or "")[:10]))
    footer = ((f'Аудит подготовил: {_e(who)}. ' if who else "")
              + f'Данные на {finished}: сайт со временем меняется, часть замечаний может быть уже исправлена.')
    return _ReportView(footer=footer, head_brand=brand.header_html(), brand_css=brand.BRAND_CSS,
                       title=f'SEO-аудит {meta.get("start", "")} - предварительный',
                       h1='SEO-аудит сайта <span class="mut">· предварительный</span>',
                       health_note=" " + HEALTH_ABOUT, sub_when="проверка " + finished)


def _operator_view(meta, summary):
    footer = ('Все данные лежат в папке этого отчёта и открываются в Excel: <code>страницы.csv</code> - все страницы с их данными,\n'
              '<code>ссылки.csv</code> - ссылки из содержимого страниц, <code>ссылки_сквозные.csv</code> - ссылки из меню и подвала (одной строкой каждая, с числом страниц), <code>проблемы.csv</code> - список проблем, <code>задачи.csv</code> - задания для разработчика по порядку важности, папка <code>проблемы</code> - по файлу на каждую проблему.\n'
              f'<br>Проверка сделана версией программы {_e(meta.get("app_version") or "до 6.3")}.')
    took = D.text(meta, summary["pages"])
    return _ReportView(footer=footer, head_brand="", brand_css="", title=f'SEO-аудит {meta.get("start", "")}',
                       h1="SEO-аудит сайта",
                       health_note=(" " + HEALTH_ABOUT + "\nСравнивать с процентом в SiteAnalyzer или Screaming Frog "
                                    "нельзя: у каждой программы своя формула."),
                       sub_when=(f'проверка {_e(when_range(meta.get("started_at"), meta.get("finished_at")))}'
                                 + (_e(" · " + took) if took else "")))


def _first_list(first):
    """Список «С чего начать»."""
    return "".join(
        f'<li><a href="#{i.key}" onclick="document.getElementById(\'{i.key}\').open=true">{_e(i.title)}</a> '
        f'<span class="mut">- {_e(i.count_text)}</span>'
        + (f' <b>+{str(i.gain).replace(".", ",")}% к здоровью</b>' if getattr(i, "gain", 0) >= 1 else "") + '</li>' for i in first)


def _head_html(view, meta):
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(view.title)}</title>
<style>
{REPORT_CSS}
{GALLERY_CSS}
{problem_shots.CSS}
{SL_CSS}
{web_cover.CSS}
{lightbox.CSS}
{REPORT_CSS_INTRO}
{view.brand_css}
{REPORT_CSS_TAIL}
</style></head><body data-site="{_e(labels.site_key(meta.get("start") or ""))}"><main>
"""


def _hero_html(view, meta, summary, notes, client):
    """Шапка и блок здоровья."""
    site = meta.get("start", "")
    hcls, hword, hnum = _health_view(summary)
    return f"""{view.head_brand}
<h1>{view.h1}</h1>
<p class="sub"><a href="{_e(site)}" target="_blank">{_e(site)}</a> · {_country_sub(summary)}{view.sub_when}</p>
{web_cover.for_report(meta, summary) if client else ""}
{"".join(notes)}
<div class="card hero {hcls}">
<div><div class="num">{hnum}</div><span>здоровье сайта - {hword}</span></div>
<div>
{_health_parts(summary)}<p>Это доля страниц, у которых <b>нет ни критичных проблем, ни предупреждений</b>. Замечания не учитываются.
Проблемы всего сайта (битая ссылка в меню, тяжёлый шаблон, медленный сервер - одна причина почти на всех страницах)
исправляются одной правкой, поэтому не портят каждую страницу, а снимают по 10% (критичная) или 5% (предупреждение),
всего не больше 30%.{_health_site(summary)}</p>
<div class="split">
<i style="width:{100 * summary["pages_clean"] / max(summary["pages"], 1):.1f}%;background:var(--good)"></i>
<i style="width:{100 * summary["pages_warn_only"] / max(summary["pages"], 1):.1f}%;background:var(--warn)"></i>
<i style="width:{100 * summary["pages_crit"] / max(summary["pages"], 1):.1f}%;background:var(--crit)"></i></div>
<div class="leg"><i style="background:var(--good);margin-left:0"></i>без проблем: {_num(summary["pages_clean"])}
<i style="background:var(--warn)"></i>только предупреждения: {_num(summary["pages_warn_only"])}
<i style="background:var(--crit)"></i>есть критичные: {_num(summary["pages_crit"])}</div>
<p class="mut" style="margin-top:8px;font-size:13px">90–100% - хорошо, 70–89% - есть что поправить, ниже 70% - много проблем.{view.health_note}</p>
</div></div>
"""


def _overview_html(meta, issues, pages, summary, first_html, client):
    """Цифры, «С чего начать», шаблоны, сравнение, безопасность, магазин, устройство сайта и сводки."""
    return f"""<div class="grid" style="margin-top:12px">
<div class="card"><b class="big">{_num(summary["pages"])}</b><span>страниц сайта проверено</span></div>
<div class="card"><b class="big">{_num(summary["indexable"])}</b><span>из них могут попасть в поиск</span></div>
<div class="card"><b class="big">{_num(summary["checked"])}</b><span>всего адресов проверено (вместе с картинками и ссылками на другие сайты)</span></div>
</div>
{f'<div class="card"><h3>С чего начать</h3><ol class="first">{first_html}</ol></div>' if first_html else ''}
{report_weight.templates_html(summary)}
{_compare_block(summary)}
{security.html_block(meta.get("security"), issues)}
{shop.html_block(issues, summary)}
<h2 class="sec">Как устроен сайт</h2>
{tech_html(meta.get("site_tech"), _e, country=summary.get("country"))}
<div class="two">
<div class="card"><h3>Что отвечают страницы</h3>{_bars(summary["by_status"], "s", _code_label)}</div>
{depth_html(summary, pages, client)}
{speed_html(pages, client)}
</div>
"""


def _found_html(meta, summary, parts, client):
    """Проблемы и блоки, идущие за ними (снимки, разделы, Вебмастер, Search Console, Метрика)."""
    return f"""<h2 class="sec">Найденные проблемы</h2>
<p class="mut" style="margin:0">Нажмите на строку, чтобы увидеть объяснение, что сделать, и список адресов.</p>
<input id="f" placeholder="Поиск по проблемам: например, title, редирект, sitemap">
<p class="infobox" id="pagef" hidden></p>
{"".join(parts) if parts else "<p>Проблем не найдено.</p>"}
{gallery_html(meta.get("mobile_view"))}
{problem_shots.html_block(summary.get("problem_shots"))}
{buy_clicks.html_block(summary.get("buy_clicks"))}
{consent_forms.html_block(summary.get("consent_forms"))}
{sl_html(meta.get("speed_lab"), _e)}
{sitemap_pic.html_block(summary, cls="card")}
{report_web.html_block(summary, client)}
{sections_html(summary, cls="card")}
{regions_html(summary, cls="card")}
{coverage.html_block(summary.get("coverage"))}
{lost_clicks.html_block(summary.get("lost_clicks"), client)}
{wm_html(meta.get("webmaster"), _e)}
{gsc_html(meta.get("gsc"), _e)}
{ym_html(meta.get("metrika"), _e)}
"""


def _weight_html(pages, summary):
    """Какие страницы сайт считает главными: вес ссылок и PageRank."""
    top = sorted([p for p in pages if p.get("pagerank") is not None], key=lambda p: -p["pagerank"])[:30]
    return f"""<h2 class="sec">Какие страницы сайт считает главными</h2>
{report_weight.weight_html(summary)}
<div class="card"><p class="mut" style="margin:0 0 8px">Внутренний PageRank (1–100) показывает, на какие страницы ведёт больше всего ссылок внутри сайта.
Чем выше число, тем важнее страница в глазах поисковика. Наверху должны быть ваши главные разделы и услуги. Если там
служебные страницы (политика, контакты), значит, внутренние ссылки стоит перераспределить.</p>
<div class="tw" style="margin:0"><table><thead><tr><th>Адрес</th><th>PageRank</th><th>Ссылаются страниц</th><th>Кликов от главной</th><th>Title</th></tr></thead><tbody>
{"".join(f'<tr><td>{_cell(p["url"])}</td><td>{p["pagerank"]}</td><td>{_num(p.get("inlinks") or 0)}</td><td>{p["depth"]}</td><td>{_e(p.get("title"))}</td></tr>' for p in top)}
</tbody></table></div></div>
"""


def _tail_html(view, meta, pages, summary, client):
    """Дополнения, смета и подвал."""
    return f"""{"" if client else extract_html(meta.get("extract_rules"), pages)}
{anchors_html(summary)}
{suggest_out.meta_html(summary, link=not client)}
{suggest_out.links_html(summary, link=not client)}
{sem_client.html_block(summary.get("semantics"), h2="h2", h2_cls="sec", cls="card")}
{fix_files.html_block(summary.get("fix_files"), client)}
{_estimate_block(summary)}
{_hidden_html(summary, client)}
<footer>{view.footer}</footer>
</main>
"""


def _script_html(client):
    return f"""<script>
{REPORT_JS}
{lightbox.JS}
{tablefs.JS}
{"" if client else LABELS_JS}
{"" if client else SHOW_JS}
</script></body></html>"""


def html_report(path, meta, issues, pages, summary, show_rows=300, client=False):
    """client - вариант для клиента (client_report.py): без советов оператору, имён файлов и версии программы,
    со вступлением «предварительный аудит» и вашими контактами."""
    parts, first = _issues_html(issues, show_rows, client, None if client else labels.load(meta.get("start") or ""))
    notes = _notes_html(meta, summary, client)
    view = _client_view(meta) if client else _operator_view(meta, summary)
    doc = "".join((_head_html(view, meta), _hero_html(view, meta, summary, notes, client),
                   _overview_html(meta, issues, pages, summary, _first_list(first), client),
                   _found_html(meta, summary, parts, client), _weight_html(pages, summary),
                   _tail_html(view, meta, pages, summary, client), _script_html(client)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
