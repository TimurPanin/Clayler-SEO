"""Решения по семантике, которые человек принимает на странице «Семантика», и то, что из них следует.

- Смешанные группы: в одной группе запросы с разными желаниями людей («онлайн» и «офлайн», «для детей» и
  «для взрослых», «купить» и «своими руками»). Одна страница не закроет оба, программа предлагает разделить группу.
  «Разделить» или «Оставить как есть» запоминается: при следующем сборе группа делится так же.
- Страницы, которые мешают друг другу (pages.cannibal): решение по каждому случаю и готовая задача разработчику.
- Галочки «сделано» у задач и итог «Проверить снова» (recheck.py).
Всё хранится по сайту: папка «данные/решения семантики», файл на сайт. Между запусками не пропадает,
новый сбор семантики решения не стирает. Решения накладываются на семантика.json при выдаче (apply), сам файл
семантики не меняется."""
import copy
import os
import re
import sqlite3
import threading
import time

from .stem import stem
from .words import CITY_WORDS
from .. import jsonfile, paths

DIR = os.environ.get("CLAYLER_DECISIONS_DIR") or paths.data("решения семантики")
_lock = threading.Lock()


def site_key(host):
    host = (host or "").lower().strip()
    return host[4:] if host.startswith("www.") else host


def site_file(host, suffix=""):
    """Файл сайта в папке «решения семантики»: «site.ru.json», «site.ru - маски.json» (suffix « - маски»).
    Папка - DIR на момент вызова (автотесты подменяют её)."""
    return os.path.join(DIR, re.sub(r"[^a-z0-9а-я.\-]", "_", site_key(host)) + suffix + ".json")


def save_site_file(host, suffix, data, **dump_args):
    """Записать файл сайта (папку создать, если её нет); dump_args - как у jsonfile.save."""
    os.makedirs(DIR, exist_ok=True)
    jsonfile.save(site_file(host, suffix), data, **dump_args)


def _path(host):
    return site_file(host)


def load(host):
    d = jsonfile.load(_path(host))
    for k in ("mixed", "cannibal", "done", "landing", "junk"):
        d.setdefault(k, {})
    d.setdefault("recheck", None)
    return d


def update(host, fn):
    """Прочитать, поменять (fn(d)), записать — под замком, чтобы два нажатия подряд не потеряли друг друга."""
    with _lock:
        d = load(host)
        fn(d)
        save_site_file(host, "", d, indent=1)
        return d


def now():
    return time.strftime("%d.%m.%Y %H:%M")


def _cap(s):
    return s[:1].upper() + s[1:]


def _short(url):
    """Адрес без https://сайта — так короче в задачах и на странице."""
    return re.sub(r"^https?://[^/]+", "", url or "") or "/"


# ---------- смешанные группы ----------

