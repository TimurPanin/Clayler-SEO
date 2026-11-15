"""Страница под группу запросов: ТЗ (что поправить в title, H1, description и тексте) и каннибализация
(несколько страниц сайта с одинаковым H1/title или на одну группу — поисковик не знает, какую показывать)."""
import html
import os
import random
import re
import sqlite3
import zlib
from collections import Counter

from .words import MODIFIER_STEMS

MIN_WORDS = 150            # меньше — «мало текста»
TEMPLATE_SAMPLE = 300      # сколько страниц смотреть, чтобы найти шаблон (меню, подвал)
TEMPLATE_SHARE = 0.3       # блок на 30% страниц и чаще — шаблон, не свой текст
STOP = {"при", "это", "как", "что", "чем", "нужна", "нужен", "нужно", "над", "про", "через", "или", "лет", "год",
        "данных", "какой", "какие", "лучше", "цена", "цены", "купить", "отзывы", "фото", "видео"}
SHOP_MIN = 20   # страниц с разметкой товара (Product) — значит, магазин
BUY_RX = re.compile(r"купит|цен|стоимост|заказ|недорог", re.I)


def _rows(db_path, urls):
    db = sqlite3.connect(db_path)
    out = {}
    for u in urls:
        r = db.execute("SELECT url, title, h1, description, content_words, blocks FROM pages WHERE url=?", (u,)).fetchone()
        if r:
            out[u] = r
    return db, out


def _template(db):
    """Блоки, которые повторяются на многих страницах (меню, подвал, контакты) — их не считаем текстом страницы."""
    urls = [u for (u,) in db.execute("SELECT url FROM pages WHERE blocks IS NOT NULL AND status=200 "
                                     "AND content_type LIKE 'text/html%'")]
    random.Random(1).shuffle(urls)
    urls = urls[:TEMPLATE_SAMPLE]
    df = Counter()
    for u in urls:
        b = db.execute("SELECT blocks FROM pages WHERE url=?", (u,)).fetchone()[0]
        try:
            df.update(set(zlib.decompress(b).decode("utf-8").lower().split("\n")))
        except Exception:
            pass
    return {t for t, n in df.items() if n >= max(5, TEMPLATE_SHARE * len(urls))}


def _blocks(blob, template):
    try:
        lines = zlib.decompress(blob).decode("utf-8").split("\n")
    except Exception:
        return []
    return [x for x in lines if x.lower() not in template]


def _text(blob, template):
    return " ".join(_blocks(blob, template))


def text_stats(blocks):
    """Вода и тошнота текста страницы (абзацы своего текста, как в отчёте) или None, если текста мало."""
    from .. import settings as S
    from ..analyze.checks.text_quality import paragraphs
    from ..textstat import stats
    return stats(paragraphs(blocks), S.TEXT_STATS_MIN_WORDS) if blocks else None


def text_problems(st, rival=None):
    """Замечания для ТЗ: много воды, переспам (с цифрами конкурента, если они есть)."""
    from .. import settings as S
    from ..textstat import fmt, top_text
    out = []
    if not st:
        return out
    if st["water"] > S.WATER_MAX:
        out.append(f"Много «воды» в тексте: {fmt(st['water'])}% (норма до {S.WATER_MAX}%)"
                   + (f", у конкурента {fmt(rival['water'])}%" if rival else ""))
    if st["classic"] > S.NAUSEA_MAX or st["academic"] > S.NAUSEA_ACAD_MAX:
        out.append(f"Слова повторяются слишком часто: тошнота {fmt(st['classic'])}, академическая {fmt(st['academic'])}% "
                   f"(норма до {fmt(S.NAUSEA_MAX)} и до {fmt(S.NAUSEA_ACAD_MAX)}%)"
                   + (f", у конкурента {fmt(rival['classic'])} и {fmt(rival['academic'])}%" if rival else "")
                   + f". Чаще всего: {top_text(st)}")
    return out


def _main_query(g, Q):
    """Главный запрос группы: самый частый без уточнений, иначе название группы."""
    pure = [q for q in g["queries"] if not Q[q]["check"] and not Q[q]["extra"]]
    return max(pure, key=lambda q: Q[q]["score"]) if pure else g["name"].lower()


# слова вопроса - не тема страницы: «Технический аудит: такое. Цены…» из «что такое технический аудит» (29.10.2026)
ASK_WORDS = {"это", "такое", "что", "как", "какой", "какая", "какие", "зачем", "почему", "где", "когда", "сколько",
             "чем", "значит", "простыми", "словами"}
