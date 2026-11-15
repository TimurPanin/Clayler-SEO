"""«Паутинка»: карта внутренних ссылок. Каждая страница — точка, ссылка — линия.
Главная в центре, вокруг кольцами страницы по числу переходов от главной; ветки идут от страницы, с которой
на страницу ведёт ссылка (из того же раздела, если такая есть), поэтому разделы ложатся своими секторами.
Сироты (есть в sitemap, ссылок нет) висят сбоку отдельной кучкой, тупики (со страницы нет ни одной ссылки)
отмечены, страницы с ошибками красные. Ссылки из меню и подвала (ведут на треть сайта и больше) не рисуются:
они есть на каждой странице и превращают картинку в сплошное пятно.
На больших сайтах показывается не больше MAX_NODES страниц: все с ошибками, сироты, тупики и самые важные
по ссылкам, плюс страницы на пути к ним от главной; у точки отмечено, сколько страниц под ней скрыто.
Здесь только данные (summary["web"]); рисует report_web.py — canvas и JavaScript без библиотек."""
from collections import defaultdict
from urllib.parse import urlsplit

from .checks.codes import not_open
from .common import CRIT, NOTE, final_url
from .sections import section_of, ROOT

MAX_NODES = 4000
MAX_EDGES = 16000
MAX_SECTIONS = 12      # цветом — самые большие разделы, остальные серые
TEMPLATE_SHARE = 0.8   # проблема на 80% страниц и больше — ошибка шаблона, страницу не красит
MENU_SHARE = 0.3       # ссылка есть на 30% страниц и больше — меню или подвал
BLOCK_SHARE = 0.05     # на 5% страниц и больше — сквозной блок («популярное», боковое меню): прячется кнопкой

# флаги точки
F_CRIT, F_WARN, F_ORPHAN, F_DEAD, F_ERR, F_HOME = 1, 2, 4, 8, 16, 32


