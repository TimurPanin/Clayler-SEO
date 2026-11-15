"""Каннибализация: разные title, но одни и те же слова (другой порядок, окончания, «купить», бренд)."""
from ..common import NOTE, WARN, defaultdict, re, urlsplit
from ...fmt import quote


def run(ctx):
    add, indexable = ctx.add, ctx.indexable
    STOP = {"в", "во", "на", "по", "и", "с", "для", "от", "до", "из", "к", "а", "the", "купить", "цена", "цены", "недорого",
            "низкой", "низким", "лучшей", "выгодной", "магазин", "интернет", "интернет-магазин", "заказать", "каталог",
            "продажа", "официальный", "сайт", "доставкой", "доставка", "руб", "₽"}
    tails = defaultdict(int)
    for p in indexable:
        t = p["title"] or ""
        m = re.split(r"\s[|—–-]\s", t)
        if len(m) > 1:
            tails[m[-1].strip().lower()] += 1
    brand_tails = {k for k, n in tails.items() if n >= max(5, 0.1 * len(indexable))}

    def tkey(t):
        parts = re.split(r"\s[|—–-]\s", t or "")
        parts = [x for x in parts if x.strip().lower() not in brand_tails] or parts
        words = re.findall(r"[\wё]+", " ".join(parts).lower())
        key = sorted({w if any(ch.isdigit() for ch in w) else w[:5] for w in words if w not in STOP and (len(w) > 1 or w.isdigit())})
        return tuple(key)
    cg = defaultdict(list)
    for p in indexable:
        if p["title"]:
            k = tkey(p["title"])
            if len(k) >= 2:
                cg[k].append(p)
    crows = []
    for k, ps in cg.items():
        titles = {p["title"] for p in ps}
        if len(ps) > 1 and len(titles) > 1:  # одинаковые title целиком — в проверке «Одинаковый title»
            crows.append([len(ps), "\n".join(sorted(titles))[:600], "\n".join(p["url"] for p in ps[:20])])
    crows.sort(key=lambda r: -r[0])
    # пример — с самого сайта (первая пара title из самой большой группы), а не из чужой ниши
    # без хвоста «- купить недорого в интернет-магазине …»: только суть title до первого разделителя
    ex = [re.split(r"\s[|—–-]\s", t)[0].strip() for t in crows[0][1].split("\n")[:2]] if crows else []
    ex = [t if len(t) <= 80 else t[:77].rstrip() + "..." for t in ex]
    add("title_cannibal", WARN, "Title", "Почти одинаковые title - страницы спорят за один запрос",
        "У этих страниц title разный на вид, но состоит из тех же слов: другой порядок, другие окончания, "
        "добавлено «купить», «цена» или название компании. Для поисковика это страницы под один и тот же запрос - "
        "они мешают друг другу, и в выдаче может оказаться не та, что нужна.",
        "Решите, какая страница главная для этого запроса. Другим дайте title под свой, более узкий запрос "
        "(уточните вид, бренд, материал или назначение), либо объедините страницы."
        + (f" Пример с сайта: {quote(ex[0])} и {quote(ex[1])}." if len(ex) == 2 else ""),
        ["Страниц", "Title", "Адреса"], crows, page_col=2)

    # Город в title: если сайт местный (город есть в title у многих страниц), показываем разделы, где его нет
    cities = defaultdict(int)
    for p in indexable:
        for m in re.findall(r"\bв[о]?\s+([А-ЯЁ][а-яё]{2,})\b", p["title"] or ""):
            cities[m] += 1
    if cities:
        city, cn = max(cities.items(), key=lambda kv: kv[1])
        if cn >= max(10, 0.2 * len(indexable)):
            stem = city[:-1] if len(city) > 3 else city  # Уфе / Уфа / Уфы
            by_sec = defaultdict(list)
            for p in indexable:
                if stem.lower() not in (p["title"] or "").lower():
                    sec = "/" + urlsplit(p["url"]).path.strip("/").split("/")[0] + "/"
                    by_sec[sec].append(p["url"])
            sec_total = defaultdict(int)
            for p in indexable:
                sec_total["/" + urlsplit(p["url"]).path.strip("/").split("/")[0] + "/"] += 1
            rows_c = [[sec, len(u), sec_total[sec], "\n".join(u[:3])] for sec, u in
                      sorted(by_sec.items(), key=lambda kv: -len(kv[1]))]
            add("title_city", NOTE, "Местное SEO", f"Title без города («{city}») - по разделам",
                f"Город «{city}» стоит в title у {cn} страниц - сайт продвигается как местный. Здесь разделы, где у части "
                "страниц города в title нет. Для коммерческих страниц (товары, услуги, категории) город в title помогает "
                "в местной выдаче Яндекса; для статей, политики, контактов - не обязателен.",
                "Добавьте город в title коммерческих страниц из списка (обычно - одна правка шаблона раздела).",
                ["Раздел", "Страниц без города", "Всего страниц в разделе", "Примеры"], rows_c, page_col=None)

