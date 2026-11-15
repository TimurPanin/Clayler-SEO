"""Сквозные ссылки (меню, подвал) на закрытые и неосновные страницы."""
from ..common import WARN


def run(ctx):
    add, all_checked, html_ok, inl = ctx.add, ctx.all_checked, ctx.html_ok, ctx.inl
    sw_limit = max(20, int(0.3 * len(html_ok)))
    idx_by = {r["url"]: r for r in all_checked}
    sw_rows = []
    for dst, srcs in inl.items():
        if len(srcs) < sw_limit:
            continue
        r = idx_by.get(dst)
        if not r:
            continue
        why = {"noindex": "закрыта noindex", "Канонизирована": "canonical на другую страницу"}.get(r["indexability"])
        if why:
            sw_rows.append([dst, why, len(srcs)])
    sw_rows.sort(key=lambda x: -x[2])
    add("sitewide_to_closed", WARN, "Ссылки", "Ссылки из меню или подвала на закрытые страницы",
        "Эти ссылки стоят почти на каждой странице (меню, шапка, подвал), но ведут на страницу, закрытую от поиска "
        "(noindex) или указывающую canonical на другую. Робот проходит по ним с каждой страницы - впустую, "
        "и внутренний вес уходит туда, где он не нужен. Ссылки на редиректы - в «Ссылки на адреса с редиректом».",
        "Если страница нужна посетителям (корзина, вход) - это нормально, можно оставить. Если нет, уберите ссылку "
        "из шаблона или откройте страницу для поиска; для canonical - поставьте ссылку сразу на основной адрес.",
        ["Куда ведёт", "Что не так", "На скольких страницах"], sw_rows, page_col=None)

