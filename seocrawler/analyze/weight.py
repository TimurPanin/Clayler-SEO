"""«Куда уходит вес ссылок»: как внутренние ссылки распределяют силу между страницами (по внутреннему PageRank).
- доля веса на служебных страницах (политика конфиденциальности, оферта, корзина, вход, сравнение, поиск);
- доля веса по разделам сайта;
- важные страницы-разделы (внутри много страниц), которым достаётся мало: меньше, чем служебной странице,
  или меньше, чем средней странице сайта;
- страницы под запросы Семантики («Запрос → страница»), которым достаётся столько же мало (10.10.2026).
Только сводка для отчёта (summary["weight"]), на здоровье не влияет."""
import re
from collections import defaultdict
from urllib.parse import urlsplit, unquote

from .sections import section_of, ROOT
from ..fmt import quote

# служебные страницы: по адресу и по title/H1
# слова адреса: целиком (cart, но не cartridge) и начала слов (politika, politiki…)
SERVICE_WORDS = {"cart", "basket", "checkout", "login", "signin", "logout", "auth", "register", "forgot", "lk",
                 "account", "cabinet", "kabinet", "profile", "compare", "wishlist", "search", "sitemap", "terms",
                 "agreement", "personal", "registration", "registraciya", "poisk", "oferta", "rules", "pravila", "cookies", "cookie", "privacy"}
SERVICE_PREFIX = ("polit", "konfiden", "confiden", "soglasie", "korzin", "sravnen", "izbrann", "favorit",
                  "personaln")
SERVICE_TITLE = re.compile(
    r"(политик|конфиденциальн|публичн[а-я]* оферт|договор[а-я]* оферт|правила (пользования|применения|сайта|работы сайта)|персональных данных|согласие на обработку|оферт|пользовательское соглашение|"
    r"условия использования|cookie|куки|корзин|оформление заказа|личный кабинет|вход в|авторизац|регистрац|"
    r"восстановление пароля|сравнени[ея] товаров|избранное|отложенные|результаты поиска|поиск по сайту|карта сайта)",
    re.I)
TOP_SERVICE = 8
TOP_SECTIONS = 10
HUB_MIN = 5        # страница-раздел: внутри неё хотя бы столько страниц
TOP_WEAK = 12
SMALL_SECTION = 3  # раздел из 1–2 страниц — в строку «Главная и отдельные страницы», как в сводке по разделам
WEAK_VS_SERVICE = 0.7  # заметно меньше служебной страницы, а не на волосок (все в одном меню — почти поровну)


def is_service(p):
    sp = urlsplit(p["url"])
    # по началу каждой части адреса: /politika-konfidentsialnosti, /lk, /personal/cart/; слово в середине
    # (/blog/pravila-i-primery) — это статья, а не служебная страница
    for seg in re.split(r"[/?&]+", unquote(sp.path + "?" + sp.query).lower()):
        w = re.split(r"[-_.=]+", seg)[0]
        if seg.startswith(("karta-sa", "karta_sa")) or w in SERVICE_WORDS or (len(w) > 4 and w.startswith(SERVICE_PREFIX)):
            return True
    return any(SERVICE_TITLE.match((t or "").strip()) for t in (p.get("title"), p.get("h1")))


