"""Индексация."""
from ... import mirror_copy
from ...robots import page_instead
from ..common import CRIT, NOTE, WARN, _q, re


def run(ctx):
    add, db, html_ok, indexable, status = ctx.add, ctx.db, ctx.html_ok, ctx.indexable, ctx.status
    # robots.txt своего сайта отвечает ошибкой сервера, 429 или не отвечает: программа обходит, как будто запретов нет,
    # а Google при таком ответе на время считает закрытым весь сайт (коды ответа по порядку). 404 и
    # другие 4xx - «файла нет, можно всё», это не проблема.
    # только где сами страницы открылись: адрес с опечаткой (www..yazyk-primer.ru) или несуществующий поддомен - не
    # беда robots.txt, а битая ссылка (она и так в «Битых ссылках»)
    rb_bad = [[o + "/robots.txt", v.get("status") or v.get("error") or "нет ответа"]
              for o, v in sorted((ctx.store.get_meta("robots", {}) or {}).items())
              if (not v.get("status") or v["status"] >= 500 or v["status"] == 429)
              and db.execute("SELECT 1 FROM pages WHERE url LIKE ? AND status=200 LIMIT 1", (o + "/%",)).fetchone()]
    add("robots_unavailable", CRIT, "Индексация", "robots.txt не открывается: ошибка сервера",
        "Файл robots.txt отвечает ошибкой сервера (5xx), «слишком много запросов» (429) или не отвечает совсем - "
        "три попытки с паузой. Google при таком ответе на время перестаёт обходить весь сайт. При проверке сайт "
        "обойдён так, как будто запретов нет.",
        "Передайте разработчику или хостингу: robots.txt должен отвечать кодом 200 (или 404, если файла нет).",
        ["Адрес", "Ответ"], rb_bad, page_col=None)
    # код 200, а вместо правил обычная страница: поисковик не получает ни запретов, ни адреса sitemap
    rb_page = [[o + "/robots.txt", "код 200, но это HTML-страница, а не файл с правилами"]
               for o, v in sorted((ctx.store.get_meta("robots", {}) or {}).items()) if page_instead(v)]
    add("robots_html", WARN, "Индексация", "Вместо robots.txt сайт отдаёт обычную страницу",
        "По адресу robots.txt открывается страница сайта, а не файл с правилами. Поисковик не получает ни запретов, "
        "ни адреса карты сайта, поэтому обходит всё подряд, в том числе служебные адреса.",
        "Передайте разработчику: положить в корень сайта настоящий файл robots.txt (готовый - в файлах для "
        "разработчика) и проверить, что он открывается как текст.",
        ["Адрес", "Что ответил сервер"], rb_page, page_col=None)
    add("noindex", NOTE, "Индексация", "Страницы, закрытые от поиска (noindex)",
        "Эти страницы просят поисковик не показывать их в выдаче.",
        "Убедитесь, что это сделано специально. Если среди них есть нужные страницы, уберите noindex.",
        ["Адрес", "meta robots", "X-Robots-Tag"],
        [[p["url"], p["meta_robots"], p["x_robots"]] for p in html_ok if p["indexability"] == "noindex"], page_col=None)
    add("canonicalised", NOTE, "Индексация", "Страницы, которые указывают на другую как на основную (canonical)",
        "Страница говорит поисковику: «главная версия меня - вот по этому адресу». Нормально для фильтров "
        "и сортировок; ошибка, если это самостоятельная страница.",
        "Проверьте, что среди них нет важных страниц.",
        ["Адрес", "Canonical"], [[p["url"], p["canonical"] or p["canonical_header"]] for p in html_ok
                                 if p["indexability"] == "Канонизирована"], page_col=None)
    bad_canon = []
    for p in html_ok:
        c = p["canonical"] or p["canonical_header"]
        if c and c != p["url"]:
            st = status.get(c)
            if st and (st[0] != 200 or st[1]):
                bad_canon.append([p["url"], c, st[0] or st[1]])
    add("canon_bad", CRIT, "Индексация", "Canonical ведёт на неработающую страницу",
        "Страница указывает как основной адрес, который перенаправляет или отдаёт ошибку. "
        "Поисковик, скорее всего, проигнорирует такое указание.",
        "Укажите в canonical рабочий конечный адрес.",
        ["Адрес", "Canonical", "Код"], bad_canon)
    # canonical на страницу, закрытую noindex, или цепочкой (A → B, а B указывает на C)
    byurl = {p["url"]: p for p in html_ok}
    canon_more = []
    for p in html_ok:
        c = p["canonical"] or p["canonical_header"]
        if not c or c == p["url"] or c not in byurl:
            continue
        t = byurl[c]
        if t["indexability"] == "noindex":
            canon_more.append([p["url"], c, "основная страница закрыта noindex"])
        else:
            c2 = t["canonical"] or t["canonical_header"]
            if c2 and c2 != c:
                canon_more.append([p["url"], c, f"цепочка: основная указывает дальше, на {c2}"])
    add("canon_chain", WARN, "Индексация", "Canonical на закрытую страницу или цепочкой",
        "Страница указывает основной адрес, но та «основная» сама закрыта от поиска (noindex) или указывает "
        "canonical на третью страницу. Поисковик получает противоречивые сигналы и может выбрать основной адрес сам.",
        "Указывайте в canonical конечную рабочую страницу, открытую для поиска.",
        ["Адрес", "Canonical", "Что не так"], canon_more, page_col=None)

    # Постраничная навигация (?PAGEN_1=2, ?page=2, /page/2/) с canonical на первую страницу
    pag_rx = re.compile(r"([?&](pagen_\d+|page|p|pg|paged)=\d+|/page[-/]?\d+/?$)", re.I)
    pag_rows = []
    for p in html_ok:
        c = p["canonical"] or p["canonical_header"]
        if c and c != p["url"] and pag_rx.search(p["url"]) and not pag_rx.search(c):
            pag_rows.append([p["url"], c])
    add("pagination_canon", NOTE, "Индексация", "Страницы 2, 3… списка указывают canonical на первую",
        "Это не ошибка, а спорная настройка. Яндекс такое допускает. Google советует, чтобы у каждой страницы "
        "навигации был свой canonical (на саму себя): иначе он может перестать обходить товары со страниц 2, 3…",
        "Если важен Google, поставьте страницам навигации canonical на себя и оставьте их открытыми для обхода.",
        ["Страница навигации", "Canonical"], pag_rows, page_col=None)

    add("canon_multi", WARN, "Индексация", "Несколько canonical на странице",
        "Если указано несколько основных адресов, поисковик может проигнорировать все.",
        "Передайте разработчику: оставить один тег canonical.",
        ["Адрес", "Сколько"], [[p["url"], p["canonical_count"]] for p in html_ok if (p["canonical_count"] or 0) > 1])
    add("canon_missing", NOTE, "Индексация", "Нет canonical",
        "Не ошибка. Canonical на саму себя защищает страницу от дублей, когда к адресу добавляют метки (utm и т. п.).",
        "По желанию: добавить на все страницы canonical на их собственный адрес.",
        ["Адрес"], [[p["url"]] for p in indexable if not (p["canonical"] or p["canonical_header"])], page_col=None)
    # страницы отдельно от файлов (CSS, JS, фото): у market-primer было «135» в проблеме и «15» в «Что не проверено»,
    # потому что сюда шли и 120 файлов WordPress. Страницы считаются тем же условием, что в coverage.py
    blocked_all = _q(db, "SELECT url, skip_reason, found_on, kind FROM urls WHERE state='skipped' AND internal=1 "
                         "AND kind<>'sitemap' AND skip_reason LIKE 'Закрыт в robots%'")
    blocked = [r for r in blocked_all if r["kind"] != "resource"]
    blocked_res = [r for r in blocked_all if r["kind"] == "resource"]
    style_js = [r for r in blocked_res if re.search(r"\.(css|js)(\?|$)", r["url"].lower())]
    add("robots_blocked_res", WARN if style_js else NOTE, "Индексация", "Файлы стилей, скриптов и картинки закрыты в robots.txt",
        "Это не страницы, а файлы, из которых браузер собирает страницу. Если закрыты стили (CSS) или скрипты (JS), "
        "Google не может их загрузить и видит страницу без оформления: может решить, что она сломана или не "
        "подходит для телефона.",
        "Откройте эти файлы в robots.txt: уберите запрет на папки со стилями и скриптами (у WordPress это часто "
        "/wp-includes/ и /wp-content/plugins/).",
        ["Адрес файла", "Правило", "Где найдена ссылка"],
        [[r["url"], r["skip_reason"].replace("Закрыт в robots.txt (", "").rstrip(")"), r["found_on"]] for r in blocked_res],
        page_col=None)
    add("robots_blocked", NOTE, "Индексация", "Адреса, закрытые в robots.txt",
        "Файл robots.txt запрещает роботам заходить на эти адреса, поэтому программа их тоже не открывала. "
        "Важно: запрет в robots.txt не прячет страницу из поиска - адрес всё равно может попасть в выдачу без описания.",
        "Проверьте, что среди них нет нужных страниц. Чтобы убрать страницу из поиска, используйте noindex, а не robots.txt.",
        ["Адрес", "Правило", "Где найдена ссылка"],
        [[r["url"], r["skip_reason"].replace("Закрыт в robots.txt (", "").rstrip(")"), r["found_on"]] for r in blocked],
        page_col=None)
    skipped = _q(db, "SELECT url, skip_reason, found_on FROM urls WHERE state='skipped' AND internal=1 "
                     "AND kind<>'sitemap' AND skip_reason NOT LIKE 'Закрыт в robots%' AND skip_reason<>?",
                 mirror_copy.SKIP)  # копия сайта с www - своя проблема «Ссылки на копию сайта» (mirrors.py)
    add("skipped", NOTE, "Обход", "Адреса, которые программа не открывала из-за ограничений",
        "Программа пропускает адреса, похожие на бесконечные ловушки: слишком много параметров (фильтры каталога), "
        "повторяющиеся куски пути, слишком большая глубина.",
        "Если среди них есть нужные страницы, ослабьте ограничения (см. ИНСТРУКЦИЯ.md) и запустите аудит снова.",
        ["Адрес", "Почему пропущен", "Где найдена ссылка"], [[r["url"], r["skip_reason"], r["found_on"]] for r in skipped],
        page_col=None)

