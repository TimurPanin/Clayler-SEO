"""Одна страница — несколько адресов: сводка по вариантам адреса и местам, где они встречаются."""
from ..common import NOTE, defaultdict, link_rows


def run(ctx):
    add, db, follow, html_ok, indexable = ctx.add, ctx.db, ctx.follow, ctx.html_ok, ctx.indexable
    redir = ctx.redir
    canon_of = {p["url"]: (p["canonical"] or p["canonical_header"]) for p in html_ok
                if p["indexability"] == "Канонизирована" and (p["canonical"] or p["canonical_header"])}
    good = {p["url"] for p in indexable}

    def real_addr(u):
        ch, loop = follow(u)
        f = ch[-1]
        if loop:
            return None
        f = canon_of.get(f, f)
        return f if f in good and f != u else None
    places = defaultdict(lambda: defaultdict(set))  # вариант -> место -> примеры страниц
    for src, dst in link_rows(db, ("src", "dst"), "kind IN ('a','canonical','hreflang') AND internal=1"):
        if dst in redir or dst in canon_of:
            places[dst]["ссылки на страницах"].add(src)
    for (u,) in db.execute("SELECT url FROM sitemap"):
        if u in redir or u in canon_of:
            places[u]["sitemap"].add("sitemap.xml")
    variants = defaultdict(list)
    for v, pl in places.items():
        r = real_addr(v)
        if r:
            how = "редирект" if v in redir else "canonical на основной"
            where = "; ".join(f"{k}: {len(x)}" + (f" (например, {sorted(x)[0]})" if k != "sitemap" else "")
                              for k, x in pl.items())
            variants[r].append([v, how, where])
    mrows = []
    for real, vs in sorted(variants.items(), key=lambda kv: -len(kv[1])):
        for v in vs:
            mrows.append([real, len(vs)] + v)
    add("url_variants", NOTE, "Адреса", "Одна страница - несколько адресов (где какой вариант стоит)",
        "Сводка: у этих страниц на сайте встречается не один адрес, а несколько - старый адрес с редиректом, "
        "вариант без www или через http, неосновная копия с canonical. Для каждого варианта указано, где он стоит: "
        "в ссылках (сколько страниц и пример) или в sitemap. Это те же находки, что в «Ссылки на адреса с редиректом» "
        "и «В sitemap устаревшие адреса», но собранные по страницам.",
        "Разработчику: во всех местах из колонки «Где встречается» заменить вариант на основной адрес. "
        "Ссылки из меню и подвала исправляются один раз в шаблоне.",
        ["Основной адрес", "Вариантов", "Вариант адреса", "Как ведёт на основной", "Где встречается"],
        mrows, page_col=None)

