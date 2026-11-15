"""Семантика для сайта, которого ещё нет (или он закрыт и не открывается): структура будущего сайта.
Своего сайта для обхода нет, поэтому семена - слова темы, которые ввёл человек, и разделы конкурентов (их
проверки). Дальше всё как в обычной семантике: подсказки Яндекса и Google, запросы из файлов (Вордстат,
Key Collector), отсев, группы. Каждая группа - страница, которую нужно создать: раздел, подраздел, главная.
Вопросы - в план статей, «фото», «примеры работ» - в портфолио.

Проект живёт как обычная папка в «отчёты» («тема.new_дата_время»), в ней crawl.db без страниц: в meta адрес
(«https://тема.new/» или будущий домен) и new_site - что ввёл человек. Так страница «Семантика», решения по
группам, файлы запросов и Excel работают без изменений."""
import os
import re
import sqlite3
import json
import time
from urllib.parse import urlsplit

from ..fmt import esc as _e, num as _n, plural as _pl
from .labels import KIND as _KIND

KEY = "new_site"
PSEUDO = ".new"          # адрес проекта без домена: «gazovye-kotly-ufa.new»
CLIENT_FILE = "структура сайта.html"
WORDS_MAX = 8            # слов темы, по которым собираются подсказки
BLOG_MAX = 30
GALLERY_MIN = 3          # столько запросов «фото», «примеры работ» - нужна страница портфолио


def _slug(text, city=""):
    from .plan import slug
    return slug(text, city) or "novyy-sayt"


def clean_domain(s):
    s = re.sub(r"^https?://", "", str(s or "").strip().lower()).split("/")[0].removeprefix("www.")
    return s if re.fullmatch(r"[a-z0-9а-яё.-]+\.[a-zа-яё]{2,}", s) else ""


def split_words(s):
    """«газовые котлы, котлы отопления; бойлеры» → список фраз (строки или запятые)."""
    out = []
    if isinstance(s, (list, tuple)):
        s = "\n".join(map(str, s))
    for w in re.split(r"[\n,;]+", str(s or "")):
        w = re.sub(r"\s+", " ", w).strip(" .-").lower().replace("ё", "е")
        if w and w not in out and len(w) <= 60:
            out.append(w)
    return out[:WORDS_MAX * 2]


def create(reports, name, words, city="", domain="", brand=""):
    """Папка проекта нового сайта. Возвращает путь."""
    from ..storage import Store
    words = split_words(words)
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:80] or (words[0][:1].upper() + words[0][1:] if words else "Новый сайт")
    host = clean_domain(domain) or _slug(name, city) + PSEUDO
    folder = os.path.join(reports, f"{host}_{time.strftime('%Y-%m-%d_%H-%M-%S')}")
    os.makedirs(folder, exist_ok=True)
    st = Store(os.path.join(folder, "crawl.db"))
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    from .. import VERSION
    for k, v in (("start", f"https://{host}/"), ("started_at", now), ("finished_at", now), ("app_version", VERSION),
                 (KEY, {"name": name, "words": words, "city": city or "", "domain": clean_domain(domain),
                        "brand": str(brand or "").strip()[:60]})):
        st.set_meta(k, v)
    st.commit()
    st.db.close()
    return folder


def info(folder):
    """Что ввёл человек (имя, слова, город) - или None, если это обычная проверка сайта."""
    db = os.path.join(folder or "", "crawl.db")
    if not os.path.exists(db):
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
        try:
            r = con.execute("SELECT value FROM meta WHERE key=?", (KEY,)).fetchone()
        finally:
            con.close()
        return json.loads(r[0]) if r else None
    except sqlite3.Error:
        return None


def load(folder, ns):
    """Тот же вид, что seeds.load(): разделов своих нет, тема - слова человека."""
    from .words import city_by_name
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    start = json.loads(db.execute("SELECT value FROM meta WHERE key='start'").fetchone()[0])
    db.close()
    return {"site": start, "host": urlsplit(start).netloc, "city": city_by_name(ns["city"]) if ns.get("city") else None,
            "brand": [ns["brand"]] if ns.get("brand") else [], "sections": [], "folder": folder,
            "topic": ns.get("words")[:WORDS_MAX], "new": True, "new_site": ns}