# Пары противоположных желаний. ra/rb — слова в запросе, ua/ub — в адресе страницы (латиницей).
AXES = [
    {"id": "format", "a": "онлайн", "b": "офлайн", "why": "одним нужно онлайн, из дома, другим вживую, в классе или в офисе",
     "ra": r"онлайн|он-лайн|online|дистанцион|удаленн|по скайпу|skype|zoom|по видеосвязи",
     "rb": r"офлайн|оффлайн|offline|\bочн(?:о|ое|ые|ый|ая|ого|ых|ую)\b|в классе|в аудитори",
     "ua": r"online|onlajn|onlayn|onlain|distan", "ub": r"offline|oflajn|oflayn|ochn"},
    {"id": "age", "a": "для детей", "b": "для взрослых", "why": "одним нужно для ребёнка, другим для себя",
     "ra": r"\bдет(?:и|ей|ям|ьми|ях|ский|ская|ские|ское|ских|ского|скому|ском|скую|сад)\b|ребен|малыш|школьник|подрост|дошкол|младш",
     "rb": r"взросл",
     "ua": r"det(?:i|ej|ey|yam|sk)|kids|child|shkol|podrost|doshkol", "ub": r"vzrosl|adult"},
    {"id": "diy", "a": "купить", "b": "своими руками", "why": "одни хотят купить или заказать, другие сделать сами",
     "ra": r"купить|\bцен[аы]\b|стоимост|заказать|недорог|в наличии",
     "rb": r"своими руками|как сделать|самому|самостоятельно|в домашних условиях|чертеж",
     "ua": r"katalog|catalog|shop|buy|product|tovar", "ub": r"blog|stat[ia]|article|kak-|sovety"},
    {"id": "rent", "a": "купить", "b": "аренда", "why": "одни хотят купить, другие взять на время",
     "ra": r"купить|продаж|в собственность", "rb": r"аренд|прокат|напрокат|\bснять\b|посуточн",
     "ua": r"kupit|prodazh|buy|sale", "ub": r"arend|prokat|rent"},
    {"id": "gender", "a": "мужское", "b": "женское", "why": "одним нужно мужское, другим женское",
     "ra": r"мужск|для мужчин|\bмужчин", "rb": r"женск|для женщин|\bженщин",
     "ua": r"muzh|men\b|male", "ub": r"zhensk|women|female"},
    {"id": "opt", "a": "оптом", "b": "в розницу", "why": "одним нужна партия для бизнеса, другим одна вещь для себя",
     "ra": r"оптом|\bопт\b|оптов", "rb": r"в розницу|розниц|поштучно",
     "ua": r"opt\b|optom|wholesale", "ub": r"rozn|retail"},
]
for _ax in AXES:
    for _k in ("ra", "rb", "ua", "ub"):
        _ax[_k] = re.compile(_ax[_k])
AXIS = {a["id"]: a for a in AXES}
MIN_SIDE = 2          # запросов на каждой стороне, чтобы считать группу смешанной
MIN_SHARE = 0.15      # меньшая сторона — не меньше этой доли запросов группы (или название группы про одну из сторон)
CANDIDATES = 6
NOT_LANDING = re.compile(r"/(news|novosti|blog|stati|statyi|articles?|press|sobytiya|events?)(/|$)")  # новости и статьи
WORD_STOP = {"для", "как", "что", "где", "или", "все", "при", "без", "это", "лучшие", "лучший",
             "цена", "цены", "купить", "отзывы", "недорого"} | CITY_WORDS   # любой город, а не только Москва


def _n(s):
    return (s or "").lower().replace("ё", "е")


def _side(text, ax, url=""):
    """«a», «b» или «» (нет признака или есть оба)."""
    t = _n(text)
    a = bool(ax["ra"].search(t) or (url and ax["ua"].search(url.lower())))
    b = bool(ax["rb"].search(t) or (url and ax["ub"].search(url.lower())))
    return "a" if a and not b else "b" if b and not a else ""


def _rows_sides(g, ax):
    out = {"a": [], "b": [], "": []}
    for r in g.get("q") or []:
        out[_side(r[0], ax)].append(r)
    return out


def _best(rows):
    """Название части группы: короткий частый запрос."""
    good = [r for r in rows if not r[7]] or rows
    top = max(r[3] for r in good)
    return min((r for r in good if r[3] >= top / 3), key=lambda r: (len(r[0].split()), -r[3], len(r[0])))[0]


def detect(g, decided=()):
    """Смешана ли группа: лучшая пара желаний (у которой меньшая сторона больше всего). decided — уже решённые
    пары для этой группы, их не предлагаем снова."""
    if g.get("kind") == "manual" or not g.get("q"):
        return None
    total = sum(1 for r in g["q"] if not r[7]) or len(g["q"])
    best = None
    for ax in AXES:
        if ax["id"] in decided:
            continue
        s = _rows_sides(g, ax)
        na = sum(1 for r in s["a"] if not r[7])
        nb = sum(1 for r in s["b"] if not r[7])
        m = min(na, nb)
        named = bool(_side(g["name"], ax))   # «Офлайн-курсы…», а запросы почти все «онлайн»
        if m >= MIN_SIDE and (m >= MIN_SHARE * total or named) and (best is None or m > best[0]):
            best = (m, ax, s)
    return best and (best[1], best[2])


