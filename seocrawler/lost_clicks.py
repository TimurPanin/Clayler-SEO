"""«Где теряем клики»: Яндекс Вебмастер, Search Console и Метрика вместе с тем, что знает проверка о странице.

Считается при анализе (analyze/checks/lost_clicks.py → summary["lost_clicks"]), показывается в отчёте одним
разделом: 5 главных действий (а не 300 ошибок) и таблица страниц с показами, кликами и отказами.
Откуда цифры:
- Вебмастер: мониторинг запросов за 2 недели (webmaster.analytics, meta webmaster qa_urls и qa_queries);
- Search Console: запросы, страницы и «запрос + страница» за 28 дней (meta gsc);
- Метрика: страницы входа из поиска за 30 дней, визиты и отказы (meta metrika).
Все числа приводятся к месяцу. Выводы - гипотезы: низкая кликабельность бывает из-за рекламы и карт над сайтом,
«отказ» в Метрике - и у того, кто сразу позвонил; на молодом сайте с десятками показов цифры случайны.
Нет ни одного источника - раздел говорит, что подключить, и ничего не выдумывает.
"""
from urllib.parse import unquote, urljoin, urlsplit

from .fmt import esc, num, plural, quote

TOP = 5                 # главных действий
PAGES = 30              # строк в таблице страниц
QUERIES = 50            # строк в таблице «Запрос → страница»
SMALL_SHOWS = 300       # показов в месяц по всем поисковикам меньше - «цифры случайны»
BOUNCE_HIGH, BOUNCE_MIN_VISITS = 35, 20   # как в analyze/checks/metrika.py
HYP = {
    "broken": "Здесь почти без сомнений: страница не работает, а люди на неё идут.",
    "snip": "Гипотеза: мало кликают и тогда, когда над сайтом реклама, карты или готовый ответ. Сначала откройте "
            "выдачу по запросу и посмотрите на свой сниппет рядом с соседями.",
    "near": "Гипотеза: «ещё кликов» - по средней кликабельности 3-го места, у каждого запроса она своя.",
    "bounce": "Гипотеза: отказ в Метрике - визит короче 15 секунд, сюда попадает и тот, кто сразу позвонил "
              "или нашёл адрес. Посмотрите записи визитов в Вебвизоре.",
}


