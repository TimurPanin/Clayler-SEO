"""Бренды в семантике: какие бренды ищут, есть ли у вас страница бренда и сколько товаров, есть ли у конкурентов,
и таблица «бренд × категория» («котлы Baxi», «бойлеры Baxi», «Baxi в Уфе»): где страница есть, где стоит создать.
Бесплатно и без сети: только запросы семантики, обход своего сайта и проверки конкурентов.

Откуда бренды:
- страницы брендов своего сайта и конкурентов (/brands/baxi/, /brendy/baxi/, /proizvoditeli/...);
- фильтры брендов в каталоге (/kotly/brand-baxi/, /filter/brand-is-baxi/apply/) - это и ячейки «бренд × категория»;
- группы семантики «страница бренда» и латиница в запросах (слово в 2+ запросах, не общее вроде «wifi», «led»);
- «Словарь» (dictionary.py), вид «Бренды»: «Samsung = самсунг, самсунк» - «Общий» и тема сайта.
Как узнаётся написание: по звучанию (stem.sound: Baxi = бакси), «х» вместо «x» (бахи = baxi), опечатка в одну букву
у длинного слова, которого нет на сайте (бакис), и пары из словаря. Варианты показываются у бренда.

Цвета и слова - как в дереве сайта (labels.TREE, tree.ST): страница бренда есть / создать / решить, нужна ли; ячейка -
фильтр есть на сайте / создать / есть у конкурента / спроса мало. Сколько нужно для «создать» - tree.FILTER_MIN и
tree.FILTER_FREQ, как у страниц-фильтров."""
import os
import re
import sqlite3
from urllib.parse import urlsplit

from . import labels as LB
from .logos import _case
from .stem import sound, stem
from .tree import (BRAND_PATH, FILTER_FREQ, FILTER_MIN, LAT_RX, ST, STOP, _dem, _freq_mode, _host, _ro)

# страница бренда: /brendy/baxi/ (последняя часть адреса - бренд)
BRAND_PAGE = re.compile(r"/(?:brands?|brendy|brend|proizvoditeli|proizvoditel|vendors?|manufacturers?)/([^/?#]+)/?$", re.I)
# фильтр бренда в категории: /kotly/brand-baxi/, /kotly/filter/brand-is-baxi/apply/
BRAND_FILTER = re.compile(r"^(.*?/)(?:filter/)?brand(?:-is)?-([a-z0-9][a-z0-9_.-]*?)(?:/apply)?/?$", re.I)
# латиница в запросах, которая не бренд
LAT_STOP = {"wifi", "wi-fi", "led", "pro", "plus", "max", "mini", "home", "eco", "gsm", "usb", "hd", "kw", "sms", "inox",
            "ppr", "pex", "ru", "com", "online", "pdf", "dn", "pn", "pvc", "abs", "hdpe", "rus", "new", "top", "the",
            "and", "for", "light", "smart", "comfort", "duo", "lux", "classic", "style", "turbo", "standard", "basic",
            "premium", "air", "gas", "water", "aqua", "power", "nova", "line", "steel", "inverter", "ip", "rs", "bt",
            "nr", "erp", "gpl", "lpg", "dhw", "ch", "kombi", "boiler", "www", "http", "https", "html", "xxl", "xl",
            # отраслевые сокращения и английские слова темы - не бренды: «Seo» (1 100), «Serm», «Programmatic Seo» в
            # листе «Бренды» у SEO-агентства (primerline.agency)
            "seo", "smm", "serm", "orm", "ppc", "crm", "cms", "saas", "b2b", "b2c", "it", "ai", "geo", "ux", "ui",
            "api", "sem", "smo", "seo-продвижение", "programmatic", "marketing", "digital", "content", "agency",
            "landing", "ecommerce", "e-commerce", "growth", "strategy", "audit", "course", "skill", "meaning",
            "examples", "system", "service", "services", "design", "web", "app", "software", "cloud"}
MIN_LAT_QUERIES = 2       # латинское слово в стольких запросах - бренд (если не из LAT_STOP)
TYPO_MIN = 5              # опечатка в одну букву - только у слов не короче (бакис = бакси)
CATS_SHOWN = 12           # столбцов категорий в таблице на странице и в отчёте
SERIES_SHARE = 0.7        # латинское слово так часто рядом с известным брендом - серия («Seoul» у Master Gas), не бренд
PAIR_MIN, PAIR_SHARE = 3, 0.6   # два бренда рядом в стольких запросах - один бренд из двух слов («Royal Thermo»)


def _words(s):
    return re.findall(r"[a-zа-я0-9]+(?:-[a-zа-я0-9]+)*", (s or "").lower().replace("ё", "е"))


def _keys(w):
    """Звучания слова: обычное и с «х» как «x» (бахи = baxi)."""
    out = {sound(w)}
    if "х" in w and re.fullmatch(r"[а-я-]+", w):
        out.add(sound(w.replace("х", "кс")))
    return {k for k in out if len(k) >= 3}


def _lev1(a, b):
    """Отличаются не больше чем на одну букву (замена, вставка, удаление или перестановка соседних)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _slug_name(slug):
    return " ".join(p.capitalize() for p in re.split(r"[-_]+", slug) if p)


def user_pairs(lines):
    """Словарь «Бренды»: «Baxi = бакси, бахи» → [(название, [варианты])]. Строка с «#» выключена."""
    out = []
    for line in lines or []:
        if line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[=,;]", line) if p.strip()]
        if parts:
            out.append((parts[0], parts[1:]))
    return out