# приписка title и описания для услуг: «запись» - только если люди сами ищут «записаться» (курсы, клиника); иначе
# «заказать» - у SEO-агентства или ремонта «цены, запись» звучало странно (hightime.agency 29.10.2026)
SIGNUP_RX = re.compile(r"(?<![а-я])запис")
BUY_WORDS_RX = re.compile(r"(?<![а-я])(купить|цен[аыу]?|стоимост|недорог|дешев|прайс|отзыв|заказать|акци|скидк)")


PROPER = {"яндекс": "Яндекс", "яндекса": "Яндекса", "яндексе": "Яндексе", "яндексу": "Яндексу",
          "google": "Google", "гугл": "Google", "гугле": "Google", "авито": "Авито", "вконтакте": "ВКонтакте",
          "seo": "SEO", "сео": "SEO", "smm": "SMM", "serm": "SERM", "ppc": "PPC", "crm": "CRM", "saas": "SaaS"}


def proper(text, city_words=()):
    """Первая буква большая; Яндекс, Google и города - с большой: «продвижение в яндексе» → «Продвижение в Яндексе»."""
    out = []
    for w in text.split():
        lw = w.lower()
        w = PROPER.get(lw) or (w[:1].upper() + w[1:] if lw in city_words else w)
        out.append(w)
    t = " ".join(out)
    return t[:1].upper() + t[1:]


def nice_name(g, Q, city_words=()):
    """Название новой страницы для H1 и title - самый востребованный естественный запрос группы, а не её название из
    слов («Продвижение яндекс» → «Продвижение в Яндексе», hightime.agency 29.10.2026). Без вопросов, 2-6 слов."""
    # без «купить», «цена», «отзывы»: их добавит хвост title («- купить, цены»), иначе «Купить кухни … - купить, цены»
    cand = [q for q in g["queries"] if not Q[q]["check"] and Q[q]["intent"] not in ("Информация", "Покупка")
            and 2 <= len(q.split()) <= 6 and not set(q.split()) & ASK_WORDS and not BUY_WORDS_RX.search(q)]
    if not cand:
        return g["name"]
    top = max(Q[q]["score"] for q in cand)
    # близкий по спросу запрос с предлогом звучит по-человечески: «продвижение сайтов в топ», а не «… сайтов топ»
    prep = lambda q: bool(set(q.split()[1:]) & {"в", "во", "на", "для", "по", "с", "под", "от"})  # noqa: E731
    best = max(cand, key=lambda q: (Q[q]["score"] >= 0.6 * top and prep(q), Q[q]["score"], -len(q.split())))
    return proper(best, city_words)


def _brand_spelling(brand, rows):
    """Название компании так, как оно написано на сайте: «hightime» → «HighTime» (из title и H1 его страниц)."""
    if not brand:
        return brand
    rx = re.compile(re.escape(brand), re.I)
    seen = Counter(m.group(0) for r in rows.values() for x in (r[1], r[2]) for m in rx.finditer(html.unescape(x or "")))
    return seen.most_common(1)[0][0] if seen else brand


def _hot_words(g, Q, keys, skip):
    """Слова, которые часто ищут вместе с группой («настенные», «двухконтурные», «навьен»): вес — сумма оценок."""
    w, form, nq = Counter(), {}, Counter()
    for q in g["queries"]:
        r = Q[q]
        if r["check"]:
            continue
        for t in sorted(set(r["extra"].split())):   # по порядку: одинаковый итог при каждом сборе
            if len(t) < 3 or re.search(r"\d", t) or t in skip or t in STOP or keys(t) & MODIFIER_STEMS or t in ASK_WORDS:
                continue
            k = min(keys(t), key=lambda x: (x.startswith("~"), len(x), x))
            w[k] += r["score"] + 1
            nq[k] += 1
            form.setdefault(k, Counter())[t] += 1
    return [(form[k].most_common(1)[0][0], k, n) for k, n in w.most_common(12) if n >= 6 and nq[k] >= 2]


class _Index:
    """Заголовки страниц → те, где есть все слова группы. То же, что covers(заголовок, слова группы) по каждой
    странице, но без перебора: на сайте в 100 тысяч страниц и 2 тысячи групп перебор шёл минутами."""
    def __init__(self, cores):
        self.idx = {}
        for i, c in enumerate(cores):
            for k in c:
                for x in k:
                    self.idx.setdefault(x, set()).add(i)

    def covering(self, gcore):
        res = None
        for k in gcore:   # каждое слово группы - хотя бы одним вариантом
            s = set().union(*(self.idx.get(x, ()) for x in k))
            res = s if res is None else res & s
            if not res:
                return []
        return sorted(res or ())


