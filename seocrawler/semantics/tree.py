"""Дерево сайта и карта признаков (по просьбе Тимура, 06.10.2026).

Дерево: главная → разделы → подразделы → фильтры, как в таблице структуры у агентств. У каждой страницы - адрес,
H1, спрос, место в Яндексе и Google (только из Вебмастера и Search Console, если есть доступ) и что с ней:
зелёный - есть на сайте, синий - фильтр есть на сайте, жёлтый - создать, серый - решить, нужна ли. Красная
отметка - спрос большой, а место хуже 10-го. Вложенность - по адресам страниц (у сайта без вложенных адресов
разделы будут одним уровнем), промежуточные страницы, под которые нет группы запросов, берутся из обхода сайта.
У нового сайта (semantics/newsite.py) дерево - его структура, всё жёлтое.

Карта признаков (как карта в XMind): у категории - признаки (тип, назначение, бренд, цвет, материал, стиль,
размер, цена, услуги) и их значения из запросов группы и из блоков фильтров каталога: своего и конкурентов
(ссылки со страницы категории на её же фильтры: «Sibio», «Белые»). У значения - спрос и есть ли страница:
у вас, только у конкурента, нигде. Сочетания признаков («белые + прованс») - какие ищут достаточно, чтобы
делать под них страницу, чтобы не плодить тысячи пустых страниц.

Только бесплатные данные: запросы семантики, обход своего сайта и проверки конкурентов."""
import json
import os
import re
import sqlite3
from urllib.parse import urlsplit

from ..fmt import esc as _e, num as _n
from .stem import stem, sound
from . import labels as LB
from .words import CITY_WORDS
from ..tablefs import JS as FS_JS

FILE = "дерево сайта.html"
ST = {**LB.TREE,   # названия - в labels.py, одни на окно, отчёты, Excel и бота
      "low": "Спроса мало", "rival": "Есть у конкурента", "none": "Нигде нет"}
FILTER_MIN = 5          # столько запросов у уточнения - стоит своя страница-фильтр
FILTER_FREQ = 50        # или столько показов в месяц (Вордстат)
COMBO_MIN = 3           # сочетание признаков: столько запросов - стоит страница
COMBO_FREQ = 30
VALUES_MAX = 12         # значений одного признака на карте
COMBOS_MAX = 15
QUERIES_MAX = 60        # запросов у страницы в дереве
BAD_POS = 10            # место хуже - «спрос большой, а место плохое»
AXIS_ORDER = ["Тип", "Назначение", "Бренд", "Размер и мощность", "Форма и размер", "Цвет", "Материал", "Стиль",
              "Цена", "Услуги"]
NAV = {"показать", "сбросить", "дешевле", "дороже", "подробнее", "все", "далее", "назад", "вперед", "вперёд", "еще",
       "ещё", "сортировать", "по цене", "по популярности", "по названию", "новинки", "хиты", "применить", "очистить",
       "в корзину", "купить", "сравнить", "читать", "смотреть все", "показать все", "все товары"}
STOP = {"как", "что", "какой", "какая", "какие", "каких", "лучше", "лучший", "лучшие", "самый", "самые", "отзывы",
        "отзыв", "своими", "руками", "фото", "видео", "цена", "цены", "купить", "куплю", "стоимость", "заказать",
        "магазин", "интернет", "каталог", "сайт", "официальный", "это", "такое", "чем", "где", "или", "при", "без",
        "про", "вид", "виды", "типы", "тип", "рейтинг", "инструкция", "схема", "характеристики", "размеры", "своим",
        "можно", "нужно", "лучшая", "лучшее", "выбрать", "выбор", "сколько", "почему", "зачем", "нужен", "нужна",
        "года", "год", "шт", "наличии", "наличие", "доставкой", "чего",
        "этого", "него", "всех", "всего", "лучшего", "самого", "какого", "такой", "такие", "любой", "разные", "свой",
        "хороший", "хорошие", "хорошая", "надежные", "надежный", "популярные", "популярный", "новые", "новый", "старый"
        } | CITY_WORDS   # город - не тип товара: любой город из общего списка, а не только города прошлых клиентов
UNIT_RX = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?(?:\s*[x×х*]\s*\d+(?:[.,]\d+)?)?)\s*(квт|kw|вт|литр\w*|л|мм|см|м2|м3|м|"
                     r"бар|кг|дюйм\w*|мест\w*|секци\w*|ампер|а|в|куб\w*)(?![\w])")
FOR_RX = re.compile(r"(?<![\w])для\s+([a-zа-яё]+)(?:\s+([a-zа-яё]+))?")
LAT_RX = re.compile(r"^[a-z][a-z0-9-]{2,}$")
ADJ_RX = re.compile(r"(ый|ий|ой|ая|яя|ое|ее|ые|ие)$")      # «газовые», «фланцевый» - тип; «размещения», «шланг» - нет
VERB_RX = re.compile(r"(ает|яет|ется|ит|ут|ют|ать|ять|ить|еть|ал|ил)$")
BRAND_PATH = re.compile(r"/(brands?|brendy|brend|proizvoditeli|proizvoditel|vendors?|manufacturers?)[/-]|[/_-]brand[-_/]", re.I)


def _host(u):
    return (urlsplit(u or "").hostname or "").removeprefix("www.")


def _key(u):
    """Адрес → ключ для вложенности: путь без косой черты в конце (и с параметрами, если есть)."""
    p = urlsplit(u or "")
    path = (p.path or "/").rstrip("/")
    return path + ("?" + p.query if p.query else "")


def _segs(key):
    return [s for s in key.split("?")[0].split("/") if s]


def _ro(path):
    try:
        return sqlite3.connect(f"file:{os.path.join(path, 'crawl.db')}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\-/.,]", " ", (s or "").lower().replace("ё", "е"))).strip()


# ---------------------------------------------------------------- данные запросов

def _freq_mode(groups):
    return any((r[11] if len(r) > 11 else 0) for g in groups for r in g.get("q") or [])


def _dem(r, freq):
    return ((r[11] if len(r) > 11 else 0) or 0) if freq else (r[3] or 0)


def _pos(rows):
    """Место в Яндексе и Google (средневзвешенное по показам), и общее, если по отдельности не знаем."""
    def avg(i):
        xs = [((r[i] if len(r) > i else 0) or 0, (r[6] or 1)) for r in rows]
        xs = [(p, w) for p, w in xs if p]
        return round(sum(p * w for p, w in xs) / sum(w for _, w in xs), 1) if xs else 0
    y, g = avg(12), avg(13)
    return y, g, (0 if y or g else avg(8))


def _queries(rows, freq):
    rows = sorted((r for r in rows if not r[7]), key=lambda r: -_dem(r, freq))
    return [[r[0], _dem(r, freq), (r[12] if len(r) > 12 else 0) or 0, (r[13] if len(r) > 13 else 0) or 0,
             r[8] if len(r) > 8 else 0] for r in rows[:QUERIES_MAX]]


# ---------------------------------------------------------------- фильтры каталога (ссылки со страницы категории)

def _is_product(db, url):
    try:
        r = db.execute("SELECT schema_types FROM pages WHERE url=?", (url,)).fetchone()
    except sqlite3.Error:
        return False
    s = (r[0] or "") if r else ""
    return "Product" in s and "Offer" in s and "ItemList" not in s and "AggregateOffer" not in s