class Brands:
    """Известные бренды: звучание → запись {name, keys, forms, page, rivals, filters, rival_filters}."""
    def __init__(self):
        self.by_key, self.items = {}, []

    def add(self, name, extra=(), weight=1):
        guess = name.startswith("~")
        name = name.lstrip("~").strip()
        ws = _words(name)
        if not ws or len(name) > 30 or len(ws) > 2:
            return None
        keys = set().union(*[_keys(re.sub(r"[\s_-]+", "", w.lower())) for w in [name, *extra] if w.strip()])
        hit = next((self.by_key[k] for k in keys if k in self.by_key), None)
        if hit is None:
            hit = {"name": name, "names": {}, "keys": set(), "forms": {}, "page": "", "rivals": {}, "filters": {},
                   "rival_filters": {}, "user": False, "guess": set(), "kind": set(), "site_models": set(),
                   "models": {}, "lat": False}
            self.items.append(hit)
        hit["names"][name] = hit["names"].get(name, 0) + (weight / 20 if guess else weight)
        if guess:
            hit["guess"].add(name)
        else:
            hit["exact"] = True     # сайт сам так называет бренд (ссылка, H1, словарь, группа)
        for k in keys:
            hit["keys"].add(k)
            self.by_key.setdefault(k, hit)
        return hit

    def get(self, name):
        """Уже известный бренд по названию или None."""
        return next((self.by_key[k] for k in _keys(re.sub(r"[\s_-]+", "", name.lower())) if k in self.by_key), None)

    def find(self, w, vocab=frozenset()):
        """Бренд по слову запроса: по звучанию, «х» как «x», опечатка у длинного слова (не слово с сайта)."""
        for k in _keys(w):
            if k in self.by_key:
                return self.by_key[k], ("" if LAT_RX.match(w) or k == sound(w) else "x")
        if len(w) >= TYPO_MIN and re.fullmatch(r"[а-я]+", w) and stem(w) not in vocab:
            s = sound(w)
            for k, b in self.by_key.items():
                if len(k) >= TYPO_MIN and k[0] == s[0] and _lev1(s, k):
                    return b, "typo"
        return None, ""


LIKE_BRAND = "({c} LIKE '%/brand%' OR {c} LIKE '%brend%' OR {c} LIKE '%proizvoditel%' OR {c} LIKE '%vendor%' " \
             "OR {c} LIKE '%manufacturer%')"


def _brand_links(db):
    """Ссылки на адреса брендов: [(адрес, текст ссылки, сколько раз)]. В новых базах ссылки хранятся числами
    (link_rows + strs) - так в разы быстрее, чем через вид links."""
    try:
        ids = dict(db.execute("SELECT id, s FROM strs WHERE s LIKE 'http%' AND " + LIKE_BRAND.format(c="s")).fetchall())
        if not ids:
            return []
        rows = db.execute("SELECT dst, anchor, COUNT(*) FROM link_rows WHERE kind='a' AND dst IN (%s) GROUP BY dst, anchor"
                          % ",".join(map(str, ids))).fetchall()
        aid = {a for _d, a, _n in rows if a}
        an = dict(db.execute("SELECT id, s FROM strs WHERE id IN (%s)" % ",".join(map(str, aid))).fetchall()) if aid else {}
        return [(ids[d], an.get(a), n) for d, a, n in rows]
    except sqlite3.Error:
        return db.execute("SELECT dst, anchor, COUNT(*) FROM links WHERE kind='a' AND " + LIKE_BRAND.format(c="dst")
                          + " GROUP BY dst, anchor").fetchall()


_CACHE, _EXTRA = {}, {}


