"""«Запрос → страница» и ТЗ копирайтеру по каждой группе. Считается при выдаче семантики (после решений человека),
поэтому работает и для семантик, собранных раньше:
- land: какая страница сайта под группу и подходит ли она (подходит / доработать / не та / создать / решить);
  для новой страницы - готовый адрес, title и H1;
- tz: объём текста по страницам конкурентов той же группы и подзаголовки H2 из запросов группы."""
import os
import re
import sqlite3
from urllib.parse import urlsplit

from .labels import STATUS as _ST

TR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
      "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
      "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
      "э": "e", "ю": "yu", "я": "ya"}
SLUG_SKIP = {"в", "во", "на", "и", "для", "с", "со", "по", "от", "из", "к", "у", "о", "об", "под", "без", "или",
             "купить", "цена", "цены", "недорого", "отзывы"}
SLUG_WORDS = 5
# объём текста: без данных по конкурентам - ориентир по типу страницы
WORDS_PAGE, WORDS_ARTICLE = 300, 1000
MIN_RIVAL_WORDS = 50     # меньше - у конкурента почти пустая страница, не ориентир
H2_MAX = 6
NOISE = {"самые", "самый", "лучшие", "лучший", "какой", "какие", "купить", "цена", "цены", "отзывы", "недорого",
         "рейтинг", "фото"}
QWORDS = ("как", "что", "какой", "какая", "какие", "почему", "зачем", "сколько", "где", "когда", "чем", "можно", "нужно")

STATUS = {k: v[0] for k, v in _ST.items()}   # названия - в labels.py, одни на окно, отчёты, Excel и бота


def _city_test(city):
    """Слово - город семантики в любой форме («уфа», «уфе», «спб», «питер»): по основе слова. До 24.10.2026 - по
    первым буквам, и город находился в обычных словах: «перила» - Пермь, «санузел» - Санкт-Петербург, «москитная» -
    Москва (слово пропадало из подзаголовков ТЗ и адреса новой страницы)."""
    from .stem import stem
    from .words import CITIES, CITY_ALIASES, canon_city
    name = canon_city(city or "")
    forms = {stem(w) for c in CITIES if name and canon_city(c[0]) == name for x in c[:2]
             for w in re.split(r"[ -]", x.lower().replace("ё", "е")) if len(w) > 2}
    forms |= {stem(a) for a, n in CITY_ALIASES.items() if n == name}
    return (lambda w: stem(w.lower().replace("ё", "е")) in forms), (name or "").lower()


def slug(text, city=None):
    """«Газовые котлы для дома в Уфе» → «gazovye-kotly-dlya-doma»: латиницей, без города и предлогов в конце."""
    is_city, _ = _city_test(city)
    words = [w for w in re.findall(r"[a-zа-яё0-9]+", (text or "").lower()) if not is_city(w)]
    words = [w for w in words if w not in SLUG_SKIP or w in ("для", "с")][:SLUG_WORDS]
    while words and words[-1] in SLUG_SKIP:
        words.pop()
    out = "-".join("".join(TR.get(ch, ch) for ch in w) for w in words)
    return re.sub(r"-+", "-", out).strip("-")


def _slash_style(groups):
    """Адреса сайта с косой чертой в конце («/kotly/») или без («/kotly»): как у большинства страниц групп."""
    ps = [urlsplit(g["page"]).path for g in groups if g.get("page")]
    ps = [p for p in ps if p not in ("", "/")]
    if not ps:
        return True
    return sum(p.endswith("/") for p in ps) * 2 >= len(ps)


def new_url(g, site, slash, city, taken, parent_url=""):
    """Адрес новой страницы: подраздел - внутри родителя, иначе - от корня сайта."""
    if (g.get("todo") or "").startswith("Главная"):     # новый сайт: тема без уточнений - главная страница
        return site
    # адрес - из названия группы, а не из H1: H1 новой страницы - запрос людей («Продвижение в Яндексе»,
    # «… под ключ»), адрес из него выходил «/prodvizhenie-yandekse», «/seo-prodvizhenie-saytov-klyuch» (29.10.2026)
    s = slug(g["name"], city) or "razdel"
    base = site.rstrip("/")
    if (g.get("todo") or "").startswith("Создать страницу бренда"):   # новый сайт: бренды - в своём разделе
        base += "/brands"
    near = g.get("near") or parent_url or ""
    if near and (g.get("todo") or "").startswith("Создать подраздел"):
        p = urlsplit(near)
        path = p.path
        if not path.endswith("/"):
            path = path.rsplit("/", 1)[0] + "/" if re.search(r"\.\w{2,5}$", path) else path + "/"
        base = f"{p.scheme}://{p.netloc}{path.rstrip('/')}"
    url = f"{base}/{s}" + ("/" if slash else "")
    n = 2
    while url in taken:
        url = f"{base}/{s}-{n}" + ("/" if slash else "")
        n += 1
    taken.add(url)
    return url


