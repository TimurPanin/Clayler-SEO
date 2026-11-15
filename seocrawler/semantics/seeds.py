"""Разделы сайта (категории, бренды, услуги) из готовой проверки: с них начинается семантика.
Раздел узнаём по ссылке в меню или каталоге: на страницу ведут ссылки с нескольких страниц, текст ссылки
короткий, без цифр и моделей. Имя раздела — текст ссылки; если заголовок H1 страницы длиннее и содержит
его («Котлы» → «Газовые котлы»), берём заголовок."""
import html
import json
import os
import re
import sqlite3
from collections import Counter
from urllib.parse import urlsplit

from .stem import stem
from .words import CITIES, SALE_URL, SERVICE_NAMES, canon_city

MIN_LINKING_PAGES = 5     # на раздел ссылаются хотя бы с 5 страниц
SITEWIDE_SHARE = 0.3      # ссылка с такой доли страниц - меню сайта: раздел, даже если лежит рядом с карточками
MAX_WORDS = 6


def _undouble(s):
    """«Газовые колонки Газовые колонки» (картинка и подпись в меню) → «Газовые колонки»."""
    w = s.split()
    for k in range(1, len(w) // 2 + 1):
        if len(w) % k == 0 and w == w[:k] * (len(w) // k):
            return " ".join(w[:k])
    return s


def _style_case(s):
    """«Мебель в стиле современный» (фильтр сайта склеен без падежа) → «Мебель в современном стиле»."""
    def fix(m):
        a = m.group(1)
        low = a.lower()
        if low.endswith(("ский", "цкий", "кий", "гий", "хий", "ый", "ой")):
            b = a[:-2] + "ом"
        elif low.endswith("ий"):
            b = a[:-2] + "ем"
        else:
            return m.group(0)
        return f"{m.group(0)[0]} {b} стиле"
    return re.sub(r"(?<![а-яё])[вВ] стиле ([а-яё]+(?:ый|ий|ой))(?![а-яё])", fix, s)


def _only_brand(s, site_words):
    """«HighTime.agency», «ГазПрофСервис.рф»: в тексте только название компании и зона адреса."""
    rest = s.lower()
    for w in sorted((w.lower() for w in site_words if w), key=len, reverse=True):
        rest = rest.replace(w, " ")
    rest = re.sub(r"\b(ru|рф|com|net|org|su|kz|by|ua|agency|pro|online|shop|store|site|info|io|biz)\b", " ", rest)
    return bool(site_words) and not re.sub(r"[\W_]", "", rest)


def clean_name(s, site_words=()):
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    parts = re.split(r"\s[—|–-]\s|\s\|", s)
    s = parts[0]  # «Газовые котлы в Уфе — купить с гарантией»
    # «HighTime.agency — кратный рост заявок»: первая часть - только название компании, от неё оставался хвост
    # «agency» (имя главной в масках и дереве, hightime.agency) - берём следующую часть
    if len(parts) > 1 and _only_brand(s, site_words):
        s = parts[1]
    s = _undouble(s)
    s = re.sub(r"\b(купить|цены?|недорого|интернет-магазин|в интернет-магазине)\b.*$", "", s, flags=re.I).strip()
    for c in CITIES:
        s = re.sub(r"\s+(в|по)\s+" + re.escape(c[1]) + r"\b.*$", "", s, flags=re.I)
    for w in site_words:
        # «от экспертов HighTime.agency» - без хвоста «.agency» от адреса
        s = re.sub(re.escape(w) + r"(\.[a-zа-я]{2,10}\b)?", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,:;!-—")
    s = re.sub(r"\s+(для|в|на|с|и|по|от|из|к)$", "", s, flags=re.I)  # «Расходомеры для» (обрезанная ссылка)
    return _style_case(s)


def site_city(db):
    """Город сайта по заголовкам страниц: «купить в Уфе» → Уфа."""
    cnt = Counter()
    for (t,) in db.execute("SELECT title FROM pages WHERE title IS NOT NULL AND status=200 LIMIT 3000"):
        for c in CITIES:
            if re.search(r"\b(в|по)\s+" + re.escape(c[1]) + r"\b", t, re.I):
                cnt[canon_city(c[0])] += 1   # «в СПб» и «в Санкт-Петербурге» - один город
    if not cnt:
        return None
    name, n = cnt.most_common(1)[0]
    return next(c for c in CITIES if c[0] == name) if n >= 3 else None


def _brand_words(db, host):
    """Название сайта/компании — из хвоста заголовков («… | ГазПрофСервис»), чтобы не путать с товаром."""
    tails = Counter()
    for (t,) in db.execute("SELECT title FROM pages WHERE title IS NOT NULL AND status=200 LIMIT 2000"):
        parts = re.split(r"\s[|—–]\s", html.unescape(t))
        if len(parts) > 1:
            tails[parts[-1].strip()] += 1
    out = [t for t, n in tails.most_common(3) if n >= 20 and len(t.split()) <= 4]
    out.append(host.split(".")[-2] if "." in host else host)
    return out


NOT_SECTION_URL = re.compile(r"/(blog|news|novosti|stati|articles?|o-kompanii|company|about|info/?$|kontakty|"
                             r"contacts?|politika|privacy|polic|konfidenc|reviews|otzyvy|rassrochk|kredit|oplat|payment|"
                             r"vakans|"
                             # exist.ru, talisman: форум и его темы, справка, документы, статистика, вакансии,
                             # филиалы, преподаватели, приложение - не товар и не услуга
                             r"forum|help/|hint/|document/|stat/|stat\.|statisti|vacanc|career|karer|filial|branches|"
                             r"teachers|prepodavatel|application|"
                             # hightime.agency: вакансии, кейсы и портфолио, словарь терминов - не услуга
                             # целым кусочком адреса: /cases/, а не /case-iphone-15/ (чехлы) или /team-building/
                             r"(?:jobs?|cases?|team)(?:/|$|\?)|kejs|keis|portfolio|glossar|slovar-terminov|komanda)", re.I)
# ссылка-фраза, а не название раздела: «сюда», «нам об этом», «@DIRECT продажи» («Как выбрать кофе?» - раздел)
FUNC_WORDS = {"сюда", "здесь", "тут", "там", "нам", "нас", "вам", "вас", "им", "об", "о", "этом", "это", "том", "тем",
              "далее", "ниже", "выше", "перейти", "нажмите", "читать", "смотреть", "узнать", "все", "всё", "наш", "наши"}


def _dir(url):
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[0] + "/"


def _product_dirs(pages):
    """Папки с карточками товаров (/product/…): много страниц, у большинства в заголовке цифры или модель."""
    stat = {}
    for u, (h1, _) in pages.items():
        d = _dir(u)
        n, k = stat.get(d, (0, 0))
        stat[d] = (n + 1, k + bool(re.search(r"\d", h1 or "") or len((h1 or "").split()) > MAX_WORDS))
    return {d for d, (n, k) in stat.items() if n >= 30 and k >= 0.5 * n}


def load(folder, cards=0):
    """Разделы сайта из папки проверки: {site, host, city, brand, sections: [{name, url, links, h1, parent}], pages}.
    cards - ещё и столько карточек товаров ({name, url, links}, самые связанные ссылками) для масок (masks.py)."""
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    start = db.execute("SELECT value FROM meta WHERE key='start'").fetchone()
    start = json.loads(start[0]) if start else ""
    host = urlsplit(start).netloc.lower().removeprefix("www.")
    pages = {u: (h1, t) for u, h1, t in db.execute(
        "SELECT url, h1, title FROM pages WHERE indexable=1 AND status=200 AND content_type LIKE 'text/html%'")}
    legacy = db.execute("SELECT type FROM sqlite_master WHERE name='links'").fetchone()
    if legacy and legacy[0] == "table":
        q = ("SELECT dst, anchor, COUNT(DISTINCT src) FROM links WHERE internal=1 AND kind='a' "
             "GROUP BY dst, anchor")
    else:
        q = ("SELECT d.s, a.s, COUNT(DISTINCT l.src) FROM link_rows l JOIN strs d ON d.id=l.dst "
             "LEFT JOIN strs a ON a.id=l.anchor WHERE l.internal=1 AND l.kind='a' GROUP BY l.dst, l.anchor")
    best = {}
    for dst, anc, n in db.execute(q):
        if not anc or dst not in pages:
            continue
        a = re.sub(r"\s+", " ", html.unescape(anc)).strip()
        if n > best.get(dst, ("", 0))[1]:
            best[dst] = (a, n)
    brand = _brand_words(db, host)
    city = site_city(db)
    home = {u for u in pages if urlsplit(u).path in ("", "/")}
    product_dirs = _product_dirs(pages)
    secs = []
    sitewide = max(MIN_LINKING_PAGES, SITEWIDE_SHARE * len(pages))
    for url, (anc, n) in best.items():
        # ссылка из меню (почти с каждой страницы) на страницу в корне - раздел, даже если корень похож на папку
        # товаров: на hightime.agency
        # все страницы в корне, у многих длинный H1 - меню уходило в карточки. В папке /product/ - нет:
        # товар в подвале каждой страницы (rsmarket24) - всё равно карточка
        if url in home or n < MIN_LINKING_PAGES or urlsplit(url).query or NOT_SECTION_URL.search(url) or \
                (_dir(url) in product_dirs and not (n >= sitewide and _dir(url) == "/")):
            continue
        name = clean_name(anc, brand)
        # в ссылке счётчик: «Центральный округ 1 перевозчик», «Шкафы 120 товаров» - раздел без числа
        # (gruzoperevozka23.ru: 37 страниц районов не попадали в маски из-за цифры в ссылке).
        # Только если заголовок страницы - про то же и без этого числа: «Котлы 24 кВт» с H1 «Котлы 24 кВт» -
        # фильтр, а не раздел
        m = re.search(r"\s+(\d[\d\s]*)\D.*$|\s+(\d[\d\s]*)$", name or "")
        if m and not re.search(r"[{}$]", name):
            cut, num_ = name[:m.start()].strip(" ,.-"), (m.group(1) or m.group(2)).strip()
            h1_ = (pages[url][0] or "").lower()
            if cut and not re.search(r"\d", cut) and cut.lower() in h1_ and num_ not in h1_:
                name = cut
        # «Мебель с {$dveri_t} без декора» - заготовка шаблона сайта, а не раздел
        if not name or re.search(r"\d|[{}$]", name) or len(name.split()) > MAX_WORDS or SERVICE_NAMES.match(name):
            continue
        # другой поддомен - обычно филиал в другом городе (ntagil.talisman-online.ru), не раздел этого сайта
        if urlsplit(url).netloc.lower().removeprefix("www.") != host:
            continue
        if re.search(r"@|«\s*»", name) or all(w in FUNC_WORDS for w in name.lower().split()):
            continue
        # H1 оборван на предлоге («Шкаф-купе с» - шаблон не подставил «без декора»): страница-фильтр без значения,
        # её ссылка «Шкаф-купе» уводила общие запросы из раздела шкафов-купе (lk-fabrika)
        if re.search(r"\s(с|со|для|из|в|на|по|от|без|под)$", (pages[url][0] or "").strip(), re.I):
            continue
        h1 = clean_name(pages[url][0] or "", brand)
        # заголовок уточняет ссылку: «Котлы» → «Газовые котлы», «Baxi» → «Запчасти Baxi для газовых котлов»
        if h1 and not re.search(r"\d", h1) and len(h1.split()) <= MAX_WORDS and len(h1) > len(name) and \
                all(w.lower() in h1.lower() for w in name.split()):
            name = h1
        secs.append({"name": name, "url": url, "links": n, "h1": pages[url][0] or ""})
    # один раздел под одним именем: не «распродажа/акции», короче адрес, больше ссылок
    by_name = {}
    for s in sorted(secs, key=lambda s: (bool(SALE_URL.search(s["url"])), len(s["url"]), -s["links"])):
        by_name.setdefault(s["name"].lower(), s)
    secs = list(by_name.values())
    # родитель — раздел, чей адрес — начало адреса этого раздела (для коротких имён: «Настенные» → котлы)
    urls = sorted(secs, key=lambda s: -len(s["url"]))
    for s in secs:
        s["parent"] = next((p["name"] for p in urls if p is not s and s["url"].startswith(p["url"])
                            and len(p["url"]) < len(s["url"])), None)
    db.close()
    # тема сайта — по заголовку и H1 главной («Курсы английского языка в Москве» → «курсы английского языка»):
    # с неё собираются подсказки шире разделов, чтобы увидеть, чего на сайте нет
    topic = []
    own = {w for b in brand + [host] for w in re.findall(r"[a-zа-яё0-9]+", b.lower())}  # «ils», «school», «талисман»
    for u in sorted(home, key=len)[:1]:
        for t in (pages[u][0], pages[u][1]):
            nm = " ".join(w for w in clean_name(t or "", brand).split() if re.sub(r"[^a-zа-яё0-9]", "", w.lower()) not in own)
            if nm and 2 <= len(nm.split()) <= MAX_WORDS and not re.search(r"\d", nm) and nm.lower() not in topic:
                topic.append(nm.lower())
    # тема из длинного title главной - только чтобы узнать пункт меню не про тему (к запросам не дописывается):
    # H1 главной бывает слоганом («кратный рост целевых заявок»), title - чаще про услугу
    wide = ""
    for u in sorted(home, key=len)[:1]:
        if not topic:
            wide = _topic_head(" ".join(w for w in clean_name(pages[u][1] or "", brand).split()
                                        if re.sub(r"[^a-zа-яё0-9]", "", w.lower()) not in own)).lower()
    _with_topic(secs, topic, brand, wide)
    # служебное имя могло появиться из H1 («Вопросы» → «Часто задаваемые вопросы», reestr-719)
    secs = [s for s in secs if not SERVICE_NAMES.match(s["name"])]
    if not topic:   # после _with_topic: к запросам разделов не дописывается, только тема главной
        topic = _menu_topic(secs)
    out = {"site": start, "host": host, "city": city, "brand": brand, "sections": secs, "folder": folder,
           "topic": topic[:2], "pages": len(pages)}
    if cards:   # карточки товаров - маски только по выбору: модель и хвосты, спроса обычно мало
        cand = []
        in_secs = {s["url"] for s in secs}
        for u, (h1, _t) in pages.items():
            # не карточка: главная, уже раздел, служебная страница («Отправить резюме», «Пригласить в тендер»)
            if _dir(u) in product_dirs and not urlsplit(u).query and u not in home and u not in in_secs and \
                    not NOT_SECTION_URL.search(u):
                nm = clean_name(h1 or "", brand)
                if nm and len(nm.split()) <= 10 and not SERVICE_NAMES.match(nm):
                    cand.append({"name": nm, "url": u, "links": best.get(u, ("", 0))[1]})
        out["cards"] = sorted(cand, key=lambda c: -c["links"])[:cards]
    return out


ADJ_END = re.compile(r"(ые|ие|ый|ий|ая|яя|ое|ее)$")
PREP_START = re.compile(r"^(с|со|без|под|во|в|для|из|на|до|по|от)\s", re.I)
PREPS = {"с", "со", "без", "под", "во", "в", "для", "из", "на", "до", "по", "от", "и"}


def _stems(t):
    out = set()
    for w in re.findall(r"[a-zа-яё]+", (t or "").lower().replace("ё", "е")):
        if len(w) >= 2 and w not in PREPS:
            st = stem(w)
            out.add(st)
            if len(st) > 4 and st[-2] in "оеё":   # беглая гласная: «кухонь» - «кухни», «потолок» - «потолка»
                out.add(st[:-2] + st[-1])
    return out


def _topic_head(t):
    """Длинный заголовок главной - его начало: до запятой или двоеточия, потом до первого «в/на/для/по…» после
    первых двух слов. «Продвижение IT-компаний и SaaS-продуктов в России и за рубежом» → «Продвижение IT-компаний и
    SaaS-продуктов» (hightime.agency: темы не было, «Тарифы» собрали «тарифы теле2»)."""
    if len(t.split()) <= MAX_WORDS:
        return t
    t = re.split(r"\s*[:,(]\s*", t)[0].strip()
    w = t.split()
    cut = next((i for i, x in enumerate(w) if i >= 2 and x.lower() in PREPS - {"и"}), len(w))
    return " ".join(w[:cut])


def _menu_topic(secs):
    """Тема главной из пунктов меню, когда её нет в заголовках главной: два слова подряд (по-русски), которые есть хотя
    бы в трёх пунктах. hightime.agency: H1 главной - слоган, title длинный, и «продвижение сайтов», «seo
    продвижение сайтов под ключ» - главные запросы агентства - лежали в «Без группы», а пункты меню - «SEO-продвижение
    сайтов в Германии», «… во Франции», «… в США»."""
    cnt = Counter()
    for s in secs:
        w = [x for x in re.findall(r"[а-яё]+", s["name"].lower().replace("-", " ")) if x not in PREPS]
        cnt.update({f"{a} {b}" for a, b in zip(w, w[1:]) if len(a) > 2 and len(b) > 2})
    pair, n = cnt.most_common(1)[0] if cnt else ("", 0)
    return [pair] if n >= 3 else []


def _related(a, b):
    """Общее слово: основа или первые 5 букв (стеммер даёт «зеркалом» - «зеркал», «зеркала» - «зерка»). Слова через
    дефис - и слитно: «E-Commerce» и «eCommerce-проектов»."""
    pre = lambda t: {w[:5] for w in re.findall(r"[a-zа-яё]+", t.lower().replace("ё", "е")) if len(w) >= 5}
    glued = lambda t: {w[:5] for w in re.findall(r"[a-zа-яё]+", t.lower().replace("ё", "е").replace("-", "")) if len(w) >= 5}
    return bool(_stems(a) & _stems(b) or pre(a) & pre(b) or glued(a) & glued(b))


def _weak(name):
    """Пункт меню, который сам по себе не запрос: одно слово, одни прилагательные или начинается с предлога
    («Детские», «С зеркалом», «Без декора», «Под потолок»)."""
    w = name.split()
    return len(w) == 1 or bool(PREP_START.match(name)) or all(ADJ_END.search(x.lower()) for x in w)


def _with_topic(secs, topic, brand=(), wide=""):
    """Короткий пункт меню - по заголовку H1 его страницы, а если и так нет слова темы сайта - со словом темы
    (lk-fabrika: «Библиотеки» собрали «библиотеки москвы», «Без декора» - «торт без декора»,
    «Кухни» вела на «Распил кухонь»). Имя для людей - H1 («Детская мебель на заказ», «Распил кухонь»); слово
    темы («мебель» из заголовка главной) - в sec["need"], его добавляет query_form к запросу."""
    head = []
    for w in (topic[0] if topic else "").split():
        if w in PREPS:
            break
        head.append(w)
    head = " ".join(head)
    cnt = Counter(s for x in secs for s in _stems(x["name"]))
    common = {s for s, n in cnt.items() if n >= 3} | _stems(head)
    rename = {}
    for s in secs:
        name = orig = s["name"]
        h1 = clean_name(s.get("h1") or "", brand)
        # длинный H1 - его начало до запятой или двоеточия: «Германия» → «SEO-продвижение сайтов в Германии» из
        # «SEO-продвижение сайтов в Германии, Австрии, Швейцарии…» (hightime.agency)
        # после двоеточия - всегда пояснение («SEO-продвижение eCommerce-проектов: магазины и экспортёры»)
        h1 = re.split(r"\s*:\s+", h1)[0].strip()
        if len(h1.split()) > MAX_WORDS:
            h1 = re.split(r"\s*[:,(]\s*", h1)[0].strip()
        ok = h1 and h1.lower() != name.lower() and not re.search(r"\d", h1) and len(h1.split()) <= MAX_WORDS \
            and not SERVICE_NAMES.match(h1)
        # H1 - только если он про то же (общее слово): у gasprof /katalog/termostat/ с H1 общего раздела «Системы
        # безопасности котла» - «Термостат» остаётся «Термостатом»
        # пункт меню без слова темы сайта («США и Европа», «E-Commerce»), а его H1 - про то же и со словом темы
        # («SEO-продвижение сайтов в США»): H1, иначе подсказки уходят в чужое («сша и европа последние новости»)
        th = _stems((head or wide).split(" ")[0])   # главное слово темы: «продвижение», «мебель»
        off_topic = th and not _stems(name) & th and _stems(h1) & th
        if ok and (_weak(name) or off_topic) and _related(name, h1):
            name = h1   # остальные - как раньше (load: H1 длиннее и содержит все слова ссылки)
        if name != s["name"]:
            rename[s["name"]] = name
            s["name"] = name
        # на маленьком сайте «частых» слов нет: там слово темы - только к пунктам вроде «Детские», «С зеркалом»
        if head and not s.get("parent") and (PREP_START.match(name) or not _stems(name) & common and (_weak(orig) or len(secs) >= 10)):
            s["need"] = head
    for s in secs:
        if s.get("parent") in rename:
            s["parent"] = rename[s["parent"]]


def query_form(sec):
    """Как раздел ищут: строчными; короткое «Настенные» дополняем родителем («настенные газовые котлы»)."""
    name = sec["name"].lower().replace("ё", "е")
    words = name.split()
    parent = (sec.get("parent") or "").lower().replace("ё", "е")
    if parent and PREP_START.match(name):   # «с зеркалом» + «шкафы-купе на заказ» → «шкафы-купе с зеркалом»
        pw = parent.split()
        pw = pw[:next((i for i, w in enumerate(pw) if i and w in PREPS), len(pw))]
        if not _related(" ".join(pw), name):
            name = " ".join(pw + words)
    elif parent and (len(words) == 1 or all(ADJ_END.search(w) for w in words)):
        pw = parent.split()
        if any(w in PREPS for w in pw[1:]):   # «шкафы-купе на заказ» → «шкафы-купе»
            cut = pw[:next(i for i, w in enumerate(pw) if i and w in PREPS)]
            if any(not ADJ_END.search(w) for w in cut):   # «комплектующие для баков» - целиком: нужно «баков»
                pw = cut
        if len(pw) >= 2 and ADJ_END.search(pw[1]) and not ADJ_END.search(pw[0]):
            pw = [pw[1], pw[0]] + pw[2:]          # «котлы газовые» → «газовые котлы»
        # слово родителя уже есть в названии: «Тепловентиляторы» в «Тепловентиляторы водяные» - без повтора
        pw = [w for w in pw if w[:5] not in {x[:5] for x in words} and not _stems(w) & _stems(name)]
        if all(ADJ_END.search(w) for w in words):
            name = " ".join(words + pw)            # «настенные» + «газовые котлы»
        else:                                      # «колбы» + «фильтры», «полипропилен» + «трубы»
            name = " ".join(words + [w for w in pw if not ADJ_END.search(w) and len(w) > 3][:1])
    need = (sec.get("need") or "").lower()
    if need and not _stems(need) & _stems(name):   # «гостиная» + «мебель»: без слова темы подсказки про другое
        name = f"{name} {need}"
    return name