def _rival_pages(comps, groups):
    """Первые страницы конкурентов у групп: {адрес: слов}, {адрес: свой текст}, {адрес: вода и тошнота}."""
    rival_words, rival_text, rival_stats = {}, {}, {}
    for c in comps:
        rurls = {u for g in groups for u in g["rivals"].get(c["host"], [])[:1]}
        d2, rr = _rows(os.path.join(c["folder"], "crawl.db"), rurls)
        tpl = _template(d2) if rr else set()
        d2.close()
        rival_words.update({u: r[4] or 0 for u, r in rr.items()})
        for u, r in rr.items():
            if r[5]:
                bl = _blocks(r[5], tpl)
                rival_text[u] = " ".join(bl)
                rival_stats[u] = text_stats(bl)
    return rival_words, rival_text, rival_stats


def _title_cores(main, comps, sem_mod, city_stems):
    """Слова заголовков (title и H1) всех страниц своего сайта и конкурентов → (titles, mine: [(адрес, слова)] своих)."""
    norm, core = sem_mod.norm, sem_mod.core
    titles, mine = [], []      # mine — (адрес, слова заголовка) своих страниц: сколько товаров под фильтр
    for f in [main["folder"]] + [c["folder"] for c in comps]:
        d3 = sqlite3.connect(os.path.join(f, "crawl.db"))
        for (u, t) in d3.execute("SELECT url, COALESCE(title, '') || ' ' || COALESCE(h1, '') FROM pages "
                                 "WHERE status=200 AND content_type LIKE 'text/html%'"):
            c = core(norm(html.unescape(t)), city_stems)
            if c:
                titles.append(c)
                if f == main["folder"]:
                    mine.append((u, c))
        d3.close()
    return titles, mine