def _site_cached(folder, host):
    """_site_brands с запоминанием: в папке проверки «.бренды сайта.json» (пока не изменился crawl.db) и в памяти.
    Там же - блоки логотипов и свойства из адресов (site_extra)."""
    from .. import jsonfile
    path = os.path.join(folder, "crawl.db")
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return [], [], []
    key = (os.path.abspath(folder), mt)
    if key in _CACHE:
        return _CACHE[key]
    cache = os.path.join(folder, CACHE_FILE)
    try:
        import json
        with open(cache, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("mtime") == mt and c.get("v") == CACHE_V:
            _CACHE[key] = ([tuple(x) for x in c["pages"]], [tuple(x) for x in c["filters"]],
                           [tuple(x) for x in c.get("models") or []])
            _EXTRA[key] = {"logos": [tuple(x) for x in c.get("logos") or []],
                           "facets": [(f, [tuple(v) for v in vs]) for f, vs in c.get("facets") or []]}
            return _CACHE[key]
    except (OSError, ValueError, KeyError):
        pass
    db = _ro(folder)
    res = _site_brands(db, host)
    extra = _extra(db, host)
    if db is not None:
        db.close()
    _CACHE[key], _EXTRA[key] = res, extra
    try:
        jsonfile.save(cache, {"v": CACHE_V, "mtime": mt, "pages": res[0], "filters": res[1], "models": res[2],
                              "logos": extra["logos"], "facets": extra["facets"]})
    except OSError:
        pass
    return res


def _extra(db, host):
    """Блоки логотипов и свойства из адресов (logos.py)."""
    from . import logos
    out = {"logos": [], "facets": []}
    if db is None:
        return out
    try:
        out["logos"] = logos.blocks(db, host)
        rows = db.execute("SELECT url, h1, title FROM pages WHERE status=200 AND (content_type LIKE '%html%' "
                          "OR content_type IS NULL)").fetchall()
        out["facets"] = logos.facets(rows, host, logos.site_words(db, logos._sample(db, host)))
    except sqlite3.Error:
        pass
    return out


def site_extra(folder, host):
    """{"logos": [(название, страница, заголовок, вид)], "facets": [(свойство, [(значение, страниц, адрес)])]}."""
    try:
        mt = os.path.getmtime(os.path.join(folder, "crawl.db"))
    except (OSError, TypeError):
        return {"logos": [], "facets": []}
    _site_cached(folder, host)
    return _EXTRA.get((os.path.abspath(folder), mt)) or {"logos": [], "facets": []}


CACHE_FILE, CACHE_V = ".бренды сайта.json", 9   # 9: адреса брендов по порядку

# Раздел марок или брендов по устройству сайта (exist.ru: /Catalog/Global/Cars/Audi «Запчасти для Audi
# (Ауди)»): в одной папке много соседних страниц, у каждой конец адреса - название, которое стоит в её title или H1
# («Audi», «Alfa_Romeo» = «Alfa Romeo», «%D0%93%D0%90%D0%97» = «ГАЗ»). Так узнаются и /brands/…, и любые другие адреса.
HUB_MIN, HUB_SHARE, HUB_LAT = 8, 0.6, 0.5    # от стольких страниц, такая доля совпала, такая доля из них - латиницей
HUB_SKIP = re.compile(r"/(tags?|blog|news|novosti|articles?|stati|author|users?|search|forum|help|faq|"
                      r"en|eng|english|de|fr|es|it|cn|zh|ua|kz|by|tr|ar)(/|$)", re.I)
# разделы сайта, а не бренды: «/eng/hotel/about_hotel», «contacts», «faq» (otel-primer.ru) - такая папка не раздел брендов
SECTION = re.compile(r"(?i)^(?:about|contacts?|faq|news|gallery|photo\w*|awards?|rules|payment\w*|delivery|offers?|"
                     r"special\w*|reviews?|blog|services?|prices?|vacanc\w*|careers?|jobs|o-nas|o-kompanii|kontakty|"
                     r"dostavka|oplata|otzyvy|uslugi|ceny|tseny|novosti|stati|aktsii|akcii|garantiya|sertifikaty|"
                     r"partners|politika\w*|privacy|sitemap|login|register)(?:[-_]|$)")
# раздел марок техники: товары «для Audi» (запчасти, аксессуары), а не товары бренда Audi
FOR_PATH = re.compile(r"(^|/)(cars?|auto|avto|avtomobil\w*|marka|marki|marks?|makes?|moto\w*|trucks?|vehicles?|"
                      r"models?|modeli|tehnika|technics)(/|$)", re.I)
FOR_TITLE = r"(?:для|for|на)\s+{}"


def _hubs(urls, host):
    """Разделы марок и брендов по устройству сайта: [(название, адрес, вид, [как ещё пишется])], вид - "for"
    (марка, для которой товары: «запчасти для Audi») или "maker" (производитель). Подразделы страницы бренда
    («/Cars/Suzuki/Grand_Vitara») - модели: [(бренд, модель)]."""
    from urllib.parse import unquote
    kids = {}
    for u, (h1, title) in urls.items():
        sp = urlsplit(u)
        if sp.query or (sp.hostname or "").removeprefix("www.") != host:
            continue
        path = sp.path.rstrip("/")
        parent, _, slug = path.rpartition("/")
        slug = unquote(slug).strip("_- ")
        if not slug or not parent or HUB_SKIP.search(parent + "/"):
            continue
        kids.setdefault(parent, []).append((slug, u, h1 or "", title or ""))

    def match(slug, h1, title, words):
        parts = [p for p in re.split(r"[\s_+-]+", slug) if p]
        if not parts or len(parts) > words or len(slug) > 30 or re.fullmatch(r"[\d\W]+", slug):
            return None
        if words == 2 and re.search(r"[a-z]\d|\d[a-z]{2,}", slug, re.I):
            return None     # код модели («air35fvs1r», «df50a2ms1»), а не название бренда
        rx = re.compile(r"(?<![\w])" + r"[\s_-]*".join(map(re.escape, parts)) + r"(?![\w])", re.I)
        for t in (h1, title):
            m = rx.search(t)
            if m:
                ru = re.search(r"\(\s*([А-Яа-яЁё][А-Яа-яЁё -]{1,25}?)\s*\)", t[m.end():m.end() + 40])
                return m.group(0), t, (ru.group(1).lower() if ru else "")
        return None
    found = {}
    for parent, ch in kids.items():
        if len(ch) < HUB_MIN:
            continue
        ok = [(c, m) for c in ch for m in [match(c[0], c[2], c[3], 2)] if m]
        lat = sum(1 for _c, m in ok if re.match(r"[A-Za-z]", m[0]))
        if len(ok) < HUB_MIN or len(ok) < HUB_SHARE * len(ch) or lat < HUB_LAT * len(ok):
            continue
        if sum(1 for c in ch if SECTION.match(c[0])) >= 2:
            continue        # пункты меню сайта («About hotel», «Contacts», «FAQ»)
        dl = sum(1 for _c, m in ok if re.search(FOR_TITLE.format(re.escape(m[0])), m[1], re.I))
        kind = "for" if FOR_PATH.search(parent) or dl >= 0.5 * len(ok) else "maker"
        found[parent] = (kind, ok)
    out, models = [], []
    # «/auto/signalizaciya-toyota/4runner»: соседние папки с одним началом и разным концом (signalizaciya-toyota,
    # signalizaciya-kia…) - это страницы марок, а их подразделы - модели этой марки, а не марки (csat.ru)
    fam = {}
    for p in found:
        gp, _, slug = p.rpartition("/")
        m = re.match(r"([^-_]+)[-_](.+)$", unquote(slug))
        if m:
            fam.setdefault((gp, m.group(1).lower()), []).append((p, m.group(2)))
    by_url = {urlsplit(u).path.rstrip("/"): u for u in urls} if any(len(v) >= 3 for v in fam.values()) else {}
    for ps in fam.values():
        if len(ps) < 3:
            continue
        for p, tail in ps:
            u = by_url.get(p, "")
            h1, title = urls.get(u, ("", ""))
            mm = match(tail, h1 or "", title or "", 2)
            brand = _case(mm[0]) if mm else _slug_name(tail)
            kind, ok = found.pop(p)
            models += [(brand, nm) for nm in dict.fromkeys(_model_name(m_[0]) for _c, m_ in ok) if nm]
            out.append((brand, u or p, kind, []))
    child = {urlsplit(c[1]).path.rstrip("/") for _k, ok in found.values() for c, _m in ok}
    found = {p: v for p, v in found.items() if p not in child}   # «/Cars/Audi/» с «A4», «Q5» - модели, не бренды
    by_path = {urlsplit(c[1]).path.rstrip("/"): _case(m[0]) for _k, ok in found.values() for c, m in ok}
    fors = {m[0].lower() for k, ok in found.values() if k == "for" for _c, m in ok}
    for p, (k, ok) in list(found.items()):   # те же названия, что в разделе марок («/Accessory/Commercial/Ford») - марки
        if k == "maker" and fors and sum(1 for _c, m in ok if m[0].lower() in fors) >= 0.5 * len(ok):
            found[p] = ("for", ok)
    for parent, (kind, ok) in sorted(found.items(), key=lambda x: -len(x[1][1])):
        for c, m in ok:
            out.append((_case(m[0]), c[1], kind, [m[2]] if m[2] else []))
    # модели: подраздел страницы бренда, названия - как в title («Запчасти для Suzuki Grand Vitara»)
    for parent, ch in kids.items():
        brand = by_path.get(parent)
        if brand is None or len(ch) < 3:
            continue
        ok = [m for c in ch for m in [match(c[0], c[2], c[3], 3)] if m and m[0].lower() != brand.lower()]
        if len(ok) >= 3 and len(ok) >= HUB_SHARE * len(ch):
            models += [(brand, nm) for nm in dict.fromkeys(_model_name(m[0]) for m in ok) if nm]
    return out, sorted(set(models))


ROMAN = re.compile(r"^(?:i{1,3}|iv|v|vi{1,3}|ix|x)$", re.I)


def _model_name(s):
    """«Baleno хэтчбек III» → «Baleno», «Grand Vitara II» → «Grand Vitara»: без кузова и поколения."""
    ws = s.split()
    out = [w for i, w in enumerate(ws) if re.search(r"[A-Za-z0-9]", w) and not (i and ROMAN.match(w))]
    return " ".join(out[:3])


def _site_brands(db, host):
    """Страницы брендов и фильтры брендов по категориям одного сайта:
    ([(название, адрес, вид, [написания])], [(название, адрес категории, адрес фильтра, H1 категории)],
    [(бренд, модель)])."""
    pages, filters, models = [], [], []
    if db is None:
        return pages, filters, models
    try:
        rows = db.execute("SELECT url, h1, title FROM pages WHERE status=200").fetchall()
        urls = {u: h for u, h, _t in rows}
        pages, models = _hubs({u: (h, t) for u, h, t in rows}, host)
        anchors = {}
        for d, a, n in _brand_links(db):
            if not (BRAND_PAGE.search(urlsplit(d or "").path) or BRAND_FILTER.match(urlsplit(d or "").path)):
                continue
            a = re.sub(r"\s+", " ", a or "").strip()
            anchors.setdefault(d, {})
            if a and len(a) <= 30 and len(a.split()) <= 2 and not re.fullmatch(r"[\d\W]+|[A-ZА-Я]", a):
                anchors[d][a] = anchors[d].get(a, 0) + n
        cand = set(anchors) | {u for u in urls if BRAND_PATH.search(u)}
    except sqlite3.Error:
        return pages, filters, models
    hub = {u for _n, u, _k, _f in pages}
    for u in sorted(cand - hub):   # по порядку: одинаковый итог при каждом сборе
        sp = urlsplit(u)
        if (sp.hostname or "").removeprefix("www.") != host or (sp.query and not re.search(r"brand", sp.query, re.I)):
            continue
        path = sp.path
        m = BRAND_PAGE.search(path)
        f = None if m else BRAND_FILTER.match(path)
        if not (m or f):
            continue
        slug = (m or f).group(1 if m else 2)
        if f and re.search(r"brand", f.group(1), re.I):
            continue        # два бренда в одном адресе («brand-baxi/nastennye/brand-bosch/») - не считаем
        name, exact = _name_for(slug, anchors.get(u) or {}, urls.get(u) or "")
        if not name:
            continue
        if not exact:
            name = "~" + name   # придумано из адреса («Barer» из /brand-barer/): если ищут по-русски - «Барьер»
        if m:
            pages.append((name, u, "maker", []))
        else:
            cat = f"{sp.scheme}://{sp.netloc}{f.group(1)}"
            filters.append((name, cat, u, urls.get(cat) or urls.get(cat.rstrip("/")) or f.group(1)))
    return pages, filters, models


def _name_for(slug, anchors, h1):
    """Как называет бренд сам сайт: текст ссылки или слово из H1 с тем же звучанием, что и адрес."""
    want = sound(slug.replace("-", "").replace("_", ""))
    for a, _ in sorted(anchors.items(), key=lambda x: -x[1]):
        if sound(a.replace(" ", "").replace("-", "")) == want:
            return _case(a), True
    for w in re.findall(r"[A-Za-zА-Яа-яЁё][\w-]*", h1 or ""):
        if sound(w.lower()) == want:
            return _case(w), True
    if re.fullmatch(r"[a-z][a-z0-9_-]{1,29}", slug, re.I) and not re.fullmatch(r"\d+", slug):
        return _slug_name(slug), False
    return "", False


def _products(folder, B):
    """Товары своего сайта по брендам (страницы с разметкой товара, бренд - в H1, названии из разметки, title или
    в бренде из разметки). Нет разметки - None."""
    if not folder:
        return None
    from . import models
    out, n = {}, 0
    for h, br in models.products(os.path.join(folder, "crawl.db")):
        n += 1
        seen = set()
        for w in _words(h) + ([re.sub(r"[\s_-]+", "", br.lower())] if br else []):
            for k in _keys(w):
                b = B.by_key.get(k)
                if b is not None and id(b) not in seen:
                    seen.add(id(b))
                    out[id(b)] = out.get(id(b), 0) + 1
    return out if n else None


PROD_BRAND_MIN = 3   # производитель из названий товаров - от стольких товаров


def _product_brands(folder):
    """Производители по товарам своего сайта: ([(название, товаров)] из разметки товара - itemprop brand, JSON-LD
    brand; {начало названий товаров: товаров} - models.parse: «Suprotec 120987», «LAVR LN1484»). Начало названия -
    только подсказка: у многих сайтов там серия или тип («Кран шаровой BASE … Valtec»), поэтому новым брендом оно
    не становится, а лишь отмечает уже найденный бренд как производителя."""
    if not folder:
        return [], {}
    from . import models
    rows = models.products(os.path.join(folder, "crawl.db"))
    cnt, case = {}, {}
    for _n, b in rows:
        b = b.strip()
        if b and len(b) <= 30 and len(_words(b)) <= 2 and not re.fullmatch(r"[\d\W]+", b):
            cnt[b.lower()] = cnt.get(b.lower(), 0) + 1
            case.setdefault(b.lower(), b)
    names = [n for n, _b in rows]
    starts = models.parse(names)["brands"] if len(names) >= models.MIN_PRODUCTS else {}
    return [(_case(case[b]), n) for b, n in cnt.items() if n >= 2], starts


def _vocab(db):
    """Слова с сайта (основы из title и H1): опечаткой бренда они быть не могут («котлов» - не «Котлофф»)."""
    out = set()
    if db is None:
        return out
    try:
        for (t,) in db.execute("SELECT COALESCE(title, '') || ' ' || COALESCE(h1, '') FROM pages WHERE status=200 "
                               "LIMIT 20000"):
            out |= {stem(w) for w in _words(t) if re.fullmatch(r"[а-я]+", w)}
    except sqlite3.Error:
        pass
    return out


def _gwords(name, city_stems):
    return {stem(w) for w in _words(name) if w not in STOP and stem(w) not in city_stems and len(w) > 2}


def build(data, folder=None, dicts=None):
    """data - семантика после decisions.apply и plan.enrich; folder - папка проверки (обход сайта, конкуренты рядом).
    Шаги: бренды из словаря, страниц, фильтров, логотипов и товаров → группы-бренды и латиница в запросах → бренды в
    каждом запросе, пары («Royal Thermo») и модели («suzuki grand vitara») → бренд × категория → итог по брендам."""
    from . import dicts as DI
    from .newsite import KEY as NS_KEY
    from .plan import _rival_folders
    d = dicts or DI.load()
    from . import dictionary   # бренды темы сайта («Словарь»): «Общий» - это d["brands"], к нему - ниша и подтема
    d = dict(d, brands=list(d["brands"]) + dictionary.lines(data, ("brand",), root=False))
    groups = [g for g in data.get("groups") or [] if g.get("land") and g["land"]["st"] != "manual"]
    freq = _freq_mode(groups)
    new = bool(data.get(NS_KEY))
    host = _host(data.get("site") or "")
    own_db = _ro(folder) if folder and not new else None
    rivals = _rival_folders(os.path.dirname(folder), data.get("competitors") or []) if folder else {}
    B = Brands()
    starts = _from_sources(B, d, data, folder, host, own_db, rivals)
    brand_groups = _from_groups(B, groups)
    rows = [(g, r) for g in groups for r in g.get("q") or [] if not r[7]]
    series = _from_latin(B, rows, starts)
    if not B.items:
        _close(own_db)
        return {"brands": [], "cats": [], "freq": freq, "new": new, "products_known": False}
    scan = _scanner(B, _vocab(own_db))
    scans = [(g, r) + scan(r[0]) for g, r in rows]
    merged, alias, root = _pairs(B, scans)
    # группы с брендом в названии («Запчасти Baxi», «Котлы Navien») - не категории, а страницы бренда в категории
    city = (data.get("city") or "").lower()
    city_stems = {stem(w) for w in _words(city)} if city else set()
    brand_named = {}
    for g in groups:
        if id(g) in brand_groups:
            continue
        _ws, f = scan(g["name"])
        if f:
            brand_named[id(g)] = root(f[0][1])
    cat_groups = [g for g in groups if id(g) not in brand_groups and id(g) not in brand_named
                  and g["land"]["st"] in ("ok", "fix", "wrong", "create", "absent")]
    gw = {id(g): _gwords(g["name"], city_stems) for g in cat_groups}
    cat_ids = set(gw)

    def cat_of(g, ws):
        if id(g) in cat_ids:
            return g
        qs = {stem(x) for x in ws}   # запрос из группы бренда («котлы бакси» в группе «Baxi») - категория по словам
        return max((c for c in cat_groups if gw[id(c)] and gw[id(c)] <= qs), key=lambda c: len(gw[id(c)]), default=None)
    pages_in = {}   # (бренд, категория) → своя страница из группы с брендом в названии
    for g in groups:
        b = brand_named.get(id(g))
        if b is not None and g["land"]["st"] in ("ok", "fix", "wrong"):
            c = cat_of(g, _words(g["name"]))
            pages_in.setdefault((id(b), c["name"] if c else ""), g["land"]["url"])
    stat = _stats(B, scans, merged, alias, series, cat_of, freq)
    prods = _products(folder if own_db is not None else None, B)
    out = _summary(B, stat, alias, groups, brand_groups, pages_in, prods, freq)
    _close(own_db)
    out.sort(key=lambda x: (-x["d"], -x["n"], -(x["products"] or 0), x["name"].lower()))
    cd = {}
    for x in out:
        for c in x["cats"]:
            if c["cat"]:
                cd[c["cat"]] = cd.get(c["cat"], 0) + c["d"]
    cats = sorted(cd, key=lambda k: -cd[k])
    return {"brands": out, "cats": cats, "freq": freq, "new": new, "products_known": prods is not None,
            "count": {k: sum(1 for x in out if x["st"] == k) for k in ("have", "create", "decide")},
            "kinds": {k: sum(1 for x in out if x["kind"] == k) for k in ("for", "maker", "parts")}}


def _from_sources(B, d, data, folder, host, own_db, rivals):
    """Бренды не из запросов: словарь человека, страницы и фильтры брендов своего сайта и конкурентов, блоки
    логотипов, «Бренды и прочие», разметка товаров. → начала названий товаров {бренд: товаров} (models.parse)."""
    from ..urls import page_key
    # 1. словарь человека - главнее всего
    for name, forms in user_pairs(d.get("brands")):
        b = B.add(name, [f.lower() for f in forms], weight=1000)
        if b:
            b["user"] = True
    # 2. страницы и фильтры брендов своего сайта и конкурентов
    own_pages, own_filters, own_models = _site_cached(folder, host) if own_db is not None else ([], [], [])
    for name, u, kind, forms in own_pages:
        b = B.add(name, forms, weight=10)
        if b:
            b["kind"].add(kind)
            if not b["page"]:
                b["page"] = u
    for name, cat, u, _h1 in own_filters:
        b = B.add(name, weight=10)
        if b:
            b["filters"].setdefault(page_key(cat), u)
            b["kind"].add("maker")
    for name, model in own_models:
        b = B.get(name)
        if b:
            b["site_models"].add(model)
    # блоки логотипов («Используем фурнитуру брендов»: Blum, Hettich…) - бренды с сайта, даже если их не ищут
    for name, u, _head, hint in (site_extra(folder, host)["logos"] if own_db is not None else []):
        b = B.add(name, weight=8)
        if b:
            b["kind"].add("logo")
            b["logo"] = b.get("logo") or u
            if hint:
                b["kind"].add(hint)
    # бренды той же ниши с других сайтов («Бренды и прочие»): узнаются в запросах, в списке - только если ищут
    for name, hint in _catalog_brands(data):
        if B.get(name) is None:
            b = B.add(name, weight=2)
            if b and hint:
                b["kind"].add(hint)
    # производители товаров: бренд из разметки товара и первое слово названий товаров («Suprotec 120987»)
    marked, starts = _product_brands(folder if own_db is not None else None)
    for name, n in marked:
        b = B.add(name, weight=4)
        if b:
            b["kind"].add("maker")
    for h, rf_ in rivals.items():
        rp, rf, _rm = _site_cached(rf_, h)
        for name, u, _k, _f in rp:
            b = B.add(name, weight=3)
            if b:
                b["rivals"].setdefault(h, u)
        for name, cat, u, h1 in rf:
            b = B.add(name, weight=3)
            if b:
                b["rival_filters"].setdefault(h, {}).setdefault(h1, u)   # категория конкурента словами (H1)
    return starts


def _from_groups(B, groups):
    """3. Группы-бренды семантики (страница бренда у конкурентов или у вас). → {id(группы): бренд}."""
    brand_groups = {}
    for g in groups:
        rv = g.get("rivals") or []
        if ((g.get("todo") or "").startswith("Создать страницу бренда") or (rv and all(BRAND_PATH.search(u) for u in rv))
                or (g.get("page") and BRAND_PAGE.search(urlsplit(g["page"]).path))) and len(g["name"].split()) <= 2:
            b = B.add(g["name"], weight=5)
            if b:
                brand_groups[id(g)] = b
                if g["land"]["st"] in ("ok", "fix", "wrong") and not b["page"]:
                    b["page"] = g["land"]["url"]
    return brand_groups


def _from_latin(B, rows, starts):
    """Латиница в запросах - бренд, если не модель с сайта и не серия при известном бренде; производитель - по
    началу названий товаров. → series: слова после бренда, которые не бренды («outlander», «tiggo»)."""
    known = set(B.by_key)    # бренды со страниц, фильтров, групп и словаря - до латиницы из запросов
    multi = {w for b in B.items for nm in b["names"] for w in _words(nm) if len(_words(nm)) > 1}
    lat, lat_known = {}, {}
    for g, r in rows:
        wl = _words(r[0])
        ws = set(wl)
        has_known = (any(k in known for w in ws for k in _keys(w))
                     or any(k in known for a, b in zip(wl, wl[1:]) for k in _keys(a + b)))
        for w in ws:
            if (LAT_RX.match(w) and w not in LAT_STOP and not re.search(r"\d", w) and not (_keys(w) & known)
                    and not any(len(p) <= 2 for p in w.split("-"))):   # «pe-rt», «pe-x» - тип трубы, не бренд
                lat[w] = lat.get(w, 0) + 1
                lat_known[w] = lat_known.get(w, 0) + has_known
    # слова моделей с сайта («Grand Vitara» в разделе Suzuki) - не бренды
    model_words = {w for b in B.items for m in b["site_models"] for w in _words(m)}
    series = set(model_words)
    for w, n in lat.items():
        if n >= MIN_LAT_QUERIES and lat_known[w] >= SERIES_SHARE * n:
            series.add(w)
    for w, n in sorted(lat.items(), key=lambda x: -x[1]):
        # «master» из «Master Gas» и серия при бренде («Seoul» почти всегда с «Master Gas») - не отдельный бренд
        if n >= MIN_LAT_QUERIES and w not in multi and w not in model_words and lat_known[w] < SERIES_SHARE * n:
            new_b = B.get(w) is None
            b = B.add(_slug_name(w), weight=1)
            if b is not None and new_b:
                b["lat"] = True     # бренд только из запросов: может оказаться моделью («vitara» у Suzuki)
    for name, n in starts.items():   # начало названий товаров - производитель, если такой бренд уже известен
        b = B.get(name) if n >= PROD_BRAND_MIN else None
        if b is not None and "for" not in b["kind"]:
            b["kind"].add("maker")
    return series


def _scanner(B, vocab):
    def scan(text):
        """Бренды в запросе по порядку: [(позиция, бренд, как написано, как узнан)]; два слова - тоже («Master Gas»)."""
        ws, out, i = _words(text), [], 0
        while i < len(ws):
            w = ws[i]
            if i + 1 < len(ws):
                b2 = next((B.by_key[k] for k in _keys(w + ws[i + 1]) if k in B.by_key), None)
                if b2 is not None and len(ws[i + 1]) >= 2 and any(" " in nm for nm in b2["names"]):
                    out.append((i, b2, w + " " + ws[i + 1], ""))
                    i += 2
                    continue
            if w not in STOP and len(w) >= 3 and not re.fullmatch(r"\d+", w):
                b, how = B.find(w, vocab)
                if b is not None:
                    out.append((i, b, w, how))
            i += 1
        return ws, out
    return scan


def _pairs(B, scans):
    """Два бренда рядом в большинстве запросов («роял термо», «federica bugatti») - один бренд из двух слов;
    слово только из запросов почти всегда после другого бренда - его модель.
    → (merged: (id a, id b) → бренд из двух слов, alias: id модели → её бренд, root: бренд или его хозяин)."""
    pair, alone = {}, {}
    for _g, _r, _ws, found in scans:
        for j, (i, b, _w, _h) in enumerate(found):
            alone[id(b)] = alone.get(id(b), 0) + 1
            if j + 1 < len(found) and found[j + 1][0] == i + len(_w.split()) and found[j + 1][1] is not b:
                k = (id(b), id(found[j + 1][1]))
                pair[k] = (pair.get(k, (0, b, found[j + 1][1]))[0] + 1, b, found[j + 1][1])
    merged, alias = {}, {}
    # модель после марки: слово только из запросов, которое почти всегда идёт после другого бренда, - модель этого
    # бренда, а не бренд («mitsubishi outlander», «suzuki grand vitara»: grand - модель Suzuki, vitara - тоже)
    root = lambda x: alias.get(id(x), x)  # noqa: E731
    for (ia, ib), (n, a, b) in sorted(pair.items(), key=lambda x: -alone[x[0][0]]):
        ra = root(a)
        if (b["lat"] and id(b) not in alias and ra is not b and n >= PAIR_SHARE * alone[ib]
                and (not a["lat"] or id(a) in alias or n < PAIR_SHARE * alone[ia])):
            alias[ib] = ra
    for (ia, ib), (n, a, b) in pair.items():
        if ia in alias or ib in alias:
            continue
        if a["lat"] != b["lat"]:
            continue    # известный бренд + слово из запросов - модель (выше), а не бренд из двух слов
        if n >= PAIR_MIN and n >= PAIR_SHARE * min(alone[ia], alone[ib]) and not (ia in merged or ib in merged):
            na = max(a["names"].items(), key=lambda x: x[1])[0]
            nb = max(b["names"].items(), key=lambda x: x[1])[0]
            m = B.add(f"{na} {nb}", weight=2)
            if m is not None and m is not a and m is not b:
                for x in (a, b):
                    m["page"] = m["page"] or x["page"]
                    for f in ("rivals", "filters", "rival_filters"):
                        for kk, vv in x[f].items():
                            m[f].setdefault(kk, vv)
                merged[(ia, ib)] = m
    part = {i: m for (ia, ib), m in merged.items() for i in (ia, ib)}
    for k, v in list(alias.items()):     # «trung nguyen legend»: legend - модель Trung Nguyen, а не «Nguyen»
        alias[k] = part.get(id(v), v)
    return merged, alias, root


def _stats(B, scans, merged, alias, series, cat_of, freq):
    """Спрос по брендам: запросы, написания, модели, категории. → {id(бренда): {"b", "n", "d", "q", "forms", "cats"}}."""
    models_ix, dup = {}, set()   # модель с сайта → марка (только латиницей, от 4 букв, у одной марки)
    for b in B.items:
        for m in b["site_models"]:
            t = m.lower()
            if re.fullmatch(r"[a-z][a-z0-9 -]{3,}", t) and t not in LAT_STOP:
                if t in models_ix and models_ix[t] is not b:
                    dup.add(t)
                models_ix[t] = b
    for t in dup:
        del models_ix[t]
    stat = {}
    for g, r, ws, found in scans:
        seen, j = set(), 0
        items = []
        while j < len(found):
            i, b, w, how = found[j]
            if j + 1 < len(found) and (id(b), id(found[j + 1][1])) in merged and found[j + 1][0] == i + len(w.split()):
                items.append((merged[(id(b), id(found[j + 1][1]))], w + " " + found[j + 1][2], "", "",
                              found[j + 1][0] + len(found[j + 1][2].split()) - 1))
                j += 2
                continue
            if id(b) in alias:   # модель: к своему бренду («suzuki grand vitara» - Suzuki, модель «grand vitara»)
                if items and items[-1][0] is alias[id(b)] and items[-1][4] + 1 >= i:
                    items[-1] = items[-1][:3] + ((items[-1][3] + " " + w).strip(), i + len(w.split()) - 1)
                else:
                    items.append((alias[id(b)], "", "", w, i + len(w.split()) - 1))
                j += 1
                continue
            end = i + len(w.split()) - 1
            items.append((b, w, how, _site_model(b, ws, end + 1, series), end))
            j += 1
        if not items:      # «grand vitara запчасти» без марки: модель с сайта, которая есть только у одной марки
            hit = next(((mb, t) for k in (3, 2, 1) for i in range(len(ws) - k + 1)
                        for t in [" ".join(ws[i:i + k])] for mb in [models_ix.get(t)] if mb is not None), None)
            if hit:
                items.append((hit[0], "", "", hit[1], -1))
        for b, w, how, model, _end in items:
            if model:
                b["models"][model] = b["models"].get(model, 0) + 1
            if id(b) in seen:
                continue
            seen.add(id(b))
            e = stat.setdefault(id(b), {"b": b, "n": 0, "d": 0, "q": [], "forms": {}, "cats": {}})
            e["n"] += 1
            e["d"] += _dem(r, freq)
            if len(e["q"]) < 8:
                e["q"].append(r[0])
            if w:
                f = e["forms"].setdefault(w, {"n": 0, "how": how})
                f["n"] += 1
            cat = cat_of(g, ws)
            key = cat["name"] if cat else ""
            c = e["cats"].setdefault(key, {"n": 0, "d": 0, "q": [], "g": cat})
            c["n"] += 1
            c["d"] += _dem(r, freq)
            if len(c["q"]) < 5:
                c["q"].append(r[0])
    return stat


def _summary(B, stat, alias, groups, brand_groups, pages_in, prods, freq):
    """5. Итог по брендам: что сделать со страницей бренда и с каждой категорией. → [бренд] (без сортировки)."""
    from ..urls import page_key
    big = lambda n, dd: n >= FILTER_MIN or (freq and dd >= FILTER_FREQ)  # noqa: E731
    out = []
    for b in B.items:
        if id(b) in alias:
            continue     # модель другого бренда
        e = stat.get(id(b))
        n_rivals = sorted(set(b["rivals"]) | set(b["rival_filters"]))
        # производитель товаров сайта - в списке, даже если его пока не ищут (решить, нужна ли страница)
        own = ("maker" in b["kind"] and (prods or {}).get(id(b), 0) >= PROD_BRAND_MIN) or "logo" in b["kind"]
        if not e and not b["page"] and not n_rivals and not b["user"] and not own:
            continue
        e = e or {"n": 0, "d": 0, "q": [], "forms": {}, "cats": {}}
        if not e["n"] and not b["page"] and not b["filters"] and not own:
            continue     # бренд только у конкурента и никто не ищет - не тема
        name = _case(max(b["names"].items(), key=lambda x: (x[1], x[0][:1].isupper(), -len(x[0])))[0])
        top = max(e["forms"].items(), key=lambda x: x[1]["n"], default=("", {}))[0]
        if (not b.get("exact") and re.fullmatch(r"[а-я]+(?: [а-я]+)?", top)
                and not any(re.search(r"[a-z]", f) for f in e["forms"])):
            name = top[:1].upper() + top[1:]   # сайт бренда не называет, ищут только по-русски: «Барьер», а не «Barer»
        grp = next((g for g in groups if brand_groups.get(id(g)) is b), None)
        if b["page"]:
            st = "have"
        elif grp is not None and grp["land"]["st"] == "create":
            st = "create"
        elif big(e["n"], e["d"]) or (e["n"] and n_rivals):
            st = "create"
        else:
            st = "decide"
        cats = []
        for key, c in e["cats"].items():
            g = c["g"]
            url = ""
            if g is not None:
                url = b["filters"].get(page_key(g["land"]["url"] or g.get("page") or ""), "")
            url = url or pages_in.get((id(b), key), "")
            rivals = sorted(h for h, fs in b["rival_filters"].items() if g is not None and _cat_match(g["name"], fs))
            cst = ("filter" if url else "create" if big(c["n"], c["d"]) else "rival" if rivals else "low") if key else \
                  ("have" if b["page"] else "create" if big(c["n"], c["d"]) else "low")
            cats.append({"cat": key, "n": c["n"], "d": c["d"], "q": c["q"], "url": url or (b["page"] if not key else ""),
                         "rivals": rivals, "st": cst})
        cats.sort(key=lambda c: -c["d"])
        forms = sorted(({"w": w, "n": f["n"], "how": f["how"]} for w, f in e["forms"].items()), key=lambda f: -f["n"])
        out.append({"name": name, "n": e["n"], "d": e["d"], "q": e["q"], "page": b["page"], "st": st,
                    "rivals": n_rivals, "rival_pages": dict(b["rivals"]), "filters": len(b["filters"]),
                    "products": (prods or {}).get(id(b), 0) if prods is not None else None,
                    "forms": forms, "user": b["user"], "cats": cats,
                    "group": grp["name"] if grp is not None else "",
                    "kind": _kind(b["kind"], (prods or {}).get(id(b), 0)), "logo": b.get("logo") or "",
                    "models": sorted(b["models"].items(), key=lambda x: (-x[1], x[0]))[:8],
                    "site_models": len(b["site_models"]), "exact": bool(b.get("exact"))})
    return out


def _kind(kinds, prods):
    """Вид бренда: марка (товары для неё), производитель товаров сайта, комплектующие и материалы (блок логотипов
    «Используем фурнитуру…»). Блок логотипов без пояснения у магазина с товарами бренда - производитель."""
    if "for" in kinds:
        return "for"
    if "maker" in kinds or ("logo" in kinds and prods >= PROD_BRAND_MIN and "parts" not in kinds):
        return "maker"
    return "parts" if "parts" in kinds else ""


def _catalog_brands(data):
    try:
        from .. import catalog
        return catalog.known_brands(data)
    except Exception:
        return []


def _site_model(b, ws, i, series=frozenset()):
    """Модель сразу после бренда в запросе: с сайта («suzuki grand vitara запчасти» → «grand vitara») или слово,
    которое в запросах почти всегда идёт после бренда («mitsubishi outlander» → «outlander»)."""
    ms = b.setdefault("_ml", {m.lower() for m in b["site_models"]})
    for k in (3, 2, 1):
        t = " ".join(ws[i:i + k])
        if len(ws) >= i + k and t in ms:
            return t
    out = []
    while i < len(ws) and len(out) < 2 and ws[i] in series:
        out.append(ws[i])
        i += 1
    return " ".join(out)


def _cat_match(name, fs):
    want = {stem(w) for w in _words(name) if w not in STOP and len(w) > 2}
    return bool(want) and any(want <= {stem(w) for w in _words(k)} for k in fs)


def _close(db):
    try:
        db and db.close()
    except sqlite3.Error:
        pass


ST_BRAND = {"have": LB.TREE["have"], "create": LB.TREE["create"], "decide": LB.TREE["decide"]}
ST_CELL = {"have": LB.TREE["have"], "filter": LB.TREE["filter"], "create": LB.TREE["create"], "rival": ST["rival"],
           "low": ST["low"]}
HOW = {"": "", "x": "«х» вместо «x»", "typo": "написано иначе"}


def view(r):
    """Для страницы «Семантика», вкладка «Бренды»: короче, с подписями статусов."""
    if not r:
        return {"brands": [], "cats": [], "count": {}}
    out = []
    for b in r["brands"]:
        out.append({"name": b["name"], "n": b["n"], "d": b["d"], "q": b["q"][:6], "page": b["page"], "st": b["st"],
                    "rivals": b["rivals"], "rp": b["rival_pages"], "products": b["products"], "user": b["user"],
                    "forms": [[f["w"], f["n"], HOW[f["how"]]] for f in b["forms"][:8]],
                    "kind": b.get("kind") or "", "models": [list(m) for m in (b.get("models") or [])[:6]],
                    "logo": b.get("logo") or "",
                    "sm": b.get("site_models") or 0,
                    "cats": {c["cat"]: [c["n"], c["d"], c["st"], c["url"], c["q"][:4], c["rivals"]] for c in b["cats"]}})
    return {"brands": out, "cats": r["cats"], "freq": r["freq"], "count": r.get("count") or {},
            "products_known": r.get("products_known"), "labels": {"brand": ST_BRAND, "cell": ST_CELL},
            "cats_shown": CATS_SHOWN, "alone": ALONE, "kinds": r.get("kinds") or {}, "kind_names": KIND}


# вид бренда: марка, для которой товары (раздел «Запчасти для Audi»), или производитель товаров
KIND = {"for": "Марка: товары для неё", "maker": "Производитель товаров",
        "parts": "Комплектующие и материалы (из чего делают)"}
ALONE = "Только бренд"   # запросы с брендом без категории: «baxi уфа», «бакси официальный сайт»


def rows(r):
    """Строки для Excel: лист «Бренды» и «Бренды по категориям»."""
    brands = []
    for b in r["brands"]:
        brands.append([b["name"], b["d"], b["n"], ", ".join(f'{f["w"]} ({f["n"]})' for f in b["forms"][:8]),
                       ST_BRAND[b["st"]], b["page"], ", ".join(b["rivals"]),
                       "" if b["products"] is None else b["products"], ", ".join(b["q"][:5]), KIND.get(b.get("kind"), ""),
                       ", ".join(f"{m} ({n})" for m, n in (b.get("models") or [])[:8])])
    cells = []
    for b in r["brands"]:
        for c in b["cats"]:
            cells.append([b["name"], c["cat"] or ALONE, c["d"], c["n"], ST_CELL[c["st"]], c["url"],
                          ", ".join(c["rivals"]), ", ".join(c["q"][:4])])
    return brands, cells
