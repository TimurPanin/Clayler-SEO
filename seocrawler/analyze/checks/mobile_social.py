"""Мобильная версия, соцсети, микроразметка, ошибки HTML (версия 6)."""
from ..common import CRIT, H2_NEEDED_WORDS, NOTE, WARN, defaultdict, re


def run(ctx):
    add, html_ok, indexable = ctx.add, ctx.html_ok, ctx.indexable
    # В проверках старыми версиями этих данных нет — тогда проверки пропускаем, чтобы не врать.
    v6 = any(p.get("content_words") is not None for p in html_ok)
    if v6:
        add("viewport_missing", WARN, "Мобильная версия", "Нет meta viewport - страница не подстроена под телефон",
            "Без тега <meta name=\"viewport\"> телефон показывает страницу как на компьютере, мелко. "
            "Google оценивает сайт по мобильной версии, Яндекс помечает удобные для телефона сайты.",
            "Передайте разработчику: добавить в <head> шаблона "
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.",
            ["Адрес"], [[p["url"]] for p in html_ok if p["viewport"] is None])
        def no_zoom(v):
            v = (v or "").lower().replace(" ", "")
            m = re.search(r"maximum-scale=([\d.]+)", v)
            return "user-scalable=no" in v or "user-scalable=0" in v or (m and float(m.group(1) or 0) < 2)
        add("viewport_zoom", NOTE, "Мобильная версия", "Запрещено увеличивать страницу пальцами",
            "В meta viewport стоит user-scalable=no или maximum-scale меньше 2. Людям со слабым зрением неудобно, "
            "проверки доступности (Lighthouse) это отмечают.",
            "Уберите из meta viewport user-scalable=no и maximum-scale.",
            ["Адрес", "viewport"], [[p["url"], p["viewport"]] for p in html_ok if p["viewport"] and no_zoom(p["viewport"])],
            page_col=None)

        # ошибки HTML, из-за которых поисковик может не увидеть мета-теги
        add("head_broken", CRIT, "Ошибки HTML", "Canonical или meta robots оказались вне <head>",
            "В <head> стоит тег, которому там не место (div, img, p, iframe…). По правилам HTML браузер и поисковик "
            "считают, что на нём <head> закончился и начался <body>. Всё, что ниже, уже в <body>, а canonical, "
            "robots и hreflang Google в <body> не учитывает.",
            "Передайте разработчику: перенести этот тег из <head> в <body> или поставить canonical, robots и hreflang "
            "выше него.",
            ["Адрес", "Тег, который закрыл <head>", "Что оказалось после него"],
            [[p["url"], f"<{p['head_break']}>", p["after_break"]] for p in html_ok
             if p["head_break"] and any(x in (p["after_break"] or "") for x in ("canonical", "robots", "hreflang"))])
        add("head_invalid", NOTE, "Ошибки HTML", "Лишний тег в <head>",
            "В <head> стоит тег, которому там не место. Сейчас после него нет canonical и robots, так что вреда нет, "
            "но если их добавят ниже - поисковик их не увидит.",
            "Передайте разработчику: перенести тег в <body>.",
            ["Адрес", "Тег", "Что после него"],
            [[p["url"], f"<{p['head_break']}>", p["after_break"]] for p in html_ok
             if p["head_break"] and not any(x in (p["after_break"] or "") for x in ("canonical", "robots", "hreflang"))],
            page_col=None)
        add("html_multi", WARN, "Ошибки HTML", "Несколько <html>, <head> или <body> на странице",
            "На странице больше одного <head> или <body> - обычно из-за вставки куска чужого шаблона. "
            "Мета-теги из второго <head> поисковик может не увидеть.",
            "Передайте разработчику: убрать лишние теги.",
            ["Адрес", "Что повторяется"], [[p["url"], p["html_multi"]] for p in html_ok if p["html_multi"]])
        add("dup_ids", NOTE, "Ошибки HTML", "Одинаковые id у разных элементов",
            "id должен быть уникальным на странице. Повторы ломают ссылки-якоря, формы и скрипты, "
            "программы для незрячих путаются.",
            "По желанию: передать разработчику.",
            ["Адрес", "Сколько повторов: примеры"], [[p["url"], p["dup_ids"]] for p in html_ok if p["dup_ids"]],
            page_col=None)

        # микроразметка Schema.org
        add("schema_error", WARN, "Микроразметка", "Ошибка в микроразметке JSON-LD",
            "Блок <script type=\"application/ld+json\"> не читается - в нём ошибка (лишняя запятая, кавычка). "
            "Поисковик такую разметку пропускает целиком.",
            "Проверьте страницу в validator.schema.org и передайте разработчику.",
            ["Адрес", "Блоков с ошибкой"], [[p["url"], p["schema_errors"]] for p in html_ok if p["schema_errors"]])
        types = defaultdict(int)
        for p in indexable:
            for t in (p["schema_types"] or "").split(", "):
                if t:
                    types[t] += 1
        add("schema_none", NOTE, "Микроразметка", "Нет микроразметки Schema.org",
            "Микроразметка сообщает поисковику, что на странице: товар с ценой, организация, статья, хлебные крошки. "
            "Из неё строятся расширенные сниппеты - цена, рейтинг, наличие прямо в выдаче."
            + (" На сайте найдены типы: " + ", ".join(f"{t} ({n})" for t, n in sorted(types.items(), key=lambda x: -x[1])[:10]) + "."
               if types else " На сайте микроразметки нет вовсе."),
            "Для товаров - Product с ценой (Offer), для компании - Organization или LocalBusiness, "
            "для статей - Article, для всех страниц - BreadcrumbList. Передайте разработчику.",
            ["Адрес"], [[p["url"]] for p in indexable if not p["schema_types"]], page_col=None)

        # Open Graph — как страница выглядит, когда ей делятся в мессенджерах и соцсетях
        import json as _json
        def og_missing(p):
            try:
                og = _json.loads(p["og"] or "{}")
            except ValueError:
                og = {}
            return [k for k in ("og:title", "og:image", "og:description") if not og.get(k)]
        ogrows = []
        for p in indexable:
            miss = og_missing(p)
            if miss:
                ogrows.append([p["url"], ", ".join(miss)])
        add("og_missing", NOTE, "Соцсети", "Нет Open Graph (og:title, og:image)",
            "Теги Open Graph задают заголовок, описание и картинку, когда ссылкой делятся в Telegram, ВКонтакте, "
            "WhatsApp. Без них мессенджер показывает что попало или только адрес.",
            "Передайте разработчику: добавить og:title, og:description и og:image в шаблон "
            "(можно брать из title, description и главной картинки страницы).",
            ["Адрес", "Чего нет"], ogrows, page_col=None)

        # meta keywords и H2
        kw = [p for p in indexable if p["keywords"]]
        add("keywords", NOTE, "Контент", "Заполнен meta keywords",
            "Google тег keywords не учитывает (объявил об этом в 2009 году), заметного влияния в Яндексе тоже не видно. "
            "Вреда нет, если там не перечислены десятки слов подряд. Главный минус - конкуренты видят в нём "
            "ваши ключевые запросы.",
            "Можно оставить как есть. Если там длинные списки слов, сократите или очистите.",
            ["Адрес", "keywords"], [[p["url"], p["keywords"][:300]] for p in kw], page_col=None)
        add("h2_missing", NOTE, "Контент", "Длинный текст без подзаголовков H2",
            "На странице больше 300 слов своего текста (без шаблона сайта), но нет ни одного подзаголовка H2. Такой текст трудно "
            "читать, а поисковику сложнее понять, из каких частей он состоит.",
            "Разбейте текст на смысловые части с подзаголовками H2.",
            ["Адрес", "Своих слов на странице"],
            [[p["url"], p.get("own_words", p["content_words"])] for p in indexable
             if (p.get("own_words", p["content_words"]) or 0) > H2_NEEDED_WORDS and not p["h2_count"]],
            page_col=None)

    ctx.v6 = v6