def filter_links(db, url, core=()):
    """Блок фильтров на странице категории: ссылки на её же адреса глубже («/kotly/brand-baxi/») или с параметрами,
    с коротким текстом («Baxi», «Белые»). Товары, листание страниц и сортировка не считаются.
    Возвращает [(текст, адрес)]."""
    if db is None or not url:
        return []
    base = urlsplit(url)
    path = base.path if base.path.endswith("/") else base.path + "/"
    try:
        rows = db.execute("SELECT dst, anchor FROM links WHERE src=? AND kind='a'", (url,)).fetchall()
    except sqlite3.Error:
        return []
    out, seen = [], set()
    core = {stem(w) for w in core}
    for dst, a in rows:
        a = re.sub(r"\s+", " ", (a or "")).strip()
        al = a.lower().replace("ё", "е")
        d = urlsplit(dst or "")
        if not a or (d.hostname or "") != (base.hostname or "") or dst in seen:
            continue
        deeper = d.path.startswith(path) and len(d.path) > len(path)
        param = d.path.rstrip("/") == base.path.rstrip("/") and d.query and not re.search(
            r"(page|pagen|sort|order|limit|view|show|count|set_filter=y$)", d.query, re.I)
        if not (deeper or param):
            continue
        words = al.split()
        if (al in NAV or len(words) > 3 or len(a) > 40 or re.fullmatch(r"[\d\s.,()+-]+", al)
                or (words and all(stem(w) in core for w in words))):
            continue
        if deeper and _is_product(db, dst):
            continue
        seen.add(dst)
        out.append((a, dst))
    return out[:60]


# ---------------------------------------------------------------- карта признаков

class Axes:
    """Какой признак у слова: словарь «Признаки» (semantics/dicts.py), латиница и знакомые бренды - бренд,
    «для …» - назначение, числа с единицами - размер и мощность, остальное - тип."""
    def __init__(self, lines, brands=()):
        self.words, self.phrases, self.exact = {}, [], set()
        for line in lines or []:
            if line.lstrip().startswith("#") or ":" not in line:
                continue
            name, vals = line.split(":", 1)
            name = name.strip()[:30]
            for v in vals.split(","):
                v = v.strip().lower().replace("ё", "е")
                if not v:
                    continue
                if " " in v:
                    self.phrases.append((v, name))
                else:
                    self.words[stem(v)] = name
                    self.exact.add(v)
        self.brands = {sound(b) for b in brands if len(b) >= 3}

    def of(self, w):
        k = stem(w)
        if k in self.words and (len(k) >= 4 or ADJ_RX.search(w) or w in self.exact):
            return self.words[k]      # короткая основа: «серый» и «серии» - «сер», поэтому только прилагательное
        if LAT_RX.match(w) or sound(w) in self.brands:
            return "Бренд"
        return "Тип"


def _vkey(axis, w):
    return (axis, sound(w) if axis == "Бренд" else " ".join(stem(x) for x in w.split()))


def _parts(q, extra, ax, core):
    """Значения признаков в запросе: [(признак, значение)]."""
    q = q.lower().replace("ё", "е")
    toks = [t for t in extra.split() if t]
    used, out = set(), []
    for ph, name in ax.phrases:
        if re.search(r"(?<![\w])" + re.escape(ph) + r"(?![\w])", q):
            out.append((name, ph))
            used |= set(ph.split())
    for m in UNIT_RX.finditer(q):
        num_, unit = m.group(1).replace(",", "."), m.group(2)
        unit = {"kw": "квт"}.get(unit, unit)
        if unit in ("а", "в", "м") and not re.search(r"\d{2,}", num_):
            continue        # «2 в 1», «3 м» - чаще не характеристика
        out.append(("Размер и мощность", f"{num_} {unit}"))
        used |= {m.group(1), m.group(2)}
    m = FOR_RX.search(q)
    if m:   # «для отопления частного дома»: слова после «для», пока они - уточнения запроса
        ws = []
        for w in q[m.start():].split()[1:4]:
            if w not in toks or w in STOP or VERB_RX.search(w) or w in used or ax.of(w) not in ("Тип", "Назначение"):
                break
            ws.append(w)
        if ws:
            out.append(("Назначение", "для " + " ".join(ws)))
            used |= set(ws)
    for t in toks:
        if t in used or len(t) < 3 or t in STOP or re.search(r"\d", t) or stem(t) in core:
            continue
        a = ax.of(t)
        if a == "Тип" and (not ADJ_RX.search(t) or re.search(r"(ние|тие|вие)$", t)):   # «отопление» - не прилагательное
            continue        # «размещения», «норма», «шланг» - не признак (бренды на кириллице - по звучанию)
        out.append((a, t))
    return out


def features(g, freq, ax, own=(), rival=(), core=()):
    """Карта признаков категории: признаки и значения со спросом и где есть страница, сочетания.
    own - [(текст, адрес)] фильтров своего каталога, rival - [(текст, адрес)] фильтров конкурентов."""
    rows = [r for r in g.get("q") or [] if not r[7]]
    core = {stem(w) for w in core}
    vals, combos = {}, {}
    ax.brands |= {sound(w) for a, u in list(own) + list(rival) if BRAND_PATH.search(u)   # «Baxi», «HAIER, HEC»
                  for w in (x.strip() for x in _norm(a).split(",")) if len(w) >= 3 and " " not in w}

    def val(axis, v):
        k = _vkey(axis, v)
        e = vals.get(k)
        if e is None:
            e = vals[k] = {"axis": axis, "forms": {}, "n": 0, "d": 0, "q": [], "url": "", "rivals": []}
        e["forms"][v] = e["forms"].get(v, 0) + 1
        return k, e
    for r in rows:
        found = {}
        for axis, v in _parts(r[0], r[1] or "", ax, core):
            k, e = val(axis, v)
            if k in found:
                continue
            found[k] = e
            e["n"] += 1
            e["d"] += _dem(r, freq)
            if len(e["q"]) < 5:
                e["q"].append(r[0])
        ks = sorted(found, key=lambda k: AXIS_ORDER.index(k[0]) if k[0] in AXIS_ORDER else 99)
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                if a[0] == b[0]:
                    continue
                c = combos.setdefault((a, b), {"n": 0, "d": 0, "q": []})
                c["n"] += 1
                c["d"] += _dem(r, freq)
                c["q"].append(r[0])

    def link_vals(links, mark):
        for a, u in links:
            words = [w for w in _norm(a).split() if stem(w) not in core]
            if not words:
                continue
            v = " ".join(words)
            axis = ax.of(words[0]) if len(words) == 1 else next((x for x in map(ax.of, words) if x != "Тип"), "Тип")
            if BRAND_PATH.search(u):
                axis = "Бренд"
            k = _vkey(axis, v)
            if k not in vals:     # значение только из фильтров: без спроса, но видно, что оно есть
                k = next((k2 for k2 in vals if k2[1] == k[1]), k)
            k, e = (k, vals[k]) if k in vals else val(axis, v)
            if mark == "own":
                e["url"] = e["url"] or u
                e["forms"][a] = e["forms"].get(a, 0) + 100   # как называет сам сайт
            elif _host(u) not in e["rivals"]:
                e["rivals"].append(_host(u))
    link_vals(own, "own")
    link_vals(rival, "rival")
    axes = {}
    for k, e in vals.items():
        if e["axis"] in ("Тип", "Бренд") and e["n"] < 2 and not e["url"] and not e["rivals"]:
            continue     # случайное слово («yandex», «cloud»)
        if not e["n"] and not e["url"] and len(e["rivals"]) < 1:
            continue
        name = max(e["forms"].items(), key=lambda x: (x[1], -len(x[0])))[0]
        big = e["n"] >= FILTER_MIN or (freq and e["d"] >= FILTER_FREQ)
        st = "filter" if e["url"] else "rival" if e["rivals"] else "create" if big else "low"
        axes.setdefault(e["axis"], []).append({"v": name, "n": e["n"], "d": e["d"], "st": st, "url": e["url"],
                                               "rivals": e["rivals"][:3], "q": e["q"], "k": k})
    if sum(len(v) for v in axes.values()) < 3:
        return None
    out = []
    for name, vs in axes.items():
        vs.sort(key=lambda v: (-v["d"], -v["n"], v["st"] != "filter"))
        out.append({"name": name, "values": vs[:VALUES_MAX], "more": max(0, len(vs) - VALUES_MAX),
                    "d": sum(v["d"] for v in vs)})
    out.sort(key=lambda a: (AXIS_ORDER.index(a["name"]) if a["name"] in AXIS_ORDER else 50, -a["d"]))
    shown = {v["k"]: v["v"] for a in out for v in a["values"]}
    cs = []
    for (a, b), c in combos.items():
        if c["n"] < 2 or a not in shown or b not in shown:
            continue
        worth = c["n"] >= COMBO_MIN or (freq and c["d"] >= COMBO_FREQ)
        best = min(c["q"], key=lambda q: (len(q.split()), q))
        cs.append({"a": shown[a], "b": shown[b], "axes": [a[0], b[0]], "n": c["n"], "d": c["d"], "worth": bool(worth),
                   "name": best[:1].upper() + best[1:], "q": c["q"][:5]})
    cs.sort(key=lambda c: (-c["d"], -c["n"]))
    for a in out:
        for v in a["values"]:
            v.pop("k", None)
    return {"axes": out, "combos": cs[:COMBOS_MAX], "combos_all": len(cs)}