def _rows_good(g):
    return [r for r in g.get("q") or [] if not r[7]]


def _clean_q(q, is_city, question=False):
    words = [w for w in q.split() if (question or w not in NOISE) and not is_city(w)]
    while words and words[-1] in ("в", "на", "для", "с", "по", "и"):
        words.pop()
    return " ".join(words)


def _stems(t):
    return {w[:4] for w in re.findall(r"[a-zа-яё0-9]+", t.lower().replace("ё", "е")) if len(w) > 2}


def _cap(s):
    """Первая буква большая; Яндекс, Google, SEO - как в H1 новой страницы (pages.proper, 29.10.2026)."""
    from .pages import proper
    return proper(s)


def h2_plan(g, city=None):
    """Подзаголовки H2 для текста: частые уточнения группы (бренд, тип, «для дома»), цены, вопросы."""
    is_city, _ = _city_test(city)
    name_l = g["name"].lower()
    rows = _rows_good(g)
    out, seen = [], [_stems(name_l)]

    def add(t, force=False):
        t = re.sub(r"\s+", " ", t).strip(" -,")
        st = _stems(t)
        # почти то же, что уже есть («как установить …» и «как правильно устанавливать …») - не нужно
        if not t or len(t.split()) < 2 or not st - seen[0] or (
                not force and any(len(st - x) <= 1 and len(x - st) <= 1 for x in seen[1:])):
            return
        seen.append(st)
        out.append(_cap(t))
    for f in (g.get("f") or [])[:3]:        # страницы-фильтры: уже готовые названия по частым уточнениям
        add(_clean_q(f["name"].lower(), is_city))
    a = g.get("a") or {}
    for w in [x.strip() for x in (a.get("words") or "").split(",") if x.strip()]:
        if len(out) >= 3:
            break
        best = max((r for r in rows if w in r[0].split() and not re.search(r"\d", r[0])), key=lambda r: r[3], default=None)
        if best:
            add(_clean_q(best[0], is_city))
    if g.get("ptype") != "article":
        buy = [r for r in rows if re.search(r"цен|стоимост|прайс", r[0])]
        if buy:
            add(f"{g['name']}: цены", force=True)
    info = sorted((r for r in rows if r[2] == "Информация" or r[0].split()[0] in QWORDS), key=lambda r: -r[3])
    faq = {x.lower() for x in g.get("faq") or []}
    nq = 0
    for r in info:
        if len(out) >= H2_MAX - 1 or nq >= 2:
            break
        if r[0] not in faq and r[0].split()[0] in QWORDS:
            before = len(out)
            add(_clean_q(r[0], is_city, question=True))
            nq += len(out) - before
    if g.get("faq"):
        add("Вопросы и ответы")
    return out[:H2_MAX]


def _round50(n):
    return int(round(n / 50.0)) * 50


