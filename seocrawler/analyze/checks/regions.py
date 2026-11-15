"""Города: проверки городских версий сайта (meta «regions» — seocrawler/regions.py, режим «Сайт с городами»).
Здесь же ctx.region_of — для сводки по городам (health.py) и раздела «По городам» в аудите."""
from collections import defaultdict
from urllib.parse import urlsplit

from ..common import NOTE, WARN, own_text
from ...regions import mentions, region_of


def run(ctx):
    regs = ctx.store.get_meta("regions", None) or []
    ctx.regions = regs
    add = ctx.add
    no_urls = ctx.store.get_meta("regions_no_urls", None)
    if no_urls:
        add("region_no_urls", WARN, "Города", "Город выбирается на сайте, а своих страниц у городов нет",
            f"На сайте можно выбрать город ({', '.join(no_urls[:10])}{' и другие' if len(no_urls) > 10 else ''}), "
            "но адрес страницы при этом не меняется: сайт сам определяет город по местоположению посетителя (по IP) "
            "или запоминает выбор в браузере (cookie), и по одному адресу разным людям показывает разные города, "
            "телефоны и адреса. Поисковый робот город не выбирает: он видит тот город, который сайт определил для его "
            "сервера (обычно Москва или город по умолчанию), и индексирует только его. Для Яндекса и Google страниц "
            "«в Уфе» или «в Туймазах» не существует, и в поиске по этим городам сайт показывается хуже местных "
            "конкурентов. Проверить, что видит робот: Вебмастер → Инструменты → «Проверка ответа сервера».",
            "Если нужны позиции в других городах, сделайте городам свои адреса: поддомены (ufa.сайт.ru) или разделы "
            "(сайт.ru/ufa/) со своим городом в title, H1, контактах и ценах. В Битрикс/Аспро это включается в "
            "настройках регионов (режим «поддомены»). Каждый поддомен добавьте в Яндекс Вебмастер и укажите регион.",
            ["Города в переключателе"], [[c] for c in no_urls], page_col=None)
    seen = [r for r in ctx.store.get_meta("regions_seen", None) or [] if not r["main"]]
    if seen and not regs:
        add("region_not_checked", NOTE, "Города", "У сайта есть городские версии - они в эту проверку не вошли",
            "Программа нашла в переключателе города с отдельными адресами. Эта проверка шла только по основному сайту.",
            "Запустите проверку ещё раз с галочкой «Сайт с городами» (Дополнительные настройки): программа проверит "
            "города вместе и сделает в аудите раздел «По городам».",
            ["Город", "Адрес"], [[r["city"], r["url"]] for r in seen], page_col=None)
    if not regs:
        return
    cache = {}

    def reg(u):
        if u not in cache:
            cache[u] = region_of(u, regs)
        return cache[u]

    ctx.region_of = reg
    name = lambda r: r["city"] or "основной сайт"
    by_city = defaultdict(list)
    for p in ctx.html_ok:
        r = reg(p["url"])
        if r:
            by_city[r["url"]].append(p)

    # 1. Город, на который не ведёт ни одна обычная ссылка с других частей сайта
    unlinked = []
    for r in regs:
        if r["main"]:
            continue
        mine = {p["url"] for p in by_city.get(r["url"], [])}
        outside = any(reg(s) is not r for u in mine for s in ctx.inl.get(u, ()))
        if not outside:
            unlinked.append([r["city"], r["url"], r["how"], len(mine)])
    add("region_unlinked", WARN, "Города", "На городскую версию не ведёт ни одна ссылка с основного сайта",
        "Программа нашла эти городские версии только через переключатель города (он работает на JavaScript) "
        "или угадала адрес. Обычных ссылок на них с основного сайта нет - поисковик может так и не узнать о них "
        "или считать их отдельными маленькими сайтами без веса.",
        "Сделайте переключатель города обычными ссылками (<a href=\"https://город.сайт.ru/\">) или добавьте "
        "ссылки на городские версии на страницу «Филиалы»/«Контакты». Каждый поддомен добавьте в Яндекс "
        "Вебмастер и укажите в нём регион.",
        ["Город", "Адрес", "Как нашла программа", "Страниц проверено"], unlinked, page_col=None)

    # 2. Одинаковый текст в разных городах (та же страница, отличается только название города)
    own = own_text(ctx.html_ok)
    by_path = defaultdict(list)
    for p in ctx.html_ok:
        r = reg(p["url"])
        o = own.get(p["url"])
        if r and o and o[1] and p["indexable"] == 1:
            base = urlsplit(r["url"]).path or "/"
            path = urlsplit(p["url"]).path[len(base) - 1:] or "/"
            by_path[path].append((r, p["url"], o[1].split(",")))
    dup = []
    for path, items in sorted(by_path.items()):
        if len({id(r) for r, _, _ in items}) < 2:
            continue
        a = items[0]
        same = [(r, u, round(100 * sum(x == y for x, y in zip(a[2], s)) / len(s))) for r, u, s in items[1:]]
        same = [x for x in same if x[2] >= 90]
        if same:
            # все адреса группы в одной колонке — проблема засчитывается странице в каждом городе
            dup.append([path, "\n".join([a[1]] + [u for _, u, _ in same]),
                        ", ".join(name(r) for r in [a[0]] + [x[0] for x in same]), f"{min(x[2] for x in same)}%"])
    add("region_dup", WARN, "Города", "В разных городах одинаковый текст - отличается только название города",
        "Одна и та же страница в разных городах почти слово в слово (совпадение своего текста - от 90%). "
        "Яндекс такие страницы считает дублями: в выдаче по городу может оказаться не та версия, а слабые "
        "городские страницы - не попасть в поиск совсем.",
        "Для главных страниц каждого города (главная, услуги, контакты) напишите свой текст: адрес и как "
        "добраться, преподаватели или сотрудники этого филиала, отзывы, цены, если они отличаются. "
        "Хватит нескольких абзацев своего текста на странице.",
        ["Страница (путь)", "Адреса в городах", "Города", "Совпадение"], dup, page_col=1)

    # 3–4. Город в title и H1: нет своего / стоит чужой
    no_city, wrong = [], []
    known = [r for r in regs if r["city"]]
    for r in known:
        others = [o for o in known if o is not r]
        for p in by_city.get(r["url"], []):
            if p["indexable"] != 1:
                continue
            t, h = p.get("title") or "", p.get("h1") or ""
            if not mentions(t, r["city"]) and not mentions(h, r["city"]):
                if not r["main"]:
                    no_city.append([p["url"], r["city"], t, h])
                bad = [o["city"] for o in others if mentions(t, o["city"]) or mentions(h, o["city"])]
                if bad:
                    wrong.append([p["url"], r["city"], ", ".join(bad), t])
    add("region_no_city", WARN, "Города", "На городской версии нет названия города в title и H1",
        "Человек ищет «курсы английского в Первоуральске» - поисковик сравнивает запрос прежде всего с title и H1. "
        "Если в них нет города, страница городской версии проигрывает тем, где город есть.",
        "Добавьте город в title и H1 городских страниц: «Курсы английского в Первоуральске». Удобнее всего "
        "шаблоном: подставлять название города автоматически для каждого поддомена.",
        ["Страница", "Город", "Title", "H1"], no_city, page_col=0)
    add("region_wrong_city", WARN, "Города", "На странице одного города в title или H1 написан другой город",
        "Страница относится к одному городу, а в title или H1 - название другого. Обычно это ошибка шаблона: "
        "текст скопирован с основного сайта. Поисковик покажет её не тем людям, а в своём городе она не найдётся.",
        "Исправьте title и H1: на каждой городской версии - свой город.",
        ["Страница", "Город страницы", "Упомянут город", "Title"], wrong, page_col=0)

    # 5. Ссылки из одного города в другой (кроме переключателя и сквозных ссылок меню)
    per_src_city = defaultdict(lambda: defaultdict(set))
    for dst, srcs in ctx.inl.items():
        rd = reg(dst)
        if not rd:
            continue
        for s in srcs:
            rs = reg(s)
            if rs and rs is not rd:
                per_src_city[rs["url"]][dst].add(s)
    cross = []
    for src_city, dsts in per_src_city.items():
        n_pages = max(1, len(by_city.get(src_city, [])))
        for dst, srcs in dsts.items():
            rd = reg(dst)
            if urlsplit(dst).path in ("", "/", urlsplit(rd["url"]).path) or len(srcs) >= max(3, 0.3 * n_pages):
                continue  # главная другого города (переключатель) или ссылка из меню на всех страницах
            rs = reg(next(iter(srcs)))
            cross.append([sorted(srcs)[0], name(rs), dst, name(rd), len(srcs)])
    cross.sort(key=lambda r: -r[4])
    add("region_cross_links", NOTE, "Города", "Ссылки из одного города ведут на страницы другого города",
        "Со страниц одного города есть ссылки на страницы другого (не на главную через переключатель). "
        "Человек из Первоуральска попадает на страницу Екатеринбурга с чужим адресом и телефоном, а поисковик "
        "получает сигнал, что город не самостоятельный.",
        "Проверьте ссылки в тексте и в блоках «Услуги», «Новости»: в каждом городе они должны вести на страницы "
        "этого же города.",
        ["Откуда (пример)", "Город", "Куда", "Город ссылки", "Страниц с такой ссылкой"], cross[:1000], page_col=0)
