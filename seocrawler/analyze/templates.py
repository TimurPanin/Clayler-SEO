"""«Ошибки по шаблонам»: страницы одного типа (карточки товаров, страницы каталога, статьи) сделаны по одному
шаблону, и проблема почти на всех страницах типа — это одна правка в шаблоне, а не тысячи правок.
Тип страницы — по адресу: общие части остаются, меняющиеся заменяются на «…» (/product/index/id/…/); название — по словам адреса или по
микроразметке (Product, OfferCatalog, Article). Отдельной строкой — общий шаблон всех страниц (шапка, подвал).
Только сводка для отчёта (summary["templates"]), на здоровье не влияет."""
from collections import Counter, defaultdict
from urllib.parse import urlsplit, unquote

from .common import CRIT, WARN, NOTE
from ..fmt import quote

MIN_PAGES = 20     # тип страниц меньше — не шаблон
FIXED = 0.25       # часть адреса у 25% страниц с тем же началом — общая (brand, reviews)
COVER = 0.7        # проблема на 70% страниц типа и больше — проблема шаблона
SITE_COVER = 0.8   # на 80% всех страниц — общий шаблон сайта
MAX_TEMPLATES = 8
MAX_ISSUES = 8

KINDS = [  # (слова в первой части адреса, название)
    ({"product", "products", "tovar", "tovary", "goods", "item", "items", "p", "card", "detail"}, "Карточки товаров"),
    ({"catalog", "katalog", "category", "categories", "shop", "collection", "collections", "c", "section"},
     "Страницы каталога"),
    ({"blog", "news", "novosti", "article", "articles", "stati", "statyi", "statya", "post", "posts", "journal",
      "zhurnal", "info", "poleznoe", "sovety"}, "Статьи и новости"),
    ({"brand", "brands", "brendy", "proizvoditeli", "manufacturers"}, "Страницы брендов"),
    ({"services", "service", "uslugi", "usluga"}, "Страницы услуг"),
]


def _keys(urls, main_host):
    """Адрес → тип: части адреса, общие для многих страниц, остаются словами (/catalog/index/name/…/brand/…/reviews/),
    меняющиеся (название товара, номер бренда) — «…». Первая часть всегда словом. Часть считается общей, если
    стоит хотя бы у FIXED страниц с тем же началом адреса."""
    segs = {}
    for u in urls:
        sp = urlsplit(u)
        host = sp.netloc.lower().removeprefix("www.")
        parts = [x.lower() for x in sp.path.split("/") if x]
        if parts:
            segs[u] = ("" if host == main_host else host, parts)
    sig = {u: [pre, parts[0]] for u, (pre, parts) in segs.items()}
    for i in range(1, max((len(p) for _, p in segs.values()), default=1)):
        groups = defaultdict(list)
        for u, (pre, parts) in segs.items():
            if len(parts) > i:
                groups[tuple(sig[u])].append(u)
        for _g, us in groups.items():
            cnt = Counter(segs[u][1][i] for u in us)
            for u in us:
                v = segs[u][1][i]
                sig[u].append(v if cnt[v] >= max(MIN_PAGES, FIXED * len(us)) else "*")
    return {u: tuple(k) for u, k in sig.items()}


def _name(key, schema, names):
    first = key[1]
    tail = key[2:]
    extra = ""
    if tail and tail[-1] in ("reviews", "otzyvy", "review", "comments"):
        extra = ": отзывы"
    elif "brand" in tail or "brands" in tail:
        extra = " по брендам"
    for words, label in KINDS:
        if first in words:
            return label + extra
    types = Counter()
    for st in schema:
        ts = {t.strip() for t in (st or "").split(",")}
        if ts & {"OfferCatalog", "ItemList", "CollectionPage"}:
            types["cat"] += 1
        elif ts & {"Product", "ProductGroup"}:
            types["prod"] += 1
        elif ts & {"Article", "BlogPosting", "NewsArticle"}:
            types["art"] += 1
    if types:
        kind, cnt = types.most_common(1)[0]
        if cnt >= 0.6 * len(schema):
            return {"cat": "Страницы каталога", "prod": "Карточки товаров", "art": "Статьи и новости"}[kind] + extra
    nm = names.get(("/" if not key[0] else key[0] + "/") + first + "/")
    return (f"Страницы раздела {quote(nm)}" if nm and not nm.startswith("/") else "Страницы раздела /" + unquote(first) + "/") + extra