def _page_side(g, ax):
    a = (g.get("a") or {}).get("now") or {}
    return _side(" ".join((a.get("title") or "", a.get("h1") or "")), ax, _short(g.get("page") or ""))


def _plan(g, ax, s):
    """Как делить: какая сторона остаётся со страницей группы (keep), какая уходит (other)."""
    ps = _page_side(g, ax) if g.get("page") else ""
    if ps:
        keep = ps
    else:
        keep = "a" if len(s["a"]) >= len(s["b"]) else "b"
    return keep, "b" if keep == "a" else "a", bool(ps)


def _core_stems(text, ax):
    t = ax["ra"].sub(" ", ax["rb"].sub(" ", _n(text)))
    return {stem(w) for w in re.findall(r"[а-яa-z0-9]+", t) if len(w) >= 3 and w not in WORD_STOP}


_pages_cache = {}


def _pages(folder):
    """Страницы проверки один раз на папку (пока crawl.db не менялся): страница «Семантика» спрашивает часто."""
    try:
        mt = os.path.getmtime(os.path.join(folder, "crawl.db"))
    except OSError:
        mt = 0
    hit = _pages_cache.get(folder)
    if hit and hit[0] == mt:
        return hit[1]
    if len(_pages_cache) > 3:
        _pages_cache.clear()
    p = _Pages(folder)
    _pages_cache[folder] = (mt, p)
    return p


class _Pages:
    """Страницы сайта из проверки (адрес, title, H1, глубина) — для «Привязать к странице»."""
    def __init__(self, folder):
        self.rows = []
        try:
            db = sqlite3.connect(os.path.join(folder, "crawl.db"))
            self.rows = [(u, _n((t or "") + " " + (h or "")), d if d is not None else 9) for u, t, h, d in db.execute(
                "SELECT p.url, p.title, p.h1, u.depth FROM pages p LEFT JOIN urls u ON u.url = p.url "
                "WHERE p.status = 200 AND p.indexable = 1 AND p.content_type LIKE 'text/html%'")]
            db.close()
        except sqlite3.Error:
            pass
        self._stems = {}

    def stems(self, i):
        if i not in self._stems:
            self._stems[i] = {stem(w) for w in re.findall(r"[а-яa-z0-9]+", self.rows[i][1]) if len(w) >= 3}
        return self._stems[i]

    def compare(self, urls, core, owners, me):
        """Сравнение страниц для «Похоже, не та страница» (идея из разговора с ChatGPT, 29.10.2026): сколько слов
        группы в title и H1, про что страница по признакам (онлайн/офлайн, детям/взрослым…), не занята ли другой
        группой. → [{url, title, words, side, busy}]"""
        at = {u: i for i, (u, _t, _d) in enumerate(self.rows)}
        out = []
        for u in urls:
            i = at.get(u)
            if i is None:
                continue
            text = self.rows[i][1]
            side = next((ax[s] for ax in AXES for s in [_side(text, ax, _short(u))] if s), "")
            busy = owners.get(u, "")
            out.append({"url": u, "title": text[:90], "words": f"{len(core & self.stems(i))} из {len(core)}" if core else "",
                        "side": side, "busy": busy if busy != me else ""})
        return out

    def candidates(self, core, ax, side, skip, first=()):
        """Страницы под часть группы: со словами группы и без признака противоположной стороны."""
        other = "b" if side == "a" else "a"
        out = []
        need = max(1, len(core) - 1)
        for i, (u, text, depth) in enumerate(self.rows):
            if u in skip or not core or NOT_LANDING.search(_short(u).lower()):
                continue
            hit = len(core & self.stems(i))
            if hit < need:
                continue
            ps = _side(text, ax, _short(u))
            if ps == other:
                continue
            out.append((u in first, ps == side, hit, -depth, -len(u), u))
        top = max((x[2] for x in out), default=0)
        out = [x for x in out if x[2] == top or x[0]]   # есть страницы со всеми словами группы — только они
        out.sort(reverse=True)
        return [x[-1] for x in out[:CANDIDATES]]