def shop_like(folders):
    """Магазин или услуги - по конкурентам: у магазина много страниц с разметкой товара."""
    n = 0
    for f in folders:
        try:
            db = sqlite3.connect(f"file:{os.path.join(f, 'crawl.db')}?mode=ro", uri=True)
            n = max(n, db.execute("SELECT COUNT(*) FROM pages WHERE schema_types LIKE '%Product%'").fetchone()[0])
            db.close()
        except sqlite3.Error:
            pass
    return n >= 20


# ---------------------------------------------------------------- структура сайта

def _host(u):
    return (urlsplit(u).hostname or "").removeprefix("www.")


def _path(u):
    return urlsplit(u).path or "/"


def _top(g, n=5, intent=None):
    return [r[0] for r in g.get("q") or [] if not r[7] and (intent is None or r[2] == intent)][:n]


def _parent_of(n, by_name):
    m = re.match(r"Создать подраздел в «(.+)»", n["todo"])
    return by_name.get(m.group(1)) if m else None


def _parent(n, by_name, home):
    """Родитель-раздел, если он тоже будет создан и цепочка родителей без петли; иначе None (раздел верхнего уровня)."""
    p = _parent_of(n, by_name)
    seen, x = {id(n)}, p
    while x is not None:
        if id(x) in seen or x is home or x["st"] != "create":
            return None
        seen.add(id(x))
        x = _parent_of(x, by_name)
    return p


def _walk(nodes, level=0):
    for n in nodes:
        n["level"] = level
        yield n
        yield from _walk(n["children"], level + 1)


def structure(data):
    """Будущий сайт из семантики (после decisions.apply и plan.enrich): главная, разделы с подразделами,
    решить (есть у конкурента, спрос мал), блог, портфолио."""
    groups = [g for g in data.get("groups") or [] if g.get("land") and g["land"]["st"] != "manual"]
    nodes, by_name = [], {}
    for g in groups:
        L = g["land"]
        n = {"name": g["name"], "url": L["url"], "path": _path(L["url"]), "h1": L.get("h1") or g["name"],
             "title": L.get("title") or "", "st": L["st"], "todo": g.get("todo") or "", "freq": g.get("freq") or 0,
             "score": g.get("score") or 0, "queries": _top(g), "n": sum(1 for r in g.get("q") or [] if not r[7]),
             "rivals": sorted({_host(u) for u in g.get("rivals") or []}), "ptype": g.get("ptype"), "children": []}
        nodes.append(n)
        by_name[g["name"]] = n
    home = next((n for n in nodes if n["todo"].startswith("Главная")), None)
    sections, decide, articles_groups, brands = [], [], [], []
    for n in nodes:
        if n is home:
            continue
        if n["todo"].startswith("Создать страницу бренда"):
            brands.append(n)
            continue
        if n["st"] == "absent":
            decide.append(n)
            continue
        if n["ptype"] == "article" and not any(_parent_of(x, by_name) is n for x in nodes):
            articles_groups.append(n)        # группа из одних вопросов и без подразделов - это статьи, а не раздел
            continue
        parent = _parent(n, by_name, home)
        if parent:
            parent["children"].append(n)
        else:
            sections.append(n)
    key = lambda n: (-n["freq"], -n["score"])  # noqa: E731
    if brands:   # страницы брендов - одним разделом «Бренды»
        site = (data.get("site") or "").rstrip("/")
        brands.sort(key=key)
        sections.append({"name": "Бренды", "url": site + "/brands/", "path": "/brands/", "h1": "Бренды", "title": "",
                         "st": "create", "todo": "", "freq": sum(b["freq"] for b in brands),
                         "score": max(b["score"] for b in brands), "queries": [b["name"].lower() for b in brands[:5]],
                         "n": sum(b["n"] for b in brands), "rivals": sorted({h for b in brands for h in b["rivals"]}),
                         "ptype": "page", "children": brands})
    sections.sort(key=key)
    for n in _walk(sections):
        n["children"].sort(key=key)
    decide.sort(key=key)
    blog = [{"title": a["title"], "group": a["group"], "queries": a["queries"][:5], "n": a["n"]}
            for a in (data.get("articles") or [])[:BLOG_MAX]]
    seen = {a["title"].lower() for a in blog}
    for n in articles_groups:
        if n["name"].lower() not in seen and len(blog) < BLOG_MAX:
            blog.append({"title": n["name"], "group": n["name"], "queries": n["queries"], "n": n["n"]})
    gallery = []
    for g in groups:
        for r in g.get("q") or []:
            if not r[7] and r[2] == "Галерея" and r[0] not in gallery:
                gallery.append(r[0])
    rivals = sorted({h for n in nodes for h in n["rivals"]})
    ns = data.get(KEY) or {}
    return {"name": ns.get("name") or data.get("site") or "", "site": data.get("site") or "", "city": data.get("city") or "",
            "domain": ns.get("domain") or "", "home": home, "sections": sections, "decide": decide, "blog": blog,
            "gallery": gallery[:20], "gallery_page": len(gallery) >= GALLERY_MIN, "rivals": rivals,
            "pages": sum(1 for _ in _walk(sections)) + bool(home),
            "made": (data.get("made") or "").split(" ")[0], "freq": any(n["freq"] for n in nodes),
            "queries": sum(n["n"] for n in nodes)}