def _pattern(key):
    pre = key[0]
    return (pre + "/" if pre else "/") + "".join(("…" if x == "*" else unquote(x)) + "/" for x in key[1:])


def run(ctx, issues, base, sections_rows=None):
    if (ctx.store.get_meta("scope", None) or {}).get("mode") == "list" or len(base) < MIN_PAGES:
        return None
    start = ctx.store.get_meta("start", "") or ""
    main_host = urlsplit(start).netloc.lower().removeprefix("www.")
    schema = {p["url"]: p.get("schema_types") for p in ctx.pages}
    names = {r["path"].lower(): r["name"] for r in sections_rows or [] if r.get("path")}

    groups = defaultdict(set)
    for u, k in _keys(base, main_host).items():
        groups[k].add(u)
    groups = {k: v for k, v in groups.items() if len(v) >= MIN_PAGES}

    # проблемы каждой страницы
    per_issue = {}
    page_issues = defaultdict(set)
    for iss in issues:
        if iss.page_col is None:
            continue
        mine = {u for row in iss.rows for u in str(row[iss.page_col]).split("\n") if u in base}
        mine |= {u for u in getattr(iss, "group_pages", ()) if u in base}   # ссылки шаблона одной строкой
        if mine:
            per_issue[iss.key] = (iss, mine)
            if iss.severity != NOTE:
                for u in mine:
                    page_issues[u].add(iss.key)

    def block(name, pattern, urls, keys, example):
        found = []
        for k in keys:
            iss, mine = per_issue[k]
            n = len(mine & urls)
            found.append({"key": k, "title": iss.title, "sev": iss.severity, "n": n})
        if not found:
            return None
        order = {CRIT: 0, WARN: 1, NOTE: 2}
        found.sort(key=lambda f: (order[f["sev"]], -f["n"]))
        fixed = set(keys)
        touched = set().union(*(per_issue[k][1] & urls for k in keys))
        clean = sum(1 for u in urls if page_issues[u] and page_issues[u] <= fixed)
        return {"name": name, "pattern": pattern, "pages": len(urls), "example": example,
                "issues": found[:MAX_ISSUES], "more": max(0, len(found) - MAX_ISSUES), "touched": len(touched),
                "serious": sum(1 for f in found if f["sev"] != NOTE),
                "gain": round(100 * clean / len(base), 1)}

    out = []
    site_keys = [k for k, (iss, mine) in per_issue.items() if len(base) >= MIN_PAGES and len(mine) >= SITE_COVER * len(base)]
    if site_keys:
        b = block("Общий шаблон всех страниц (шапка, меню, подвал, настройки сервера)", "все страницы", set(base),
                  site_keys, None)
        if b:
            out.append(b)
    site_set = set(site_keys)
    for k, urls in groups.items():
        keys = [ik for ik, (iss, mine) in per_issue.items()
                if ik not in site_set and len(mine & urls) >= COVER * len(urls)]
        if not keys:
            continue
        # пример - самый короткий адрес, при равной длине - первый по алфавиту: раньше среди равных выбор зависел от
        # порядка во множестве и менялся от сборки к сборке
        b = block(_name(k, [schema.get(u) for u in urls], names), _pattern(k), urls, keys,
                  min(urls, key=lambda u: (len(u), u)))
        if b:
            out.append(b)
    if not out:
        return None
    # одинаковые названия у разных типов — различаем образцом адреса
    names = Counter(b["name"] for b in out)
    for b in out:
        b["same_name"] = names[b["name"]] > 1
    head = out[:1] if site_keys else []
    rest = sorted(out[len(head):], key=lambda b: (b["serious"] == 0, -b["touched"]))
    return {"templates": (head + rest)[:MAX_TEMPLATES], "total": len(out), "base": len(base)}
