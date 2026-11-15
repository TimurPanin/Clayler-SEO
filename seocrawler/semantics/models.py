"""Бренды, серии и модели из названий товаров.

«Оправа Christian Lacroix CL1160 004» → тип «оправа», бренд «christian lacroix», модель «cl1160», цвет «004».
«ACUVUE OASYS with HydraLuxe (30 линз) -1.00/8.5» → тип нет, бренд «acuvue», серия «oasys».
Артикулы в Вордстате обычно ищут 0-5 раз в месяц, поэтому подсказки собираются не по моделям, а уровнем выше:
«оправа christian lacroix» (тип + бренд) и «acuvue oasys» (бренд + серия). Бесплатно и без сети: только H1 страниц
с разметкой товара из обхода.

Как отличить бренд от серии без словаря: бренд - начало названия, общее для многих товаров; если за первым словом
почти всегда идёт одно и то же второе («christian» → «lacroix», «david» → «beckham»), бренд из двух слов. Серия -
следующее слово, общее хотя бы для MIN_SERIES товаров бренда. Модель - первое слово с цифрами, цвет - последнее."""
import re
import sqlite3

MIN_PRODUCTS = 30      # меньше товаров с разметкой - на сайте не каталог, разбирать нечего
MIN_PAIR = 3           # тип + бренд: столько товаров, чтобы стоило собирать подсказки
MIN_SERIES = 3         # бренд + серия: столько товаров
TWO_WORD_SHARE = 0.9   # за первым словом бренда так часто одно и то же второе - бренд из двух слов
MAX_PAIRS = 40         # фраз «тип + бренд» в сборе (самые большие по числу товаров)
MAX_SERIES = 25        # фраз «бренд + серия»
SMALL = {"для", "с", "со", "и", "в", "на", "без", "из", "по", "от", "под", "with", "for", "and", "the", "of"}
# служебные слова в названии: не бренд и не серия («линзы при астигматизме», «очки детские»)
NOT_BRAND = {"линзы", "линза", "очки", "оправа", "оправы", "при", "детские", "детская", "женские", "мужские", "новый",
             "new", "uv", "шт", "уп", "набор", "комплект"}


def _tokens(name):
    return re.findall(r"[0-9a-zа-яё][0-9a-zа-яё./+-]*", (name or "").replace("ё", "е"), re.I)


def _is_model(t):
    return bool(re.search(r"\d", t))


def split(name):
    """Название → (тип, слова до модели, модель, цвет). Тип - русские слова с маленькой буквы в начале (первое - с
    большой): «Солнцезащитные очки», «Цветные линзы». Дальше - бренд и серия до первого слова с цифрами."""
    toks = _tokens(name)
    typ = []
    i = 0
    while i < len(toks) and re.fullmatch(r"[а-яе-]+", toks[i], re.I) and (i == 0 or toks[i][:1].islower()) \
            and not _is_model(toks[i]):
        typ.append(toks[i].lower())
        i += 1
    words = []   # как в названии: регистр нужен, чтобы отличить серию («Пантера») от слова («средней обжарки»)
    while i < len(toks) and not _is_model(toks[i]) and not toks[i].startswith("("):
        words.append(toks[i])
        i += 1
    rest = toks[i:]
    model = rest[0].lower() if rest else ""
    color = rest[-1].lower() if len(rest) > 1 else ""
    return " ".join(typ), words, model, color


def _acronym(w):
    """«ГВС», «НТС» - сокращение, а не бренд."""
    return bool(re.fullmatch(r"[А-ЯЁ]{2,4}", w))


def _series_word(w):
    if w.lower() in NOT_BRAND or len(w) < 3:
        return False
    return bool(re.match(r"[a-z]", w, re.I)) or w[:1].isupper()