def _mixed_info(g, ax, s, pages, first):
    keep, other, fits = _plan(g, ax, s)
    label = {"a": ax["a"], "b": ax["b"]}
    keep_rows, other_rows = s[keep] + s[""], s[other]
    core = _core_stems(_best(other_rows), ax) | _core_stems(g["name"], ax)
    return {
        "axis": ax["id"], "a": ax["a"], "b": ax["b"],
        "title": f"В группе смешаны «{ax['a']}» и «{ax['b']}»",
        "text": f"Люди ищут разное: {ax['why']}. Одна страница не закроет оба запроса. Предлагаем разделить группу.",
        "parts": [
            {"side": keep, "label": _cap(label[keep]), "n": len(keep_rows), "neutral": len(s[""]),
             "name": _part_name(g, ax, keep, keep_rows),
             "sample": [r[0] for r in s[keep][:5]], "page": g.get("page") or "", "fits": fits},
            {"side": other, "label": _cap(label[other]), "n": len(other_rows), "name": _cap(_best(other_rows)),
             "sample": [r[0] for r in other_rows[:5]], "page": "",
             "candidates": pages.candidates(core, ax, other, {g.get("page")}, first) if pages else []}]}


def _part_name(g, ax, side, rows):
    """Часть, что остаётся со страницей, сохраняет имя группы, если оно не про другую сторону."""
    other = "b" if side == "a" else "a"
    if _side(g["name"], ax) == other:
        return _cap(_best(rows))
    return g["name"]


def _score(rows):
    return sum(sorted((r[3] for r in rows if not r[7]), reverse=True)[:10])


def _intents(rows):
    info = sum(1 for r in rows if r[2] == "Информация" and not r[7])
    comm = sum(1 for r in rows if r[2] in ("Покупка", "Услуга") and not r[7])
    pt = "both" if info >= 3 and comm >= 3 and info * 3 >= comm else "article" if info >= 3 and info >= 1.5 * comm else "page"
    return pt, info, comm


def _split(g, ax, s, d):
    """Разделить группу по решению d = {page: адрес или "new"}: две группы вместо одной."""
    keep, other, _fits = _plan(g, ax, s)
    keep_rows, other_rows = s[keep] + s[""], s[other]
    keep_set = {r[0] for r in keep_rows}
    a = copy.deepcopy(g)
    a["q"] = [r for r in g["q"] if r[0] in keep_set]
    a["name"] = _part_name(g, ax, keep, keep_rows)
    a["score"] = _score(a["q"])
    a["ptype"], a["info"], a["comm"] = _intents(a["q"])
    a["split"] = {"from": g["name"], "axis": ax["id"], "side": ax[keep], "at": d.get("at", "")}
    b_name = _cap(_best(other_rows))
    page = d.get("page") if d.get("page") not in (None, "", "new") else ""
    b = {"name": b_name, "page": page, "near": "" if page else (g.get("page") or g.get("near") or ""),
         "kind": "page" if page else "create",
         "todo": "Продвигать эту страницу" if page else f"Создать страницу: часть группы «{g['name']}» про «{ax[other]}»",
         "score": _score(other_rows), "rivals": [], "products": 0, "f": [], "faq": [],
         "q": other_rows, "split": {"from": g["name"], "axis": ax["id"], "side": ax[other], "at": d.get("at", "")}}
    b["ptype"], b["info"], b["comm"] = _intents(other_rows)
    b["a"] = d.get("audit") if page else {"main": other_rows[0][0] if other_rows else b_name, "problems": [], "new": True,
                                "title": b_name, "h1": b_name, "description": "", "now": {}, "words": ""}
    return [a, b]


def _gkey(name):
    return _n(name).strip()


