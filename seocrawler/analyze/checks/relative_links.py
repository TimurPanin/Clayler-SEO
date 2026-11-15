"""Одна и та же запись ссылки ведёт с разных страниц на разные адреса: ссылка без «/» в начале.

Сама по себе такая ссылка не ошибка: с тегом <base> или в карточке товара (`reviews/` у каждого товара свой) всё верно.
Ошибка - когда запись, которая с главной ведёт в корень сайта (`otzyvy` → /otzyvy), с другой страницы даёт другой адрес
(/blog/otzyvy). Поэтому смотрим итоговые адреса, а не вид ссылки (пример с nabiullin.com)."""
from urllib.parse import urlsplit

from ... import urls as U
from ..common import WARN, _q


# запись с одним адресом находкой быть не может: на сайте с <base> таких строк тысячи, и в память они не идут
ONE_RAW_MANY_DST = ("SELECT raw, dst, anchor, src FROM rel_links "
                    "WHERE raw IN (SELECT raw FROM rel_links GROUP BY raw HAVING COUNT(*) > 1)")


def _place(url):
    p = urlsplit(url)
    return p.path + ("?" + p.query if p.query else "")


def groups(rows):
    """Строки таблицы rel_links -> [(запись, текст ссылки, адрес в корне, [другие адреса], страница с другим адресом)].
    Корень - по пути, без имени сайта: начальный адрес проверки мог быть разделом или перенаправлять на www."""
    by_raw = {}
    for r in rows:
        by_raw.setdefault(r["raw"], []).append(r)
    out = []
    for raw, items in sorted(by_raw.items()):
        place = _place(U.normalize(raw, "https://site.invalid/") or "")
        others = [r for r in items if _place(r["dst"]) != place]
        if others and len(others) < len(items):   # и в корень, и не в корень: одна запись понимается по-разному
            root = next(r["dst"] for r in items if _place(r["dst"]) == place)
            out.append((raw, items[0]["anchor"] or "", root, sorted(r["dst"] for r in others), others[0]["src"]))
    return out


def run(ctx):
    rows = [[raw, anchor, root, "\n".join(others[:20]), src]
            for raw, anchor, root, others, src in groups(_q(ctx.db, ONE_RAW_MANY_DST))]
    ctx.add("relative_links", WARN, "Ссылки", "Одна и та же ссылка ведёт с разных страниц на разные адреса",
            "В коде ссылка записана без «/» в начале, поэтому браузер отсчитывает её от текущей страницы. С главной "
            "она "
            "ведёт куда нужно, а с других страниц - на другой адрес. Посетитель и поисковик попадают не туда, а на "
            "сайте "
            "появляются лишние адреса.",
            "Передайте разработчику: поставить «/» в начале адреса в ссылке (в шаблоне меню это одна правка) или "
            "указать тег <base href=\"/\"> в шаблоне сайта.",
            ["Как записана ссылка", "Текст ссылки", "Правильный адрес", "Куда ещё ведёт", "Например, здесь"],
            rows, page_col=None)
