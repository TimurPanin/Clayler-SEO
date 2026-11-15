"""Дубли и контент."""
from ..common import (CRIT, NEAR_DUP, NOTE, THIN_OWN_WORDS, WARN, defaultdict, near_duplicates, own_blocks, own_text, re,
                      unpack_blocks)


# Отдельная строка страницы, которая говорит, что содержимого нет. «Раздел не найден» сюда не входит: на thehome.ru так
# пишет пустой блок «Похожие товары» и на 1 296 настоящих товарах
_NF_LINE = re.compile(r"(?:(?:элемент|товар|продукт|страница|запись|статья|новость|публикация|объявление|документ)\s+"
                      r"не\s+(?:найден[аоы]?|существует)|страница\s+(?:была\s+)?удалена|товар\s+(?:снят|удал[её]н)"
                      r"(?:\s+с\s+продажи)?|ошибка\s*404|error\s*404|page\s+not\s+found|404\s+not\s+found)[.!]?", re.I)


def _not_found_line(p):
    """Строка «Элемент не найден» (или похожая) отдельным блоком текста страницы - или ""."""
    for ln in unpack_blocks(p) or ():
        t = " ".join(ln.split())
        if len(t) <= 60 and _NF_LINE.fullmatch(t):
            return t
    return ""


def _template_nf(pages, own, sample=300):
    """Строки «…не найден», которые есть и на нормальных страницах (с H1 и своим текстом): это шаблон сайта
    (скрытое окно «Товар не найден» у быстрого просмотра), а не признак пустышки. Иначе каждая короткая карточка
    становилась бы критичной «мягкой 404». У удалённых товаров thehome.ru строки
    «Элемент не найден» на нормальных страницах нет - они остаются. Выборка - первые sample нормальных страниц."""
    from collections import Counter
    normal = [p for p in pages if (p["h1"] or "").strip() and own.get(p["url"], (0,))[0] >= 50][:sample]
    cnt = Counter(_not_found_line(p) for p in normal)
    return {t for t, n in cnt.items() if t and n >= 2}


def _groups_note(ctx, key):
    """У дублей строка списка - группа одинаковых страниц: в заголовке «4 группы, 1 905 стр.», а не «4» (на thehome.ru
    «4» стояло над группой из 1 871 страницы)."""
    from ...fmt import num, plural
    iss = ctx.issues[-1] if ctx.issues and ctx.issues[-1].key == key else None
    if iss and iss.rows:
        n, pages = len(iss.rows), sum(int(r[0]) for r in iss.rows)
        iss.count_note = f"{num(n)} {plural(n, 'группа', 'группы', 'групп')}, {num(pages)} стр."