def apply(data, folder):
    """Наложить решения на семантику (для страницы, Excel, ТЗ и бота). Возвращает новый словарь."""
    if not data:
        return data
    data = copy.deepcopy(data)
    host = data.get("host") or ""
    dec = load(host)
    mixed = dec["mixed"]
    pages = None
    cann_first = {}   # группа → другие её разделы (из «Несколько разделов под одну группу»)
    for c in data.get("cannibal") or []:
        m = re.match(r"Несколько разделов под одну группу «(.+)»$", c.get("why") or "")
        if m:
            cann_first[_gkey(m.group(1))] = [p["url"] for p in c["pages"]]
    # «Убрать в отсеянное»: группы из текста кнопок и меню
    junk = dec["junk"]
    kept_groups, removed = [], []
    for g in data.get("groups") or []:
        (removed if _gkey(g["name"]) in junk else kept_groups).append(g)
    if removed:
        lst = data.setdefault("dropped", {}).setdefault(JUNK_REASON, [])
        for g in removed:
            lst += [r[0] for r in g.get("q") or []]
        data["total"] = max(0, (data.get("total") or 0) - sum(len(g.get("q") or []) for g in removed))
    data["junk_removed"] = [{"name": g["name"], "n": len(g.get("q") or []), "at": junk[_gkey(g["name"])].get("at", "")}
                            for g in removed]
    # «Похоже, не та страница»: страница, выбранная человеком, или «создать новую»
    for g in kept_groups:
        d = dec["landing"].get(_gkey(g["name"]))
        if d and d.get("choice") in ("page", "new"):
            _rebind(g, d)
    out = []
    queue = kept_groups
    guard = 0
    while queue and guard < 5000:
        guard += 1
        g = queue.pop(0)
        dd = mixed.get(_gkey(g["name"])) or {}
        done_split = False
        for axid, d in dd.items():
            if d.get("choice") != "split" or axid not in AXIS or g.get("_split_" + axid):
                continue
            ax = AXIS[axid]
            s = _rows_sides(g, ax)
            if not s["a"] or not s["b"]:
                continue
            parts = _split(g, ax, s, d)
            for p in parts:
                p["_split_" + axid] = True
            queue[:0] = parts   # части тоже проверяются (у части может быть своя смесь)
            done_split = True
            break
        if done_split:
            continue
        out.append(g)
    groups = [{k: v for k, v in g.items() if not k.startswith("_split_")} for g in out]
    for i, g in enumerate(groups):
        dd = mixed.get(_gkey(g["name"])) or {}
        decided = {k for k, d in dd.items() if d.get("choice") in ("split", "keep")}
        if g.get("split"):
            decided.add(g["split"]["axis"])
        found = detect(g, decided)
        if found:
            if pages is None:
                pages = _pages(folder)
            g["mixed"] = _mixed_info(g, found[0], found[1], pages, cann_first.get(_gkey(g["name"]), ()))
        if is_junk(g):
            g["junk"] = True
        else:
            ld = dec["landing"].get(_gkey(g["name"])) or {}
            if not ld:
                why = wrong_page(g)
                if why:
                    if pages is None:
                        pages = _pages(folder)
                    core = _core_stems(g["name"], AXES[0])
                    side = next(((ax, _side(g["name"], ax)) for ax in AXES if _side(g["name"], ax)), None)
                    cands = pages.candidates(core, side[0], side[1], {g.get("page")}) if side else \
                        pages.candidates(core, _NOAXIS, "a", {g.get("page")})
                    owners = {x.get("page"): x["name"] for x in groups if x.get("page")}
                    g["landing"] = {"why": why, "candidates": cands,
                                    "compare": pages.compare([g["page"]] + cands, core, owners, g["name"])}
            elif ld.get("choice") in ("page", "new"):
                g["landing_set"] = {"choice": ld["choice"], "page": ld.get("page") or "", "from": ld.get("from") or "",
                                    "at": ld.get("at", "")}
            elif ld.get("choice") == "keep":
                g["landing_set"] = {"choice": "keep", "at": ld.get("at", "")}
        kept = [k for k, d in dd.items() if d.get("choice") == "keep" and k in AXIS]
        if kept:
            g["mixed_kept"] = [{"axis": k, "title": f"«{AXIS[k]['a']}» и «{AXIS[k]['b']}» оставлены в одной группе"}
                               for k in kept]
    data["groups"] = groups
    _apply_cannibal(data, dec)
    data["decisions"] = {"host": site_key(host), "done": dec["done"], "recheck": dec.get("recheck"),
                         "cannibal": progress(data)}
    return data