def run(ctx, issues, base, sections_rows):
    if (ctx.store.get_meta("scope", None) or {}).get("mode") == "list":
        return None  # список адресов — без обхода по ссылкам, связей нет
    start = ctx.store.get_meta("start", "") or ""
    sp = urlsplit(start)
    main_host = sp.netloc.lower()
    main_host = main_host[4:] if main_host.startswith("www.") else main_host
    prefix = f"{sp.scheme}://{sp.netloc}"

    orphans = set()
    for iss in issues:
        if iss.key == "orphans":
            orphans = {r[0] for r in iss.rows}
    urls = sorted(base | orphans)
    if len(urls) < 3:
        return None
    idx = {u: i for i, u in enumerate(urls)}
    n = len(urls)
    status = ctx.status

    # ссылки между страницами: in_src[d] — откуда ведут на d; out_n — сколько ссылок уходит со страницы (куда угодно)
    in_src = [set() for _ in range(n)]
    out_n = defaultdict(int)
    for dst, srcs in ctx.inl.items():
        d = idx.get(final_url(ctx.redir, dst))
        for s in srcs:
            out_n[s] += 1
            si = idx.get(s)
            if d is not None and si is not None and si != d:
                in_src[d].add(si)
    menu_min = max(20, int(len(base) * MENU_SHARE))
    menu = {d for d in range(n) if len(in_src[d]) >= menu_min}

    # раздел каждой страницы
    names = {r["path"]: r["name"] for r in sections_rows or [] if r.get("path")}
    sec_key = [section_of(u, main_host)[0] for u in urls]
    count = defaultdict(int)
    for k in sec_key:
        count[k] += 1
    big = [k for k, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0])) if k != ROOT and count[k] >= 3][:MAX_SECTIONS]
    sec_ix = {k: i + 1 for i, k in enumerate(big)}  # 0 — главная, страницы в корне и мелкие разделы
    sec = [sec_ix.get(k, 0) for k in sec_key]

    # проблемы страниц без «ошибок шаблона» (они на всех страницах и красили бы всю паутину)
    crit, warn = set(), set()
    for iss in issues:
        if iss.page_col is None or iss.severity == NOTE:
            continue
        mine = {u for row in iss.rows for u in str(row[iss.page_col]).split("\n") if u in idx}
        mine |= {u for u in getattr(iss, "group_pages", ()) if u in idx}   # ссылки шаблона одной строкой
        if len(base) >= 20 and len(mine) >= TEMPLATE_SHARE * len(base):
            continue
        (crit if iss.severity == CRIT else warn).update(idx[u] for u in mine)

    # главная и переходы от неё (обход в ширину по всем ссылкам, включая меню)
    home = idx.get(final_url(ctx.redir, start))
    if home is None:
        home = idx.get(start.rstrip("/")) if start.rstrip("/") in idx else None
    if home is None:
        dep = {p["url"]: p.get("depth") for p in ctx.pages}
        home = min(range(n), key=lambda i: (dep.get(urls[i]) if dep.get(urls[i]) is not None else 99, urls[i]))
    out_adj = [[] for _ in range(n)]
    for d in range(n):
        for s in in_src[d]:
            out_adj[s].append(d)
    depth = [-1] * n
    depth[home] = 0
    front = [home]
    while front:
        nxt = []
        for u in front:
            for v in out_adj[u]:
                if depth[v] < 0:
                    depth[v] = depth[u] + 1
                    nxt.append(v)
        front = nxt
    del out_adj
    # родитель: страница на шаг ближе к главной; лучше из того же раздела и с меньшим числом ссылок
    # (раздел каталога, а не меню на каждой странице)
    parent = [-1] * n
    for v in range(n):
        if v == home or depth[v] <= 0:
            continue
        cand = [s for s in in_src[v] if depth[s] == depth[v] - 1]
        if cand:
            parent[v] = min(cand, key=lambda s: (sec[s] != sec[v] or s == home, out_n.get(urls[s], 0), urls[s]))

    flags = [0] * n
    for i, u in enumerate(urls):
        st, err = status.get(u, (None, None))
        f = 0
        if u in status and not_open(st, err, ctx.redir.get(u, "")):   # общее правило «не открывается» (codes.not_open)
            f |= F_ERR | F_CRIT
        if i in crit:
            f |= F_CRIT
        elif i in warn:
            f |= F_WARN
        if u in orphans:
            f |= F_ORPHAN
        elif st == 200 and not out_n.get(u) and u in base:
            f |= F_DEAD
        if i == home:
            f |= F_HOME
        flags[i] = f

    # какие точки показать
    pr = {p["url"]: p.get("pagerank") or 0 for p in ctx.pages}
    chosen = {home}

    def take(cands, limit):
        for i in cands[:limit]:
            chosen.add(i)
    by_rank = sorted(range(n), key=lambda i: (-pr.get(urls[i], 0), depth[i] if depth[i] >= 0 else 99, urls[i]))
    if n > MAX_NODES:
        take([i for i in by_rank if flags[i] & F_ERR], MAX_NODES // 4)
        take([i for i in by_rank if flags[i] & F_ORPHAN], MAX_NODES // 8)
        take([i for i in by_rank if flags[i] & F_DEAD], MAX_NODES // 8)
        take([i for i in by_rank if flags[i] & F_CRIT], MAX_NODES // 8)
        for i in by_rank:
            if len(chosen) >= MAX_NODES * 0.9:
                break
            chosen.add(i)
        for i in list(chosen):  # путь от главной до каждой показанной точки
            p = parent[i]
            while p >= 0 and p not in chosen:
                chosen.add(p)
                p = parent[p]
    else:
        chosen = set(range(n))
    shown = sorted(chosen, key=lambda i: (depth[i] if depth[i] >= 0 else 99, urls[i]))
    new = {o: k for k, o in enumerate(shown)}

    # скрытые страницы — к ближайшей показанной выше по ветке
    hidden = defaultdict(int)
    for i in range(n):
        if i in new:
            continue
        p = parent[i]
        while p >= 0 and p not in new:
            p = parent[p]
        if p >= 0:
            hidden[new[p]] += 1

    def short(u):
        return u[len(prefix):] or "/" if u.startswith(prefix) else u

    nodes = []
    for k, i in enumerate(shown):
        nodes.append([short(urls[i]), new.get(parent[i], -1), depth[i], sec[i], flags[i],
                      len(in_src[i]), out_n.get(urls[i], 0), hidden.get(k, 0), pr.get(urls[i], 0)])

    # линии: ссылки между показанными страницами, кроме меню и самих веток (ветки рисуются отдельно)
    edges = []
    total_links = 0
    for d in shown:
        if d in menu:
            continue
        for s in sorted(in_src[d]):
            if s in new and parent[d] != s:
                total_links += 1
                edges.append((new[s], new[d]))
    if len(edges) > MAX_EDGES:  # равномерно по всему сайту, а не первые по порядку
        edges = edges[::-(-len(edges) // MAX_EDGES)]

    # разделы: страниц, ссылок из других разделов, доля страниц с одной ссылкой и меньше
    secs = [{"key": ROOT, "name": "Главная и отдельные страницы", "pages": 0, "from_other": 0, "weak": 0, "crit": 0}]
    for k in big:
        secs.append({"key": k, "name": names.get(k) or k, "pages": 0, "from_other": 0, "weak": 0, "crit": 0})
    from_other = defaultdict(set)
    block_min = max(20, int(len(base) * BLOCK_SHARE))
    sec_all, sec_clean = defaultdict(int), defaultdict(int)  # ссылок (пар страниц) из раздела в раздел
    for i in range(n):
        if i not in menu:
            for src in sorted(in_src[i]):
                if sec[src] != sec[i]:
                    key = f"{sec[src]}-{sec[i]}"
                    sec_all[key] += 1
                    if len(in_src[i]) < block_min:
                        sec_clean[key] += 1
    for i in range(n):
        s = secs[sec[i]]
        s["pages"] += 1
        if flags[i] & F_CRIT:
            s["crit"] += 1
        if len(in_src[i]) <= 1 and i != home:
            s["weak"] += 1
        for src in in_src[i]:
            if sec[src] != sec[i]:
                from_other[sec[i]].add(src)
    for j, s in enumerate(secs):
        s["from_other"] = len(from_other[j])
    return {"nodes": nodes, "edges": [x for e in edges for x in e], "sections": secs, "total": n,
            "shown": len(nodes), "links": total_links, "edges_shown": len(edges), "menu": len(menu),
            "orphans": sum(1 for f in flags if f & F_ORPHAN), "dead": sum(1 for f in flags if f & F_DEAD),
            "errors": sum(1 for f in flags if f & F_ERR), "crit": sum(1 for f in flags if f & F_CRIT), "unreached": sum(1 for i in range(n) if depth[i] < 0),
            "prefix": prefix, "block_min": block_min, "sec_links": dict(sec_clean), "sec_links_all": dict(sec_all)}