def volume(g, rival_words):
    """Сколько слов в тексте: по страницам конкурентов той же группы (без меню и подвала), иначе ориентир."""
    ws = sorted(w for w in (rival_words.get(u, 0) for u in g.get("rivals") or []) if w >= MIN_RIVAL_WORDS)
    art = g.get("ptype") == "article"
    if ws:
        med = ws[len(ws) // 2] if len(ws) % 2 else (ws[len(ws) // 2 - 1] + ws[len(ws) // 2]) / 2
        lo = max(WORDS_PAGE if not art else 600, _round50(med * 0.8))
        hi = max(lo + 100, _round50(med * 1.2))
        return {"min": lo, "max": hi, "rivals": ws, "text": f"{lo}-{hi} слов, как у конкурентов ({', '.join(map(str, ws[:4]))})"}
    lo = WORDS_ARTICLE if art else WORDS_PAGE
    return {"min": lo, "max": 0, "rivals": [], "text": f"не меньше {lo} слов" +
            (" (страниц конкурентов по этой группе нет, ориентир для статьи)" if art else
             " (страниц конкурентов по этой группе нет, ориентир для страницы товара или услуги)")}


def _rival_folders(reports, hosts):
    """Последняя проверка каждого конкурента в папке «отчёты» (имя папки «сайт_дата_время»)."""
    out = {}
    try:
        names = sorted(os.listdir(reports))
    except OSError:
        return out
    for h in hosts:
        h0 = h.removeprefix("www.")
        for n in names:
            site = n.rsplit("_", 2)[0] if n.count("_") >= 2 else ""
            if site.removeprefix("www.") == h0 and os.path.exists(os.path.join(reports, n, "crawl.db")):
                out[h0] = os.path.join(reports, n)   # по имени по возрастанию: последняя - самая новая
    return out


def rival_words(data, folder):
    """Адрес страницы конкурента → слов текста (без меню и подвала) из его проверки. Нет проверки - нет данных."""
    urls = {u for g in data.get("groups") or [] for u in g.get("rivals") or []}
    by_host = {}
    for u in urls:
        by_host.setdefault(urlsplit(u).netloc.removeprefix("www."), []).append(u)
    out = {}
    for h, f in _rival_folders(os.path.dirname(folder), list(by_host)).items():
        try:
            db = sqlite3.connect(f"file:{os.path.join(f, 'crawl.db')}?mode=ro", uri=True)
            for u in by_host[h]:
                r = db.execute("SELECT COALESCE(content_words, word_count) FROM pages WHERE url=?", (u,)).fetchone()
                if r and r[0]:
                    out[u] = r[0]
            db.close()
        except sqlite3.Error:
            pass
    return out


def status(g):
    if g["kind"] == "page":
        if g.get("landing"):
            return "wrong"
        return "fix" if (g.get("a") or {}).get("problems") else "ok"
    return g["kind"] if g["kind"] in STATUS else "manual"


def _depth(g, groups):
    """Вложенность новой страницы: подраздел подраздела создаётся после своего родителя (адрес - внутри его)."""
    names = {x["name"]: x for x in groups}
    d, seen = 0, {g["name"]}
    while not g.get("near"):
        m = re.match(r"Создать подраздел в «(.+)»", g.get("todo") or "")
        g = names.get(m.group(1)) if m else None
        if not g or g["name"] in seen:
            break
        seen.add(g["name"])
        d += 1
    return d


LEVEL_WHY = {1: "пункт меню", 2: "раздел сайта", 3: "подраздел или карточка"}


def why_page(g, site=""):
    """Почему у группы эта страница (вкладка «Запрос → страница», 29.10.2026): ручное решение, главная (тема сайта),
    страница, из маски которой выросла группа, или почему страницу надо создать."""
    url = g.get("page") or ""
    todo = g.get("todo") or ""
    if not url:
        m = re.match(r"Создать подраздел в «(.+)»", todo)
        if m:
            return f"Уточнение группы «{m.group(1)}»: своей страницы на сайте нет"
        return "Страницы под эти запросы на сайте нет" if g.get("kind") in ("create", "absent") else ""
    if "(выбрана вручную)" in todo:
        return "Выбрана вами вручную"
    if (g.get("landing_set") or {}).get("choice") == "keep":
        return "Оставлена вами после «Похоже, не та страница»"
    if site and url.rstrip("/") == site.rstrip("/"):
        return "Главная: общие запросы темы сайта"
    kind = LEVEL_WHY.get(g.get("lv"))
    return f"{kind[:1].upper() + kind[1:]}: группа собрана по его маске" if kind else "Раздел сайта, из которого выросла группа"


def enrich(data, folder):
    """Добавить каждой группе land и tz (меняет data на месте и возвращает её)."""
    if not data or not data.get("groups"):
        return data
    groups = data["groups"]
    slash = _slash_style(groups)
    city = data.get("city")
    taken = {g["page"] for g in groups if g.get("page")}
    rw = rival_words(data, folder) if folder else {}
    made = {}   # новый сайт: подраздел - внутри адреса раздела, который тоже ещё создать
    for g in sorted(groups, key=lambda g: _depth(g, groups)):
        st = status(g)
        a = g.get("a") or {}
        land = {"st": st, "label": STATUS[st], "url": g.get("page") or "", "new": False, "title": "", "h1": "",
                "why": why_page(g, data.get("site") or "")}
        if st in ("create", "absent") or (not g.get("page") and st != "manual"):
            m = re.match(r"Создать подраздел в «(.+)»", g.get("todo") or "")
            land.update(url=new_url(g, data.get("site") or "", slash, city, taken, made.get(m.group(1)) if m else ""), new=True,
                        title=(a.get("title") or "").replace(" — ", " - "), h1=a.get("h1") or g["name"])
        g["land"] = land
        if land["new"]:
            made.setdefault(g["name"], land["url"])
        if st == "manual":
            continue
        g["tz"] = {"volume": volume(g, rw), "h2": h2_plan(g, city)}
    for g in groups:
        r = real_stats(g)
        if r:
            g["real"] = r
        # запрос из одного слова не входит в спрос группы из нескольких слов - как плашки частотности (direct.progress):
        # «консультация» (3 028, про врачей) давала «Консультации по стратегии роста» 3 365 (hightime.agency 29.10.2026)
        multi = len(g["name"].split()) > 1
        f = sum((r[11] if len(r) > 11 else 0) or 0 for r in g.get("q") or []
                if not r[7] and not (multi and len(r[0].split()) == 1))
        if f:
            g["freq"] = f      # частотность в месяц из добавленных файлов (Вордстат и т. п.)
    data["rival_gaps"] = rival_gaps(groups)
    return data


def _same_page(a, b):
    """Один и тот же адрес: общее правило для адресов из файлов и обхода (urls.page_key)."""
    from ..urls import same_page
    return same_page(a, b)


def real_stats(g):
    """Настоящие запросы группы (Вебмастер и Search Console): показы, переходы, среднее место по показам, главные
    запросы и какую страницу Google показывает на самом деле, если не ту, что под группу."""
    rows = [r for r in g.get("q") or [] if len(r) > 8 and (r[6] or r[8])]
    if not rows:
        return None
    shows = sum(r[6] or 0 for r in rows)
    clicks = sum((r[10] if len(r) > 10 else 0) or 0 for r in rows)
    wp = [(r[8], r[6] or 1) for r in rows if r[8]]
    pos = round(sum(p * w for p, w in wp) / sum(w for _, w in wp), 1) if wp else 0
    top = [[r[0], r[6] or 0, r[8] or 0] for r in sorted(rows, key=lambda r: -(r[6] or 0))[:5]]
    from ..urls import page_key
    pages, url_of = {}, {}   # http и https, www, слэш в конце - одна страница (адреса из разных файлов пишутся по-разному)
    for r in rows:
        if len(r) > 9 and r[9]:
            k = page_key(r[9]) or r[9]
            pages[k] = pages.get(k, 0) + (r[6] or 1)
            url_of.setdefault(k, r[9])
    other = None
    if pages:
        best, w = max(pages.items(), key=lambda x: x[1])
        target = (g.get("land") or {}).get("url") or g.get("page") or ""
        if not _same_page(url_of[best], target) and w * 2 >= sum(pages.values()):
            other = {"url": url_of[best], "shows": w,
                     "n": sum(1 for r in rows if len(r) > 9 and r[9] and (page_key(r[9]) or r[9]) == best)}
    return {"shows": shows, "clicks": clicks, "pos": pos, "n": len(rows), "top": top, "other": other}


def rival_gaps(groups):
    """По каждому конкуренту: сколько его тем есть и у вас, и каких нет (страницы нет, а у него есть)."""
    by = {}
    for i, g in enumerate(groups):
        st = (g.get("land") or {}).get("st")
        if st in (None, "manual"):
            continue
        for u in g.get("rivals") or []:
            h = (urlsplit(u).hostname or "").removeprefix("www.")
            if not h:
                continue
            e = by.setdefault(h, {"host": h, "total": 0, "have": 0, "missing": []})
            e["total"] += 1
            if st in ("create", "absent"):
                e["missing"].append({"i": i, "name": g["name"], "url": u, "st": st, "score": g.get("score") or 0,
                                     "n": sum(1 for r in g.get("q") or [] if not r[7])})
            else:
                e["have"] += 1
    out = sorted(by.values(), key=lambda e: -len(e["missing"]))
    for e in out:
        e["missing"].sort(key=lambda m: -m["score"])
    return out
