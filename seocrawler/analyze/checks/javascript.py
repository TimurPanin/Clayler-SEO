"""JavaScript: что меняется после выполнения скриптов."""
from ..common import CRIT, NOTE, WARN


def run(ctx):
    add, html_ok, pages = ctx.add, ctx.html_ok, ctx.pages
    rendered_all = [p for p in html_ok if p.get("js_time") is not None]
    # страницы с JS-редиректом не сравниваем: после скриптов это уже другая страница
    rendered = [p for p in rendered_all if not p.get("js_redirect")]
    if rendered_all:
        def norm(x):
            return " ".join((x or "").split()).lower()

        def changed(field_raw, field_js):
            only, diff = [], []
            for p in rendered:
                a, b = norm(p[field_raw]), norm(p[field_js])
                if b and not a:
                    only.append([p["url"], p[field_js]])
                elif a and b and a != b:
                    diff.append([p["url"], p[field_raw], p[field_js]])
            return only, diff

        t_only, t_diff = changed("raw_title", "title")
        add("js_title_only", WARN, "JavaScript", "Title появляется только после JavaScript",
            "В исходном коде страницы заголовка нет - его подставляет скрипт. Google выполнит скрипт, но позже, "
            "а роботы, которые JavaScript не выполняют, увидят страницу без заголовка.",
            "Передайте разработчику: title должен быть в HTML, который отдаёт сервер (серверный рендеринг).",
            ["Адрес", "Title после JavaScript"], t_only)
        add("js_title_diff", WARN, "JavaScript", "JavaScript меняет title",
            "В исходном коде один заголовок, а после выполнения скриптов - другой. Поисковики могут показать любой из них.",
            "Сделайте так, чтобы сервер сразу отдавал правильный title.",
            ["Адрес", "Title в исходном HTML", "Title после JavaScript"], t_diff)
        d_only, d_diff = changed("raw_description", "description")
        add("js_desc", NOTE, "JavaScript", "Description добавляется или меняется скриптом",
            "Описание в исходном коде отсутствует или отличается от того, что получается после скриптов.",
            "Лучше, чтобы сервер сразу отдавал правильный description.",
            ["Адрес", "В исходном HTML", "После JavaScript"],
            [[r[0], "", r[1]] for r in d_only] + d_diff, page_col=None)
        h_only, h_diff = changed("raw_h1", "h1")
        add("js_h1", WARN, "JavaScript", "H1 появляется только после JavaScript",
            "Главного заголовка нет в исходном коде, его рисует скрипт.",
            "Передайте разработчику: H1 должен быть в HTML от сервера.",
            ["Адрес", "H1 после JavaScript"], h_only)
        canon = []
        for p in rendered:
            a, b = p["raw_canonical"] or "", p["canonical"] or ""
            if a and b and a != b:
                canon.append([p["url"], a, b, "меняется"])
            elif b and not a:
                canon.append([p["url"], "-", b, "только после JavaScript"])
        add("js_canonical", CRIT, "JavaScript", "Canonical меняется или появляется только после JavaScript",
            "Google прямо рекомендует не менять canonical скриптом: он может взять значение из исходного кода, "
            "а может - после скриптов. Результат непредсказуем.",
            "Передайте разработчику: canonical должен быть в HTML от сервера и не меняться скриптами.",
            ["Адрес", "Canonical в исходном HTML", "После JavaScript", "Что происходит"], canon)
        rob_removed, rob_added = [], []
        for p in rendered:
            a = "noindex" in (p["raw_robots"] or "").lower()
            b = "noindex" in (p["meta_robots"] or "").lower()
            if a and not b:
                rob_removed.append([p["url"], p["raw_robots"], p["meta_robots"] or "-"])
            elif b and not a:
                rob_added.append([p["url"], p["raw_robots"] or "-", p["meta_robots"]])
        add("js_noindex_removed", CRIT, "JavaScript", "noindex в исходном коде, скрипт его убирает",
            "Google видит noindex ещё до выполнения скриптов и дальше страницу не обрабатывает. "
            "То, что скрипт потом убирает noindex, уже не поможет - страница не попадёт в поиск.",
            "Если страница должна быть в поиске, уберите noindex из HTML, который отдаёт сервер.",
            ["Адрес", "Robots в исходном HTML", "После JavaScript"], rob_removed)
        add("js_noindex_added", WARN, "JavaScript", "Скрипт добавляет noindex",
            "В исходном коде запрета на индексацию нет, а после выполнения скриптов он появляется. "
            "Робот без JavaScript проиндексирует страницу, а Google после рендеринга - нет.",
            "Решите, должна ли страница быть в поиске, и укажите это прямо в HTML от сервера.",
            ["Адрес", "Robots в исходном HTML", "После JavaScript"], rob_added)
        jl = [[p["url"], p["js_only_links_count"], p["js_only_links"]] for p in rendered if (p["js_only_links_count"] or 0) > 0]
        jl.sort(key=lambda r: -r[1])
        add("js_links", WARN, "JavaScript", "Ссылки, которые появляются только после JavaScript",
            "Эти ссылки на страницы вашего сайта скрипт дорисовывает уже в браузере. Google их найдёт, но позже, "
            "а роботы, которые JavaScript не выполняют, их не увидят вовсе. Если так устроено меню или каталог, "
            "часть сайта может плохо индексироваться.",
            "Важные ссылки (меню, каталог, пагинация) должны быть обычными ссылками <a href> прямо в HTML от сервера.",
            ["Страница", "Ссылок только в JS", "Примеры"], jl)
        txt = [[p["url"], p["raw_words"], p["word_count"], p.get("js_text_sample") or ""] for p in rendered
               if (p["word_count"] or 0) - (p["raw_words"] or 0) >= 100 and (p["word_count"] or 0) > 1.5 * (p["raw_words"] or 0)]
        add("js_text", WARN, "JavaScript", "Основной текст появляется только после JavaScript",
            "В исходном коде текста намного меньше, чем видит посетитель: остальное подгружает скрипт. "
            "Поисковики, которые скрипты не выполняют или выполняют с задержкой, увидят страницу почти пустой.",
            "Проверьте сами: откройте страницу, нажмите Ctrl+U (исходный код) и поищите фразу из последней колонки. "
            "Если её там нет, текст действительно добавляет скрипт. Для важного текста (описание курса, цены) "
            "попросите разработчика выводить его сразу в HTML.",
            ["Адрес", "Слов в исходном HTML", "Слов после JavaScript", "Пример текста, которого нет в HTML"], txt)
        jsr = [[p["url"], p["js_redirect"]] for p in pages if p.get("js_redirect")]
        add("js_redirects", WARN, "JavaScript", "Редиректы через JavaScript",
            "Страница перенаправляет посетителя скриптом, а не ответом сервера. Google такие редиректы понимает, "
            "но хуже и медленнее, чем обычный 301.",
            "Замените на редирект сервера (301).",
            ["Адрес", "Куда перенаправляет скрипт"], jsr)
        blk = [[p["url"], p["js_blocked"]] for p in rendered if p["js_blocked"]]
        add("js_blocked", WARN, "JavaScript", "robots.txt закрывает скрипты или стили",
            "Файлы JavaScript или CSS, нужные для отрисовки страницы, закрыты в robots.txt. Google их не загрузит "
            "и может увидеть страницу сломанной.",
            "Откройте эти файлы в robots.txt.",
            ["Страница", "Закрытые файлы"], blk, page_col=None)
        jerr = [[p["url"], p["js_error"]] for p in rendered_all if p["js_error"]]
        add("js_fail", NOTE, "JavaScript", "Страницы, которые не удалось отрендерить",
            "Встроенный браузер не смог открыть страницу со скриптами (например, не дождался загрузки). "
            "Для них в отчёте данные только из исходного HTML.",
            "Откройте страницы в браузере. Если медленные, попробуйте проверку с большим временем ожидания.",
            ["Адрес", "Ошибка"], jerr, page_col=None)