# ---------- группы из текста кнопок и меню, «похоже, не та страница» ----------

JUNK_REASON = "текст кнопки или меню"
# название группы — подпись кнопки или служебного раздела, а не то, что ищут клиенты
UI_RX = re.compile(r"^(узнать|подробнее|начать|наш[иаея]?\b|мои\b|ваш[иа]?\b|записаться|запись на|зарегистрир|регистрация|"
                   r"войти|вход\b|оставить|заказать звонок|позвонить|смотреть|посмотреть|читать|показать|перейти|скачать|"
                   r"далее|ещ[её]\b|больше\b|все\b|весь\b|информация об?\b|правила|политика|согласие|сведения|"
                   r"f\.?a\.?q|faq|вопрос|отзыв|контакт|карта сайта|подписаться|назад|главная)")
_NOAXIS = {"id": "", "a": "", "b": "", "ra": re.compile(r"(?!x)x"), "rb": re.compile(r"(?!x)x"),
           "ua": re.compile(r"(?!x)x"), "ub": re.compile(r"(?!x)x")}


def is_junk(g):
    return g.get("kind") != "manual" and bool(UI_RX.search(_n(g["name"]).strip()))


def wrong_page(g):
    """Группа привязана к странице, которая не про неё: в title и H1 нет ни одного слова группы, или страница
    про противоположное («Офлайн-курсы…» → страница про онлайн). Пустая строка — страница подходит."""
    if g.get("kind") != "page" or not g.get("page"):
        return ""
    now = (g.get("a") or {}).get("now") or {}
    text = f"{now.get('title') or ''} {now.get('h1') or ''}"
    if not text.strip():
        return ""
    for ax in AXES:
        gs = _side(g["name"], ax)
        ps = _side(text, ax, _short(g["page"]))
        if gs and ps and gs != ps:
            return f"группа про «{ax[gs]}», а страница про «{ax[ps]}»"
    core = {stem(w) for w in re.findall(r"[а-яa-z0-9]+", _n(g["name"])) if len(w) >= 3 and w not in WORD_STOP}
    pt = {stem(w) for w in re.findall(r"[а-яa-z0-9]+", _n(text))}
    if core and not core & pt:
        return f"в title и H1 страницы нет слов группы, страница про «{(now.get('h1') or now.get('title') or '').strip()[:80]}»"
    return ""


def other_part(g, axis):
    """Вторая часть группы при разделении (та, что уходит от страницы группы): название и строки запросов."""
    ax = AXIS[axis]
    s = _rows_sides(g, ax)
    _keep, other, _fits = _plan(g, ax, s)
    return (_cap(_best(s[other])) if s[other] else g["name"]), s[other]