def key(u):
    """Один адрес в разных источниках: без схемы, www, кодировки и слеша в конце."""
    sp = urlsplit(u or "")
    host = (sp.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = unquote(sp.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return host + path + ("?" + unquote(sp.query) if sp.query else "")


def _facts(p, inl):
    """Что проверка знает о странице - коротко, только то, что может мешать."""
    if not p:
        return ["проверка эту страницу не открывала"]
    out = []
    st = p.get("status")
    if st != 200:
        out.append(f"при проверке ответ {st or p.get('error') or 'нет ответа'}")
        return out
    if p.get("indexable") == 0:
        out.append("закрыта от поиска" + (f" ({p['indexability']})" if p.get("indexability") else ""))
    t = (p.get("title") or "").strip()
    if not t:
        out.append("нет title")
    elif len(t) > 70:
        out.append(f"title длинный, {len(t)} знаков")
    elif len(t) < 20:
        out.append(f"title короткий, {len(t)} знаков")
    if not (p.get("description") or "").strip():
        out.append("нет description")
    w = p.get("word_count")
    if w is not None and w < 250:
        out.append(f"мало текста, {num(w)} {plural(w, 'слово', 'слова', 'слов')}")
    n = len(inl.get(p["url"], ()))
    if n <= 2 and p.get("depth"):   # на главную ведут с каждой страницы, даже если ссылки идут на /index.html
        out.append(f"ссылок на неё с сайта: {n}")
    if (p.get("depth") or 0) >= 4:
        out.append(f"{p['depth']} кликов от главной")
    first = p.get("ttfb") if p.get("ttfb") is not None else p.get("elapsed")
    if first and first > 1.5:
        out.append(f"сервер отвечал {first:.1f} с".replace(".", ","))
    return out


def compute(ctx):
    meta = ctx.store.get_meta
    wm, g, ym = meta("webmaster", None) or {}, meta("gsc", None) or {}, meta("metrika", None) or {}
    start = meta("start", "") or ""
    sources = [n for n, d, k in (("Яндекс Вебмастер", wm, "qa_urls"), ("Google Search Console", g, "pages"),
                                 ("Яндекс Метрика", ym, "landing")) if d.get(k)]
    named = (("Яндекс Вебмастер", wm), ("Google Search Console", g), ("Яндекс Метрика", ym))
    res = {"sources": sources, "missing": [n for n, d in named if not d],
           # подключено, но при загрузке были ошибки (сброс входа, нет доступа): «показов нет» тут было бы неправдой
           "failed": [n for n, d in named if d and d.get("errors") and n not in sources]}
    if not sources:
        return res
    from .search_console import NEAR_FROM, NEAR_TO, TARGET, NEAR_MIN_SHOWS, LOW_CTR_MAX_POS, LOW_CTR_MIN_SHOWS
    from .semantics.bukvarix import ctr
    from .webmaster import QA_DAYS
    k_y, k_g = 30 / QA_DAYS, 30 / 28
    by_key = {key(p["url"]): p for p in ctx.pages}

    def full(u):
        return urljoin(start, u) if u.startswith("/") else u

    # страницы: показы, клики, место, визиты, отказы
    rows = {}

    def row(u):
        u = full(u)
        return rows.setdefault(key(u), {"url": u})
    for x in wm.get("qa_urls") or []:
        r = row(x["text"])
        r.update(y_shows=x["shows"] * k_y, y_clicks=x["clicks"] * k_y, y_pos=x["pos"])
    for x in g.get("pages") or []:
        r = row(x["url"])
        r.update(g_shows=x["shows"] * k_g, g_clicks=x["clicks"] * k_g, g_pos=x.get("pos"))
    for x in ym.get("landing") or []:
        if key(full(x["url"])).split("/")[0] != key(start).split("/")[0]:
            continue
        r = row(x["url"])
        r.update(visits=x["visits"], bounce=x["bounce"])

    acts = {}

    def act(kind, u, score, **kw):
        a = acts.setdefault((kind, key(full(u))), {"kind": kind, "url": full(u), "score": 0, "queries": [],
                                                   "src": set(), "more": 0})
        a["score"] += score
        for k, v in kw.items():
            if k == "query":
                a["queries"].append(v)
            elif k == "src":
                a["src"].add(v)
            else:
                a[k] = v
    # запросы со страницей: до тройки недалеко и плохой сниппет - так же, как search_console.lost
    from .search_console import _page_by_query
    gpage = _page_by_query(g)
    qs = [("Яндекс", x["text"], x["other"], x["shows"] * k_y, x["clicks"] * k_y, x["pos"])
          for x in wm.get("qa_queries") or []]
    qs += [("Google", x["q"], gpage.get(x["q"], ""), x["shows"] * k_g, x["clicks"] * k_g, x.get("pos"))
           for x in g.get("queries") or []]
    for src, q, page, shows, clicks, pos in qs:
        if pos is None or not page:
            continue
        if NEAR_FROM <= round(pos) <= NEAR_TO and shows >= NEAR_MIN_SHOWS:
            more = shows * ctr(TARGET) - clicks
            if more >= 1:
                act("near", page, more, query=(more, q, src, pos), src=src)
        elif round(pos) <= LOW_CTR_MAX_POS and shows >= LOW_CTR_MIN_SHOWS and clicks < shows * ctr(pos) / 2:
            more = shows * ctr(pos) - clicks
            if more >= 1:
                act("snip", page, more, query=(more, q, src, pos), src=src)
    for r in rows.values():
        p = by_key.get(key(r["url"]))
        came = r.get("visits") or (r.get("y_clicks") or 0) + (r.get("g_clicks") or 0)
        if p and ((p.get("status") or 0) >= 400 or not p.get("status")) and came >= 1:
            act("broken", r["url"], came * 2, came=came, code=p.get("status") or p.get("error"))
        elif (r.get("visits") or 0) >= BOUNCE_MIN_VISITS and (r.get("bounce") or 0) >= BOUNCE_HIGH:
            act("bounce", r["url"], r["visits"] * r["bounce"] / 200, visits=r["visits"], rate=r["bounce"])
    out = []
    for a in sorted(acts.values(), key=lambda a: -a["score"]):
        a["queries"].sort(key=lambda x: -x[0])
        a["more"] = round(sum(x[0] for x in a["queries"]))
        a["queries"] = [(q, s, round(pos, 1)) for _m, q, s, pos in a["queries"][:3]]
        a["src"] = sorted(a["src"])
        a["facts"] = _facts(by_key.get(key(a["url"])), ctx.inl)
        a["score"] = round(a["score"], 1)
        out.append(a)
    res["actions"] = out[:TOP]
    res["actions_total"] = len(out)
    for r in rows.values():
        r["facts"] = _facts(by_key.get(key(r["url"])), ctx.inl)
    res["pages"] = sorted(rows.values(), key=lambda r: -((r.get("y_shows") or 0) + (r.get("g_shows") or 0)
                                                        + 20 * (r.get("visits") or 0)))[:PAGES]
    res["shows_month"] = round(sum((r.get("y_shows") or 0) + (r.get("g_shows") or 0) for r in rows.values()))
    res["small"] = res["shows_month"] < SMALL_SHOWS and not any((r.get("visits") or 0) >= BOUNCE_MIN_VISITS
                                                                 for r in rows.values())
    res["yandex_qa"] = bool(wm.get("qa_urls") or wm.get("qa_queries"))
    res["yandex_no_qa"] = bool(wm) and not res["yandex_qa"]
    res["queries"] = _queries(qs, full)
    return res


def qkey(q):
    """Один запрос в разных источниках и в Семантике: формы слов и порядок слов не важны."""
    from .semantics import keys, norm, tokens

    def base(t):   # самая короткая основа: «котел» и «котлы» - «котл»
        ks = [k for k in keys(t) if not k.startswith("~")]
        return min(ks, key=lambda k: (len(k), k)) if ks else t
    return " ".join(sorted(base(t) for t in tokens(norm(q or "").replace("-", " "))))   # «шкаф-купе» = «шкаф купе»


def _queries(qs, full):
    """Таблица «Запрос → страница → место и клики»: Яндекс и Google по одному запросу в одной строке.
    qs - [(поисковик, запрос, страница, показы, клики, место)] за месяц, как в compute."""
    rows = {}
    for src, q, page, shows, clicks, pos in qs:
        if not q:
            continue
        r = rows.setdefault(qkey(q), {"q": q})
        p = "y" if src == "Яндекс" else "g"
        r.update({p + "_page": full(page) if page else "", p + "_shows": shows, p + "_clicks": clicks, p + "_pos": pos})
    for r in rows.values():
        r["diff"] = bool(r.get("y_page") and r.get("g_page") and key(r["y_page"]) != key(r["g_page"]))
    return sorted(rows.values(), key=lambda r: -((r.get("y_shows") or 0) + (r.get("g_shows") or 0)))[:QUERIES]


def bind_semantics(d, groups):
    """Группа Семантики у запросов таблицы: groups - {qkey: {"name", "page"}} из semantics.client.summary."""
    if not d or not groups:
        return
    d["sem"] = True
    for r in d.get("queries") or []:
        g = groups.get(qkey(r["q"]))
        if not g:
            continue
        r["group"], r["group_page"] = g["name"], g.get("page") or ""
        shown = [_path(r[k]) for k in ("y_page", "g_page") if r.get(k)]
        r["group_other"] = bool(r["group_page"] and shown and _path(r["group_page"]) not in shown)


def _path(u):
    """Адрес без сайта для сравнения: путь страницы из key()."""
    k = key(u if "//" in u else "http://x" + u)
    return "/" + k.split("/", 1)[1] if "/" in k else "/"


def _what(a):
    qs = ", ".join(esc(quote(q)) for q, _s, _p in a["queries"])
    if a["kind"] == "broken":
        return ("Почините страницу или поставьте 301-редирект на близкую по смыслу рабочую",
                f"Из поиска сюда приходит около {num(round(a['came']))} человек в месяц, а при проверке страница "
                f"отдаёт {esc(a['code'])}.")
    if a["kind"] == "bounce":
        return ("Проверьте первый экран, скорость и вид на телефоне",
                f"Из поиска {num(round(a['visits']))} визитов в месяц, отказов {a['rate']:.0f}%.")
    where = ", ".join(f"{s} - {p:g} место".replace(".", ",") for _q, s, p in a["queries"][:2])
    if a["kind"] == "snip":
        return (f"Перепишите title и description под запросы {qs}",
                f"Сайт высоко ({where}), а кликают меньше половины обычного: около +{num(a['more'])} кликов в месяц.")
    return (f"Усильте страницу под запросы {qs}: текст под запрос, title и H1, ссылки с других страниц",
            f"До первой тройки недалеко ({where}): около +{num(a['more'])} кликов в месяц.")


def html_block(d, client=False):
    """Раздел «Где теряем клики» в отчёте. В отчёте для клиента без подсказки «что подключить»."""
    if not d:
        return ""
    if not d.get("sources"):
        if client:
            return ""
        missing, failed = d.get("missing") or [], d.get("failed") or []
        connected = [n for n in ("Яндекс Вебмастер", "Google Search Console", "Яндекс Метрика")
                     if n not in missing and n not in failed]
        ask = ("Попросите у клиента гостевой доступ, подключите {} в «Подключениях» и нажмите «⋯ → Обновить отчёт»: "
               "сайт заново проверять не нужно.")
        if not connected and not failed:
            text = ('Нет данных Яндекс Вебмастера, Google Search Console и Яндекс Метрики для этого сайта, поэтому '
                    'посчитать, где сайт теряет клики, не из чего. ' + ask.format("их"))
        else:
            # подключено, но показов и визитов из поиска нет (новый или малопосещаемый сайт) - это не «нет данных»;
            # подключено, но не загрузилось - ни то ни другое, причина в разделе этого сервиса ниже
            parts = []
            if connected:
                parts.append(f'Подключено: {", ".join(connected)}, но показов и переходов из поиска по страницам там '
                             f'пока нет (так бывает у нового или малопосещаемого сайта), поэтому считать потери не из чего.')
            if failed:
                parts.append(f'Не загрузилось: {", ".join(failed)} - причина в разделе этого сервиса ниже. Когда '
                             f'доступ заработает, нажмите «⋯ → Обновить отчёт».')
            if missing:
                parts.append(f'Не подключено: {", ".join(missing)}. ' + ask.format("недостающее"))
            text = " ".join(parts)
        return (f'<h2 class="sec">Где теряем клики</h2><div class="card"><p class="mut" style="margin:0">{esc(text)}'
                f'</p></div>')
    parts = [f'<h2 class="sec">Где теряем клики</h2><p class="mut" style="margin:0">Сведено из: '
             f'{esc(", ".join(d["sources"]))}, вместе с тем, что проверка нашла на самих страницах. Все числа '
             f'приведены к месяцу и примерные.'
             + (f' Не подключено: {esc(", ".join(d["missing"]))}.' if d.get("missing") and not client else "")
             + '</p>']
    if d.get("yandex_no_qa") and not client:
        parts.append('<p class="mut">Вебмастер подключён, но показы по страницам из него не пришли (мониторинг '
                     'запросов). Если ошибка видна в разделе «Яндекс Вебмастер», дело в доступе приложения.</p>')
    if d.get("small"):
        parts.append(f'<p class="infobox">Показов мало (около {num(d["shows_month"])} в месяц по всем '
                     f'поисковикам): на таких числах выводы случайны. Ниже - то, на что стоит посмотреть, а не '
                     f'доказанные потери.</p>')
    acts = d.get("actions") or []
    if acts:
        li = []
        for a in acts:
            what, why = _what(a)
            facts = ("<br><span class=\"mut\">Что видит проверка: " + esc("; ".join(a["facts"])) + ".</span>") \
                if a.get("facts") else ""
            li.append(f'<li><b>{esc(what) if a["kind"] in ("broken", "bounce") else what}</b><br>{why} '
                      f'<span class="u">{esc(a["url"])}</span>{facts}<br><span class="mut">{HYP[a["kind"]]}</span></li>')
        more = d.get("actions_total", 0) - len(acts)
        parts.append(f'<div class="card"><h3>{len(acts)} главных {plural(len(acts), "действие", "действия", "действий")}'
                     f'</h3><ol class="first">{"".join(li)}</ol>'
                     + (f'<p class="mut">Ещё {more} - в таблице ниже и в разделах Вебмастера, Search Console и '
                        f'Метрики.</p>' if more > 0 else "") + '</div>')
    else:
        parts.append('<div class="card"><p class="mut" style="margin:0">Явных потерь не видно: нет страниц, где '
                     'много показов и мало кликов, сайт рядом с тройкой или люди из поиска сразу уходят.</p></div>')
    rs = d.get("pages") or []
    if rs:
        f = lambda v: "-" if v is None else num(round(v))
        pos = lambda v: "-" if v is None else f"{v:.1f}".replace(".", ",")
        tr = "".join(f'<tr><td class="u">{esc(r["url"])}</td><td>{f(r.get("y_shows"))}</td><td>{f(r.get("y_clicks"))}</td>'
                     f'<td>{pos(r.get("y_pos"))}</td><td>{f(r.get("g_shows"))}</td><td>{f(r.get("g_clicks"))}</td>'
                     f'<td>{pos(r.get("g_pos"))}</td><td>{f(r.get("visits"))}</td>'
                     f'<td>{"-" if r.get("bounce") is None else f"{r["bounce"]:.0f}%"}</td>'
                     f'<td>{esc("; ".join(r.get("facts") or [])) or "-"}</td></tr>' for r in rs)
        parts.append('<div class="card"><h3>Страницы из поиска</h3><p class="mut">Показы и клики в месяц: Яндекс '
                     '(Вебмастер, за 2 недели), Google (Search Console, за 28 дней); визиты и отказы из поиска - '
                     'Метрика за 30 дней.</p><div class="tw" style="margin:0"><table><thead><tr><th>Страница</th>'
                     '<th>Яндекс показы</th><th>Яндекс клики</th><th>Яндекс место</th><th>Google показы</th>'
                     '<th>Google клики</th><th>Google место</th><th>Визитов из поиска</th><th>Отказы</th>'
                     f'<th>Что видит проверка</th></tr></thead><tbody>{tr}</tbody></table></div></div>')
    parts.append(_queries_html(d))
    return "".join(parts)


def _queries_html(d):
    """Таблица «Запрос → страница»: по каждому запросу страница, место, показы и клики в Яндексе и Google."""
    rs = d.get("queries") or []
    if not rs:
        return ""
    f = lambda v: "-" if v is None else num(round(v))  # noqa: E731
    pos = lambda v: "-" if v is None else f"{v:.1f}".replace(".", ",")  # noqa: E731

    def page(r):
        y, g = r.get("y_page"), r.get("g_page")
        if not (y or g):
            return "-"
        if not r.get("diff"):
            return f'<span class="u">{esc(y or g)}</span>'
        return f'Яндекс: <span class="u">{esc(y)}</span><br>Google: <span class="u">{esc(g)}</span>'

    def group(r):
        if not r.get("group"):
            return "-"
        s = esc(r["group"])
        if r.get("group_other"):
            s += f'<br><span class="mut">под группу - <span class="u">{esc(r["group_page"])}</span>, а поиск показывает другую</span>'
        return s
    sem = d.get("sem")
    tr = "".join(f'<tr><td>{esc(r["q"])}</td><td>{page(r)}</td><td>{pos(r.get("y_pos"))}</td><td>{f(r.get("y_shows"))}</td>'
                 f'<td>{f(r.get("y_clicks"))}</td><td>{pos(r.get("g_pos"))}</td><td>{f(r.get("g_shows"))}</td>'
                 f'<td>{f(r.get("g_clicks"))}</td>' + (f'<td>{group(r)}</td>' if sem else "") + '</tr>' for r in rs)
    n_diff = sum(1 for r in rs if r.get("diff"))
    n_other = sum(1 for r in rs if r.get("group_other"))
    notes = []
    if n_diff:
        notes.append(f"У {n_diff} {plural(n_diff, 'запроса', 'запросов', 'запросов')} Яндекс и Google показывают "
                     f"разные страницы: поиск не понимает, какая из них главная по запросу.")
    if n_other:
        notes.append(f"У {n_other} {plural(n_other, 'запроса', 'запросов', 'запросов')} поиск показывает не ту "
                     f"страницу, что выбрана под группу в Семантике: на нужную страницу стоит добавить запрос в title, "
                     f"H1 и текст и поставить на неё ссылки.")
    return ('<div class="card"><h3>Запрос → страница → место и клики</h3><p class="mut">Главные запросы сайта по '
            'показам: какую страницу по ним показывает поиск, на каком она месте и сколько кликов. В месяц: Яндекс '
            '(Вебмастер, за 2 недели), Google (Search Console, за 28 дней).'
            + (' Группа - из Семантики этого сайта.' if sem else '') + '</p>'
            + "".join(f'<p class="mut">{esc(n)}</p>' for n in notes)
            + '<div class="tw" style="margin:0"><table><thead><tr><th>Запрос</th><th>Страница в поиске</th>'
            '<th>Яндекс место</th><th>Яндекс показы</th><th>Яндекс клики</th><th>Google место</th>'
            '<th>Google показы</th><th>Google клики</th>' + ('<th>Группа в Семантике</th>' if sem else '')
            + f'</tr></thead><tbody>{tr}</tbody></table></div></div>')