def audit(sem_mod, main, comps, groups, Q, city, city_stems):
    """Для групп со своей страницей — замечания и предложения; для «создать» — заготовка новой страницы."""
    norm, core, keys, covers = sem_mod.norm, sem_mod.core, sem_mod.keys, sem_mod._covers
    city_prep = city[1] if city else ""
    brand = (main["brand"] or [""])[0]
    urls = {g["page"] for g in groups if g.get("page")}
    db, rows = _rows(os.path.join(main["folder"], "crawl.db"), urls)
    brand = _brand_spelling(brand, rows)
    template = _template(db) if rows else set()
    # магазин или услуги: у магазина много страниц с разметкой товара. Для услуг (школа, клиника, ремонт)
    # «купить, наличие, доставка» в заготовках title и описания не к месту
    try:
        shop = db.execute("SELECT COUNT(*) FROM pages WHERE schema_types LIKE '%Product%'").fetchone()[0] >= SHOP_MIN
    except sqlite3.Error:
        shop = True
    db.close()
    if main.get("new"):   # сайта ещё нет: магазин или услуги - по конкурентам
        from .newsite import shop_like
        shop = shop_like([c["folder"] for c in comps])
    rival_words, rival_text, rival_stats = _rival_pages(comps, groups)
    rival_names = {sem_mod.sound(c["host"].split(".")[0]) for c in comps}
    # слова, которые есть почти на всех страницах конкурента («в корзине», «достаточно») — не тема, а шаблон
    df = Counter()
    for t in rival_text.values():
        df.update({min(keys(w), key=lambda x: (x.startswith("~"), len(x), x))
                   for w in set(re.findall(r"[а-яёa-z]{4,}", t.lower().replace("ё", "е")))})
    generic = {k for k, n in df.items() if n >= max(3, 0.4 * len(rival_text))}
    # город сайта (как есть и «в …»): не уточнение для фильтров и слов ТЗ. До 16.10.2026 здесь были зашиты «уфа», «уфе»
    city_words = {w for x in (city or ())[:2] if isinstance(x, str) for w in norm(x).replace("-", " ").split()}
    city_words |= {a for a, n in sem_mod.CITY_ALIASES.items() if city and n == city[0]}   # «спб», «мск»
    skip = {"купить", "цена", "цены"} | city_words
    # заголовки всех страниц своего сайта и конкурентов: слово советуем, только если оно встречается
    # в заголовках вместе с названием группы («настенные газовые котлы» — да, «группа безопасности на высоте» — нет)
    titles, mine = _title_cores(main, comps, sem_mod, city_stems)
    sec_urls = {s_["url"] for s_ in main["sections"]}
    cities = sem_mod.City()
    t_idx, m_idx = _Index(titles), _Index([c for _, c in mine])
    for g in groups:
        g["audit"] = None
        if g["prio"] == 4 or not g["core"]:
            continue
        mq = _main_query(g, Q)
        name = g["name"]
        buy = sum(1 for q in g["queries"] if Q[q]["intent"] == "Покупка") >= 2
        hot = _hot_words(g, Q, keys, skip)
        near_t = [titles[i] for i in t_idx.covering(g["core"])]
        seen_k = set().union(*[k for t in near_t for k in t]) if len(near_t) >= 3 else None
        if seen_k is not None:
            hot = [h for h in hot if h[1] in seen_k]
        g["filters"] = (_filters(g, Q, keys, skip, seen_k, [mine[i] for i in m_idx.covering(g["core"])], sec_urls,
                                 NAME_NOISE | city_words)
                        if g["prio"] in (1, 2) else [])
        signup = any(SIGNUP_RX.search(q) for q in g["queries"])
        tail = "купить, цены" if shop else "цены, запись" if signup else "цены, заказать"
        pname = name if g.get("page") else nice_name(g, Q, city_words)   # новая страница - из запроса людей
        title_new = f"{pname} в {city_prep} - {tail}" if city_prep and city_prep.lower() not in pname.lower() else f"{pname} - {tail}"
        title_new += f" | {brand}" if brand else ""
        hot_txt = ", ".join(PROPER.get(t, t) for t, _, _ in hot[:4])
        desc_new = (f"{pname} {('в ' + city_prep) if city_prep and city_prep.lower() not in pname.lower() else ''}: {hot_txt + '. ' if hot_txt else ''}"
                    + ("Цены, наличие, доставка, консультация" if shop else
                       "Цены, условия, запись и консультация" if signup else
                       "Цены и условия" if "консультац" in pname.lower() else "Цены, условия и консультация")
                    + (f" - {brand}" if brand else "") + ".")
        desc_new = re.sub(r"\s+", " ", desc_new).replace(" :", ":")
        # одно слово после двоеточия («… в топ: Яндекса.») читается обрывком - только список из двух и больше;
        # после двоеточия - со строчной («Продвижение в Яндексе: цены, условия…», 29.10.2026)
        if hot_txt and "," not in hot_txt:
            desc_new = desc_new.replace(f": {hot_txt}. ", ": ", 1)
        desc_new = re.sub(r": (Цены)", lambda m: ": " + m.group(1).lower(), desc_new, count=1)
        a = {"main": mq, "problems": [], "title": "", "h1": "", "description": "",
             "now": {}, "words": hot_txt}
        rst = next((rival_stats.get(u) for urls_ in g["rivals"].values() for u in urls_[:1] if rival_stats.get(u)), None)
        if rst:  # вода и тошнота у страницы конкурента - ориентир для ТЗ
            a["rival_text"] = {k: rst[k] for k in ("water", "classic", "academic")}
        if not g.get("page"):                       # создать страницу: заготовка
            if g["prio"] == 2:
                a.update(title=title_new, h1=pname, description=desc_new, new=True)
                g["audit"] = a
            continue
        r = rows.get(g["page"])
        if not r:
            continue
        _u, title, h1, desc, words, blob = r
        title, h1, desc = (html.unescape(x or "") for x in (title, h1, desc))
        # одинаковые H1 (для компьютера и телефона) - один раз: «A | A» в «сейчас» ТЗ (hightime.agency 29.10.2026)
        h1 = " | ".join(dict.fromkeys(x.strip() for x in h1.split(" | ") if x.strip()))
        bl = _blocks(blob, template) if blob else []
        text = " ".join(bl)
        a["now"] = {"title": title, "h1": h1, "description": desc, "words": words or 0}
        st = text_stats(bl)
        if st:
            a["now"].update(water=st["water"], classic=st["classic"], academic=st["academic"])
        has = lambda s: bool(s) and covers(core(norm(s), city_stems), g["core"])  # noqa: E731
        P = a["problems"]
        if not has(title):
            P.append(f"В title нет главного запроса «{mq}»")
            a["title"] = title_new
        elif buy and not BUY_RX.search(title):
            P.append("В title нет «купить» или «цена», а группу ищут, чтобы купить" if shop else
                     "В title нет «цена» или «стоимость», а по этим запросам выбирают, где заниматься или заказать")
            a["title"] = title_new
        # ищут с городом: город целым словом (City.find). Раньше - первые три буквы где угодно: у Перми «перила»,
        # у Курска «курсы», у Самары «самый» давали ложное «В title нет города» (24.10.2026)
        elif city_prep and city_prep.lower() not in title.lower() and city[0].lower() not in title.lower() \
                and any(city[0] in cities.find(q) for q in g["queries"]):
            P.append(f"В title нет города - ищут «… {city[0].lower()}»")
            a["title"] = title_new
        if not has(h1):
            P.append(f"В H1 нет главного запроса - сейчас «{h1 or 'H1 нет'}»")
            a["h1"] = name
        if not desc:
            P.append("Нет описания (description) - Яндекс возьмёт для сниппета случайный кусок текста")
            a["description"] = desc_new
        elif not has(desc):
            P.append("В описании (description) нет главного запроса")
            a["description"] = desc_new
        if text and not has(text):
            P.append(f"Главный запрос «{mq}» не встречается в тексте страницы")
        page_keys = set()
        for t in set(re.findall(r"[a-zа-яё0-9]+", norm(" ".join((title, h1, desc, text))))):
            page_keys |= keys(t)
        miss = [t for t, k, _ in hot if k not in page_keys][:6]
        if miss:
            P.append("В тексте нет слов, которые часто ищут в этой группе: " + ", ".join(miss))
        a["missing"] = miss
        rtext = " ".join(rival_text.get(u, "") for urls_ in g["rivals"].values() for u in urls_[:1])
        lsi = _lsi(rtext, page_keys | generic, keys, rival_names, sem_mod.sound) if rtext else []
        if lsi:
            P.append("У конкурента в тексте есть слова, которых нет у вас: " + ", ".join(lsi))
        a["lsi"] = lsi
        rw = max((rival_words.get(u, 0) for urls_ in g["rivals"].values() for u in urls_[:1]), default=0)
        if (words or 0) < MIN_WORDS:
            P.append(f"Мало текста: {words or 0} слов" + (f", у конкурента {rw}" if rw > (words or 0) else ""))
        elif rw and rw > 2 * words:
            P.append(f"Текста в {rw / words:.0f} раза меньше, чем у конкурента ({words} слов против {rw})")
        P += text_problems(st, rst)
        g["audit"] = a


