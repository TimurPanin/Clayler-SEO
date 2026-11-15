"""Примерный вес страницы."""
from ..common import PAGE_HEAVY_MB, TEMPLATE_HEAVY_MB, WARN, defaultdict


def run(ctx):
    KB, add, db, html_ok, res_info = ctx.KB, ctx.add, ctx.db, ctx.html_ok, ctx.res_info
    sizes = {u: (i.get("size") or 0) for u, i in res_info.items() if i.get("status") == 200}
    eager, lazy_imgs = defaultdict(set), defaultdict(set)
    for page, src, loading in db.execute("SELECT page, src, loading FROM images"):
        (lazy_imgs if loading == "lazy" else eager)[page].add(src)
    for r in db.execute("SELECT page, src FROM resources WHERE type IN ('css','js')"):
        eager[r[0]].add(r[1])
    weights = []
    MB = 1024 * KB
    all_first = []
    for p in html_ok:
        first = (p["size"] or 0) + sum(sizes.get(f, 0) for f in eager.get(p["url"], ()))
        later = sum(sizes.get(f, 0) for f in lazy_imgs.get(p["url"], set()) - eager.get(p["url"], set()))
        all_first.append(first)
        if first > PAGE_HEAVY_MB * MB:
            weights.append([p["url"], round(first / MB, 1), round((first + later) / MB, 1),
                            len(eager.get(p["url"], ())), len(lazy_imgs.get(p["url"], ()))])
    weights.sort(key=lambda x: -x[1])
    add("page_weight", WARN, "Скорость", f"Тяжёлые страницы (больше {PAGE_HEAVY_MB} МБ при открытии)",
        "Сколько весит страница при открытии: HTML плюс картинки, стили и скрипты, которые браузер загружает сразу. "
        "«Ленивые» картинки (loading=\"lazy\" или data-src), которые грузятся только при прокрутке, посчитаны отдельно "
        "в колонке «Всего». Шрифты, видео и то, что догружают сами скрипты, не учтены.",
        "Начните с тяжёлых картинок (раздел «Картинки»): обычно основной вес именно в них. Картинкам ниже первого "
        "экрана добавьте loading=\"lazy\" - они перестанут тормозить открытие страницы.",
        ["Страница", "МБ при открытии", "МБ всего, с прокруткой", "Файлов сразу", "Ленивых картинок"], weights)

    # Вес шаблона: файлы, которые грузятся сразу на большинстве страниц (меню, шапка, подвал). Если шаблон сам тяжёлый,
    # «тяжёлые страницы» — это одна причина на всём сайте, и исправлять надо её, а не тысячи страниц.
    if len(html_ok) >= 20:
        cnt = defaultdict(int)
        for p in html_ok:
            for f in eager.get(p["url"], ()):
                cnt[f] += 1
        tmpl = [f for f, n in cnt.items() if n >= 0.5 * len(html_ok) and sizes.get(f)]
        tmpl_size = sum(sizes[f] for f in tmpl)
        if tmpl_size > TEMPLATE_HEAVY_MB * MB:
            tmpl.sort(key=lambda f: (-sizes[f], f))
            add("template_weight", WARN, "Скорость",
                f"Шаблон сайта сам весит {tmpl_size / MB:.1f} МБ - на каждой странице".replace(".", ","),
                "Эти файлы (картинки меню, шапки, подвала, стили, скрипты) грузятся сразу на большинстве страниц сайта. "
                "Браузер скачивает картинки, даже если меню скрыто до нажатия. Поэтому страницы тяжёлые независимо "
                "от своего содержимого.",
                "Сожмите картинки из списка (WebP, размер под показ), картинки скрытого меню грузите лениво "
                "(loading=\"lazy\" или при открытии меню). Исправляется один раз в шаблоне - и легче станет весь сайт.",
                ["Файл", "КБ", "На скольких страницах"],
                [[f, round(sizes[f] / KB), cnt[f]] for f in tmpl], page_col=None)

    ctx.MB, ctx.all_first = MB, all_first
