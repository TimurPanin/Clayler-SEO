"""Внутренний PageRank и здоровье сайта (итог всех проверок)."""
from . import sections

# что такое процент здоровья и почему он меняется - одной фразой для отчёта, аудита и Excel (разбор отчёта market-primer.ru:
# клиент спрашивал, откуда «57%» и почему в прошлый раз было иначе). Уходит и клиенту: без «программа»
ABOUT = ("Здоровье - внутренняя оценка этого аудита, а не показатель Яндекса или Google: доля страниц без критичных "
         "проблем и предупреждений, минус проблемы всего сайта. Процент меняется, когда на сайте что-то исправили или "
         "сломали, когда проверено другое число страниц и когда в аудит добавлены новые проверки.")
from .common import ALL_PAGES_KEYS, CRIT, NOTE, SITEWIDE_SHARE, TEMPLATE_KEYS, WARN, _q, note_fault, pagerank


def run(ctx):
    store = ctx.store
    MB, all_checked, all_first, db, html_ok = ctx.MB, ctx.all_checked, ctx.all_first, ctx.db, ctx.html_ok
    indexable, issues, left, pages, redir = ctx.indexable, ctx.issues, ctx.left, ctx.pages, ctx.redir
    sitemap_checked, sm, summary_waste, v6 = ctx.sitemap_checked, ctx.sm, ctx.summary_waste, ctx.v6
    shares = {}
    pr = pagerank(db, {p["url"] for p in html_ok}, redir, shares=shares)
    for p in pages:
        p["pagerank"] = pr.get(p["url"])
        p["inlinks"] = len(ctx.inl.get(p["url"], ()))  # со скольких страниц сайта ведут ссылки (как Unique Inlinks у SF)

    # ================= Здоровье сайта
    # Здоровье считается по страницам: рабочие HTML-страницы и адреса страниц с ошибкой (404, 500, нет ответа).
    # Редиректы и файлы (PDF и т. п.) — не страницы: раньше они шли в «здоровые» и завышали процент.
    base = health_base(pages)
    per_issue, site_level, site_why = _page_sets(issues, base)
    bad_c, bad_w = set(), set()
    for iss in issues:
        if id(iss) in per_issue:
            (bad_c if iss.severity == CRIT else bad_w).update(per_issue[id(iss)])
    bad_all = bad_c | bad_w
    by_region = _by_region(ctx, issues, base, bad_c, bad_w)
    try:
        by_section = sections.run(ctx, issues, base, bad_c, bad_w)
    except Exception as e:   # дополнение: его сбой не должен ломать анализ, но и пропасть молча тоже
        note_fault("сводка по разделам", "", e)
        by_section = []
    try:
        from . import web
        link_web = web.run(ctx, issues, base, by_section)
    except Exception as e:   # дополнение: его сбой не должен ломать анализ, но и пропасть молча тоже
        note_fault("паутина ссылок", "", e)
        link_web = None
    try:
        from . import weight
        link_weight = weight.run(ctx, shares, by_section)
    except Exception as e:   # дополнение: его сбой не должен ломать анализ, но и пропасть молча тоже
        note_fault("вес ссылок", "", e)
        link_weight = None
    try:
        from . import templates
        by_template = templates.run(ctx, issues, base, by_section)
    except Exception as e:   # дополнение: его сбой не должен ломать анализ, но и пропасть молча тоже
        note_fault("шаблоны сайта", "", e)
        by_template = None
    # Проблемы всего сайта (одна правка в шаблоне или на сервере) снимают по SITE_PENALTY, всего не больше SITE_PENALTY_MAX
    penalty = min(SITE_PENALTY_MAX, sum(site_level.values()))
    health = max(0, round(100 * (1 - len(bad_all) / len(base))) - penalty) if base else 0
    parts = _health_parts(issues, per_issue, site_level, base)
    # Сколько прибавит здоровье, если исправить только эту проблему: страницы, у которых она — единственная;
    # у проблемы всего сайта - её доля в штрафе
    from collections import Counter
    hits = Counter(u for us in per_issue.values() for u in us)   # у скольких проблем эта страница
    for iss in issues:
        if id(iss) in per_issue and base:
            only = sum(1 for u in per_issue[id(iss)] if hits[u] == 1)
            iss.gain = round(100 * only / len(base), 1)
        if id(iss) in site_level:
            iss.gain = round((getattr(iss, "gain", 0) or 0) + min(site_level[id(iss)], penalty), 1)

    # Проблемы одной настройки сайта (заголовок сервера, строка в шаблоне): если они почти на всех страницах,
    # это одна правка, а не тысячи проблем. Здоровье выше уже посчитано по каждой странице.
    for iss in issues:
        # часть проверок идёт по всем рабочим страницам, часть — только по индексируемым
        total = (len(html_ok) if iss.key in ALL_PAGES_KEYS else len(indexable)) or 1
        total = max(total, len(iss.rows))   # в строках бывают и страницы только из sitemap: «9 000 из 3 000» не писать
        if iss.key in TEMPLATE_KEYS and len(iss.rows) >= 20 and len(iss.rows) >= SITEWIDE_SHARE * total:
            iss.sitewide = f"на всём сайте ({len(iss.rows):,} из {total:,} стр.)".replace(",", " ")
            iss.why += " Проблема почти на всех страницах - значит, это одна настройка сервера или шаблона: исправляется один раз."

    order = {CRIT: 0, WARN: 1, NOTE: 2}
    issues.sort(key=lambda i: (order[i.severity], -(1 if i.sitewide else i.count)))
    summary = {
        "pages": len(pages), "html_ok": len(html_ok), "indexable": len(indexable),
        "checked": len(all_checked), "external": sum(1 for r in all_checked if not r["internal"]),
        "health": health, "regions": by_region, "sections": by_section, "web": link_web,
        "weight": link_weight, "templates": by_template,
        "anchors": getattr(ctx, "anchor_table", []), "meta_suggest": getattr(ctx, "meta_suggest", []),
        "meta_manual": getattr(ctx, "meta_manual", []),
        "link_plan": getattr(ctx, "link_plan", []), "lost_clicks": getattr(ctx, "lost_clicks", None), "pages_crit": len(bad_c), "pages_warn_only": len(bad_w - bad_c),
        "pages_clean": len(base) - len(bad_all), "queue_left": left,
        # из чего сложилось здоровье: доля «чистых» страниц и проблемы всего сайта, каждая со своим штрафом
        "health_pages": round(100 * (1 - len(bad_all) / len(base))) if base else 0,
        "health_site": [{"title": i.title, "severity": i.severity, "minus": site_level[id(i)], "why": site_why[id(i)]}
                        for i in issues if id(i) in site_level],
        "health_penalty": penalty,
        "health_parts": parts,
        "unchecked": not html_ok,   # ни одной рабочей страницы: «не удалось проверить», а не 0%
        "max_pages": store.get_meta("max_pages", None),
        "crit": sum(1 for i in issues if i.severity == CRIT),
        "warn": sum(1 for i in issues if i.severity == WARN),
        "note": sum(1 for i in issues if i.severity == NOTE),
        "sitemap_urls": len(sm), "sitemap_checked": sitemap_checked,
        "render_js": bool(store.get_meta("render_js", False)),
        "seen_as": {k: (store.get_meta("config", None) or {}).get(k) for k in ("user_agent", "robots_for")},
        "rendered": sum(1 for p in html_ok if p.get("js_time") is not None),
        "by_status": _by_status(pages),
        "by_depth": _q(db, """SELECT u.depth AS d, COUNT(*) AS n FROM pages p JOIN urls u ON u.url=p.url
                              WHERE u.internal=1 AND u.kind='page' AND p.status=200 GROUP BY d ORDER BY d"""),
    }
    all_first.sort()
    summary["crawl_waste_pct"] = summary_waste
    # какие данные есть в этой проверке (старые версии программы многое не собирали) — для аудита
    summary["has_v6"] = v6
    summary["has_shop"] = bool(getattr(ctx, "shop_pages", 0) or (ctx.store.get_meta("consent_forms", None) or {}).get("forms")
                               or ((ctx.store.get_meta("consent_forms", None) or {}).get("operator") or {}).get("docs"))  # «Что мешает покупать»: цены и формы прочитаны
    summary["shop_sampled"] = ctx.store.get_meta("shop_sampled", None)
    summary["has_mirrors"] = bool(store.get_meta("mirrors", None))
    summary["median_weight_mb"] = round(all_first[len(all_first) // 2] / MB, 2) if all_first else None
    return issues, pages, summary


SITE_PENALTY = {CRIT: 10, WARN: 5}   # проблема всего сайта снимает столько процентов здоровья
SITE_PENALTY_MAX = 30                # и все вместе - не больше этого
SITE_MIN_PAGES = 20                  # на маленьком сайте каждая страница на счету: «всего сайта» не бывает
# Проблемы «ссылка на странице», где плоха сама ссылка (номер столбца с ней): ссылка из меню или подвала -
# одна правка в шаблоне, а не беда каждой страницы, где меню показано.
LINK_COL = {"broken_links": 1, "tracking_links": 1, "http_links": 1, "mixed_active": 1, "mixed_passive": 1}
TEMPLATE_LINK_SHARE = 0.25           # ссылка из шаблона - стоит хотя бы на такой доле страниц (и на 10+ страницах)
TEMPLATE_LINK_MIN = 10


def _by_status(pages):
    """Сводка «Что отвечают страницы»: [{s: код или «нет ответа», n}]. По тем же правилам, что пункты о кодах
    (codes.bucket): страница с кодом 200, которая пришла обрывком, - «нет ответа», а не «200 работает»."""
    from collections import Counter
    from .checks.codes import bucket
    cnt = Counter("нет ответа" if bucket(p["status"], p["error"], p["location"]) == "noresp" else str(p["status"])
                  for p in pages)
    return [{"s": s, "n": n} for s, n in sorted(cnt.items(), key=lambda kv: (not kv[0].isdigit(), kv[0].zfill(3)))]


def health_base(pages):
    """Страницы, по которым считается здоровье: рабочие HTML-страницы и адреса страниц с ошибкой или необычным ответом
    (все ящики codes.bucket, кроме рабочего ответа и редиректа с адресом - раньше «код от 400 или ошибка»: страницы с
    кодом 204, 206 и редирект без адреса в здоровье не участвовали)."""
    from .checks.codes import bucket
    return {p["url"] for p in pages
            if (p["status"] == 200 and p["content_type"] in ("text/html", "application/xhtml+xml"))
            or bucket(p["status"], p["error"], p.get("location", "?") or "") not in ("ok", "redirect")}


def template_link(n_pages, n_base):
    """Ссылка стоит на n_pages страницах - это ссылка шаблона (меню, подвал)? Одно правило для здоровья и для
    строки «на N страницах» в «Битых ссылках» (analyze/checks/codes.py)."""
    return n_base >= SITE_MIN_PAGES and n_pages >= TEMPLATE_LINK_MIN and n_pages >= TEMPLATE_LINK_SHARE * n_base


# Контентные проблемы - то, что правит контент-менеджер или копирайтер в админке (тексты, заголовки, карточки
# товаров, цены). Всё остальное - техника: сервер, шаблон, ссылки, индексация, скорость.
CONTENT_CATS = {"Title", "Description", "H1", "Контент", "Магазин", "Коммерческие факторы", "Местное SEO", "Соцсети",
                "Города", "Что мешает покупать"}
CONTENT_KEYS = {"img_alt_empty", "img_alt_long", "img_alt_missing", "near_dup", "dup_content"}


def is_content(iss):
    # «Передайте разработчику: …» в совете - правка в шаблоне или на сервере, это техника, даже в разделе Title или
    # «Что мешает покупать» (кодировка, два тега title, формула цены, og:image) - ревизия
    if (iss.fix or "").lstrip().lower().startswith("передайте разработчику"):
        return False
    return iss.category in CONTENT_CATS or iss.key in CONTENT_KEYS


def _health_parts(issues, per_issue, site_level, base):
    """«Здоровье» отдельно по технике и по контенту - по той же формуле, что общее: доля страниц без критичных
    проблем и предупреждений своей части минус штраф за её проблемы всего сайта (не больше SITE_PENALTY_MAX).
    Общее здоровье не выше каждой части: страница «чистая», только если чиста в обеих."""
    if not base:
        return None
    out = {}
    for part, want in (("tech", False), ("content", True)):
        mine = [i for i in issues if is_content(i) == want]
        bad = set().union(*(per_issue[id(i)] for i in mine if id(i) in per_issue))
        pen = min(SITE_PENALTY_MAX, sum(site_level[id(i)] for i in mine if id(i) in site_level))
        out[part] = max(0, round(100 * (1 - len(bad) / len(base))) - pen)
    return out


def _page_sets(issues, base):
    """Страницы, которые портит каждая проблема ({id(Issue): set}), и проблемы всего сайта ({id(Issue): штраф}).
    Проблема всего сайта - одна причина на почти всех страницах (≥ SITEWIDE_SHARE, сервер или шаблон: тяжёлые
    страницы, нет viewport, медленный сервер) или ссылка из меню и подвала. Такие страницы не считаются
    «больными» по отдельности: иначе одна битая ссылка в меню давала здоровье 0% (62 из 78 проверок были ниже 10%).
    Вместо этого проблема снимает SITE_PENALTY процентов."""
    per_issue, site_level, why = {}, {}, {}
    big = len(base) >= SITE_MIN_PAGES
    for iss in issues:
        if iss.page_col is None or iss.severity == NOTE:
            continue
        rows = iss.rows
        col = LINK_COL.get(iss.key)
        if big and col is not None:
            on = {}
            for row in rows:
                if len(row) > col:
                    on.setdefault(row[col], set()).add(row[iss.page_col])
            tpl = {t for t, ps in on.items() if template_link(len(ps), len(base))}
            tpl |= getattr(iss, "group_dsts", set())   # ссылки шаблона, уже собранные одной строкой (codes.py)
            if tpl:
                site_level[id(iss)] = SITE_PENALTY[iss.severity]
                why[id(iss)] = "ссылка в меню или подвале"
                rows = [row for row in rows if len(row) <= col or row[col] not in tpl]
        us = {u for row in rows for u in str(row[iss.page_col]).split("\n") if u in base}
        if big and len(us) >= SITEWIDE_SHARE * len(base):
            site_level[id(iss)] = SITE_PENALTY[iss.severity]
            why[id(iss)] = f"на {round(100 * len(us) / len(base))}% страниц"
            us = set()
        per_issue[id(iss)] = us
    return per_issue, site_level, why


def _by_region(ctx, issues, base, bad_c, bad_w):
    """Сводка по городам (режим «Сайт с городами»): страниц, здоровье, главные проблемы в каждом городе."""
    regs, reg = getattr(ctx, "regions", None), getattr(ctx, "region_of", None)
    if not regs or not reg:
        return []
    out = []
    for r in regs:
        mine = {u for u in base if reg(u) is r}
        if not mine:
            out.append({"city": r["city"] or "основной сайт", "url": r["url"], "how": r["how"], "pages": 0,
                        "health": None, "crit": 0, "warn": 0, "top": []})
            continue
        top = []
        for iss in issues:
            if iss.page_col is None or iss.severity == NOTE:
                continue
            n = sum(1 for row in iss.rows for u in str(row[iss.page_col]).split("\n") if u in mine)
            if n:
                top.append((0 if iss.severity == CRIT else 1, -n, iss.title, n))
        top.sort()
        bad = (bad_c | bad_w) & mine
        out.append({"city": r["city"] or "основной сайт", "url": r["url"], "how": r["how"], "pages": len(mine),
                    "health": round(100 * (1 - len(bad) / len(mine))), "crit": len(bad_c & mine),
                    "warn": len((bad_w - bad_c) & mine), "top": [f"{t} - {n}" for _, _, t, n in top[:3]]})
    return out
