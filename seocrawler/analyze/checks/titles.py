"""Title / Description / H1."""
import re

from ..common import CRIT, DESC_LONG, DESC_SHORT, NOTE, TITLE_LONG, TITLE_SHORT, WARN, defaultdict
from .content import _not_found_line


def run(ctx):
    add, html_ok, indexable = ctx.add, ctx.html_ok, ctx.indexable
    # страницы только из sitemap, кроме пустых («Элемент не найден»): тем нужен код 404, а не заголовок (soft404)
    sitemap_live = [p for p in ctx.sitemap_html if not _not_found_line(p)]
    sitemap_live_idx = [p for p in sitemap_live if p["indexable"] == 1]
    def dup_groups(field_):
        g = defaultdict(list)
        for p in indexable:
            v = (p[field_] or "").strip().lower()
            if v:
                g[v].append(p)
        return [ps for ps in g.values() if len(ps) > 1]

    add("title_missing", CRIT, "Title", "Нет заголовка title",
        "Title - это заголовок страницы, который поисковик показывает в выдаче крупным синим текстом. "
        "Без него поисковик придумает заголовок сам, и обычно неудачно.",
        "Напишите для каждой страницы свой title: о чём страница и ключевое слово, по которому её ищут.",
        ["Адрес"], [[p["url"]] for p in html_ok + sitemap_live if not (p["title"] or "").strip()])
    add("title_dup", WARN, "Title", "Одинаковый title у разных страниц",
        "Несколько страниц называются одинаково. Поисковику трудно понять, какую из них показывать, "
        "и в выдаче они неотличимы. Иногда это признак того, что одна страница открывается по нескольким адресам.",
        "Сделайте title уникальным для каждой страницы. Если это одна и та же страница по разным адресам, "
        "оставьте один адрес, а остальные перенаправьте на него.",
        ["Title", "Страниц", "Адреса"], [[g[0]["title"], len(g), "\n".join(p["url"] for p in g[:500])] for g in dup_groups("title")],
        page_col=2)
    add("title_long", NOTE, "Title", f"Длинный title (больше {TITLE_LONG} символов)",
        "Google показывает в выдаче примерно 55–70 символов заголовка, остальное обрезает многоточием. "
        "Яндекс обычно показывает заголовок длиннее. Точная длина зависит от ширины букв и экрана.",
        "Не ошибка. Проверьте, что самое важное стоит в начале заголовка, а хвост (например, название компании) "
        "можно и потерять.",
        ["Адрес", "Символов", "Title"],
        [[p["url"], len(p["title"]), p["title"]] for p in indexable if p["title"] and len(p["title"]) > TITLE_LONG],
        page_col=None)
    add("title_short", NOTE, "Title", f"Короткий title (меньше {TITLE_SHORT} символов)",
        "Короткий заголовок мало говорит о странице и упускает слова, по которым её могли бы найти.",
        "Добавьте, о чём страница: услуга, город, особенность.",
        ["Адрес", "Символов", "Title"],
        [[p["url"], len(p["title"]), p["title"]] for p in indexable if p["title"] and len(p["title"]) < TITLE_SHORT],
        page_col=None)
    add("title_multi", WARN, "Title", "Несколько тегов title в коде страницы",
        "В коде страницы заголовок указан дважды. Обычно это ошибка шаблона сайта.",
        "Передайте разработчику: оставить один тег title.",
        ["Адрес", "Сколько"], [[p["url"], p["title_count"]] for p in html_ok if (p["title_count"] or 0) > 1])

    add("desc_missing", WARN, "Description", "Нет описания (meta description)",
        "Description - короткий текст под заголовком в выдаче. Без него поисковик сам возьмёт кусок текста "
        "со страницы, часто случайный.",
        "Напишите 1–2 предложения: что человек найдёт на странице и почему стоит зайти.",
        ["Адрес"], [[p["url"]] for p in indexable + sitemap_live_idx if not (p["description"] or "").strip()])
    add("desc_dup", WARN, "Description", "Одинаковое описание у разных страниц",
        "У нескольких страниц одинаковый description - в выдаче они выглядят как близнецы.",
        "Сделайте описание уникальным для каждой страницы.",
        ["Description", "Страниц", "Адреса"],
        [[g[0]["description"][:150], len(g), "\n".join(p["url"] for p in g[:500])] for g in dup_groups("description")],
        page_col=2)
    add("desc_long", NOTE, "Description", f"Длинное описание (больше {DESC_LONG} символов)",
        "В выдаче покажется только начало, остальное обрежется.",
        "Не ошибка. Проверьте, что главное сказано в первых 150 символах.",
        ["Адрес", "Символов"], [[p["url"], len(p["description"])] for p in indexable
                                if p["description"] and len(p["description"]) > DESC_LONG], page_col=None)
    add("desc_short", NOTE, "Description", f"Короткое описание (меньше {DESC_SHORT} символов)",
        "Описание слишком короткое, чтобы убедить человека зайти на страницу.",
        "Допишите одно-два предложения о пользе страницы.",
        ["Адрес", "Символов", "Description"], [[p["url"], len(p["description"]), p["description"]] for p in indexable
                                              if p["description"] and len(p["description"].strip()) < DESC_SHORT],
        page_col=None)

    add("h1_missing", WARN, "H1", "Нет главного заголовка H1",
        "H1 - главный заголовок на самой странице (крупный текст вверху). Он помогает и человеку, "
        "и поисковику сразу понять тему страницы.",
        "Добавьте на страницу один заголовок H1 с её темой.",
        ["Адрес"], [[p["url"]] for p in indexable + sitemap_live_idx if not p["h1_count"]])
    add("h1_multi", NOTE, "H1", "Несколько H1 на странице",
        "Не критично, но обычно это ошибка вёрстки: логотип или блоки оформлены как главный заголовок.",
        "Передайте разработчику: оставить один H1, остальные сделать H2.",
        ["Адрес", "Сколько", "Заголовки H1"], [[p["url"], p["h1_count"], p["h1"]] for p in indexable if (p["h1_count"] or 0) > 1],
        page_col=None)
    # заготовки шаблона, которые сайт не подставил: «Мебель с {$dveri_t} без декора» (lk-fabrika, 15.10.2026)
    tmpl_rx = re.compile(r"\{\$?[A-Za-z_][\w.]*(?:\|\w+)*\}|\{\{[^}]{1,40}\}\}|#[A-Z][A-Z_]{2,}#|%[a-z_]{3,}%|\[\[[^\]]{1,40}\]\]")
    tmpl = []
    for p in html_ok:
        for where, txt in (("title", p["title"]), ("H1", p["h1"]), ("description", p["description"])):
            m = tmpl_rx.search(txt or "")
            if m:
                tmpl.append([p["url"], where, m.group(0), txt])
    # и в текстах ссылок (меню каталога): посетитель видит «{$dveri_t}» прямо на сайте; одна строка на текст ссылки
    seen = set()
    for src, anchor, n in ctx.db.execute(
            "SELECT MIN(src), anchor, COUNT(DISTINCT src) FROM links WHERE kind='a' AND internal=1 AND (anchor LIKE '%{%' "
            "OR anchor LIKE '%#%' OR anchor LIKE '%[[%' OR anchor LIKE '%!%%' ESCAPE '!') GROUP BY anchor"):
        m = tmpl_rx.search(anchor or "")
        if m and anchor not in seen:
            seen.add(anchor)
            tmpl.append([src, f"текст ссылки (на {n} стр.)", m.group(0), anchor])
    add("tmpl_meta", WARN, "Title", "Заготовки шаблона в title, H1, описании или текстах ссылок",
        "Сайт не подставил значение в шаблон, и в заголовок или текст ссылки попала служебная заготовка вроде {$color} "
        "или #NAME#. Поисковик показывает такой заголовок в выдаче как есть, посетитель видит её в меню - сайт выглядит "
        "сломанным.",
        "Передайте разработчику: поправить шаблон, чтобы вместо заготовки подставлялось значение, или не создавать "
        "страницы, для которых значения нет.",
        ["Адрес", "Где", "Заготовка", "Текст целиком"], tmpl)
    add("h1_dup", NOTE, "H1", "Одинаковый H1 у разных страниц",
        "У разных страниц одинаковый главный заголовок.",
        "Сделайте H1 уникальным, если это действительно разные страницы.",
        ["H1", "Страниц", "Адреса"], [[g[0]["h1"], len(g), "\n".join(p["url"] for p in g[:500])] for g in dup_groups("h1")],
        page_col=None)