def page_audit(folder, data, name, rows, url):
    """Замечания к одной странице сайта под группу (тем же pages.audit, что при сборе семантики), по данным
    проверки сайта (crawl.db), без скачивания. Нужны сразу, когда человек выбрал группе страницу вручную."""
    import importlib
    from . import pages as PG, seeds as S
    from .words import city_by_name
    sm = importlib.import_module(__package__)
    try:
        main = S.load(folder)
    except Exception:
        return None
    city = city_by_name(data["city"]) if data.get("city") else None
    city_stems = {s for _n2, forms in sm.City().items for f in forms for s in f}
    Q = {r[0]: {"check": r[7], "extra": r[1], "score": r[3], "intent": r[2]} for r in rows}
    # группа-город («Тула»): без города слов не остаётся, тогда город и есть главное слово
    g = {"name": name, "core": sm.core(sm.norm(name), city_stems) or sm.core(sm.norm(name)), "queries": list(Q),
         "prio": 1, "page": url,
         "rivals": {}}
    if not g["core"] or not Q:
        return None
    try:
        PG.audit(sm, main, [], [g], Q, city, city_stems)
    except Exception:
        return None
    a = g.get("audit")
    if a:
        a["chosen"] = True   # страница выбрана человеком
    return a


def _rebind(g, d):
    """Человек выбрал для группы другую страницу или «создать новую»."""
    old = g.get("page") or ""
    a = g.get("a") or {}
    if d["choice"] == "page" and d.get("page"):
        g["page"], g["kind"], g["todo"] = d["page"], "page", "Продвигать эту страницу (выбрана вручную)"
        # замечания к новой странице посчитаны при сохранении решения (page_audit), старые были к прежней странице
        g["a"] = d.get("audit") or {"main": a.get("main") or g["name"].lower(), "problems": [], "title": "", "h1": "",
                                    "description": "", "now": {}, "words": a.get("words") or "", "rebound": True}
    else:
        g["page"], g["kind"], g["near"] = "", "create", old or g.get("near") or ""
        g["todo"] = "Создать страницу: подходящей на сайте нет"
        g["a"] = {"main": a.get("main") or g["name"].lower(), "problems": [], "new": True, "title": g["name"],
                  "h1": g["name"], "description": "", "now": {}, "words": a.get("words") or ""}


# ---------- страницы, которые мешают друг другу ----------

CHOICES = {
    "main": ("Оставить одну главной", "Остальные ссылаются на неё и не используют её запросы"),
    "merge": ("Склеить", "Перенести текст на главную, со второй 301-переадресация"),
    "split": ("Развести по смыслу", "Например: «для взрослых» и «для детей», «онлайн» и «в классе»"),
    "ok": ("Не проблема", "Скрыть случай, больше не показывать"),
}


def case_key(c):
    return "|".join(sorted(p["url"] for p in c["pages"]))


def case_title(c):
    m = re.search(r"«(.+)»", c.get("why") or "")
    return _cap(m.group(1)) if m else (c.get("why") or "Случай")


def _apply_cannibal(data, dec):
    page_group = {}
    for g in data["groups"]:
        if g.get("page"):
            page_group.setdefault(g["page"], g)
    split_pairs = {}  # группа делилась: её страница и страница второй части больше не мешают друг другу
    for g in data["groups"]:
        if g.get("split") and g.get("page"):
            split_pairs.setdefault(_gkey(g["split"]["from"]), set()).add(g["page"])
    for c in data.get("cannibal") or []:
        c["key"] = case_key(c)
        c["title"] = case_title(c)
        for p in c["pages"]:
            g = page_group.get(p["url"])
            if g:
                p["group"] = g["name"]
        d = dec["cannibal"].get(c["key"])
        c.pop("decision", None)
        if d and d.get("choice") in CHOICES:
            c["decision"] = d["choice"]
            c["decided_at"] = d.get("at", "")
            if d.get("main") in {p["url"] for p in c["pages"]}:
                c["main"] = d["main"]
        else:
            m = re.match(r"Несколько разделов под одну группу «(.+)»$", c.get("why") or "")
            urls = {p["url"] for p in c["pages"]}
            if m and len(urls & split_pairs.get(_gkey(m.group(1)), set())) >= 2:
                c["decision"], c["auto"] = "split", f"Группу «{m.group(1)}» разделили, у частей свои страницы"
        c["task"] = task_text(c, data) if c.get("decision") else ""


def progress(data):
    cs = data.get("cannibal") or []
    return {"decided": sum(1 for c in cs if c.get("decision")), "total": len(cs),
            "hidden": sum(1 for c in cs if c.get("decision") == "ok")}