def rows(s):
    """Структура строками для Excel: (уровень, название, адрес, H1, title, главные запросы, спрос, у конкурентов)."""
    out = []

    def add(level, n, depth=0):
        out.append((level, "    " * depth + n["name"], n["path"], n["h1"], n["title"], ", ".join(n["queries"]),
                    n["freq"] or n["score"], ", ".join(n["rivals"])))
    if s["home"]:
        add("Главная", s["home"])
    for n in _walk(s["sections"]):
        add("Раздел" if not n["level"] else "Подраздел", n, n["level"])
    if s["gallery_page"]:
        out.append(("Портфолио", "Наши работы (фото)", "/portfolio/", "Наши работы", "", ", ".join(s["gallery"][:6]), "", ""))
    for a in s["blog"]:
        out.append(("Статья в блог", a["title"], f"/blog/{_slug(a['title'])}/", a["title"], "", ", ".join(a["queries"]), "", ""))
    for n in s["decide"]:
        out.append((_KIND["absent"][0], n["name"], n["path"], n["h1"], n["title"], ", ".join(n["queries"]),
                    n["freq"] or n["score"], ", ".join(n["rivals"])))
    return out


CSS = """:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1d1f;--mut:#6b6b70;--line:#e6e3dc;--acc:#2f5bd3;--ok:#2e7d4f}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--card:#222225;--ink:#ececee;--mut:#a0a0a8;--line:#36363a;--acc:#8aa8ff;--ok:#6cc08b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.w{max-width:980px;margin:0 auto;padding:28px 16px 48px}h1{font-size:26px;margin:0 0 6px}h2{font-size:19px;margin:30px 0 10px}
.mut{color:var(--mut)}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.tiles div{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:8px 14px;color:var(--mut);font-size:14px}.tiles b{display:block;font-size:22px;color:var(--ink)}
.sec{border-left:3px solid var(--acc)}.sec h3{margin:0;font-size:16px}.url{font-family:Consolas,monospace;font-size:13px;color:var(--acc)}
.q{font-size:13px;color:var(--mut);margin-top:2px}.sub{margin:8px 0 0 18px;padding-left:12px;border-left:1px dashed var(--line)}
.sub div{margin:6px 0}ol,ul{padding-left:22px}li{margin:4px 0}.tag{display:inline-block;font-size:12px;color:var(--mut);
border:1px solid var(--line);border-radius:20px;padding:0 8px;margin-left:6px}
@media print{body{background:#fff}.card{break-inside:avoid}}"""


