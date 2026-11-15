"""Здоровье по разделам сайта (каталог, статьи, услуги…): как «Сегменты» у Screaming Frog.
Раздел — первая папка адреса (/katalog/…, /blog/…). Если раздел большой и внутри есть свои папки
(/katalog/gazovye-kotly/…), для него считаются и подразделы. Страницы прямо в корне (/about, /kontakty) —
отдельной строкой. На поддоменах и в городах раздел подписывается адресом сайта."""
from collections import defaultdict
from urllib.parse import urlsplit, unquote

from .common import CRIT, NOTE, note_fault

MAX_SECTIONS = 20      # больше — остальное одной строкой «другие разделы»
SUB_MIN_SECTION = 30   # подразделы показываются у разделов не меньше этого
SUB_MIN_PAGES = 5      # и только подразделы с таким числом страниц
MAX_SUBS = 10
WEAK = {"подробнее", "читать далее", "читать", "далее", "ещё", "еще", "тут", "здесь", "перейти", "смотреть",
        "смотреть все", "все", "показать все", "узнать больше", "больше", "открыть", "more", "read more"}
TEMPLATE_SHARE = 0.8   # проблема на 80% страниц и больше — «ошибка шаблона»
SMALL = 3              # раздел меньше — в общую строку «Главная и отдельные страницы»
ROOT = "/"


def _parts(url):
    s = urlsplit(url)
    segs = [x for x in s.path.split("/") if x]
    # последняя часть с точкой (page.html, index.php) — это файл, а не папка
    if segs and "." in segs[-1] and not s.path.endswith("/"):
        segs = segs[:-1]
    return s.netloc.lower(), segs


def section_of(url, main_host):
    """('/katalog/', '/katalog/gazovye-kotly/') — раздел и подраздел адреса; у страниц в корне — ('/', None)."""
    host, segs = _parts(url)
    pre = "" if host == main_host or host == "www." + main_host or "www." + host == main_host else host
    if not segs:
        return pre + ROOT, None
    sec = pre + "/" + segs[0] + "/"
    sub = sec + segs[1] + "/" if len(segs) >= 2 else None
    return sec, sub