FILTER_MIN_QUERIES = 3


def _cap(s):
    return s[:1].upper() + s[1:]


NAME_NOISE = {"самые", "самый", "лучшие", "лучший", "какой", "какие", "купить", "цена", "цены", "отзывы", "недорого",
              "в", "рейтинг", "фото"}   # и город сайта - в audit


def _filters(g, Q, keys, skip, seen_k, mine, sec_urls, noise=NAME_NOISE):
    """Страницы-фильтры: уточнения, которые часто ищут вместе с группой (бренд, тип, мощность), — сколько запросов
    и сколько своих товаров под них. «газовые котлы навьен: 20 запросов, 14 товаров»."""
    agg, agg_qs = {}, {}
    for q in g["queries"]:
        r = Q[q]
        if r["check"]:
            continue
        for t in sorted(set(r["extra"].split())):   # по порядку: одинаковый итог при каждом сборе
            if len(t) < 3 or t in skip or t in STOP or keys(t) & MODIFIER_STEMS:
                continue
            if re.fullmatch(r"\d+", t):
                continue
            k = min(keys(t), key=lambda x: (x.startswith("~"), len(x), x))
            e = agg.setdefault(k, {"forms": Counter(), "qs": [], "score": 0, "keys": keys(t)})
            e["forms"][t] += 1
            e["qs"].append(q)
            e["score"] += r["score"]
    out = []
    for k, e in agg.items():
        if len(e["qs"]) < FILTER_MIN_QUERIES or (seen_k is not None and not e["keys"] & seen_k):
            continue
        agg_qs[e["forms"].most_common(1)[0][0]] = e["qs"]
        prods = [u for u, c in mine if u not in sec_urls and any(e["keys"] & x for x in c)]   # mine - уже со словами группы
        word = e["forms"].most_common(1)[0][0]
        # название — самый частый запрос, где уточнение только это слово («ибп для газовых котлов»)
        only = [q for q in e["qs"] if Q[q]["extra"] == word] or e["qs"]
        only = [q for q in only if Q[q]["intent"] in ("Покупка", "Общий")] or only
        top = max(Q[q]["score"] for q in only)
        best = min((q for q in only if Q[q]["score"] >= top / 4),
                   key=lambda q: (sum(1 for t in q.split() if t in noise), len(q.split()), -Q[q]["score"]))
        out.append({"word": word, "name": _cap(" ".join(t for t in best.split() if t not in noise) or best), "queries": len(e["qs"]), "score": e["score"],
                    "products": len(prods), "example": prods[0] if prods else "",
                    "sample": sorted(e["qs"], key=lambda q: -Q[q]["score"])[:5]})
    out.sort(key=lambda f: (-f["queries"], -f["score"]))
    kept = []   # «частного» и «дома» — почти одни и те же запросы: оставляем один фильтр
    for f in out:
        qs = set(agg_qs[f["word"]])
        if not any(len(qs & set(agg_qs[k["word"]])) >= 0.6 * min(len(qs), len(agg_qs[k["word"]])) for k in kept):
            kept.append(f)
    return kept[:15]