def task_text(c, data):
    """Готовая задача разработчику по решению (без длинных тире: текст уходит в Word и Telegram как есть)."""
    ch = c.get("decision")
    main = c["main"]
    others = [p for p in c["pages"] if p["url"] != main]
    o = ", ".join(_short(p["url"]) for p in others)
    title = c.get("title") or case_title(c)
    if ch == "main":
        mp = next((p for p in c["pages"] if p["url"] == main), {})
        lines = [f"Главная страница по теме «{title}»: {main}."]
        lines.append(f"На страницах {o} убрать эти запросы из Title и H1 и поставить с них ссылку на главную "
                     f"({_short(main)}) с текстом по теме.")
        same = [p for p in others if _n(p.get("title")) == _n(mp.get("title")) or _n(p.get("h1")) == _n(mp.get("h1"))]
        for p in same:
            lines.append(f"Сейчас у {_short(p['url'])} title «{p.get('title') or 'нет'}», H1 «{p.get('h1') or 'нет'}»: "
                         "дать свои, про то, чем эта страница отличается.")
        return "\n".join(lines)
    if ch == "merge":
        return (f"Перенести полезный текст со страниц {o} на {main}. Затем настроить с них 301-переадресацию на "
                f"{main}, убрать их из меню и из sitemap.xml, а ссылки внутри сайта поменять на {_short(main)}.")
    if ch == "split":
        if c.get("auto"):
            head = c["auto"] + ". "
        else:
            head = ""
        by_group = {}
        for g in data["groups"]:
            if g.get("page"):
                by_group.setdefault(g["page"], g)
        lines = [head + "Развести страницы по смыслу: у каждой свой Title, H1 и текст под свои запросы."]
        names = [by_group[p["url"]]["name"] for p in c["pages"] if p["url"] in by_group]
        if len(set(names)) == len(c["pages"]):
            for p in c["pages"]:
                g = by_group[p["url"]]
                qs = [r[0] for r in g.get("q") or [] if not r[7]][:4]
                lines.append(f"{_short(p['url'])}: про «{g['name']}»" + (", запросы: " + ", ".join(f"«{q}»" for q in qs) if qs else "") + ".")
        else:
            g = by_group.get(main)
            mx = (g or {}).get("mixed")
            by_axis = None   # страницы уже различаются по смыслу (адрес, title, H1): «онлайн» и «офлайн»
            for ax in AXES:
                sides = [_side(f"{p.get('title') or ''} {p.get('h1') or ''}", ax, _short(p["url"])) for p in c["pages"]]
                if all(sides) and len(set(sides)) > 1:
                    by_axis = (ax, sides)
                    break
            if by_axis:
                ax, sides = by_axis
                lines.append("Страницы уже различаются: " + ", ".join(
                    f"{_short(p['url'])} про «{ax[sd]}»" for p, sd in zip(c["pages"], sides))
                    + ". Пропишите это в Title и H1 каждой, а запросы с «" + ax["a"] + "» и «" + ax["b"]
                    + "» разведите по своим страницам" + (" (на странице группы: «Разделить на две группы»)" if mx else "") + ".")
            elif mx:
                lines.append(f"В группе «{g['name']}» смешаны «{mx['a']}» и «{mx['b']}»: одну страницу отдать под "
                             f"«{mx['a']}», другую под «{mx['b']}».")
            else:
                lines.append("Решите, чем страницы отличаются (например, «для взрослых» и «для детей», «онлайн» и "
                             "«в классе»), и пропишите это в Title и H1 каждой.")
            for p in c["pages"]:
                lines.append(f"Сейчас {_short(p['url'])}: title «{p.get('title') or 'нет'}», H1 «{p.get('h1') or 'нет'}».")
        return "\n".join(lines)
    if ch == "ok":
        return ""
    return ""


def find_case(data, key):
    return next((c for c in data.get("cannibal") or [] if c.get("key") == key), None)