def run(ctx, shares, sections_rows):
    if not shares or len(shares) < 5 or (ctx.store.get_meta("scope", None) or {}).get("mode"):
        return None  # раздел или список: ссылки с остальных страниц не видны, вес неверен
    start = ctx.store.get_meta("start", "") or ""
    main_host = urlsplit(start).netloc.lower()
    main_host = main_host[4:] if main_host.startswith("www.") else main_host
    pages = {p["url"]: p for p in ctx.html_ok if p["url"] in shares}
    total = sum(shares.values()) or 1
    share = {u: v / total for u, v in shares.items()}
    n = len(pages)
    avg = 1 / n

    service = sorted((u for u, p in pages.items() if is_service(p)), key=lambda u: -share[u])
    service_share = sum(share[u] for u in service)

    names = {r["path"]: r["name"] for r in sections_rows or [] if r.get("path")}
    by_sec = defaultdict(lambda: [0.0, 0])
    for u in pages:
        s = section_of(u, main_host)[0]
        by_sec[s][0] += share[u]
        by_sec[s][1] += 1
    for k in [k for k, v in by_sec.items() if v[1] < SMALL_SECTION and k != ROOT]:  # /akit/, /privacy_policy/…
        v = by_sec.pop(k)
        by_sec[ROOT][0] += v[0]
        by_sec[ROOT][1] += v[1]
    secs = sorted(by_sec.items(), key=lambda kv: -kv[1][0])
    sec_rows = [{"name": "Главная и отдельные страницы" if k == ROOT else (names.get(k) or unquote(k)), "path": k,
                 "share": round(100 * v[0], 1), "pages": v[1], "pages_pct": round(100 * v[1] / n, 1)}
                for k, v in secs[:TOP_SECTIONS]]

    # страницы-разделы: адрес — начало адресов других страниц (/catalog/koshki/ → /catalog/koshki/korm/…)
    def norm(u):
        s = urlsplit(u)
        return s.netloc.lower().removeprefix("www.") + (s.path if s.path.endswith("/") else s.path + "/")
    keys = {norm(u): u for u in pages}
    inside = defaultdict(int)
    for u in pages:
        k = norm(u)
        parts = k.rstrip("/").split("/")
        for i in range(2, len(parts)):  # все родительские папки адреса
            pk = "/".join(parts[:i]) + "/"
            if pk in keys:
                inside[pk] += 1
    svc_max = max((share[u] for u in service), default=0)
    weak = []
    for k, cnt in inside.items():
        u = keys[k]
        if cnt < HUB_MIN or k.count("/") < 2 or urlsplit(u).path in ("", "/"):
            continue
        why = ""
        if svc_max and share[u] < svc_max * WEAK_VS_SERVICE:
            why = "service"
        elif share[u] < avg:
            why = "avg"
        if why:
            weak.append({"url": u, "inside": cnt, "share": share[u], "why": why,
                         "title": (pages[u].get("h1") or pages[u].get("title") or "")[:80],
                         "pagerank": pages[u].get("pagerank")})
    weak.sort(key=lambda w: (-w["inside"], w["share"]))

    # страницы под запросы Семантики («Запрос → страница», Подходит / Доработать) с малой силой
    sem_weak = []
    try:
        from ..urls import page_key
        from .checks.link_plan import sem_pages
        key_url = {page_key(u) or u: u for u in pages}
        planned = {x["url"]: len(x["links"]) for x in getattr(ctx, "link_plan", None) or []}
        for lu, g in sem_pages(ctx).items():
            u = key_url.get(page_key(lu) or lu)
            if not u:
                continue
            why = "service" if svc_max and share[u] < svc_max * WEAK_VS_SERVICE else "avg" if share[u] < avg else ""
            if why:
                main = (g.get("a") or {}).get("main") or g["name"]
                if u not in planned and getattr(ctx, "link_more", None):   # готовые ссылки - в план перелинковки
                    x = ctx.link_more(u, [f"страница группы запросов {quote(main)} из семантики",
                                          "силы ссылок меньше, чем у служебной страницы" if why == "service"
                                          else "силы ссылок меньше, чем у средней страницы сайта"])
                    planned[u] = len(x["links"]) if x else 0
                sem_weak.append({"url": u, "share": share[u], "why": why, "score": g.get("score") or 0,
                                 "main": main, "plan": planned.get(u, 0)})
        sem_weak.sort(key=lambda w: (-w["score"], w["share"]))
        if getattr(ctx, "link_plan", None):
            ctx.link_plan.sort(key=lambda x: x["prio"])
    except Exception:   # дополнение: сбой не должен ломать сводку
        sem_weak = []
    top_service = service[0] if service else None
    return {
        "pages": n, "service_share": round(100 * service_share, 1), "service_count": len(service),
        "service": [{"url": u, "share": round(100 * share[u], 2), "title": (pages[u].get("title") or "")[:80],
                     "path": unquote(urlsplit(u).path) or "/", "x_avg": round(share[u] / avg, 1)} for u in service[:TOP_SERVICE]],
        "sections": sec_rows, "weak": [dict(w, share=round(100 * w["share"], 3)) for w in weak[:TOP_WEAK]],
        "weak_total": len(weak),
        "sem_weak": [dict(w, share=round(100 * w["share"], 3)) for w in sem_weak[:TOP_WEAK]],
        "sem_weak_total": len(sem_weak),
        "top_service": {"url": top_service, "path": unquote(urlsplit(top_service).path) or "/",
                        "share": round(100 * share[top_service], 2)} if top_service else None,
        "home_share": round(100 * max((share[u] for u in pages if urlsplit(u).path in ("", "/")), default=0), 1),
    }
