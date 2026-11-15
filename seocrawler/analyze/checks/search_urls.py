"""Страницы, которые знает поиск (Яндекс Вебмастер, Google Search Console), а на сайте на них нет ссылок.
Адреса берутся при обходе (crawler/sitemaps.py, check_search_urls, meta «search_urls») и проверяются отдельно."""
from ..common import WARN

NAMES = {"yandex": "Яндекс", "google": "Google"}


def run(ctx):
    meta = ctx.store.get_meta("search_urls", None)
    if not meta or not meta.get("complete") or not meta.get("urls"):
        return
    info = {r["url"]: r for r in ctx.all_checked}
    sm = getattr(ctx, "sm", set())
    shows = {p["url"]: p.get("shows", 0) for p in (ctx.store.get_meta("gsc", None) or {}).get("pages") or []}
    rows = []
    for u, src in meta["urls"].items():
        r = info.get(u)
        if not r or ctx.inl.get(u) or u in ctx.redir:
            continue
        if r["status"] != 200 or r["indexable"] != 1 or r["content_type"] not in ("text/html", "application/xhtml+xml"):
            continue
        row = [u, ", ".join(NAMES[s] for s in src if s in NAMES), "да" if u in sm else "нет"]
        if shows:
            row.append(round(shows.get(u, 0)))
        rows.append(row)
    rows.sort(key=lambda r: (-(r[3] if len(r) > 3 else 0), r[0]))
    cols = ["Адрес", "Где знают", "Есть в sitemap"] + (["Показов в Google за 28 дней"] if shows else [])
    ctx.add("search_orphans", WARN, "Индексация", "Страницы, которые знает поиск, но на сайте на них нет ссылок",
            "Яндекс или Google показывают эти страницы в поиске (данные Вебмастера и Search Console), а при обходе "
            "сайта по ссылкам до них не дойти: ни одна страница на них не ссылается. Посетитель найдёт их только "
            "из поиска, внутреннего веса они почти не получают, и со временем поисковик может убрать их из выдачи.",
            "Если страница нужна, поставьте на неё ссылки из подходящего раздела, меню или похожих страниц. "
            "Если она устарела, поставьте 301-редирект на актуальную страницу или удалите (404/410).",
            cols, rows, page_col=None)