def _anchors(ctx, keys, main_host):
    """Текст ссылок на страницу-раздел (обычно пункт меню: «Детям», «Каталог») — самый частый."""
    from collections import Counter
    db, out = ctx.db, {}
    scheme = urlsplit(ctx.store.get_meta("start", "") or "https://x/").scheme or "https"
    for k in keys:
        if not k.startswith("/"):
            continue
        cnt = Counter()
        for host in (main_host, "www." + main_host):
            for u in (f"{scheme}://{host}{k}", f"{scheme}://{host}{k.rstrip('/')}"):
                if ctx.store.legacy_links:
                    q = db.execute("SELECT anchor, COUNT(*) FROM links WHERE dst=? AND kind='a' GROUP BY anchor", (u,))
                else:
                    q = db.execute("SELECT a.s, COUNT(*) FROM link_rows l JOIN strs d ON d.id=l.dst "
                                   "LEFT JOIN strs a ON a.id=l.anchor WHERE d.s=? AND l.kind='a' GROUP BY a.s", (u,))
                for a, n in q:
                    w = (a or "").split()
                    if len(w) % 2 == 0 and w[:len(w) // 2] == w[len(w) // 2:]:  # «Прочие запчасти Прочие запчасти»
                        w = w[:len(w) // 2]
                    a = " ".join(w)
                    if 2 <= len(a) <= 40 and not any(ch.isdigit() for ch in a) and a.lower().strip(".…»> ") not in WEAK:
                        cnt[a] += n
        if cnt:
            out[k] = cnt.most_common(1)[0][0]
    return out


def _names(pages, keys):
    """Имя раздела по самой странице-разделу: H1, а если его нет — title."""
    out = {}
    for p in pages:
        if p.get("status") != 200:
            continue
        path = urlsplit(p["url"]).path
        if not path.endswith("/"):
            path += "/"
        if path in keys and path not in out:
            nm = (p.get("h1") or p.get("title") or "").strip()
            if nm:
                out[path] = nm[:60]
    return out


def run(ctx, issues, base, bad_c, bad_w):
    pages = ctx.pages
    start = ctx.store.get_meta("start", "") or (pages[0]["url"] if pages else "")
    main_host = urlsplit(start).netloc.lower()
    if main_host.startswith("www."):
        main_host = main_host[4:]
    sec_of, sub_of = {}, {}
    for u in base:
        s, sub = section_of(u, main_host)
        sec_of[u], sub_of[u] = s, sub
    if not base:
        return []
    groups = defaultdict(set)
    for u, s in sec_of.items():
        groups[s].add(u)
    if len(groups) < 2:
        # всё в одном разделе — разбивка по разделам ничего не скажет; но если внутри есть подразделы, покажем их
        only = next(iter(groups))
        subs = defaultdict(set)
        for u in groups[only]:
            if sub_of[u]:
                subs[sub_of[u]].add(u)
        if sum(1 for v in subs.values() if len(v) >= SUB_MIN_PAGES) < 2:
            return []

    # проблемы по страницам (критичные и предупреждения) — один раз для всех групп
    per_page = defaultdict(list)
    for iss in issues:
        if iss.page_col is None or iss.severity == NOTE:
            continue
        seen = set()
        for row in iss.rows:
            for u in str(row[iss.page_col]).split("\n"):
                if u in base and u not in seen:
                    seen.add(u)
                    per_page[u].append(iss)
        for u in getattr(iss, "group_pages", ()):   # битые ссылки шаблона одной строкой - на всех своих страницах
            if u in base and u not in seen:
                seen.add(u)
                per_page[u].append(iss)

    # «Ошибки шаблона» — проблемы почти на всех страницах (ссылка в меню, строка в подвале): исправляются одной правкой,
    # но красят в красный все разделы сразу. Для карты сайта считаем и здоровье без них.
    cover = defaultdict(int)
    for u in base:
        for iss in per_page.get(u, ()):
            cover[iss.key] += 1
    template = {k for k, n in cover.items() if n >= TEMPLATE_SHARE * len(base) and len(base) >= 20}
    titles = {iss.key: iss.title for iss in issues}
    idx_urls = {p["url"] for p in ctx.indexable}
    ok_urls = {p["url"] for p in ctx.html_ok}

    def stats(name, urls, path):
        top = defaultdict(int)
        info, ex = {}, defaultdict(list)
        for u in sorted(urls):
            for iss in per_page.get(u, ()):
                top[iss.key] += 1
                info[iss.key] = iss
                if len(ex[iss.key]) < 5:
                    ex[iss.key].append(u)
        order = sorted(top, key=lambda k: (0 if info[k].severity == CRIT else 1, -top[k], k))
        bad = (bad_c | bad_w) & urls
        bad_nt = {u for u in urls if any(i.key not in template for i in per_page.get(u, ()))}
        return {"name": name, "path": path, "pages": len(urls),
                # индексируются / рабочие, но закрыты от поиска (noindex, canonical на другую); остальное - ошибки
                "idx": len(urls & idx_urls), "closed": len((urls & ok_urls) - idx_urls),
                "health": round(100 * (1 - len(bad) / len(urls))) if urls else None,
                "health_nt": round(100 * (1 - len(bad_nt) / len(urls))) if urls else None,
                "crit": len(bad_c & urls), "warn": len((bad_w - bad_c) & urls),
                "top": [f"{info[k].title} - {top[k]}" for k in order[:3]],
                "issues": [{"key": k, "title": info[k].title, "n": top[k], "sev": info[k].severity,
                            "template": k in template, "ex": ex[k]} for k in order[:12]],
                "sub": []}

    keys = set(groups)
    subs_all = {sub_of[u] for u in base if sub_of[u]}
    names = _names(pages, keys | subs_all)
    try:
        names.update(_anchors(ctx, keys | subs_all, main_host))  # текст пункта меню понятнее, чем длинный H1
    except Exception as e:   # дополнение: разделы останутся с названиями из заголовков
        note_fault("названия разделов из текста ссылок", "", e)
    out = []
    # разделы из одной-двух страниц («Контакты», «О нас») — одной строкой вместе со страницами в корне
    small = [k for k, v in groups.items() if len(v) < SMALL and k != ROOT]
    if small:
        for k in small:
            groups.setdefault(ROOT, set()).update(groups.pop(k))
    ordered = sorted(groups.items(), key=lambda kv: (kv[0] == ROOT, -len(kv[1]), kv[0]))
    rest, n_rest = set(), 0
    for i, (s, urls) in enumerate(ordered):
        if i >= MAX_SECTIONS and s != ROOT:
            rest |= urls
            n_rest += 1
            continue
        label = ("Главная и отдельные страницы" + (f" ({', '.join(names.get(k) or unquote(k) for k in sorted(small)[:6])}"
                                                   f"{'…' if len(small) > 6 else ''})" if small else "")
                 if s == ROOT else (names.get(s) or unquote(s)))
        row = stats(label, urls, s)
        if len(urls) >= SUB_MIN_SECTION and s != ROOT:
            subs = defaultdict(set)
            for u in urls:
                if sub_of[u]:
                    subs[sub_of[u]].add(u)
            big = sorted((kv for kv in subs.items() if len(kv[1]) >= SUB_MIN_PAGES), key=lambda kv: (-len(kv[1]), kv[0]))
            if len(big) >= 2:
                row["sub"] = [stats(names.get(k) or unquote(k), v, k) for k, v in big[:MAX_SUBS]]
        out.append(row)
    if rest:
        out.insert(len(out) - (1 if out and out[-1]["path"] == ROOT else 0),
                   stats(f"Другие разделы ({n_rest})", rest, ""))
    if out:
        out[0]["template_issues"] = [titles[k] for k in sorted(template)]  # для подписи на карте
    return out
