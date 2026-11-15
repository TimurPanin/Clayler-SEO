"""Сравнение своего сайта с конкурентами: одинаковые метрики по каждой проверке — в одну таблицу.
Первый сайт в списке — ваш, остальные — конкуренты."""
import os
import re
import statistics
import time
from collections import Counter
from urllib.parse import urlsplit

from .analyze import cached_analyze
from .robots import page_instead
from .storage import Store
from .fmt import esc as _e


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def site_metrics(folder):
    store = Store(os.path.join(folder, "crawl.db"))
    issues, pages, summary = cached_analyze(store)
    iss = {i.key: i.count for i in issues}
    db = store.db
    html_ok = [p for p in pages if p["status"] == 200 and p["content_type"] in ("text/html", "application/xhtml+xml")]
    idx = [p for p in html_ok if p["indexable"] == 1]
    n = len(idx) or 1
    # время ответа: до заголовков (версия 6), иначе — полная загрузка; «медленная» — если медленная и при повторе
    def _t(p):
        return p.get("ttfb") if p.get("ttfb") is not None else p["elapsed"]
    elapsed = [_t(p) for p in html_ok if _t(p)]
    first_slow = [p for p in html_ok if (_t(p) or 0) > 1]
    re_ = [p for p in first_slow if p.get("ttfb_recheck") is not None]
    re_slow = sum(1 for p in re_ if p["ttfb_recheck"] > 1)
    if re_:  # как в отчёте: неперемеренные считаем, только если перемер подтвердил хотя бы половину
        slow_n = re_slow + (len(first_slow) - len(re_) if re_slow / len(re_) >= 0.5 else 0)
    else:
        slow_n = len(first_slow)
    # слова без меню и подвала (<nav>, <footer>) — есть только в проверках версии 6
    words = [p["own_words"] for p in idx if p.get("own_words") is not None]  # свой текст, без шаблона сайта
    words_all = [p["word_count"] for p in idx if p["word_count"] is not None]
    v6 = bool(words)
    mirrors = store.get_meta("mirrors", None)
    mirrors_ok = None
    if mirrors:
        mirrors_ok = True
        for mm in mirrors["variants"]:
            ch = mm["chain"]
            f0 = ch[0][1]
            if not isinstance(f0, int) or (f0 in (404, 410) and len(ch) == 1):
                continue
            if not (len(ch) == 2 and f0 in (301, 308) and ch[-1][0] == mirrors["main"]):
                mirrors_ok = False
    titles = [len(p["title"]) for p in idx if p["title"]]
    img = db.execute("""SELECT COUNT(DISTINCT i.src),
        SUM(CASE WHEN p.img_format IN ('WebP','AVIF','SVG') THEN 1 ELSE 0 END),
        SUM(CASE WHEN p.img_format IS NOT NULL THEN 1 ELSE 0 END)
        FROM (SELECT DISTINCT src FROM images) i LEFT JOIN pages p ON p.url=i.src""").fetchone()
    sm = db.execute("SELECT COUNT(*) FROM sitemap").fetchone()[0]
    robots = store.get_meta("robots", {}) or {}
    robots_ok = any(v.get("status") == 200 and not page_instead(v) for v in robots.values())
    start = store.get_meta("start", "")
    # разделы сайта: первая часть пути у индексируемых страниц
    sections = Counter()
    for p in idx:
        seg = urlsplit(p["url"]).path.strip("/").split("/")[0]
        sections["/" + seg + "/" if seg else "/ (главная)"] += 1
    top = sorted([p for p in idx if p.get("pagerank") is not None], key=lambda p: -p["pagerank"])[:12]
    m = {
        "site": start, "folder": os.path.basename(folder),
        "finished": store.get_meta("finished_at", ""), "js": bool(store.get_meta("render_js", False)),
        "queue_left": summary["queue_left"],
        "health": summary["health"], "pages": summary["pages"], "indexable": summary["indexable"],
        "https": start.startswith("https://"), "robots": robots_ok, "sitemap": sm,
        "resp_median": round(statistics.median(elapsed), 2) if elapsed else None,
        "resp_slow_pct": _pct(slow_n, len(elapsed)),
        "weight_mb": summary.get("median_weight_mb"),
        "compress_pct": _pct(sum(1 for p in html_ok if p["content_encoding"]), len(html_ok)),
        "words_median": int(statistics.median(words)) if words else None,
        "words_all": int(statistics.median(words_all)) if words_all else None,
        # вода и тошнота своего текста (у страниц с текстом от TEXT_STATS_MIN_WORDS слов)
        "water_median": _med([p.get("water") for p in idx]),
        "nausea_median": _med([p.get("nausea") for p in idx]),
        "nausea_acad_median": _med([p.get("nausea_acad") for p in idx]),
        "nausea_pct": _pct(iss.get("text_nausea", 0), sum(1 for p in idx if p.get("nausea") is not None))
        if any(p.get("nausea") is not None for p in idx) else None,
        "viewport_pct": _pct(sum(1 for p in html_ok if p.get("viewport") is not None), len(html_ok)) if v6 else None,
        "schema_pct": _pct(sum(1 for p in idx if p.get("schema_types")), n) if v6 else None,
        "og_pct": _pct(sum(1 for p in idx if '"og:title"' in (p.get("og") or "")), n) if v6 else None,
        "mirrors_ok": mirrors_ok, "crawl_waste": summary.get("crawl_waste_pct"),
        "title_len": int(statistics.median(titles)) if titles else None,
        "no_desc_pct": _pct(iss.get("desc_missing", 0), n),
        "no_h1_pct": _pct(iss.get("h1_missing", 0), n),
        "dup_title": iss.get("title_dup", 0), "dup_content": iss.get("dup_content", 0), "near_dup": iss.get("near_dup", 0),
        "canonical_pct": _pct(sum(1 for p in idx if p["canonical"] or p["canonical_header"]), n),
        "lastmod_pct": _pct(sum(1 for p in idx if p["last_modified"]), n),
        "broken": iss.get("broken_links", 0), "errors_4xx": iss.get("4xx", 0), "errors_5xx": iss.get("5xx", 0),
        "redirect_chains": iss.get("redirect_chains", 0), "links_to_redirect": iss.get("links_to_redirect", 0),
        "deep": iss.get("deep", 0),
        "depth_max": max((p["depth"] or 0) for p in idx) if idx else None,
        "imgs": img[0] or 0, "img_modern_pct": _pct(img[1] or 0, img[2] or 0),
        "img_heavy": iss.get("img_big", 0), "img_no_alt": iss.get("img_alt_missing", 0),
        "sections": sections.most_common(12),
        "top": [(p["url"], p["pagerank"], p.get("title") or "") for p in top],
        "crit": summary["crit"], "warn": summary["warn"],
        "menu": menu_items(store, len(html_ok), store.get_meta("start", "")),
    }
    store.db.close()
    return m


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def menu_items(store, n_html, site=""):
    """Пункты меню и подвала: внутренние ссылки, которые стоят на 30% страниц и больше. [(текст, адрес)]"""
    threshold = max(3, int(n_html * 0.3))
    if store.legacy_links:
        q = """SELECT dst, anchor, COUNT(DISTINCT src) AS n FROM links WHERE kind='a' AND internal=1
               GROUP BY dst, anchor HAVING n>=?"""
    else:
        q = """SELECT d.s, a.s, g.n FROM (SELECT dst, anchor, COUNT(DISTINCT src) AS n FROM link_rows
               WHERE kind='a' AND internal=1 GROUP BY dst, anchor HAVING n>=?) g
               JOIN strs d ON d.id=g.dst LEFT JOIN strs a ON a.id=g.anchor"""
    host = (urlsplit(site).hostname or "").lower()
    skip = {_stems(host.split(".")[-2] if host.count(".") else host)} | {_stems(x) for x in SKIP_MENU}
    out, seen = [], set()
    for dst, anchor, n in sorted(store.db.execute(q, (threshold,)), key=lambda r: -r[2]):
        a = re.sub(r"\s+", " ", anchor or "").strip()
        a = re.sub(r"^\d+\s+", "", a)  # «0 Избранное» — счётчик перед текстом
        w = a.split(" ")
        if len(w) % 2 == 0 and w[:len(w) // 2] == w[len(w) // 2:]:
            a = " ".join(w[:len(w) // 2])  # «Акции Акции» — текст повторён (картинка + подпись)
        if 2 < len(a) <= 60 and _stems(a) and _stems(a) not in seen and _stems(a) not in skip:
            seen.add(_stems(a))
            out.append((a, dst))
    return out


SKIP_MENU = ["logo", "лого", "логотип", "главная", "home", "избранное", "сравнение", "корзина", "войти",
             "вход", "личный кабинет", "наверх", "подробнее", "ещё", "все"]


def _stems(text):
    """«Газовые котлы» и «Котлы газовые» — одно и то же: первые 5 букв каждого слова, без порядка."""
    return frozenset(w[:5] for w in re.findall(r"[а-яёa-z]{3,}", text.lower()))


def missing_menu(sites):
    """Пункты меню конкурентов, которых нет в меню вашего сайта: [(текст, [(сайт, адрес)])]."""
    own = [_stems(a) for a, _ in sites[0].get("menu") or []]
    res = {}
    for s in sites[1:]:
        for a, u in s.get("menu") or []:
            st = _stems(a)
            if any(st <= o or o <= st for o in own if o):
                continue
            res.setdefault(st, [a, []])[1].append((urlsplit(s["site"]).netloc, u))
    return sorted(res.values(), key=lambda x: (-len(x[1]), x[0].lower()))


# (ключ, название, как лучше: "high" / "low" / None — не сравнивать, формат)
ROWS = [
    ("Общее", None),
    ("health", "Здоровье сайта", "high", "{}%"),
    ("pages", "Страниц найдено по ссылкам", None, "{}"),
    ("indexable", "Из них могут попасть в поиск", None, "{}"),
    ("sitemap", "Адресов в sitemap", None, "{}"),
    ("https", "HTTPS", "high", "bool"),
    ("robots", "Есть robots.txt", "high", "bool"),
    ("Скорость", None),
    ("resp_median", "Время ответа сервера (медиана), с", "low", "{}"),
    ("resp_slow_pct", "Страниц, отвечающих дольше 1 с", "low", "{}%"),
    ("weight_mb", "Вес страницы при открытии (медиана), МБ", "low", "{}"),
    ("compress_pct", "Страниц со сжатием (gzip/brotli)", "high", "{}%"),
    ("Контент и мета-теги", None),
    ("words_median", "Своего текста на странице, слов - без шаблона сайта (медиана)", "high", "{}"),
    ("words_all", "Слов на странице вместе с меню (медиана)", None, "{}"),
    ("water_median", "Вода в тексте, % (медиана)", "low", "{}%"),
    ("nausea_median", "Тошнота текста (медиана)", "low", "{}"),
    ("nausea_acad_median", "Тошнота академическая, % (медиана)", "low", "{}%"),
    ("nausea_pct", "Страниц с переспамом (из страниц с текстом)", "low", "{}%"),
    ("title_len", "Длина title (медиана), символов", None, "{}"),
    ("no_desc_pct", "Страниц без description", "low", "{}%"),
    ("no_h1_pct", "Страниц без H1", "low", "{}%"),
    ("dup_title", "Групп страниц с одинаковым title", "low", "{}"),
    ("dup_content", "Групп полных дублей", "low", "{}"),
    ("near_dup", "Групп почти дублей", "low", "{}"),
    ("canonical_pct", "Страниц с canonical", "high", "{}%"),
    ("lastmod_pct", "Страниц с Last-Modified (для Яндекса)", "high", "{}%"),
    ("schema_pct", "Страниц с микроразметкой Schema.org", "high", "{}%"),
    ("og_pct", "Страниц с Open Graph (для соцсетей)", "high", "{}%"),
    ("Мобильная версия и домен", None),
    ("viewport_pct", "Страниц с meta viewport", "high", "{}%"),
    ("mirrors_ok", "Склейка домена (www, http, index.php → один 301)", "high", "bool"),
    ("Ошибки и структура", None),
    ("broken", "Битых ссылок", "low", "{}"),
    ("errors_4xx", "Адресов с ошибкой 4xx", "low", "{}"),
    ("errors_5xx", "Адресов с ошибкой 5xx", "low", "{}"),
    ("redirect_chains", "Цепочек редиректов", "low", "{}"),
    ("links_to_redirect", "Ссылок на адреса с редиректом (разных адресов)", "low", "{}"),
    ("crawl_waste", "Адресов «впустую» для робота (редиректы, ошибки, noindex, canonical)", "low", "{}%"),
    ("deep", "Страниц глубже 3 кликов", "low", "{}"),
    ("depth_max", "Максимальная глубина, кликов", "low", "{}"),
    ("Картинки", None),
    ("imgs", "Разных картинок", None, "{}"),
    ("img_modern_pct", "Картинок в WebP/AVIF/SVG", "high", "{}%"),
    ("img_heavy", "Картинок тяжелее 100 КБ", "low", "{}"),
    ("img_no_alt", "Картинок без атрибута alt", "low", "{}"),
]


# Эти показатели считаются в штуках, а сайты разного размера: лучшего и худшего выбираем
# в пересчёте на одну страницу, иначе маленький сайт всегда «выигрывает».
PER_PAGE = {"dup_title", "dup_content", "near_dup", "broken", "errors_4xx", "errors_5xx", "redirect_chains",
            "links_to_redirect", "deep", "img_heavy", "img_no_alt"}


def _fmt(v, f):
    if v is None:
        return "-"
    if f == "bool":
        return "да" if v else "нет"
    if isinstance(v, float):  # 5.3 → «5,3», 7.0 → «7»
        v = int(v) if v == int(v) else str(v).replace(".", ",")
    return f.format(v)


def write_report(path, sites):
    """sites — список метрик; первый — ваш сайт."""
    head = "".join(f'<th>{"Ваш сайт" if i == 0 else "Конкурент"}<br><span class="site">{_e(urlsplit(s["site"]).netloc)}</span>'
                   f'{"<br><span class=warn>проверен не целиком</span>" if s["queue_left"] else ""}</th>' for i, s in enumerate(sites))
    body = []
    wins = [0] * len(sites)
    for row in ROWS:
        if row[1] is None:
            body.append(f'<tr class="sec"><td colspan="{len(sites) + 1}">{_e(row[0])}</td></tr>')
            continue
        key, label, better, f = row
        vals = [s.get(key) for s in sites]
        per_page = key in PER_PAGE
        cmp_vals = [(v / max(s["indexable"], 1) if per_page and v is not None else v) for v, s in zip(vals, sites)]
        nums = [v for v in cmp_vals if isinstance(v, (int, float, bool)) and v is not None]
        best = worst = None
        if better and len(set(nums)) > 1 and len(nums) == len(vals):
            best = max(nums) if better == "high" else min(nums)
            worst = min(nums) if better == "high" else max(nums)
        cells = []
        for i, v in enumerate(vals):
            cls, cv = "", cmp_vals[i]
            if best is not None and cv == best:
                cls, wins[i] = "best", wins[i] + 1
            elif worst is not None and cv == worst:
                cls = "worst"
            extra = ""
            if per_page and v and sites[i]["indexable"]:
                extra = f' <span class="mut2">({round(100 * v / sites[i]["indexable"])} на 100 стр.)</span>'
            cells.append(f'<td class="{cls}">{_e(_fmt(v, f))}{extra}</td>')
        body.append(f"<tr><td>{_e(label)}</td>{''.join(cells)}</tr>")
    body.append(f'<tr class="sum"><td>Лучший результат в строках</td>{"".join(f"<td>{w}</td>" for w in wins)}</tr>')

    def sec_table(s):
        rows = "".join(f"<tr><td>{_e(k)}</td><td>{v}</td></tr>" for k, v in s["sections"])
        return f'<table class="small"><thead><tr><th>Раздел</th><th>Страниц</th></tr></thead><tbody>{rows}</tbody></table>'

    def top_table(s):
        rows = "".join(f'<tr><td><a href="{_e(u)}" target="_blank">{_e(urlsplit(u).path or "/")}</a></td><td>{_e(t)}</td></tr>'
                       for u, pr, t in s["top"])
        return f'<table class="small"><thead><tr><th>Страница</th><th>Title</th></tr></thead><tbody>{rows}</tbody></table>'

    blocks = "".join(
        f'<div class="card"><h3>{"Ваш сайт" if i == 0 else "Конкурент"}: {_e(urlsplit(s["site"]).netloc)}</h3>'
        f'<p class="mut">Проверка {_e(s["finished"])}{" · с JavaScript" if s["js"] else ""}</p>'
        f'<h4>Разделы сайта (сколько страниц)</h4>{sec_table(s)}'
        f'<h4>Главные страницы по внутренним ссылкам и их title</h4>{top_table(s)}</div>'
        for i, s in enumerate(sites))
    miss = missing_menu(sites)
    if miss and sites[0].get("menu") is not None:
        def who_html(who):
            return "<br>".join(f'<a href="{_e(u)}" target="_blank">{_e(h)}</a>' for h, u in who)
        mrows = "".join(f"<tr><td>{_e(a)}</td><td>{who_html(who)}</td></tr>" for a, who in miss[:80])
        menu_block = (f'<h2 style="font-size:18px;font-weight:600;margin:24px 0 0">Что есть в меню у конкурентов, а у вас нет</h2>'
                      f'<p class="mut">Пункты меню и подвала конкурентов (ссылки, которые стоят на 30% страниц и больше), '
                      f'которых нет в меню вашего сайта. Это подсказка, каких разделов и страниц может не хватать: '
                      f'«Доставка», «Отзывы», отдельные разделы каталога. Сравнивается по словам, поэтому «Доставка и оплата» '
                      f'и «Оплата и доставка» - одно и то же; разные названия одного раздела программа может посчитать разными.</p>'
                      f'<div class="card"><table class="small"><thead><tr><th>Пункт меню</th><th>У кого есть</th></tr></thead>'
                      f'<tbody>{mrows}</tbody></table>'
                      + (f'<p class="mut">…и ещё {len(miss) - 80}.</p>' if len(miss) > 80 else "") + '</div>')
    else:
        menu_block = ""
    uneven = len({s["pages"] for s in sites}) > 1 and any(s["queue_left"] for s in sites)
    note = ('<p class="warnbox">Часть сайтов проверена не целиком (упёрлись в лимит страниц). Цифры в штуках (битые ссылки, '
            'дубли) у них занижены - сравнивайте в первую очередь проценты и медианы.</p>') if uneven else ""
    if any(s.get("words_median") is None for s in sites):
        note += ('<p class="warnbox">Часть проверок сделана до версии 6 программы: для них нет своего текста страниц, '
                 'микроразметки, Open Graph, viewport и склейки домена (в таблице «-»). Чтобы сравнить и это, '
                 'проверьте такие сайты заново.</p>')
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Сравнение с конкурентами</title><style>
:root{{--bg:#f7f6f3;--card:#fff;--tx:#1f1e1c;--mut:#6b6a66;--bd:#e4e2dc;--good:#2f855a;--goodbg:#e3f3ea;--bad:#c0392b;--badbg:#fbe5e2;--warn:#b7791f;--acc:#3b5bdb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#181817;--card:#222220;--tx:#ecebe7;--mut:#a3a19b;--bd:#3a3936;--good:#58c08a;--goodbg:#1f3a2b;--bad:#ef6f5e;--badbg:#45231f;--warn:#e0a84a;--acc:#8ea6ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 60px}}h1{{font-size:24px;font-weight:600;margin:0 0 4px}}
h3{{font-size:16px;font-weight:600;margin:0 0 2px}}h4{{font-size:14px;font-weight:600;margin:14px 0 6px}}.mut{{color:var(--mut);margin:0}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px;margin:14px 0;overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--bd);vertical-align:top}}
th{{font-weight:500;color:var(--mut);font-size:13px}}th .site{{color:var(--tx);font-size:15px;font-weight:600}}
td.best{{background:var(--goodbg);color:var(--good);font-weight:600}}td.worst{{background:var(--badbg);color:var(--bad)}}
tr.sec td{{font-weight:600;padding-top:16px;border-bottom:1px solid var(--bd)}}tr.sum td{{font-weight:600}}
table.small{{font-size:13px}}.mut2{{color:var(--mut);font-size:12px;font-weight:400}}a{{color:var(--acc);text-decoration:none}}.warn{{color:var(--warn);font-size:12px}}
.warnbox{{background:var(--card);border:1px solid var(--warn);border-radius:10px;padding:12px 14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}.grid .card{{margin:0}}
</style></head><body><main>
<h1>Сравнение с конкурентами</h1>
<p class="mut">Технические показатели сайтов рядом. Зелёным - лучший результат в строке, красным - худший.
Показатели в штуках (битые ссылки, дубли и т. п.) сравниваются в пересчёте на 100 страниц, потому что сайты разного размера.
Это сравнение техники сайта, а не позиций в поиске: кто выше в выдаче, по этим данным сказать нельзя.</p>
{note}
<div class="card"><table><thead><tr><th>Показатель</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>
{menu_block}
<h2 style="font-size:18px;font-weight:600;margin:24px 0 0">Как устроены сайты</h2>
<p class="mut">Разделы показывают, где у конкурента больше страниц (например, каталог или статьи). Title главных страниц
показывает, под какие запросы сайт себя продвигает.</p>
<div class="grid">{blocks}</div>
<p class="mut" style="margin-top:20px">Собрано {time.strftime("%Y-%m-%d %H:%M")}.</p>
</main></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