# ---------------------------------------------------------------- дерево

def _node(name, path, **kw):
    n = {"name": name, "path": path, "url": "", "h1": "", "title": "", "st": "have", "kind": "page", "d": 0, "n": 0,
         "q": [], "py": 0, "pg": 0, "p": 0, "rivals": [], "todo": "", "children": [], "also": []}
    n.update(kw)
    return n


def _from_group(g, freq, st, path, url=""):
    rows = [r for r in g.get("q") or [] if not r[7]]
    py, pg, p = _pos(rows)
    L = g.get("land") or {}
    d = (g.get("freq") or 0) if freq else (g.get("score") or 0)
    return _node(g["name"], path, url=url, h1=L.get("h1") or ((g.get("a") or {}).get("now") or {}).get("h1") or "",
                 title=L.get("title") or "", st=st, kind="page", d=d, n=len(rows), q=_queries(rows, freq),
                 py=py, pg=pg, p=p, rivals=sorted({_host(u) for u in g.get("rivals") or []}), todo=g.get("todo") or "",
                 g=g)


def _filters_of(n, g, freq, db, ax):
    """Фильтры под страницей категории: уточнения из запросов (pages._filters) и фильтры каталога сайта."""
    own = filter_links(db, n["url"], n["name"].lower().split()) if n["st"] == "have" and n["url"] else []
    used = set()
    for f in g.get("f") or []:
        w = stem(f["word"])
        hit = next(((a, u) for a, u in own if any(stem(x) == w or sound(x) == sound(f["word"])
                                                 for x in _norm(a).split())), None)
        sample = set(f.get("sample") or [])
        rows = [r for r in g.get("q") or [] if not r[7] and (r[0] in sample or f["word"] in (r[1] or "").split())]
        d = sum((r[11] if len(r) > 11 else 0) or 0 for r in rows) if freq else f.get("score") or 0
        big = f.get("queries", 0) >= FILTER_MIN or (freq and d >= FILTER_FREQ)
        if hit:
            used.add(hit[1])
        st = "filter" if hit else "create" if big else "low"
        py, pg, p = _pos(rows)
        path = urlsplit(hit[1]).path if hit else (n["path"].rstrip("/") + "/" + _slug(f["word"]) + "/")
        n["children"].append(_node(f["name"], path, url=hit[1] if hit else "", h1=f["name"], st=st, kind="filter",
                                   d=d, n=f.get("queries", 0), q=_queries(rows, freq) or [[q, 0, 0, 0, 0] for q in sample],
                                   py=py, pg=pg, p=p, todo="Страница-фильтр" if hit else
                                   "Создать страницу-фильтр" if big else "Спроса мало: фильтр в каталоге, без своей страницы"))
    rest = [(a, u) for a, u in own if u not in used]
    if rest:   # фильтры каталога, которых нет в запросах: страницы есть, спроса не нашлось - одной строкой
        n["children"].append(_node(f"Другие фильтры каталога: {len(rest)}", "", st="filter", kind="filter", n=len(rest),
                                   q=[[a, 0, 0, 0, 0] for a, _u in rest],
                                   todo="Страницы-фильтры есть, но запросов под них не нашлось (ниже - их названия)"))


def _slug(text):
    from .plan import slug
    return slug(text) or "filter"


def _walk(n, depth=0):
    yield n, depth
    for c in n["children"]:
        yield from _walk(c, depth + 1)


def _sort(n):
    n["children"].sort(key=lambda c: (c["kind"] == "group", c["kind"] == "filter", -c["d"], -c["n"], c["name"]))
    for c in n["children"]:
        _sort(c)


def _brands(data):
    out = set()
    for g in data.get("groups") or []:
        for r in g.get("q") or []:
            out |= {t for t in (r[1] or "").split() if LAT_RX.match(t)}
        rv = g.get("rivals") or []
        if (g.get("todo") or "").startswith("Создать страницу бренда") or (rv and all(BRAND_PATH.search(u) for u in rv)):
            if len(g["name"].split()) == 1:     # группа - один бренд («Baxi», «Лемакс»)
                out.add(g["name"].lower())
    return out


def _rival_dbs(data, folder):
    from .plan import _rival_folders
    hosts = sorted({_host(u) for g in data.get("groups") or [] for u in g.get("rivals") or []})
    return {h: _ro(f) for h, f in _rival_folders(os.path.dirname(folder), hosts).items()} if folder else {}