def html(s):
    """Страница для клиента: структура будущего сайта простыми словами."""
    def demand(n):
        if n["freq"]:
            return f'спрос {_n(n["freq"])} в месяц'
        return ""

    def node(n, head="h3"):
        q = ", ".join(n["queries"][:4])
        riv = (f'<span class="tag">есть у {_e(", ".join(n["rivals"][:3]))}</span>' if n["rivals"] else
               '<span class="tag">у конкурентов отдельной страницы нет</span>')
        d = demand(n)
        return (f'<{head}>{_e(n["h1"])} {riv}</{head}><div class="url">{_e(n["path"])}</div>'
                + (f'<div class="q">Ищут: {_e(q)}</div>' if q else "") + (f'<div class="q">{_e(d)}</div>' if d else ""))
    def kids(n):
        return (f'<div class="sub">' + "".join(f'<div>{node(c, "b")}{kids(c)}</div>' for c in n["children"]) + '</div>'
                if n["children"] else "")
    parts = [f'<div class="card sec">{node(n)}{kids(n)}</div>' for n in s["sections"]]
    n_sub = s["pages"] - len(s["sections"]) - bool(s["home"])
    tiles = [(len(s["sections"]), _pl(len(s["sections"]), "раздел", "раздела", "разделов")),
             (n_sub, _pl(n_sub, "подраздел", "подраздела", "подразделов")),
             (len(s["blog"]), _pl(len(s["blog"]), "статья в блог", "статьи в блог", "статей в блог")),
             (s["queries"], _pl(s["queries"], "запрос", "запроса", "запросов"))]
    city = f' ({_e(s["city"])})' if s["city"] else ""
    head = (f'Собрано {_n(s["queries"])} {_pl(s["queries"], "запрос", "запроса", "запросов")}, которые люди набирают '
            f'в Яндексе и Google по теме{city}, и разбито по страницам: одна группа запросов - одна страница. '
            f'Так сайт с первого дня строится под то, что ищут, и каждой странице есть по чему показываться в поиске.')
    if s["rivals"]:
        head += f' Учтены разделы конкурентов: {_e(", ".join(s["rivals"]))}.'
    home = ""
    if s["home"]:
        h = s["home"]
        home = (f'<h2>Главная страница</h2><div class="card"><b>{_e(h["h1"])}</b>'
                + (f'<div class="q">Title: {_e(h["title"])}</div>' if h["title"] else "")
                + (f'<div class="q">Ищут: {_e(", ".join(h["queries"][:5]))}</div>' if h["queries"] else "") + '</div>')
    blog = ""
    if s["blog"]:
        blog = ('<h2>Статьи для блога</h2><p class="mut">Вопросы, которые люди задают по теме. Статья отвечает на вопрос '
                'и ведёт на страницу товара или услуги.</p><ol>'
                + "".join(f'<li>{_e(a["title"])}' + (f' <span class="mut">- {_e(", ".join(a["queries"][:3]))}</span>'
                                                       if len(a["queries"]) > 1 else "") + '</li>' for a in s["blog"]) + '</ol>')
    gal = ""
    if s["gallery_page"]:
        gal = ('<h2>Портфолио и фото работ</h2><p class="mut">Люди ищут фото и примеры, поэтому нужна страница с работами '
               'и подписями к фото. Например: ' + _e(", ".join(s["gallery"][:6])) + '.</p>')
    decide = ""
    if s["decide"]:
        decide = (f'<h2>{_KIND["absent"][0]}</h2><p class="mut">Есть у конкурента, но спрос небольшой. Добавлять ли такие '
                  'страницы, зависит от того, продаёте ли вы это.</p><ul>'
                  + "".join(f'<li>{_e(n["h1"])}' + (f' <span class="mut">- есть у {_e(", ".join(n["rivals"][:2]))}</span>'
                                                     if n["rivals"] else "") + '</li>' for n in s["decide"][:20]) + '</ul>')
    note = ("Спрос в месяц - по частотности в Яндексе (Вордстат). " if s["freq"] else
            "Спрос оценён по подсказкам Яндекса и Google, это не число показов в месяц. ")
    note += "Своя страница под запрос не обещает места в поиске, но без неё сайт по этому запросу почти не показывается."
    if s["made"]:
        note += f" Запросы собраны {_e(s['made'])}."
    title = f'Структура сайта: {s["name"]}'
    body = (f'<div class="w"><h1>{_e(title)}</h1><p class="mut">{head}</p><div class="tiles">'
            + "".join(f'<div><b>{_n(v)}</b>{_e(t)}</div>' for v, t in tiles if v) + '</div>' + home
            + (f'<h2>Разделы и страницы</h2><p class="mut">Сначала - самые востребованные. Адреса и заголовки H1 - '
               f'предложение, их можно поменять.</p>{"".join(parts)}' if parts else "")
            + gal + blog + decide + f'<p class="mut" style="margin-top:28px">{note}</p></div>')
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head>'
            f'<body>{body}</body></html>')


def write_client(folder, data):
    """«структура сайта.html» в папке проекта и копия в «для клиента». Возвращает путь или ""."""
    s = structure(data)
    if not s["sections"] and not s["home"]:
        return ""
    text = html(s)
    path = os.path.join(folder, CLIENT_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    out = os.path.join(folder, "для клиента")
    os.makedirs(out, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|]+', " ", s["name"]).strip() or "сайт"
    with open(os.path.join(out, f"Структура сайта - {name}.html"), "w", encoding="utf-8") as f:
        f.write(text)
    return path