def parse(names):
    """Названия товаров → {"types": {тип: товаров}, "pairs": [(тип, бренд, товаров, пример)],
    "series": [(бренд, серия, товаров, пример)], "brands": {бренд: товаров}}."""
    items = []
    for n in names:
        if n:
            typ, orig, model, color = split(n)
            items.append((n, typ, [w.lower() for w in orig], orig, model, color))
    first = {}
    for n, typ, words, orig, model, color in items:
        if words:
            w0 = words[0]
            nxt = first.setdefault(w0, {})
            key = words[1] if len(words) > 1 and _series_word(orig[1]) else ""   # «illy средней» - не бренд
            nxt[key] = nxt.get(key, 0) + 1
    two = set()   # «christian» почти всегда с «lacroix» - бренд из двух слов
    for w0, nxt in first.items():
        tot = sum(nxt.values())
        top, cnt = max(nxt.items(), key=lambda x: x[1])
        if top and top not in SMALL and tot >= MIN_PAIR and cnt >= TWO_WORD_SHARE * tot:
            two.add(w0)
    types, brands, pairs, series = {}, {}, {}, {}
    for n, typ, words, orig, model, color in items:
        if not words or words[0] in NOT_BRAND or words[0] in SMALL or _acronym(orig[0]):
            continue
        k = 2 if words[0] in two and len(words) > 1 else 1
        brand = " ".join(words[:k])
        if typ:
            types[typ] = types.get(typ, 0) + 1
            p = pairs.setdefault((typ, brand), [0, n])
            p[0] += 1
        brands[brand] = brands.get(brand, 0) + 1
        tail = [w for w in orig[k:] if w.lower() not in SMALL]
        # серия - латиницей или с большой буквы, не короче 3 знаков (DB, PLD - начало артикула, а не серия)
        if tail and _series_word(tail[0]):
            s = series.setdefault((brand, tail[0].lower()), [0, n])
            s[0] += 1
    return {"types": types, "brands": brands,
            "pairs": sorted(((t, b, v[0], v[1]) for (t, b), v in pairs.items() if v[0] >= MIN_PAIR), key=lambda x: -x[2]),
            "series": sorted(((b, s, v[0], v[1]) for (b, s), v in series.items()
                              if v[0] >= MIN_SERIES and v[0] < brands.get(b, 0)), key=lambda x: -x[2])}


def from_db(path):
    """Названия товаров из crawl.db (H1, иначе title страниц с разметкой товара)."""
    return [n for n, _b in products(path)]


SAME_SHARE = 0.2   # одно и то же «название» у такой доли товаров - это шаблон сайта («Автозапчасти | Интернет-магазин»)


def products(path):
    """Товары из crawl.db: [(название, бренд из разметки)]. Название - H1, иначе название из разметки товара
    (itemprop name, JSON-LD name; запоминается с 11.10.2026), иначе title. Бренд - itemprop brand / JSON-LD brand."""
    import json
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            rows = db.execute("SELECT COALESCE(h1, ''), COALESCE(title, ''), COALESCE(schema_info, '') FROM pages "
                              "WHERE status=200 AND schema_types LIKE '%Product%' AND schema_types NOT LIKE '%ItemList%' "
                              "AND schema_types NOT LIKE '%AggregateOffer%' LIMIT 100000").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []
    out = []
    for h1, title, si in rows:
        p = {}
        if '"title"' in si or '"brand"' in si:
            try:
                p = json.loads(si).get("product") or {}
            except (ValueError, AttributeError):
                p = {}
        out.append([h1.strip() or p.get("title") or title.strip(), p.get("brand") or ""])
    cnt = {}
    for n, _b in out:
        cnt[n] = cnt.get(n, 0) + 1
    lim = max(10, SAME_SHARE * len(out))
    return [(n, b) for n, b in out if n and cnt[n] < lim]


def seeds(folder):
    """Фразы для подсказок: «тип + бренд» и «бренд + серия» (самые большие по числу товаров). Мало товаров - []."""
    import os
    names = from_db(os.path.join(folder, "crawl.db"))
    if len(names) < MIN_PRODUCTS:
        return []
    p = parse(names)
    out = [(f"{t} {b}", "тип + бренд", n, ex) for t, b, n, ex in p["pairs"][:MAX_PAIRS]]
    out += [(f"{b} {s}", "бренд + серия", n, ex) for b, s, n, ex in p["series"][:MAX_SERIES]]
    seen, res = set(), []
    for ph, src, n, ex in out:
        # «носителем. средний» - кусок из двух предложений названия (курсы talisman), а не бренд и серия
        if re.search(r"[.,;:!?]\s", ph):
            continue
        if ph not in seen:
            seen.add(ph)
            res.append({"t": ph, "src": src, "n": n, "ex": ex})
    return res