def _new_root(data, by_name, freq, decide):
    """Новый сайт: дерево из будущей структуры (newsite.structure). → (корень, название)."""
    from . import newsite as NS
    s = NS.structure(data)

    def conv(sn):
        g = by_name.get(sn["name"])
        n = _from_group(g, freq, "create", sn["path"]) if g else _node(
            sn["name"], sn["path"], st="create", d=sn["freq"] if freq else sn["score"], n=sn["n"],
            q=[[q, 0, 0, 0, 0] for q in sn["queries"]], rivals=sn["rivals"])
        n["h1"], n["title"] = sn["h1"], sn["title"]
        n["children"] = [conv(c) for c in sn["children"]]
        return n
    root = conv(s["home"]) if s["home"] else _node("Главная", "/", st="create")
    root["kind"] = "home"
    root["children"] += [conv(x) for x in s["sections"]]
    decide["children"] = [conv(x) for x in s["decide"]]
    for c in decide["children"]:
        c["st"] = "decide"
    if s["gallery_page"]:
        root["children"].append(_node("Наши работы (фото)", "/portfolio/", h1="Наши работы", st="create",
                                      kind="gallery", q=[[q, 0, 0, 0, 0] for q in s["gallery"]],
                                      n=len(s["gallery"]), todo="Портфолио: люди ищут фото и примеры"))
    if s["blog"]:
        blog = _node("Блог", "/blog/", h1="Статьи", st="create", kind="blog", todo="Статьи на вопросы людей")
        blog["children"] = [_node(a["title"], f"/blog/{_slug(a['title'])}/", h1=a["title"], st="create",
                                  kind="article", n=a["n"], q=[[q, 0, 0, 0, 0] for q in a["queries"]])
                            for a in s["blog"]]
        root["children"].append(blog)
    return root, s["name"]


def _site_root(groups, freq, site, db, decide):
    """Свой сайт: группы по адресам их страниц, промежуточные страницы с сайта. → (корень, название)."""
    stmap = {"ok": "have", "fix": "have", "wrong": "have", "create": "create", "absent": "decide"}
    nodes = {}
    for g in sorted(groups, key=lambda g: -((g.get("freq") or 0) if freq else (g.get("score") or 0))):
        L = g["land"]
        st = stmap.get(L["st"], "decide")
        url = L["url"] or ""
        if url and _host(url) != _host(site):
            continue
        if st == "decide":
            decide["children"].append(_from_group(g, freq, "decide", _key(url) + "/" if url else ""))
            continue
        k = _key(url)
        n = _from_group(g, freq, st, (k or "") + ("/" if url.endswith("/") or not k else ""),
                        url if st == "have" else "")
        if k in nodes:   # две группы ведут на одну страницу («Вести на …»): запросы - вместе
            m = nodes[k]
            m["also"].append(g["name"])
            m["q"] = sorted(m["q"] + n["q"], key=lambda r: -r[1])[:QUERIES_MAX]
            m["n"] += n["n"]
            m["d"] += n["d"]
            continue
        nodes[k] = n
    pages = {}
    if db is not None:
        try:
            for u, h1 in db.execute("SELECT url, h1 FROM pages WHERE status=200 AND content_type LIKE '%html%'"):
                if _host(u) == _host(site):
                    pages.setdefault(_key(u), (u, h1 or ""))
        except sqlite3.Error:
            pass
    root = nodes.pop("", None)
    if root is None:
        u, h1 = pages.get("", (site, ""))
        root = _node("Главная", "/", url=u, h1=h1)
    root["kind"] = "home"
    if not root["h1"] and "" in pages:
        root["h1"] = pages[""][1]

    def parent(k):
        ss = _segs(k)
        for i in range(len(ss) - 1, 0, -1):
            pk = "/" + "/".join(ss[:i])
            if pk in nodes:
                return nodes[pk]
            if pk in pages:   # промежуточная страница есть на сайте, группы запросов под неё нет
                u, h1 = pages[pk]
                nodes[pk] = _node(h1 or ss[i - 1], pk + "/", url=u, h1=h1, todo="Страница есть, запросов под неё не нашлось")
                p = parent(pk)
                (p or root)["children"].append(nodes[pk])
                return nodes[pk]
        return None
    for k, n in list(nodes.items()):
        if "?" in k and k.split("?")[0] in nodes:
            nodes[k.split("?")[0]]["children"].append(n)
            continue
        (parent(k) or root)["children"].append(n)
    return root, _host(site)


