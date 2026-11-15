"""Какими словами ссылаются на главные страницы сайта (версия 7.1) — как вкладка Inlinks/Anchor Text у Screaming Frog.
Текст ссылки — подсказка поисковику, о чём страница. Если на «Газовые котлы» ссылаются только «Каталог» и
«Подробнее», поисковик хуже связывает страницу с запросом. Ссылки из меню и подвала (есть на 30% страниц и больше)
считаются отдельно от ссылок из текста: внутри текста ссылка весит больше."""
import re
from collections import Counter, defaultdict

from ..common import NOTE
from ...fmt import quote

TOP = 60           # сколько важных страниц смотреть (по числу страниц, которые на них ссылаются)
MIN_INLINKS = 5
_W = re.compile(r"[а-яёa-z]{4,}", re.I)
STOP = {"купить", "цена", "цены", "заказать", "недорого", "интернет", "магазин",
        "официальный", "сайт", "компания", "главная", "страница", "доставкой", "доставка", "лучшие", "каталог"}
_CITY = []   # основы названий всех городов («уфа», «уфе», «казани»): город - не тема страницы. До здесь были
# зашиты только Уфа и Москва, и у сайтов других городов ссылка с одним городом в тексте считалась «по теме»


# служебные страницы: текст ссылки на них («Контакты», «О нас») не важен для поиска
SERVICE = re.compile(r"(kontakt|contact|o-kompanii|o_kompanii|about|o-nas|policy|politik|privacy|soglas|oferta|"
                     r"oplata|/pay/|dostavka|delivery|payment|cart|korzin|basket|login|auth|register|lk/|personal|filial|feedback|"
                     r"vakans|vacanc|career|otzyv|review|sitemap|search|poisk|compare|favorite|izbran|news|novost|"
                     r"blog|stat|article)", re.I)


def _stems(text):
    from ...semantics.stem import stem
    if not _CITY:
        from ...semantics import City
        _CITY.append(City().stems)
    out = {stem(w.lower().replace("ё", "е")) for w in _W.findall(text or "") if w.lower() not in STOP}
    return out - _CITY[0]


def anchors_for(ctx, urls):
    """{url: Counter(текст ссылки → на скольких страницах)} — только обычные внутренние ссылки <a>."""
    db, out = ctx.db, defaultdict(Counter)
    if ctx.store.legacy_links:
        for u in urls:
            for a, n in db.execute("SELECT anchor, COUNT(DISTINCT src) FROM links WHERE dst=? AND kind='a' AND internal=1 "
                                   "AND src<>dst GROUP BY anchor", (u,)):
                out[u][" ".join((a or "").split())] += n
        return out
    for u in urls:
        r = db.execute("SELECT id FROM strs WHERE s=?", (u,)).fetchone()
        if not r:
            continue
        for a, n in db.execute("SELECT a.s, COUNT(DISTINCT l.src) FROM link_rows l LEFT JOIN strs a ON a.id=l.anchor "
                               "WHERE l.dst=? AND l.kind='a' AND l.internal=1 AND l.src<>l.dst GROUP BY a.s", (r[0],)):
            out[u][" ".join((a or "").split())] += n
    return out


def run(ctx):
    pages = {p["url"]: p for p in ctx.indexable}
    if len(pages) < 20:
        return
    home = min(pages, key=lambda u: (pages[u].get("depth") or 0, len(u)))
    cand = sorted((u for u in pages if u != home and len(ctx.inl.get(u, ())) >= MIN_INLINKS
                   and not SERVICE.search(u.split("://", 1)[-1].split("/", 1)[-1])),
                  key=lambda u: -len(ctx.inl.get(u, ())))[:TOP]
    if not cand:
        return
    menu_min = max(20, int(0.3 * len(ctx.html_ok)))
    anc = anchors_for(ctx, cand)
    weak, only_menu, table = [], [], []
    for u in cand:
        c = anc.get(u) or Counter()
        if not c:
            continue
        p = pages[u]
        name = (p.get("h1") or p.get("title") or "").split(" | ")[0]
        menu = {a: n for a, n in c.items() if n >= menu_min}
        text = {a: n for a, n in c.items() if n < menu_min}
        top = ", ".join(f"{quote(a) if a else '«(картинка без alt)»'} - {n}" for a, n in c.most_common(4))
        table.append([u, name, sum(c.values()), sum(text.values()), top])
        want = _stems(name) | _stems(p.get("title"))
        if want and not any(_stems(a) & want for a in c):
            weak.append([u, name, top])
        if menu and not text:
            only_menu.append([u, name, ", ".join(quote(a) for a in menu)])
    ctx.anchor_table = table  # для отчёта: «Какими словами ссылаются на главные страницы»
    ctx.add("anchors_off_topic", NOTE, "Ссылки", "На важные страницы ссылаются словами не про них",
            "Текст ссылок на страницу - подсказка поисковику, о чём она. Здесь ни одна ссылка не содержит слов из "
            "заголовка страницы: только «Каталог», «Подробнее», «Перейти» или картинка без alt. Страница от этого "
            "хуже связывается с запросом.",
            "В меню, хлебных крошках и анонсах писать название раздела: «Газовые котлы», а не «Подробнее». У ссылок-"
            "картинок заполнить alt. Из текста статей ставить ссылки со словами запроса.",
            ["Страница", "Заголовок", "Какими словами ссылаются (на скольких страницах)"], weak, page_col=None)
    ctx.add("anchors_menu_only", NOTE, "Ссылки", "На важные страницы ссылаются только из меню",
            "На эти страницы ведёт много ссылок, но все - из меню или подвала (есть почти на каждой странице). Ссылок из "
            "текста других страниц нет. Ссылка внутри текста, рядом со словами по теме, для поисковика весит больше, "
            "чем пункт меню.",
            "Поставить на эти страницы ссылки из текста: из статей, описаний соседних разделов, карточек товаров "
            "(«подойдёт к газовым котлам Baxi»). Подборку слов для ссылок даёт «Семантика».",
            ["Страница", "Заголовок", "Ссылки из меню"], only_menu, page_col=None)