def run(ctx):
    add, html_ok, indexable, pages = ctx.add, ctx.html_ok, ctx.indexable, ctx.pages
    # Сайт с городами: дубли ищем внутри каждого города; одинаковые страницы разных городов — проверка region_dup
    from ...regions import region_of
    regs = ctx.store.get_meta("regions", None) or []
    city = (lambda u: (region_of(u, regs) or {}).get("url")) if regs else (lambda u: None)
    hg = defaultdict(list)
    for p in indexable:
        if p["content_hash"]:
            hg[(city(p["url"]), p["content_hash"])].append(p)
    add("dup_content", CRIT, "Дубли", "Страницы с полностью одинаковым текстом",
        "Один и тот же текст открывается по разным адресам. Поисковик видит дубли и сам решает, какой адрес "
        "показывать, и это не всегда тот, что нужен вам.",
        "Выберите основной адрес. Остальные перенаправьте на него (301-редирект) или укажите на них "
        "canonical на основной адрес.",
        ["Страниц", "Адреса"], [["%d" % len(g), "\n".join(p["url"] for p in g[:500])] for g in hg.values() if len(g) > 1],
        page_col=1)
    _groups_note(ctx, "dup_content")

    # Свой текст страницы (без шаблона сайта) — версия 6; в старых проверках — текст без <nav>/<footer>
    ctx.own_blocks = own_blocks(indexable)  # и для водности и тошноты (text_quality.py)
    own = own_text(indexable, ctx.own_blocks)
    for p in pages:
        if p["url"] in own:
            p["own_words"] = own[p["url"]][0]
    # Почти дубли: MinHash по своему тексту страницы, порог 90% (как у Screaming Frog)
    # near_duplicates берёт только адрес, отпечаток и полный хеш текста: копировать страницу целиком не нужно
    # (на thehome.ru копии всех страниц - сотни МБ)
    near_src = [{"url": p["url"], "minhash": own[p["url"]][1] if p["url"] in own else p.get("minhash"),
                 "content_hash": p.get("content_hash")} for p in indexable]
    by_city = defaultdict(list)
    for p in near_src:
        by_city[city(p["url"])].append(p)
    near = sorted((g for part in by_city.values() for g in near_duplicates(part, threshold=NEAR_DUP)),
                  key=lambda r: -r[0])
    add("near_dup", WARN, "Дубли", f"Почти одинаковые страницы (совпадение текста {NEAR_DUP:.0%} и больше)",
        ("Свой текст этих страниц почти не отличается (шаблон сайта - меню, шапка, повторяющиеся блоки - не учитывается). "
         if own else "Текст этих страниц почти не отличается (меню и подвал не учитываются). ") +
        "Поисковик может посчитать их "
        "дублями и показывать только одну, а остальные - нет. Часто так выглядят страницы, сделанные по одному "
        "шаблону с заменой пары слов (город, уровень курса, цвет товара).",
        "Сделайте тексты разными по сути: добавьте на каждую страницу то, что отличает её от соседних. "
        "Если страницы действительно дублируют друг друга, оставьте одну, а остальные перенаправьте на неё.",
        ["Страниц", "Похожесть", "Адреса"], near, page_col=2)
    _groups_note(ctx, "near_dup")

    ok_urls = {p["url"] for p in html_ok if p["indexable"] == 1}
    slash = [[u[:-1], u] for u in ok_urls if u.endswith("/") and u.count("/") > 3 and u[:-1] in ok_urls]
    add("slash_dup", CRIT, "Дубли", "Одна страница открывается со слешем и без: /page и /page/",
        "Оба адреса открываются с кодом 200. Для поисковика это две разные страницы с одинаковым содержимым.",
        "Настройте на сервере, чтобы один вариант перенаправлял на другой (301-редирект). Какой оставить - "
        "неважно, главное - один.",
        ["Без слеша", "Со слешем"], slash)

    soft = []
    rx404 = re.compile(r"(^\s*404\b|ошибка\s*404|error\s*404|404\s*error|не\s+найден|не\s+существует|"
                       r"not\s+found|страница\s+удалена|товар\s+снят)", re.I)
    # текст страницы: только явные фразы и только на почти пустой странице - «ничего не найдено» в поиске по
    # каталогу или «товар не найден» в отзыве на большой странице не в счёт
    rx404_text = re.compile(r"(страница\s+не\s+найдена|такой\s+страницы\s+нет|страница\s+(?:была\s+)?удалена|"
                            r"ошибка\s*404|error\s*404|page\s+not\s+found|404\s+not\s+found)", re.I)
    # как выглядит заведомо несуществующая страница этого сайта, если она открылась с кодом 200 (crawler/extra_passes)
    f404 = ctx.store.get_meta("fake404", None) or {}
    home = ctx.home
    f_title = (f404.get("title") or "").strip()
    if f_title and f_title == (home.get("title") or "").strip():
        f_title = ""   # вместо «не найдено» сайт отдаёт главную: по title их не отличить
    if f_title and sum(1 for p in html_ok if (p["title"] or "").strip() == f_title) > max(20, 0.2 * len(html_ok)):
        f_title = ""   # такой title у большой части сайта (один title на всё) - это не признак пустышки
    tpl_nf = None   # строки «…не найден» из шаблона сайта (_template_nf)
    # своего текста у них не посчитать: без шаблона считаем только pages
    only_sitemap = {p["url"] for p in ctx.sitemap_html}
    for p in html_ok + ctx.sitemap_html:
        hay = " ".join(x or "" for x in (p["title"], p["h1"]))
        if rx404.search(hay):
            soft.append([p["url"], p["title"], p["h1"], "в title или H1 написано, что страницы нет"])
        elif f_title and (p["title"] or "").strip() == f_title and p["url"] != home.get("url"):
            soft.append([p["url"], p["title"], p["h1"], "title как у заведомо несуществующей страницы сайта"])
        elif (p.get("word_count") or 0) < 150 and rx404_text.search(p.get("text_sample") or ""):
            soft.append([p["url"], p["title"], p["h1"], "почти пустая страница с текстом «не найдена»"])
        elif p["url"] != home.get("url") and (not (p["h1"] or "").strip()
                                              or (p["url"] not in only_sitemap and own.get(p["url"], (0,))[0] < 50)):
            # удалённый товар Битрикса: код 200, меню и подвал на месте, а вместо товара строка «Элемент не найден»
            # (thehome.ru: 4 299 страниц). Фраза - отдельной строкой; без H1 или почти без своего текста:
            # настоящий товар с такой фразой где-то в виджете сюда не попадёт
            nf = _not_found_line(p)
            if nf and tpl_nf is None:
                tpl_nf = _template_nf(html_ok, own)   # считаем, только если такая строка вообще встретилась
            if nf and nf not in tpl_nf:
                soft.append([p["url"], p["title"], p["h1"], f"вместо содержимого строка «{nf}»"])
    for row in soft:
        if row[0] in only_sitemap:
            row[3] += "; ссылок на сайте на неё нет, адрес есть в sitemap"
    ctx.soft404 = {row[0] for row in soft}
    add("soft404", CRIT, "Коды ответа", "Страница «не найдена», но сервер говорит, что всё в порядке",
        "На странице написано, что её нет, а сервер отвечает поисковику «200 OK». Такие пустышки могут "
        "попасть в выдачу. Это называют «мягкой 404». Как узнали - в колонке «Почему»: по title и H1, по тексту "
        "почти пустой страницы или потому, что страница выглядит так же, как заведомо несуществующий адрес сайта.",
        "Настройте, чтобы несуществующие страницы отдавали код 404. Если страница на самом деле нужна, "
        "проверьте, почему на ней написано «не найдена».",
        ["Адрес", "Title", "H1", "Почему"], soft)

    # сайт на любой адрес отдаёт главную: весь её текст повторяется и считается шаблоном, «своих слов 0» - неправда
    same_as_home = ctx.home_copies | {home.get("url")} if ctx.home_copies else set()
    if own:
        add("thin", NOTE, "Контент", f"Мало своего текста (меньше {THIN_OWN_WORDS} слов без шаблона сайта)",
            "Слова посчитаны без шаблона: меню, шапки, подвала и блоков, которые повторяются на многих страницах. "
            "Для карточек товаров, контактов и форм мало текста - нормально, для категорий, статей и услуг - "
            "повод дописать. Если в списке почти все товары, у них нет описаний.",
            "Проверьте важные страницы из списка, остальные можно пропустить.",
            ["Адрес", "Своих слов", "Всего слов на странице"],
            [[p["url"], own[p["url"]][0], p["word_count"]] for p in indexable if p["url"] in own
             and own[p["url"]][0] < THIN_OWN_WORDS
             and p["url"] not in same_as_home],
            page_col=None)
    else:
        add("thin", NOTE, "Контент", "Мало текста (меньше 200 слов)",
            "На странице мало текста. Для карточек, контактов и форм это нормально, для статей и услуг - "
            "повод дописать.",
            "Проверьте важные страницы из списка, остальные можно пропустить.",
            ["Адрес", "Слов"], [[p["url"], p["word_count"]] for p in indexable if (p["word_count"] or 0) < 200], page_col=None)
    add("encoding", CRIT, "Контент", "Нечитаемый текст из-за кодировки («кракозябры»)",
        "Часть текста не удалось прочитать: сервер сообщает одну кодировку, а страница написана в другой. "
        "Посетители и поисковики могут видеть вместо букв «������».",
        "Передайте разработчику: кодировка в заголовке сервера и в <meta charset> должна совпадать "
        "с настоящей (обычно UTF-8).",
        ["Адрес", "Кодировка", "Откуда взята", "Нечитаемых символов"],
        [[p["url"], p["encoding"], p["encoding_source"], p["bad_chars"]] for p in html_ok if (p["bad_chars"] or 0) > 0])