def build(data, folder=None, dicts=None):
    """Дерево из семантики (после decisions.apply и plan.enrich). folder - папка проверки (обход сайта и
    проверки конкурентов рядом в «отчёты»); без неё - только по запросам."""
    from . import newsite as NS
    from . import dicts as DI
    groups = [g for g in data.get("groups") or [] if g.get("land") and g["land"]["st"] != "manual"]
    freq = _freq_mode(groups)
    ax = Axes((dicts or DI.load()).get("axes") or DI.AXES, _brands(data))
    new = bool(data.get(NS.KEY))
    db = _ro(folder) if folder and not new else None
    rdbs = _rival_dbs(data, folder)
    site = data.get("site") or ""
    by_name = {g["name"]: g for g in groups}
    decide = _node(LB.TREE["decide"], "", st="decide", kind="group",
                   todo="Есть у конкурентов, но спроса мало или своих товаров нет: " + LB.DECIDE)
    if new:
        root, name = _new_root(data, by_name, freq, decide)
    else:
        root, name = _site_root(groups, freq, site, db, decide)
    # фильтры и карта признаков у страниц с группой
    for n, _d in list(_walk(root)):
        g = n.get("g")
        if not g or n["kind"] not in ("page", "home"):
            continue
        if n["kind"] == "page":
            _filters_of(n, g, freq, db, ax)
        own = filter_links(db, n["url"], n["name"].lower().split()) if n["st"] == "have" and n["url"] else []
        rival = []
        for u in g.get("rivals") or []:
            rdb = rdbs.get(_host(u))
            rival += filter_links(rdb, u, n["name"].lower().split())
        core = re.findall(r"[a-zа-яё0-9]+", g["name"].lower().replace("ё", "е"))
        fm = features(g, freq, ax, own, rival, core)
        if fm:
            n["fm"] = fm
    if decide["children"]:
        root["children"].append(decide)
        decide["d"] = sum(c["d"] for c in decide["children"])
    _sort(root)
    for x in [db] + list(rdbs.values()):
        if x is not None:
            x.close()
    # красная отметка: спрос в верхней четверти, место хуже 10-го
    ds = sorted((n["d"] for n, _ in _walk(root) if n["d"] and n["kind"] != "group"), reverse=True)
    thr = ds[len(ds) // 4] if ds else 0
    nid = 0
    for n, depth in _walk(root):
        n.pop("g", None)
        n["id"] = nid
        nid += 1
        worst = max(n["py"], n["pg"]) or n["p"]
        n["bad"] = bool(worst > BAD_POS and n["d"] and n["d"] >= thr)
    cnt = {}
    for n, _ in _walk(root):
        if n["kind"] not in ("group", "blog"):
            k = "filter_create" if n["kind"] == "filter" and n["st"] == "create" else n["st"]
            cnt[k] = cnt.get(k, 0) + 1
    return {"name": name, "site": "" if new else site, "new": new, "freq": freq, "root": root, "count": cnt,
            "pos": any(n["py"] or n["pg"] or n["p"] for n, _ in _walk(root)),
            "maps": sum(1 for n, _ in _walk(root) if n.get("fm")), "made": (data.get("made") or "").split(" ")[0],
            "city": data.get("city") or ""}


# ---------------------------------------------------------------- Excel

def level(n, depth, under_decide=False):
    if under_decide and n["kind"] != "group":
        return LB.TREE["decide"]
    return {"home": "Главная", "filter": "Фильтр", "article": "Статья в блог", "gallery": "Портфолио", "blog": "Блог",
            "group": LB.TREE["decide"]}.get(n["kind"]) or ("Раздел" if depth == 1 else "Подраздел")


def rows(t):
    """Строки для Excel: (уровень, название с отступом, адрес, H1, что с ней, спрос, Яндекс, Google, запросов,
    главные запросы, у конкурентов, статус, красная отметка)."""
    out = []

    def go(n, depth, dec):
        if n["kind"] != "group":
            pos = n["p"] if not (n["py"] or n["pg"]) else 0
            out.append((level(n, depth, dec), "    " * max(0, depth - (1 if dec else 0)) + n["name"], n["path"],
                        n["h1"], n["todo"] or ST[n["st"]], n["d"] or "", n["py"] or pos or "", n["pg"] or "", n["n"] or "",
                        ", ".join(q[0] for q in n["q"][:6]), ", ".join(n["rivals"][:3]), n["st"], n["bad"]))
        for c in n["children"]:
            go(c, depth + 1, dec or n["kind"] == "group")
    go(t["root"], 0, False)
    return out


FILL = {"have": "D9EAD3", "filter": "D6E2FA", "create": "FCEFC2", "decide": "ECEAE4", "low": "F4F2EC", "rival": "FCE1CC",
        "none": "FCEFC2"}


def write_sheets(wb, t, sheet_name, first=False):
    """Лист дерева и лист «Признаки» в книгу openpyxl."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    bold, wrap = Font(bold=True), Alignment(wrap_text=True, vertical="top")
    head_fill = PatternFill("solid", fgColor="EDEBE6")

    def sheet(ws, cols, widths):
        ws.append(cols)
        for i, w in enumerate(widths, 1):
            c = ws.cell(row=1, column=i)
            c.font, c.fill, c.alignment = bold, head_fill, wrap
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"
    dem = "Спрос в месяц" if t["freq"] else "Оценка спроса, баллы"
    ws = wb.create_sheet(sheet_name, 0 if first else None)
    sheet(ws, ["Что", "Страница", "Адрес", "H1", "Что с ней", dem, "Место Яндекс", "Место Google", "Запросов",
               "Главные запросы", "У конкурентов"], [16, 46, 44, 40, 34, 11, 10, 10, 9, 70, 30])
    red = Font(color="C0392B", bold=True)
    for r in rows(t):
        ws.append([_clean(x) if isinstance(x, str) else x for x in r[:11]])
        i = ws.max_row
        ws.cell(row=i, column=1).fill = PatternFill("solid", fgColor=FILL.get(r[11], "FFFFFF"))
        ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor=FILL.get(r[11], "FFFFFF"))
        if r[0] in ("Главная", "Раздел"):
            ws.cell(row=i, column=2).font = bold
        if r[12]:
            for c in (2, 6, 7, 8):
                ws.cell(row=i, column=c).font = red
            ws.cell(row=i, column=5).value = "Спрос большой, а место хуже 10-го. " + (ws.cell(row=i, column=5).value or "")
        ws.cell(row=i, column=10).alignment = wrap
    i = ws.max_row + 2
    for st, text in (("have", "зелёный - " + LB.TREE["have"].lower()), ("filter", "синий - " + LB.TREE["filter"].lower()),
                     ("create", "жёлтый - " + LB.TREE["create"].lower()), ("decide", "серый - " + LB.TREE["decide"].lower()),
                     (None, "красный текст - спрос большой, а место хуже 10-го (только с доступом к Вебмастеру и Search Console)")):
        ws.cell(row=i, column=2, value=text)
        if st:
            ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor=FILL[st])
        else:
            ws.cell(row=i, column=2).font = red
        i += 1
    maps = [(n, d) for n, d in _walk(t["root"]) if n.get("fm")]
    if not maps:
        return
    ws = wb.create_sheet("Признаки", 1 if first else None)
    sheet(ws, ["Категория", "Признак", "Значение", dem, "Запросов", "Где есть страница", "Примеры запросов"],
          [36, 20, 34, 11, 9, 30, 80])
    where = {"filter": "у вас (фильтр)", "rival": "у конкурента: ", "create": "нигде, стоит создать", "low": "нигде, спроса мало"}
    for n, _ in sorted(maps, key=lambda x: -x[0]["d"]):
        for a in n["fm"]["axes"]:
            for v in a["values"]:
                ws.append([_clean(n["name"]), a["name"], _clean(v["v"]), v["d"] or "", v["n"] or "",
                           where[v["st"]] + (", ".join(v["rivals"]) if v["st"] == "rival" else ""), _clean(", ".join(v["q"][:4]))])
                ws.cell(row=ws.max_row, column=3).fill = PatternFill("solid", fgColor=FILL[v["st"]])
        for c in n["fm"]["combos"]:
            ws.append([_clean(n["name"]), "Сочетание: " + " + ".join(c["axes"]), _clean(f'{c["a"]} + {c["b"]}'), c["d"] or "",
                       c["n"], "стоит сделать страницу" if c["worth"] else "мало запросов", _clean(", ".join(c["q"][:4]))])
            if c["worth"]:
                ws.cell(row=ws.max_row, column=3).fill = PatternFill("solid", fgColor=FILL["create"])


def _clean(s):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(s or "")).replace(" — ", " - ")


# ---------------------------------------------------------------- страница

def _strip(n):
    """Для страницы: без лишних полей и с короткими ключами."""
    out = {"i": n["id"], "t": n["name"], "u": n["path"], "h": n["h1"], "ti": n["title"], "s": n["st"], "k": n["kind"],
           "d": n["d"], "n": n["n"], "q": n["q"], "py": n["py"], "pg": n["pg"], "p": n["p"], "r": n["rivals"],
           "do": n["todo"], "b": n["bad"], "a": n["also"], "c": [_strip(c) for c in n["children"]]}
    if n["url"]:
        out["l"] = n["url"]
    if n.get("fm"):
        out["fm"] = n["fm"]
    return out


def html(t):
    title = f'Дерево сайта: {t["name"]}'
    data = json.dumps({"root": _strip(t["root"]), "freq": t["freq"], "pos": t["pos"], "ns": t["new"],
                       "st": ST}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    c = t["count"]
    h, cr, fc, d = c.get("have", 0) + c.get("filter", 0), c.get("create", 0), c.get("filter_create", 0), c.get("decide", 0)
    tiles = [(h, LB.tile("have", h, "page"), "have"), (cr, LB.tile("create", cr, "page"), "create"),
             (fc, LB.tile("create", fc, "filter"), "create"), (d, LB.tile("decide", d, "page"), "decide"),
             (t["maps"], "карт признаков", "")]
    if t["new"]:
        tiles[0] = (0, "", "")
    note = ("Спрос - показов в месяц по частотности Яндекса (Вордстат). " if t["freq"] else
            "Спрос оценён по подсказкам Яндекса и Google (чем выше подсказка, тем больше баллов), это не число показов. ")
    note += ("Место в поиске - из Яндекс Вебмастера и Google Search Console. " if t["pos"] else "")
    note += "Своя страница под запросы не обещает места в поиске, но без неё сайт по ним почти не показывается."
    if t["made"]:
        note += f" Запросы собраны {_e(t['made'])}."
    head = ("Каждая строка - страница сайта: главная, разделы, подразделы и фильтры. Нажмите на строку, чтобы увидеть, "
            "что по ней ищут. У категорий есть карта признаков: какие уточнения ищут люди (бренд, назначение, цвет, "
            "размер) и под какие сочетания стоит делать страницы.")
    if t["new"]:
        head = ("Структура будущего сайта по запросам людей и разделам конкурентов. " + head.split(". ", 1)[1])
    body = (f'<div class="w"><h1>{_e(title)}</h1><p class="mut">{head}</p><div class="tiles">'
            + "".join(f'<div class="{k}"><b>{_n(v)}</b>{_e(x)}</div>' for v, x, k in tiles if v) + '</div>'
            + LEGEND + TOOLS + '<div class="lay" data-fs="Дерево сайта"><div id="tree" class="tree" role="tree"></div><aside id="side" class="side">'
            '<p class="mut">Нажмите на страницу в дереве.</p></aside></div>'
            '<section id="mapw" class="mapw" hidden><div class="maphead"><h2 id="mapt"></h2>'
            '<select id="mapsel" aria-label="Категория"></select></div><div id="map" class="map"></div>'
            '<div id="combos"></div></section>'
            f'<p class="mut note">{note}</p></div>')
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head>'
            f'<body>{body}<script>const T={data};</script><script>{JS}</script><script>{FS_JS}</script></body></html>')


LEGEND = ('<div class="legend">' + "".join(f'<span class="lg {k}">{v.lower()}</span>' for k, v in LB.TREE.items())
          + '<span class="lg rival">есть только у конкурента</span><span class="lg bad">спрос большой, место хуже 10-го</span></div>')
TOOLS = ('<div class="tools"><div class="seg" role="tablist"><button data-v="tree" class="on">Дерево</button>'
         '<button data-v="map">Карта признаков</button></div>'
         '<input id="find" type="search" placeholder="Найти страницу или запрос" aria-label="Найти">'
         '<button class="btn" id="open">Раскрыть всё</button><button class="btn" id="shut">Свернуть</button>'
         '<label class="chk"><input type="checkbox" id="flt" checked> фильтры</label>'
         '<label class="chk"><input type="checkbox" id="dec" checked> «решить»</label></div>')

CSS = """:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1d1f;--mut:#6b6b70;--line:#e6e3dc;--acc:#2f5bd3;
--have:#e3f1e7;--have-b:#2e7d4f;--filter:#e5ecfb;--filter-b:#2f5bd3;--create:#fbefc4;--create-b:#b98900;
--decide:#efede8;--decide-b:#8a877f;--rival:#fde3cf;--rival-b:#c96a1e;--low:#f4f2ec;--low-b:#b5b1a7;--bad:#c0392b;--sel:#fff6d6}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--card:#222225;--ink:#ececee;--mut:#a0a0a8;--line:#36363a;--acc:#8aa8ff;
--have:#1f3a2a;--have-b:#6cc08b;--filter:#1f2a45;--filter-b:#8aa8ff;--create:#3d3417;--create-b:#e2bd4f;--decide:#2c2b28;
--decide-b:#a29f96;--rival:#40291a;--rival-b:#f0a060;--low:#262523;--low-b:#77746c;--bad:#ff7b6b;--sel:#3a3520}}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.w{max-width:none;margin:0 auto;padding:24px 16px 48px}h1{font-size:24px;margin:0 0 6px}h2{font-size:18px;margin:0}
.mut{color:var(--mut)}.note{margin-top:24px}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.tiles div{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:6px 14px;color:var(--mut);font-size:13px;border-left:4px solid var(--line)}.tiles b{display:block;font-size:20px;color:var(--ink)}
.tiles .have{border-left-color:var(--have-b)}.tiles .create{border-left-color:var(--create-b)}.tiles .decide{border-left-color:var(--decide-b)}
.legend{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 12px}.lg{font-size:12px;border-radius:20px;padding:1px 10px;border:1px solid}
.lg.have{background:var(--have);border-color:var(--have-b)}.lg.filter{background:var(--filter);border-color:var(--filter-b)}
.lg.create{background:var(--create);border-color:var(--create-b)}.lg.decide{background:var(--decide);border-color:var(--decide-b)}
.lg.rival{background:var(--rival);border-color:var(--rival-b)}.lg.bad{color:var(--bad);border-color:var(--bad);font-weight:600}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}.seg button{border:0;background:var(--card);
color:var(--ink);padding:6px 12px;cursor:pointer;font:inherit}.seg button.on{background:var(--acc);color:#fff}
#find{flex:1;min-width:160px;max-width:360px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit}
.chk{color:var(--mut);font-size:13px;display:flex;gap:4px;align-items:center}
.lay{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:14px;align-items:start}
.tree{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.8fr) 70px 54px 54px;gap:8px;align-items:center;padding:4px 10px 4px 0;
border-bottom:1px solid var(--line);cursor:pointer}.row:hover{background:var(--sel)}.row.on{background:var(--sel);outline:2px solid var(--acc);outline-offset:-2px}
.row.hd{cursor:default;font-size:12px;color:var(--mut);background:var(--card);position:sticky;top:0;z-index:1}.row.hd:hover{background:var(--card)}
.nm{display:flex;align-items:center;gap:6px;min-width:0}.nm span.t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.car{width:18px;flex:none;text-align:center;color:var(--mut);font-size:11px;user-select:none}
.dot{width:12px;height:12px;border-radius:3px;flex:none;border:1px solid}
.s-have .dot{background:var(--have);border-color:var(--have-b)}.s-filter .dot{background:var(--filter);border-color:var(--filter-b);border-radius:50%}
.s-create .dot{background:var(--create);border-color:var(--create-b)}.s-decide .dot{background:var(--decide);border-color:var(--decide-b)}
.s-low .dot{background:var(--low);border-color:var(--low-b);border-radius:50%}.s-rival .dot{background:var(--rival);border-color:var(--rival-b)}
.s-create>.nm .t{font-style:normal}.s-low,.s-decide{color:var(--mut)}
.row.b .t,.row.b .num{color:var(--bad);font-weight:600}.row.b .t::after{content:" !";}
.nopos .row{grid-template-columns:minmax(0,1fr) minmax(0,.8fr) 70px}.nopos .row>div:nth-child(n+4){display:none}
.ur{font-family:Consolas,monospace;font-size:12px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums}.fm{font-size:11px;color:var(--acc);border:1px solid var(--acc);border-radius:10px;padding:0 6px;flex:none}
.side{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;position:sticky;top:10px;max-height:calc(100vh - 20px);overflow:auto}
.side h3{margin:0 0 4px;font-size:16px}.side .ur{white-space:normal;word-break:break-all}.chip{display:inline-block;font-size:12px;border-radius:20px;padding:1px 9px;border:1px solid;margin:4px 0}
.chip.have{background:var(--have);border-color:var(--have-b)}.chip.filter{background:var(--filter);border-color:var(--filter-b)}
.chip.create{background:var(--create);border-color:var(--create-b)}.chip.decide,.chip.low{background:var(--decide);border-color:var(--decide-b)}
.chip.rival{background:var(--rival);border-color:var(--rival-b)}.kv{margin:6px 0;font-size:13px}.kv b{font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:3px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:400;font-size:12px}td.num,th.num{text-align:right}
.mapw{margin-top:4px}.maphead{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
#mapsel{padding:6px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;max-width:100%}
.map{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:28px 60px;align-items:center;
background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px 16px;overflow:hidden}
.map svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.col{display:flex;flex-direction:column;gap:18px;position:relative;z-index:1}.col.l{align-items:flex-end}
.ctr{position:relative;z-index:1;background:var(--acc);color:#fff;border-radius:12px;padding:12px 18px;font-weight:600;font-size:16px;text-align:center;max-width:240px}
.ctr small{display:block;font-weight:400;font-size:12px;opacity:.85}
.axis{display:flex;flex-direction:column;gap:4px}.col.l .axis{align-items:flex-end}
.axn{font-weight:600;border:2px solid var(--acc);border-radius:10px;padding:3px 10px;background:var(--card);align-self:flex-start}.col.l .axn{align-self:flex-end}
.vals{display:flex;flex-wrap:wrap;gap:4px;max-width:420px}.col.l .vals{justify-content:flex-end}
.v{font-size:12px;border-radius:14px;padding:1px 9px;border:1px solid;cursor:default;white-space:nowrap}
.v.filter{background:var(--filter);border-color:var(--filter-b)}.v.rival{background:var(--rival);border-color:var(--rival-b)}
.v.create{background:var(--create);border-color:var(--create-b)}.v.low{background:var(--low);border-color:var(--low-b);color:var(--mut)}
.v i{font-style:normal;color:var(--mut);margin-left:4px}
#combos{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.worth{color:var(--have-b);font-weight:600}
@media (max-width:900px){.lay{grid-template-columns:1fr}.side{position:static;max-height:none}
.row{grid-template-columns:minmax(0,1fr) 64px 46px 46px}.row .ur{display:none}.nopos .row{grid-template-columns:minmax(0,1fr) 64px}
.map{grid-template-columns:1fr;gap:16px}.col.l{align-items:stretch}.col.l .axis,.col.l .vals{align-items:flex-start;justify-content:flex-start}.col.l .axn{align-self:flex-start}.map svg{display:none}.ctr{max-width:none;order:-1}}
@media print{.tools,.side{display:none}.lay{grid-template-columns:1fr}}"""

JS = r"""
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = n => n ? String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') : '';
const pos = x => x ? String(x).replace('.', ',') : '';
const ALL = []; const BY = {}; const PAR = {};
(function index(n, p){ ALL.push(n); BY[n.i] = n; if (p) PAR[n.i] = p; n.c.forEach(c => index(c, n)); })(T.root, null);
const open = new Set([T.root.i]); T.root.c.forEach(c => { if (c.k !== 'group') open.add(c.i); });
let sel = null, q = '';
const DEM = T.freq ? 'Спрос/мес' : 'Спрос';
// без частотности спрос - баллы по подсказкам, а не показы: показываем уровнем (верхняя треть страниц - высокий)
const DS = ALL.map(n => n.d).filter(Boolean).sort((a, b) => b - a);
const HI = DS[Math.floor(DS.length / 3)] || 0, MID = DS[Math.floor(DS.length * 2 / 3)] || 0;
const dem = d => !d ? '' : T.freq ? num(d) : d >= HI ? 'высокий' : d >= MID ? 'средний' : 'низкий';
function visible(n){
  if (!$('flt').checked && n.k === 'filter') return false;
  if (!$('dec').checked && (n.k === 'group' || n.s === 'decide')) return false;
  return true;
}
function match(n){ if (!q) return true;
  return (n.t + ' ' + n.u + ' ' + n.h).toLowerCase().includes(q) || n.q.some(r => r[0].includes(q)); }
function hit(n){ return match(n) || n.c.some(hit); }
function rowHtml(n, depth){
  const kids = n.c.filter(visible);
  const car = kids.length ? (open.has(n.i) || q ? '▾' : '▸') : '';
  const y = n.py || (!n.pg && n.p), g = n.pg;
  return `<div class="row s-${n.s}${n.b ? ' b' : ''}${sel === n.i ? ' on' : ''}" data-i="${n.i}" role="treeitem" aria-level="${depth + 1}"${kids.length ? ` aria-expanded="${open.has(n.i) || !!q}"` : ''}>
<div class="nm" style="padding-left:${6 + depth * 18}px"><span class="car" data-t="${n.i}">${car}</span><span class="dot"></span><span class="t">${esc(n.t)}</span>${n.fm ? '<span class="fm" title="Есть карта признаков">признаки</span>' : ''}</div>
<div class="ur">${esc(n.u)}</div><div class="num">${dem(n.d)}</div><div class="num">${pos(y)}</div><div class="num">${pos(g)}</div></div>`;
}
function draw(){
  const out = [`<div class="row hd"><div style="padding-left:30px">Страница</div><div class="ur">Адрес</div><div class="num"${T.freq ? '' : ' title="Примерно, по месту в подсказках Яндекса и Google: это не число показов"'}>${DEM}</div><div class="num">${T.pos ? 'Яндекс' : ''}</div><div class="num">${T.pos ? 'Google' : ''}</div></div>`];
  (function go(n, d){
    if (!visible(n) || (q && !hit(n))) return;
    out.push(rowHtml(n, d));
    if (open.has(n.i) || q) n.c.forEach(c => go(c, d + 1));
  })(T.root, 0);
  $('tree').innerHTML = out.join('');
  $('tree').classList.toggle('nopos', !T.pos);
}
function qtable(rows){
  if (!rows.length) return '<p class="mut">Запросов под эту страницу не нашлось.</p>';
  const hasPos = rows.some(r => r[2] || r[3] || r[4]);
  return `<table><tr><th>Что ищут</th><th class="num">${DEM}</th>${hasPos ? '<th class="num">Я</th><th class="num">G</th>' : ''}</tr>`
    + rows.map(r => `<tr><td>${esc(r[0])}</td><td class="num">${num(r[1])}</td>${hasPos ? `<td class="num">${pos(r[2] || (!r[3] && r[4]))}</td><td class="num">${pos(r[3])}</td>` : ''}</tr>`).join('') + '</table>';
}
function side(n){
  const path = []; for (let x = PAR[n.i]; x; x = PAR[x.i]) path.unshift(x.t);
  const st = T.st[n.s] || '';
  const y = n.py || (!n.pg && n.p);
  $('side').innerHTML = `<div class="mut" style="font-size:12px">${esc(path.join(' › '))}</div><h3>${esc(n.t)}</h3>
<span class="chip ${n.s}">${esc(st)}</span>${n.b ? ' <span class="chip" style="color:var(--bad);border-color:var(--bad)">спрос большой, место хуже 10-го</span>' : ''}
${n.do && n.do !== st ? `<div class="kv">${esc(n.do)}</div>` : ''}
${n.u ? `<div class="kv">Адрес: ${n.l && !T.ns ? `<a class="ur" href="${esc(n.l)}" target="_blank" rel="noopener">${esc(n.u)}</a>` : `<span class="ur">${esc(n.u)}</span>`}</div>` : ''}
${n.h ? `<div class="kv">H1: <b>${esc(n.h)}</b></div>` : ''}${n.ti ? `<div class="kv">Title: ${esc(n.ti)}</div>` : ''}
${n.d ? `<div class="kv">${T.freq ? 'Спрос в месяц' : 'Спрос (по подсказкам, примерно)'}: <b>${dem(n.d)}</b>${n.n ? `, запросов ${num(n.n)}` : ''}</div>` : ''}
${n.py || n.pg ? `<div class="kv">Среднее место: ${n.py ? `Яндекс <b>${pos(n.py)}</b>` : ''}${n.py && n.pg ? ', ' : ''}${n.pg ? `Google <b>${pos(n.pg)}</b>` : ''}</div>`
  : n.p ? `<div class="kv">Среднее место в поиске: <b>${pos(n.p)}</b> (лучшее из Яндекса и Google)</div>` : ''}
${n.r.length ? `<div class="kv">Есть у конкурентов: ${esc(n.r.join(', '))}</div>` : ''}
${n.a.length ? `<div class="kv mut">Сюда же: ${esc(n.a.join(', '))}</div>` : ''}
${n.fm ? `<p><button class="btn" id="tomap">Карта признаков</button></p>` : ''}${n.k === 'group' ? '' : qtable(n.q)}`;
  if (n.fm) $('tomap').onclick = () => { tab('map'); showMap(n.i); };
}
$('tree').addEventListener('click', e => {
  const r = e.target.closest('.row'); if (!r || r.classList.contains('hd')) return;
  const n = BY[r.dataset.i];
  if (e.target.dataset.t !== undefined || sel === n.i) { open.has(n.i) ? open.delete(n.i) : open.add(n.i); }
  sel = n.i; side(n); draw();
});
$('find').addEventListener('input', e => { q = e.target.value.trim().toLowerCase(); draw(); });
$('open').onclick = () => { ALL.forEach(n => open.add(n.i)); draw(); };
$('shut').onclick = () => { open.clear(); open.add(T.root.i); draw(); };
$('flt').onchange = draw; $('dec').onchange = draw;
// ---- карта признаков
const MAPS = ALL.filter(n => n.fm).sort((a, b) => b.d - a.d);
function tab(v){
  document.querySelectorAll('.seg button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  document.querySelector('.lay').hidden = v !== 'tree'; $('mapw').hidden = v !== 'map';
  ['find', 'open', 'shut'].forEach(id => $(id).hidden = v !== 'tree');
  document.querySelectorAll('.chk').forEach(x => x.hidden = v !== 'tree');
  if (v === 'map' && !$('map').innerHTML) showMap(MAPS.length ? MAPS[0].i : null);
}
document.querySelectorAll('.seg button').forEach(b => b.onclick = () => tab(b.dataset.v));
$('mapsel').innerHTML = MAPS.map(n => `<option value="${n.i}">${esc(n.t)}${n.d ? ' · ' + (T.freq ? num(n.d) : 'спрос ' + dem(n.d)) : ''}</option>`).join('');
$('mapsel').onchange = e => showMap(+e.target.value);
function vtitle(v){
  const w = v.st === 'filter' ? 'страница-фильтр есть'
    : v.st === 'rival' ? 'есть у ' + v.rivals.join(', ') : v.st === 'create' ? 'нигде нет, стоит создать' : 'нигде нет, спроса мало';
  return `${v.v}: ${w}${v.n ? `, запросов ${v.n}` : ''}${v.q.length ? '\n' + v.q.join('\n') : ''}`;
}
function showMap(i){
  if (i == null){ $('mapt').textContent = 'Карт признаков нет'; $('map').innerHTML = '<p class="mut">Уточнений в запросах слишком мало.</p>'; return; }
  const n = BY[i]; $('mapsel').value = i;
  $('mapt').textContent = 'Карта признаков: ' + n.t;
  const ax = n.fm.axes, L = [], R = [];
  ax.forEach((a, k) => (k % 2 ? L : R).push(a));
  const axHtml = a => `<div class="axis"><span class="axn">${esc(a.name)}</span><div class="vals">`
    + a.values.map(v => `<span class="v ${v.st}" title="${esc(vtitle(v))}">${esc(v.v)}${v.d ? `<i>${num(v.d)}</i>` : ''}</span>`).join('')
    + (a.more ? `<span class="v low">и ещё ${a.more}</span>` : '') + '</div></div>';
  $('map').innerHTML = `<svg aria-hidden="true"></svg><div class="col l">${L.map(axHtml).join('')}</div>
<div class="ctr">${esc(n.t)}<small>${n.d ? 'спрос ' + dem(n.d) : ''}</small></div><div class="col r">${R.map(axHtml).join('')}</div>`;
  lines();
  const cs = n.fm.combos;
  $('combos').innerHTML = '<h2 style="margin-bottom:6px">Сочетания признаков</h2><p class="mut" style="margin-top:0">Какие уточнения ищут вместе. '
    + 'Страницу под сочетание стоит делать, только если его ищут: остальные сочетания - фильтр в каталоге без своей страницы.</p>'
    + (cs.length ? `<table><tr><th>Сочетание</th><th>Пример запроса</th><th class="num">${DEM}</th><th class="num">Запросов</th><th>Страница</th></tr>`
      + cs.map(c => `<tr><td>${esc(c.a)} + ${esc(c.b)} <span class="mut">(${esc(c.axes.join(' + ').toLowerCase())})</span></td><td>${esc(c.name)}</td><td class="num">${num(c.d)}</td><td class="num">${c.n}</td><td>${c.worth ? '<span class="worth">стоит сделать</span>' : '<span class="mut">мало запросов</span>'}</td></tr>`).join('') + '</table>'
      : '<p class="mut">Сочетаний, которые ищут хотя бы дважды, нет.</p>');
}
function lines(){
  const m = $('map'), svg = m.querySelector('svg'); if (!svg) return;
  const box = m.getBoundingClientRect(), c = m.querySelector('.ctr').getBoundingClientRect();
  const cx = c.left + c.width / 2 - box.left, cy = c.top + c.height / 2 - box.top;
  svg.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
  svg.innerHTML = [...m.querySelectorAll('.axn')].map(a => {
    const r = a.getBoundingClientRect(), left = a.closest('.col').classList.contains('l');
    const x = (left ? r.right : r.left) - box.left, y = r.top + r.height / 2 - box.top;
    const sx = left ? c.left - box.left : c.right - box.left, mx = (sx + x) / 2;
    return `<path d="M${sx},${cy} C${mx},${cy} ${mx},${y} ${x},${y}" fill="none" stroke="var(--acc)" stroke-width="2" opacity=".6"/>`;
  }).join('');
}
window.addEventListener('resize', () => { if (!$('mapw').hidden) lines(); });
draw(); sel = T.root.i; side(T.root); draw();
"""


def write(folder, data, dicts=None):
    """«дерево сайта.html» в папке проверки и копия в «для клиента». Возвращает (путь, дерево) или ("", None)."""
    t = build(data, folder, dicts)
    if not t["root"]["children"]:
        return "", t
    text = html(t)
    path = os.path.join(folder, FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    out = os.path.join(folder, "для клиента")
    os.makedirs(out, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|]+', " ", t["name"]).strip() or "сайт"
    with open(os.path.join(out, f"Дерево сайта - {name}.html"), "w", encoding="utf-8") as f:
        f.write(text)
    return path, t