LSI_STOP = set("""который которые которая которого также можно более очень если только этот этого этой эти этим
будет было были быть есть нет него неё них ним нему вам вас ваш ваши наш наши нашей нашем нашего свой своих своей
всех весь всего всей все всё каждый любой другой других такой такие такого когда тогда where with your from this that
чтобы потому поэтому однако кроме между после перед около через более менее много мало самый самые часто всегда
очень хорошо лучше просто именно поэтому например является являются может могут должен должны нужно необходимо
купить цена цены стоимость товар товары товаров корзина корзину наличии наличие артикул доставка доставки оплата
заказ заказать магазин магазина каталог руб рублей штук отзывы отзыв характеристики описание подробнее сравнить
избранное вход регистрация телефон звоните менеджер скидка акция производитель страна гарантия""".split())


def _lsi(rtext, page_keys, keys, rival_names, sound):
    """Слова, которые повторяются в тексте страницы конкурента (2+ раза), а на вашей странице их нет."""
    cnt, form = Counter(), {}
    for t in re.findall(r"[а-яёa-z]{4,}", rtext.lower().replace("ё", "е")):
        if t in LSI_STOP or sound(t) in rival_names:
            continue
        ks = keys(t)
        if ks & page_keys or ks & MODIFIER_STEMS:
            continue
        k = min(ks, key=lambda x: (x.startswith("~"), len(x)))
        cnt[k] += 1
        form.setdefault(k, Counter())[t] += 1
    return [form[k].most_common(1)[0][0] for k, n in cnt.most_common(10) if n >= 2]


def cannibal(main, groups):
    """Страницы сайта, которые мешают друг другу: одинаковый H1 или title у разделов, или одна группа — несколько разделов."""
    db = sqlite3.connect(os.path.join(main["folder"], "crawl.db"))
    secs = {s["url"]: s for s in main["sections"]}
    meta = {u: db.execute("SELECT title, h1 FROM pages WHERE url=?", (u,)).fetchone() or ("", "") for u in secs}
    db.close()
    group_of = {u: g["name"] for g in groups for u in g.get("main") or []}
    out, seen = [], set()

    def add(why, urls):
        urls = sorted(set(urls), key=lambda u: (-secs.get(u, {}).get("links", 0), u))
        key = frozenset(urls)
        if len(urls) < 2 or key in seen:
            return
        seen.add(key)
        out.append({"why": why, "main": urls[0], "pages": [
            {"url": u, "title": html.unescape(meta.get(u, ("", ""))[0] or ""), "h1": html.unescape(meta.get(u, ("", ""))[1] or ""),
             "group": group_of.get(u, ""), "links": secs.get(u, {}).get("links", 0)} for u in urls]})

    def clean(s):
        return re.sub(r"\s+", " ", html.unescape(s or "")).strip().lower()
    for i, what in ((1, "Одинаковый H1"), (0, "Одинаковый title")):
        by = {}
        for u, m in meta.items():
            k = clean(m[i])
            if k:
                by.setdefault(k, []).append(u)
        for k, us in by.items():
            if len(us) > 1:
                add(f"{what}: «{k}»", us)
    for g in groups:
        if len(set(g.get("main") or [])) > 1:
            add(f"Несколько разделов под одну группу «{g['name']}»", g["main"])
    return out
