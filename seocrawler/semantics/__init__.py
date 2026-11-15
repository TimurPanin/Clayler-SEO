"""Семантика сайта: какие запросы ищут люди и какая страница сайта должна по ним показываться.

Откуда фразы: разделы своего сайта и сайтов конкурентов (из готовых проверок) → подсказки Яндекса и Google
по каждому разделу → запросы из Вебмастера и Search Console (если вход подключён).
Потом мусор отсеивается (чужие города, конкуренты, «скачать», не по теме), фразы раскладываются по группам
(группа = раздел), у группы — страница сайта или пометка «создать раздел». Результат — семантика.xlsx."""
import json
import math
import os
import re
import sqlite3
import sys
import time
import zlib

from . import seeds as S
from .stem import sound, stem
from .suggest import Suggest
from .words import (CITIES, CITY_ALIASES, CITY_WORDS, INTENT, JUNK, MODIFIER_STEMS, canon_city, city_by_name, load_stop, own_names,
                    refine_intent)

# Версия «Семантики» - своя, отдельно от версии программы (seocrawler/__init__.py). Показывается в окне и пишется
# в семантика.json. Повышать при заметном изменении сбора, групп, ТЗ или раздела для клиента: 1.0 → 1.1;
# если старые семантики стоит собрать заново - 2.0. Что поменялось - строкой в РЕШЕНИЯ.md.
VERSION = "1.6"  #: одинаковый результат при каждом сборе, город сайта в ТЗ, бренды и серии с конкурентом по адресу

VOWELS = "аеиоуыэюя"
MAX_QUERY_WORDS = 8
MAX_INFO_WORDS = 12   # вопрос бывает длинным: «биметаллические радиаторы и алюминиевые в чем разница между ними»
SOFT_JUNK = {"своими руками", "картинки", "форум"}   # с маркером статьи или галереи - не мусор, а тема для блога
INFO_RX = INTENT[0][1]
NEUTRAL = {"это", "пример", "примеры", "разница", "качественные", "хорошие", "рф", "россия", "ру", "ru",
           "инструкция", "характеристики", "размеры", "виды", "типы", "производитель", "страна"}
LONG_OK_RX = re.compile(r"(?<![а-я])(купить|заказ|цен[аыу]|стоимост|недорог|дешев|доставк|производител|под ключ)")
# общие слова ниши: по ним одним запрос к группе не привязывается
SHARED_STEMS = {stem(w) for w in ("заказ", "заказу", "индивидуальным", "размерам", "размеры", "недорого", "цены", "купить",
                                  "производителя", "фото", "дизайн", "интерьере")} | {stem(w) for w in CITY_WORDS}
BIG_VOCAB = 2000   # слов в тексте страниц сайтов: меньше - запросы «про другое» не отсеиваются, только помечаются
# обычные уточнения, которых на сайте может не быть: запрос с ними не «про другое»
GENERIC_OK = {stem(w) for w in ("женские", "женский", "мужские", "мужской", "детские", "детский", "подростковые",
                                "унисекс", "взрослые", "взрослых", "большие", "маленькие", "красивые", "современные",
                                "производителя", "производитель", "оптом", "розницу", "складе", "склада")}
COMMON_BRAND_STEMS = {stem(w) for w in ("компания", "компании", "интернет-магазин", "магазин", "интернет", "группа",
                                        "сервис", "центр", "торговый", "дом", "официальный", "сайт", "ооо")}
JUNK_RX = re.compile(r"(?<![а-яa-z0-9])(" + "|".join(re.escape(j.strip()) for j in JUNK) + r")(?![а-яa-z0-9])")
BU_RX = re.compile(r"(?<![а-я])б\s*/?\s*у(?![а-я])")


def norm(q):
    q = q.lower().replace("ё", "е")
    q = re.sub(r"[^\w\s\-/+.]", " ", q)
    return re.sub(r"\s+", " ", q).strip(" -./")


def tokens(q):
    return re.findall(r"[a-zа-я0-9]+(?:-[a-zа-я0-9]+)*", q)


def repeated_word(toks):
    """Главное слово запроса, повторённое в начале два раза подряд (то же слово или его форма): «тепловентиляторы
    тепловентиляторы», «теплоноситель теплоноситель». Вордстат такие фразы склеивает с обычной и показывает её
    частоту - в семантике это дубль. Повтор дальше по фразе - обычно тип товара: «подводка гайка гайка»,
    «папа папа» (резьба с двух сторон), его оставляем. Возвращает слово или ""."""
    if len(toks) < 2 or len(toks[0]) < 3 or toks[0].isdigit():
        return ""
    if ("-" in toks[0]) != ("-" in toks[1]):   # «шкаф-купе купить»: часть «купе» - не повтор «купить»
        return ""
    a, b = ({k for k in keys(t) if not k.startswith("~")} for t in toks[:2])   # основы, «котел» = «котла»
    return toks[1] if a & b else ""


TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                     "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def keys(tok):
    """Варианты слова для сравнения: основа, основа без беглой гласной (котел/котл), звучание латиницей."""
    out = set()
    parts = tok.split("-") if re.fullmatch(r"[а-я]+(-[а-я]+)+", tok) else [tok]
    for t in parts:
        if re.fullmatch(r"[а-я]+", t):
            st = stem(t)
            out.add(st)
            if len(st) >= 4 and st[-1] not in VOWELS and st[-2] in "ео" and st[-3] not in VOWELS:
                out.add(st[:-2] + st[-1])
            if len(t) >= 4:
                out.add("~" + sound(st))
                out.add("~" + sound(t))
            elif len(t) == 3:   # «сео» = «seo», «смм» = «smm» (hightime.agency): буква в букву латиницей,
                # а не по звучанию - звучание склеивало «час» и «касса», «суд» и «зуд»
                out.add("".join(TRANSLIT.get(c, c) for c in t))
        else:
            out.add(t)
            s = sound(t)
            if len(s) >= 3:
                out.add("~" + s)
    return out


NOT_MODIFIER = {"купе"}   # основа как у «купить», но это товар: «шкаф купе»


def _mod(t):
    return t not in NOT_MODIFIER and bool(keys(t) & MODIFIER_STEMS)


def core(q, drop=frozenset()):
    """Значимые слова фразы (без «купить», «в», города): список множеств вариантов."""
    out = []
    for t in tokens(q):
        k = keys(t)
        # слово через дефис - уточнение, только если уточнения все его части («интернет-магазин»): у «шкафы-купе»
        # часть «купе» совпадала с «купить», и группа «Шкафы-купе на заказ» становилась группой «на заказ»
        mod = all(_mod(p) for p in t.split("-")) if "-" in t else _mod(t)
        if mod or k & drop or (len(t) == 1 and not t.isdigit()):
            continue
        if re.fullmatch(r"[а-я]+(-[а-я]+)+", t):   # «шкафы-купе» - два слова: «шкафы купе» и «шкаф-купе» - одно и то же,
            # а «шкафы» отдельно - другое (иначе «шкафы купе» уходили в «Шкафы на заказ»)
            out += [keys(p) for p in t.split("-") if len(p) > 1 and not _mod(p)]
            continue
        out.append(k)
    return out


def _canon(k):
    plain = [x for x in k if not x.startswith("~")]
    # есть латинская форма - она: «seo» и «сео» (keys: «seo» буква в букву) - одна группа, а не «Seo продвижение
    # сайтов» и «Сео продвижения сайтов» рядом (hightime.agency)
    lat = [x for x in plain if re.fullmatch(r"[a-z0-9\-]+", x)]
    if lat:
        return min(lat, key=lambda x: (len(x), x))
    return min(plain, key=lambda x: (len(x), x)) if plain else min(k)


def _covers(qcore, gcore):
    return all(any(g & q for q in qcore) for g in gcore)


class City:
    def __init__(self):
        self.items = []
        for name, prep, _lr in CITIES:
            forms = {tuple(stem(w) for w in norm(x).replace("-", " ").split()) for x in (name, prep)}
            self.items.append((canon_city(name), forms))   # «Питер», «СПб» - это Санкт-Петербург, не другой город
        for alias, name in CITY_ALIASES.items():
            self.items.append((name, {(stem(alias),)}))
        self.stems = {s for _, forms in self.items for f in forms if len(f) == 1 for s in f}

    def find(self, q):
        """Города в запросе - их полные имена («кухни спб» → {"Санкт-Петербург"})."""
        sts = [stem(t) for t in norm(q).replace("-", " ").split()]
        found = set()
        for name, forms in self.items:
            for f in forms:
                n = len(f)
                if any(tuple(sts[i:i + n]) == f for i in range(len(sts) - n + 1)):
                    found.add(name)
        return found


DEEP_LETTERS = "абвгдезиклмнопрстуфхчшэ"
INFO_SEEDS = 20  # по стольким главным разделам ещё и вопросы («раздел как», «раздел что»)
NICHE_MIN = 3   # столько запросов вне разделов с одинаковыми двумя главными словами — уже своя группа   # «подробно»: раздел + буква — длинные точные запросы


BRAND_URL = re.compile(r"/(brands?|brendy|brend|proizvoditeli|proizvoditel|vendors?|manufacturers?)/", re.I)
NEW_MIN_SCORE = 20   # новый сайт: раздел одного конкурента с таким спросом (оценка группы) - создавать, меньше - решить


def _brand_page(g):
    urls = [u for us in g["rivals"].values() for u in us]
    return bool(urls) and all(BRAND_URL.search(u) for u in urls)


def _todo_new(g, glist, other, keyset):
    """Новый сайт: страницы нет ни одной, вопрос - создавать ли и где. Тема без уточнений - главная; раздел
    двух конкурентов или заметный спрос - создать (подраздел, если есть группа шире)."""
    g["page"] = ""

    def strong(m):
        return len(m["rivals"]) >= 2 or m["score"] >= NEW_MIN_SCORE
    if g["main"]:
        g["todo"], g["prio"] = "Главная страница сайта", 2
        return
    if not strong(g):
        g["todo"], g["prio"] = "Есть у конкурента, спроса мало - решить, нужна ли страница", 3
        return
    if _brand_page(g):   # у конкурентов это страница бренда: и у вас - в «Брендах»
        g["todo"], g["prio"] = "Создать страницу бренда", 2
        return
    ks = keyset(g)
    parent = max((m for m in glist if m is not g and m is not other and not m["main"] and m["core"]
                  and keyset(m) < ks and strong(m) and not _brand_page(m)), key=lambda m: len(m["core"]), default=None)
    if not parent:   # слова разные, но у конкурента раздел вложен («Котлы» → «Haier»): так же и у вас
        alive = {id(m) for m in glist}
        cand = [(n, m) for n, m in g.get("_up") or [] if id(m) in alive and m is not other and not m["main"]
                and strong(m) and not _brand_page(m) and not any(x is g for _, x in m.get("_up") or [])]
        parent = max(cand, key=lambda x: x[0])[1] if cand else None
    if parent:   # название родителя - после цикла: имя группы ещё может уточниться («Настенные» → …)
        g["todo"], g["prio"], g["_parent"] = "Создать подраздел", 2, parent
    else:
        g["todo"], g["prio"] = "Создать раздел", 2


class Stopped(Exception):
    """Сбор остановили кнопкой «Остановить»: прежняя семантика остаётся как была."""


def build(folder, competitors=(), log=print, region=None, offline=False, deep=False, rival_hosts=(), stop=None,
          light=False):
    """light - быстрый сбор (очередь сайтов): только главная и разделы по маскам (уровни 1-2), без «+ буква».
    Маски не подтверждены - берутся предложенные программой (и сохраняются, чтобы человек потом их увидел).
    Шаги: семена (разделы, тема, маски, бренды) → подсказки → настоящие запросы → слова сайтов → отсев →
    группы по разделам → группы вне разделов → страницы и что делать → сверка страниц (pages.py), GEO."""
    t0 = time.time()

    def check_stop():
        if stop and stop():
            raise Stopped()
    from . import newsite as NS
    ns = NS.info(folder)   # сайта ещё нет: семена - слова темы и разделы конкурентов (newsite.py)
    main = NS.load(folder, ns) if ns else S.load(folder)
    new = bool(ns)
    from . import masks as MK   # маски, подтверждённые человеком: только включённые разделы и их текст
    if light and not new:
        deep = False
        # только если масок нет: обновление по новым правилам сбросило бы подтверждение человека (новые маски -
        # «подтвердить заново»), и обычный сбор пошёл бы без его масок. Обновить - кнопкой в окне (проверка кода 28.10)
        if not MK.load(main["host"]).get("masks"):
            MK.propose(folder, log)
    use_masks = None if new else MK.for_build(main, log, light=light)
    check_stop()
    comps = []
    for c in competitors:
        comps.append(S.load(c))
        check_stop()
    rivals_light = _rivals_by_address(rival_hosts, folder, offline, log)   # конкуренты по адресу, без проверки
    city = city_by_name(region) if region else main["city"]
    lr = (city[2] if city and city[2] else 225)
    if new:
        log(f"Новый сайт «{ns['name']}»: своего сайта нет, семантика - по словам темы и разделам конкурентов.")
        if not comps and not rivals_light:
            log("Конкурентов нет - разделы будут только из подсказок по словам темы. С 1-3 конкурентами структура полнее.")
    log(f"Семантика для {main['site']}: разделов на сайте {len(main['sections'])}"
        + "".join(f", у {c['host']} - {len(c['sections'])}" for c in comps + rivals_light)
        + (f". Город: {city[0]}." if city else ". Город не определил - подсказки по всей России."))
    cities = City()
    city_stems = {s for f in cities.items for forms in [f[1]] for t in forms for s in t}

    seeds = _seed_phrases(main, [main] + comps + rivals_light)
    niche, topic_masks, own_masks, models = _topic_phrases(main, seeds, folder, new, light)
    topic = set()   # слова тематики: из названий всех разделов и темы сайта (и брендов с сериями товаров)
    for ph in list(seeds) + niche + models:
        # «seo-аудиты» - одно слово, а в запросах пишут «seo аудит»: тема - и по частям через дефис
        for k in core(ph, city_stems) + core(ph.replace("-", " "), city_stems):
            topic |= {x for x in k if not x.startswith("~") or len(x) > 4}

    # ---- подсказки
    sug = Suggest(folder, lr=lr, log=log, offline=offline)
    city_word = norm(city[0]) if city else ""
    tasks = _suggest_tasks(main, seeds, niche, topic_masks, models, city_word, new, deep, use_masks)
    if models:
        log(f"Бренды и серии из названий товаров: {len(models)} фраз, например "
            + ", ".join(f"«{t}»" for t in models[:4]))
    if niche:
        log("Тема сайта для поиска того, чего на сайте нет: " + ", ".join(f"«{t}»" for t in niche))
    if deep:
        log("Подробный сбор: по каждому своему разделу ещё и «раздел + буква» - это дольше.")
    log(f"Собираю подсказки Яндекса и Google: {len(tasks)} запросов (уже сохранённые не повторяются)…")
    res = sug.many(tasks, progress=lambda d, n: log(f"  подсказки: {d} из {n}"), stop=stop)
    if stop and stop():
        log("Сбор остановлен. Полученные подсказки сохранены: следующий сбор их не повторит.")
        raise Stopped()
    miss = sum(1 for v in res.values() if v is None)
    if miss:
        log(f"  без ответа: {miss} из {len(tasks)} (сервис подсказок не ответил) - эти разделы соберутся беднее.")
    short = _shorter_tasks(list(seeds) + niche, res, sug, stop, log)
    if stop and stop():
        raise Stopped()

    Q = {}
    for ph, e in seeds.items():
        _add(Q, ph, "раздел сайта" if main["host"] in e["sites"] else "раздел конкурента", ph)
    for (engine, ph), lst in res.items():
        base = re.sub(r" [а-я]$", "", ph.strip())          # «газовые котлы а» → раздел «газовые котлы»
        if city_word and base.endswith(" " + city_word):
            base = base[:-len(city_word) - 1]
        letter = base != ph.strip() and not ph.strip().endswith(city_word or "\0")
        for i, s in enumerate(lst or []):
            # по «раздел + буква» место в подсказках не говорит о спросе — считаем его скромнее
            _add(Q, s, "подсказки " + ("Яндекса" if engine == "yandex" else "Google"), base,
                 (i + 1) + (5 if letter else 0), "y" if engine == "yandex" else "g")
    for (engine, ph), (lst, base) in short.items():   # короткая форма маски: запросы идут к самой маске
        for i, s in enumerate(lst):
            _add(Q, s, "подсказки " + ("Яндекса" if engine == "yandex" else "Google"), base, i + 1,
                 "y" if engine == "yandex" else "g")
    wm, gsc, real = _real_queries(folder, main, new, offline, log, Q)
    check_stop()
    log("Читаю слова со страниц сайтов: на большом сайте это до минуты…")
    vocab, words_seen, tvocab, main_pages = _site_vocab(folder, competitors, main, new)

    # ---- отсев
    my_city = city[0] if city else None
    own = own_names(main["host"]) if not new else set()   # запросы с названием сайта - навигация
    dropped = _drop_junk(Q, main, comps + rivals_light, cities, my_city, topic)

    # ---- группы: одна на раздел (одинаковые по смыслу разделы разных сайтов — одна группа)
    glist, sec_group = _seed_groups(seeds, main, city_stems)
    other = {"name": "Без группы", "core": [], "phrases": set(), "main": [], "rivals": {}, "queries": []}
    client_ok = {k for w in MK.load(main["host"]).get("ok") or [] for t in tokens(norm(w)) for k in keys(t)}   # слова «это про нас»
    ok_words = tvocab | GENERIC_OK | client_ok   # слова сайтов, обычные уточнения и «это про нас» человека
    big_text = len(words_seen) >= BIG_VOCAB
    gone = _assign_queries(Q, glist, other, city_stems, cities, my_city, own, vocab, topic, ok_words, big_text,
                           client_ok)
    for q, why in gone:
        dropped.append((q, why, ", ".join(sorted(Q[q]["src"]))))
        del Q[q]
    _niche_groups(Q, glist, other, niche, topic_masks, own_masks, main, new, city_stems, rivals_light, log)
    if other["queries"]:
        glist.append(other)

    glist = _with_pages(glist, main, main_pages, Q, city_stems, dropped)
    _set_todos(glist, other, seeds, sec_group, new)
    glist.sort(key=lambda g: (g["prio"], -g["score"]))
    check_stop()
    log("Сверяю страницы сайта с группами: title, H1, описание, текст…")
    from . import pages as PG
    PG.audit(sys.modules[__name__], main, comps, glist, Q, city, city_stems)
    cann = PG.cannibal(main, glist)
    from . import geo as GEO
    GEO.faq(glist, Q, keys)
    if not new:
        log("GEO: проверяю, готов ли сайт к ответам нейросетей…")
    geo = GEO.check(folder, main["sections"]) if not offline and not new else {"checks": [], "faq_pages": []}
    out = {"site": main["site"], "host": main["host"], "city": city[0] if city else None,
           "competitors": [c["host"] for c in comps + rivals_light], "light": [c["host"] for c in rivals_light],
           "groups": glist, "queries": Q, "dropped": dropped,
           "wm": bool(wm.get("queries")), "gsc": bool(gsc.get("queries")), "fetched": sug.fetched,
           "made": time.strftime("%d.%m.%Y %H:%M"), "seconds": round(time.time() - t0), "deep": deep,
           "cannibal": cann, "geo": geo, "real": real, "version": VERSION,
           "new_site": ns, "masks": use_masks}
    n_fix = sum(1 for g in glist if g.get("audit") and g["audit"]["problems"])
    log(f"Запросов: {len(Q)} в {len(glist)} группах, отсеяно {len(dropped)}. Страниц с замечаниями: {n_fix}, "
        f"мешают друг другу: {len(cann)}.")
    return out


# ---------------------------------------------------------------- шаги сбора (build)

def _rivals_by_address(rival_hosts, folder, offline, log):
    """Конкуренты по адресу, без проверки: разделы из меню главной (rivals.py)."""
    out = []
    if rival_hosts and not offline:
        from . import rivals as RV
        for h in rival_hosts:
            c = RV.sections(h, folder, log)
            if c["sections"]:
                out.append(c)
            else:
                log(f"У {h} не нашёл разделов в меню главной (возможно, меню рисуется скриптом) - пропускаю. "
                    "Такой сайт лучше проверить на главной странице программы и выбрать здесь.")
    return out


def _seed_phrases(main, sites):
    """Семена - разделы сайтов: фраза → {"sites": {host: [раздел]}, "name", "lv"}."""
    seeds = {}
    for site in sites:
        for sec in site["sections"]:
            ph = norm(sec.get("q") or S.query_form(sec))   # q - текст маски, если человек его поправил
            if not ph:
                continue
            e = seeds.setdefault(ph, {"sites": {}, "name": sec["name"], "lv": 9})
            e["sites"].setdefault(site["host"], []).append(sec)
            # уровень маски: 1 - главная и меню, 2 - разделы, 3 - подразделы и карточки (у конкурентов - 2)
            e["lv"] = min(e["lv"], sec.get("lv") or 2)
            if site is main:
                e["name"] = sec["name"]
    return seeds


def _topic_phrases(main, seeds, folder, new, light):
    """Фразы шире разделов: тема сайта (заголовок главной), свои маски человека, бренды и серии из названий
    товаров. → (niche, topic_masks, own_masks, models)."""
    # тема сайта (заголовок главной): подсказки по ней шире разделов — так видно, чего на сайте нет
    niche = [norm(t) for t in main.get("topic") or [] if norm(t) and (new or norm(t) not in seeds)]
    topic_masks = set(niche)   # «тема + буква» - только по теме главной, не по своим маскам
    # свои маски человека (masks.py): собираются как тема сайта, группы - по их словам
    niche += [norm(t) for t, _lv in main.get("own") or [] if norm(t) and norm(t) not in seeds and norm(t) not in niche]
    own_masks = set(niche) - topic_masks
    # бренды и серии из названий товаров (models.py): маски уровня 3 или, без подтверждённых масок, сами
    models = main.get("models")
    # быстрый сбор (light) - без них. До здесь по ошибке проверялся список конкурентов по адресу (имя light
    # было перекрыто): с конкурентом по адресу бренды и серии не собирались, а в быстром сборе собирались
    if models is None and not new and not light:
        from . import models as MD
        models = [x["t"] for x in MD.seeds(folder)]
    models = [norm(t) for t in models or [] if norm(t) and norm(t) not in seeds and norm(t) not in niche]
    return niche, topic_masks, own_masks, models


def _one(w):
    """Единственное число для подсказок: «технические» → «технический», «аудиты» → «аудит», «услуги» → «услуга».
    Неверная форма не страшна: по ней просто не будет подсказок."""
    pre, _, w = w.rpartition("-")
    for a, b in (("ые", "ый"), ("ие", "ий"), ("ки", "ка"), ("ги", "га"), ("хи", "ха"), ("ы", "")):
        if len(w) > 4 and w.endswith(a):
            w = w[:-len(a)] + b
            break
    return (pre + "-" if pre else "") + w


def shorter(ph):
    """Короткие формы длинной маски: до предлога, потом без первых прилагательных, и у каждой - единственное число.
    «технические seo-аудиты с ручной проверкой» → «технические seo-аудиты», «технический seo-аудит», «seo-аудиты»,
    «seo-аудит». Меньше 3 слов - без форм."""
    w = ph.split()
    if len(w) < 3:
        return []
    head = w[:next((i for i, x in enumerate(w) if i and x in S.PREPS), len(w))]
    out = [head] if len(head) < len(w) else []
    while len(head) > 1 and S.ADJ_END.search(head[0]):
        head = head[1:]
        out.append(head)
    forms = []
    for x in out:
        forms += [" ".join(x), " ".join(_one(t) for t in x)]
    return [f for f in dict.fromkeys(forms) if len(f) >= 4 and f != ph]


def _shorter_tasks(phrases, res, sug, stop, log):
    """Маска, по которой оба поисковика ответили пустыми подсказками (длинный заголовок, слоган): спрашиваем её
    короткие формы, все подсказки идут к самой маске. Без этого у сайта с длинными названиями 0 запросов
    (timurpanin.ru). → {(поисковик, короткая фраза): ([подсказки], маска)}."""
    out = {}
    for ph in dict.fromkeys(phrases):
        if res.get(("yandex", ph)) != [] or res.get(("google", ph)) != []:
            continue   # подсказки есть или сервис не ответил - короче не нужно
        used = []
        for sh in shorter(ph):
            if stop and stop():
                return out
            got = {(e, sh): (v, ph) for e in ("yandex", "google") for v in [sug.get(e, sh)] if v}
            if got:
                used.append(sh)
                out.update(got)
        if used:
            log(f"По «{ph}» подсказок нет - взял короче: " + ", ".join(f"«{x}»" for x in used) + ".")
    if out:
        sug.save()
    return out


def _suggest_tasks(main, seeds, niche, topic_masks, models, city_word, new, deep, use_masks):
    """Что спросить у подсказок: [(поисковик, фраза)] без повторов."""
    tasks = []
    for ph, e in seeds.items():
        tasks += [("yandex", ph), ("yandex", ph + " "), ("google", ph)]
        if city_word and (new or main["host"] in e["sites"]):
            tasks.append(("yandex", ph + " " + city_word))
        # «шкафы-купе на заказ» (так названо на сайте) - подсказки и без «на заказ»: иначе общий спрос «шкаф купе»
        # не собирается вовсе (lk-fabrika)
        if main["host"] in e["sites"] and ph.endswith(" на заказ") and e["lv"] <= 2 and len(ph.split()) >= 3:
            tasks += [("yandex", ph[:-len(" на заказ")]), ("google", ph[:-len(" на заказ")])]
        if deep and main["host"] in e["sites"] and e["lv"] <= 2:   # подразделы и карточки - без «+ буква»
            tasks += [("yandex", f"{ph} {ch}") for ch in DEEP_LETTERS]
    # вопросы людей («… как выбрать», «… что лучше») по главным своим разделам — для плана статей
    if new:   # своих разделов нет: вопросы по разделам, которые есть у большего числа конкурентов
        own = sorted(seeds, key=lambda ph: (-len(seeds[ph]["sites"]),
                                            -max(s["links"] for ss in seeds[ph]["sites"].values() for s in ss)))
    else:
        own = sorted((ph for ph, e in seeds.items() if main["host"] in e["sites"]),
                     key=lambda ph: -max(s["links"] for s in seeds[ph]["sites"][main["host"]]))
    for ph in own[:INFO_SEEDS]:
        tasks += [("yandex", ph + " как"), ("yandex", ph + " что")]
    for ph in niche:
        tasks += [("yandex", ph), ("yandex", ph + " "), ("google", ph)]
        if ph in topic_masks or not use_masks:
            tasks += [("yandex", f"{ph} {ch}") for ch in DEEP_LETTERS]
        if city_word:
            tasks.append(("yandex", ph + " " + city_word))
    for ph in models:   # «оправа christian lacroix», «acuvue oasys»: без «+ буква» - артикулы почти не ищут
        tasks += [("yandex", ph), ("yandex", ph + " ")]
    return list(dict.fromkeys(tasks))   # одна фраза - один запрос, даже если она и раздел, и маска


def _add(Q, q, src, seed=None, pos=None, engine=None, shows=None, clicks=None, place=None, page=None, imp=None):
    """Запрос в общий список Q (одна строка на фразу, источники копятся)."""
    q = norm(q)
    if not q or len(q) > 120:
        return
    r = Q.setdefault(q, {"src": set(), "seeds": set(), "y": None, "g": None, "wm": None, "gsc": None, "imp": None})
    r["src"].add(src)
    if seed:
        r["seeds"].add(seed)
    if engine and pos:
        if r[engine] is None or pos < r[engine]:
            r[engine] = pos
    if src == "Вебмастер":
        r["wm"] = {"shows": shows, "clicks": clicks, "pos": place}
    if src == "Search Console":
        r["gsc"] = {"shows": shows, "clicks": clicks, "pos": place, "page": page or ""}
    if imp:
        r["imp"] = imp


def _real_queries(folder, main, new, offline, log, Q):
    """Настоящие запросы: Вебмастер и Search Console (из проверки или прямо сейчас), файлы человека. → (wm, gsc, real)."""
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))

    def meta(key):
        r = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else None
    wm, gsc = meta("webmaster") or {}, meta("gsc") or {}
    db.close()
    # настоящие запросы: из проверки, а если их там нет — прямо сейчас из Вебмастера и Search Console
    real = {"wm": "ok" if wm.get("queries") else "", "gsc": "ok" if gsc.get("queries") else ""}
    if new:   # сайта нет - и запросов Вебмастера с Search Console нет
        real = {"wm": "new", "gsc": "new"}
    elif not offline and not (real["wm"] and real["gsc"]):
        try:
            from .. import webmaster, search_console
            if not real["wm"]:
                real["wm"], rows = webmaster.queries_for_semantics(main["site"], log)
                wm = dict(wm, queries=rows) if rows else wm
            if not real["gsc"]:
                real["gsc"], rows = search_console.queries_for_semantics(main["site"], log)
                gsc = dict(gsc, queries=rows) if rows else gsc
        except Exception as e:
            log("Настоящие запросы не загружены - " + str(e)[:150])
    for k, name in (("wm", "Яндекс Вебмастер"), ("gsc", "Search Console")):
        log(f"{name}: " + {"ok": "настоящие запросы есть", "not_connected": "вход не подключён - спрос только по подсказкам",
                          "no_access": "сайта нет в подключённом аккаунте (нужен доступ от владельца сайта)",
                          "no_data": "запросов пока нет", "error": "не ответил", "": "не загружался",
                          "no_link": "нет связи (VPN или обрыв)", "no_scope": "у входа Google нет галочки Search Console",
                          "new": "сайта ещё нет - спрос по подсказкам и файлам Вордстата"}.get(real[k], real[k]))
    for q in wm.get("queries") or []:
        ind = q.get("indicators") or {}
        _add(Q, q.get("query_text") or "", "Вебмастер", shows=ind.get("TOTAL_SHOWS"), clicks=ind.get("TOTAL_CLICKS"),
             place=ind.get("AVG_SHOW_POSITION"))
    gsc_pages = {}   # какую страницу Google показывает по запросу: видно, если он показывает не ту
    if gsc.get("queries") and not offline:
        try:
            from .. import search_console
            gsc_pages = search_console.query_pages(main["site"], log)
        except Exception as e:
            log("Search Console: страницы по запросам не загружены - " + str(e)[:150])
    for q in gsc.get("queries") or []:
        _add(Q, q.get("q") or "", "Search Console", shows=q.get("shows"), clicks=q.get("clicks"), place=q.get("pos"),
             page=gsc_pages.get(q.get("q") or ""))
    # запросы из файлов, добавленных на странице «Семантика» (Вордстат, Key Collector, выгрузки Вебмастера и SC)
    from . import imports as IMP
    imp_rows = IMP.rows(main["host"])
    if imp_rows:
        log(f"Запросы из файлов: {len(imp_rows)}.")
    for q, x in imp_rows.items():
        _add(Q, q, "из файла", imp=x)
    if any(x.get("shows") for x in imp_rows.values()):
        real["file"] = "ok"      # показы и места сайта из выгрузки - тоже настоящие данные
    return wm, gsc, real


def _site_vocab(folder, competitors, main, new):
    """Слова со страниц всех сайтов: запрос со словами не отсюда — возможно, про другое.
    → (vocab: title и H1, words_seen: слова текста, tvocab: всё вместе, main_pages: [(адрес, H1 или title)])."""
    vocab = set()
    words_seen = set()
    for f in [folder] + list(competitors):
        d2 = sqlite3.connect(os.path.join(f, "crawl.db"))
        for (t,) in d2.execute("SELECT COALESCE(title, '') || ' ' || COALESCE(h1, '') FROM pages WHERE status=200 "
                               "AND content_type LIKE 'text/html%'"):
            for w in set(tokens(norm(t))):
                vocab |= keys(w)
        # и слова из текста страниц (без меню и подвала - блоки своего текста): слова, которых нет нигде на
        # сайтах, значат «про другое» («торт без декора», «группа безопасности active directory») - в отсеянное
        try:
            for (b,) in d2.execute("SELECT blocks FROM pages WHERE status=200 AND blocks IS NOT NULL LIMIT 5000"):
                try:
                    words_seen.update(tokens(norm(zlib.decompress(b).decode("utf-8"))))
                except Exception:   # noqa: BLE001 - испорченный блок одной страницы
                    pass
        except sqlite3.OperationalError:   # старая проверка без колонки blocks
            pass
        d2.close()
    tvocab = set(vocab)
    for w in words_seen:
        tvocab |= keys(w)
    # слова темы нового сайта и своих масок человека - тоже «со страниц»: человек сам сказал, что это про сайт
    for t in (main.get("topic") or [] if new else []) + [t for t, _lv in main.get("own") or []]:
        for w in tokens(norm(t)):
            vocab |= keys(w)
    db = sqlite3.connect(os.path.join(folder, "crawl.db"))
    main_pages = db.execute("SELECT url, COALESCE(h1, title, '') FROM pages WHERE indexable=1 AND status=200 "
                            "AND content_type LIKE 'text/html%'").fetchall()
    db.close()
    return vocab, words_seen, tvocab, main_pages


def _drop_junk(Q, main, rivals, cities, my_city, topic):
    """Отсев до групп: стоп-слова, повторы, длинные фразы, мусор, чужие города, конкуренты, не по теме.
    Отсеянное убирается из Q; у оставшихся - r["mark"] (статья, галерея) и r["brand"]. → [(запрос, причина, откуда)]."""
    from . import masks as MK
    own_brand = {k for w in main["brand"] for t in tokens(norm(w)) for k in keys(t) if len(t) > 3}
    rival_brand = {k for c in rivals for w in c["brand"] + [c["host"].split(".")[0]]
                   for t in tokens(norm(w)) if len(t) > 3 and not keys(t) & COMMON_BRAND_STEMS
                   for k in keys(t)} - own_brand
    rival_brand |= {"~" + sound(norm(c["host"].split(".")[0])) for c in rivals}
    dropped = []
    user_stop = set(load_stop())   # отмечены пользователем на странице «Семантика»
    from . import dictionary       # и мусорные слова темы сайта («Словарь»)
    user_stop |= set(dictionary.junk_for(main["host"], list(Q)))
    from . import dicts as DI
    dd = DI.load()   # маркеры статей и галереи - словари на странице «Семантика», вкладка «Разложить новые»
    client_stop = MK.stop_hit(main["host"])   # стоп-слова этого клиента (masks.py)
    for q, r in list(Q.items()):
        reason = None
        toks = tokens(q)
        allk = set().union(*[keys(t) for t in toks]) if toks else set()
        r["mark"] = DI.intent_of(q, dd)[0]
        junk = JUNK_RX.search(q) or BU_RX.search(q)
        if junk and r["mark"] and all(m.group(0).strip() in SOFT_JUNK for m in JUNK_RX.finditer(q)) and not BU_RX.search(q):
            junk = None
        if client_stop and (cw := client_stop(q)):
            reason = "стоп-слово клиента: " + cw
        elif user_stop and (sw := set(toks) & user_stop):
            reason = "стоп-слово: " + ", ".join(sorted(sw))
        elif (rep := repeated_word(toks)):
            reason = "слово повторяется: " + rep
        # длинный запрос с покупкой или своим городом - настоящий хвост («изготовление фасадов для кухни на заказ в
        # москве недорого»), до MAX_INFO_WORDS слов, как вопросы
        elif len(toks) > (MAX_INFO_WORDS if r["mark"] == "info" or LONG_OK_RX.search(q)
                          or (my_city and my_city in cities.find(q)) else MAX_QUERY_WORDS):
            reason = "слишком длинная фраза - не запрос"
        elif junk:
            reason = "мусор: " + junk.group(0).strip()
        elif (cs := cities.find(q) - {my_city}):
            reason = "другой город: " + ", ".join(sorted(cs))
        elif allk & rival_brand:
            reason = "название конкурента"
        elif not (allk & topic) and not r["src"] & {"Вебмастер", "Search Console"}:
            reason = "не по теме сайта"
        r["brand"] = bool(allk & own_brand)
        if reason:
            dropped.append((q, reason, ", ".join(sorted(r["src"]))))
            del Q[q]
    return dropped


def _seed_groups(seeds, main, city_stems):
    """Группы по разделам (одинаковые по смыслу разделы разных сайтов - одна группа), длинные первыми.
    → (glist, sec_group: (сайт, раздел) → группа - для вложенности разделов конкурентов)."""
    groups = {}
    sec_group = {}
    for ph, e in seeds.items():
        c = core(ph, city_stems)
        if not c:
            continue
        key = frozenset(_canon(k) for k in c)
        g = groups.setdefault(key, {"name": e["name"], "core": c, "phrases": set(), "main": [], "rivals": {},
                                    "queries": [], "level": 9})
        g["phrases"].add(ph)
        g["level"] = min(g["level"], e["lv"])
        for host, secs in e["sites"].items():
            for s_ in secs:
                sec_group[(host, s_["name"])] = g
            if host == main["host"]:
                g["main"] += [s["url"] for s in secs]
                g["name"] = e["name"]
            else:
                g["rivals"].setdefault(host, []).extend(s["url"] for s in secs)
    return sorted(groups.values(), key=lambda g: -len(g["core"])), sec_group


def _covering_index(glist):
    """covering(qc): группы, все слова которых есть в запросе (то же, что _covers по каждой группе), в порядке glist.
    Индекс: вариант слова → (группа, какое слово группы) - без перебора всех групп."""
    gidx = {}
    for gi, g in enumerate(glist):
        for j, k in enumerate(g["core"]):
            for x in k:
                gidx.setdefault(x, []).append((gi, j))

    def covering(qc):
        hit = {}
        for qk in qc:
            for x in qk:
                for gi, j in gidx.get(x, ()):
                    hit.setdefault(gi, set()).add(j)
        return [glist[gi] for gi in sorted(hit) if len(hit[gi]) == len(glist[gi]["core"])]
    return covering


def _assign_queries(Q, glist, other, city_stems, cities, my_city, own, vocab, topic, ok_words, big_text,
                    client_ok=frozenset()):
    """Каждый запрос - в лучшую группу (или в other); уточнение, намерение, пометка «про другое», оценка спроса.
    → [(запрос, причина)] - отсеять: слов запроса нет на сайтах."""
    covering = _covering_index(glist)
    known = vocab | client_ok   # один раз, а не на каждое слово каждого запроса
    gone = []
    for q, r in Q.items():
        qc = core(q, city_stems)
        best, best_rank = None, None
        for g in covering(qc):
            # главное слово запроса обычно первое: «термопара для газового котла» — это термопары
            rank = (bool(qc) and any(qc[0] & k for k in g["core"]), len(g["core"]),
                    bool(g["phrases"] & r["seeds"]), bool(g["main"]))
            if best is None or rank > best_rank:
                best, best_rank = g, rank
        if best is None:  # подсказка ушла от раздела: к разделу, откуда пришла, если совпадает больше половины
            for g in glist:
                if g["phrases"] & r["seeds"]:
                    hit = sum(1 for k in g["core"] if any(k & x for x in qc))
                    # совпасть должно не только общее слово: «мебель на заказ» из подсказок к «шкафы-купе на заказ»
                    # совпадала одним «заказ» и уводила 130 общих запросов в шкафы-купе (lk-fabrika)
                    real = sum(1 for k in g["core"] if not k & SHARED_STEMS and any(k & x for x in qc))
                    if hit * 2 >= len(g["core"]) and real:
                        best = g
                        break
        g = best or other
        gw = set().union(*g["core"]) if g["core"] else set()
        r["extra"] = " ".join(t for t in tokens(q) if not keys(t) & (gw | MODIFIER_STEMS | city_stems) and len(t) > 1)
        r["intent"] = {"info": "Информация", "gallery": "Галерея"}.get(r.get("mark")) or \
            next((name for name, rx in INTENT if rx.search(q)), "Общий")
        if r["intent"] == "Общий" and my_city and my_city in cities.find(q):
            r["intent"] = "Покупка"
        r["intent"] = refine_intent(q, r["intent"], own)
        # «под ключ» - обычное коммерческое уточнение, а не слово «про другое» («seo продвижение сайтов под ключ» у
        # hightime.agency уходило в «Без группы»: слова «ключ» нет на сайте)
        turnkey = "ключ" if re.search(r"(?<![а-я])под ключ(?![а-я])", q) else None
        extra = [t for t in r["extra"].split() if not re.search(r"\d", t) and not INFO_RX.search(t)
                 and t not in NEUTRAL and t != turnkey]
        # «про нас» человека («топ», «раскрутка») - не «возможно, про другое»: раньше слово спасало запрос только от
        # «Отсеяно», а пометка оставалась, и запрос лежал в «Без группы» (hightime.agency)
        odd = [t for t in extra if not keys(t) & known]
        # слова нет ни в тексте страниц сайтов, ни в заголовках: запрос про другое - в отсеянное (
        # gasprof: «группа безопасности для самогонного аппарата»); настоящие запросы из Вебмастера и Search
        # Console и запросы с показами из файлов не трогаем
        # латиница (марки и модели: «royal thermo insignia») - только пометка: это может быть марка, которой нет на сайте
        # маленький сайт (мало текста) - только пометка: там и обычных слов («женские») может не быть
        foreign = [t for t in odd if len(t) > 2 and re.fullmatch(r"[а-я-]+", t) and not keys(t) & ok_words] \
            if big_text else []
        if foreign and not r["src"] & {"Вебмастер", "Search Console"} and not (r["imp"] or {}).get("shows"):
            gone.append((q, "слов нет на сайтах: " + ", ".join(foreign)))
            continue
        # у раздела из одного слова («Запчасти», «Stout») уточнение должно быть со страниц сайтов,
        # иначе «запчасти на китайские авто», «stout пиво»
        if len(g["core"]) == 1 and extra and len(odd) < len(extra) and not any(keys(t) & topic for t in extra):
            odd = odd or [t for t in extra if not keys(t) & client_ok]   # кроме слов «про нас»
        r["check"] = ""
        if odd and not r["src"] & {"Вебмастер", "Search Console"} and not (r["imp"] or {}).get("shows"):
            r["check"] = "возможно, про другое: на сайтах нет слов «" + ", ".join(odd) + "»"
        ys = max(1, 11 - r["y"]) if r["y"] else 0
        gs = max(1, 11 - r["g"]) if r["g"] else 0
        r["score"] = ys + gs + (3 if r["src"] & {"раздел сайта", "раздел конкурента"} else 0) + \
            (5 if r["wm"] or r["gsc"] or (r["imp"] or {}).get("shows") else 0) + \
            (round(min(10, 2 * math.log10(1 + r["imp"]["freq"]))) if (r["imp"] or {}).get("freq") else 0)
        g["queries"].append(q)
    return gone


def _reextra(Q, qs, gcore, city_stems):
    """Уточнение запроса - относительно его новой группы, а не «Без группы», где оно было почти всем запросом:
    иначе «продвижение» в группе «Seo продвижение сайтов» считалось уточнением, и в дереве сайта у каждой новой
    группы был фильтр-двойник «/seo-prodvizhenie-saytov/prodvizhenie/» (hightime.agency)."""
    gw = set().union(*gcore) if gcore else set()
    for q in qs:
        Q[q]["extra"] = " ".join(x for x in tokens(q) if not keys(x) & (gw | MODIFIER_STEMS | city_stems) and len(x) > 1)


def _niche_groups(Q, glist, other, niche, topic_masks, own_masks, main, new, city_stems, rivals_light, log):
    """Запросы, не подошедшие ни к одному разделу (обычно из подсказок по теме сайта), - свои группы по двум
    главным словам: «курсы английского для детей», «английский по скайпу». Так появляются группы без страницы."""
    if other["queries"]:
        buckets = {}
        # длинная тема первой: «мебель на заказ по индивидуальным размерам» - главная, а не подраздел «мебели на заказ»
        tcores = sorted(((t, core(t, city_stems)) for t in niche), key=lambda x: -len(x[1]))
        for q in other["queries"]:
            if Q[q]["check"]:  # «школа языков евразия», «… ньюбридж» — чужие названия, не тема
                continue
            qc = core(q, city_stems)
            key = None
            for t, tc in tcores:  # запрос по теме сайта: группа по уточнению («… для детей»), без уточнения — главная
                if tc and _covers(qc, tc):
                    rest = [k for k in qc if not any(k & x for x in tc)]
                    key = ("тема", t, _canon(rest[0]) if rest else "")
                    break
            if key is None:
                if len(qc) < 2:
                    continue
                key = frozenset(_canon(k) for k in qc[:2])
            buckets.setdefault(key, []).append(q)
        home = main["site"]
        fold = {}   # тема + слово, которого мало для своей группы: «продвижение сайтов услуги» - к главной
        for key, qs in buckets.items():
            # у нового сайта главная - первое слово темы, остальные слова без уточнений - свои разделы
            is_home = isinstance(key, tuple) and not key[2] and key[1] in topic_masks and (not new or key[1] == niche[0])
            is_own = isinstance(key, tuple) and not key[2] and key[1] in own_masks   # своя маска - группа всегда
            if len(qs) < NICHE_MIN and not is_home and not is_own:
                if isinstance(key, tuple) and key[1] in topic_masks and not new:
                    fold.setdefault(key[1], []).extend(qs)
                continue
            best = min(qs, key=lambda q: (len(q.split()), -Q[q]["score"]))
            name = key[1] if is_home or is_own else best
            gcore = core(name, city_stems)
            glist.append({"name": name[:1].upper() + name[1:], "core": gcore, "phrases": set(),
                          "main": [home] if is_home else [], "rivals": {}, "queries": qs, "niche": not is_home,
                          "level": 1 if is_home else 2})
            _reextra(Q, qs, gcore, city_stems)
            other["queries"] = [q for q in other["queries"] if q not in set(qs)]
        # чистые запросы «тема + одно слово» без своей группы - в группу главной, а не в «Без группы»: там лежали
        # «продвижение сайтов услуги», «… агентство», «… за результат» (hightime.agency). Запросы с
        # пометкой «возможно, про другое» сюда не попадают (в buckets их нет)
        for t, qs in fold.items():
            hg = next((g for g in glist if g["main"] == [home] and g["name"].lower() == t), None)
            if not hg:
                continue
            tc = core(t, city_stems)
            # тема + одно-два слова («… в поисковых системах», «услуги разработка и …»); длиннее - на ручной разбор
            # («ровно одно» после проверки кода вернуло эти запросы в «Без группы»)
            qs = [q for q in qs if sum(1 for k in core(q, city_stems) if not any(k & x for x in tc)) <= 2]
            _reextra(Q, qs, hg["core"], city_stems)
            hg["queries"] += qs
            other["queries"] = [q for q in other["queries"] if q not in set(qs)]
        if (niche or rivals_light) and not new:
            log(f"Групп, которых нет среди разделов сайта (по теме и конкурентам): "
                f"{sum(1 for g in glist if g.get('niche')) + sum(1 for g in glist if not g['main'] and g['rivals'])}.")
    if new and niche and not any(g["main"] for g in glist):
        # первое слово темы - уже раздел конкурента («газовые котлы»): эта группа и есть главная нового сайта
        want = {_canon(k) for k in core(niche[0], city_stems)}
        g = next((g for g in glist if want and {_canon(k) for k in g["core"]} == want), None)
        if g:
            g["main"] = [main["site"]]


def _with_pages(glist, main, main_pages, Q, city_stems, dropped):
    """Карточки товаров с теми же словами - у группы без своего раздела, оценка группы; группы без спроса (одно
    название своей страницы или раздела конкурента) - в отсеянное (дописывается в dropped). → новый glist."""
    sec_urls = {s["url"] for s in main["sections"]}
    page_core = [(u, core(norm(h), city_stems)) for u, h in main_pages if u not in sec_urls]
    from .pages import _Index
    p_idx = _Index([pc for _, pc in page_core])
    for g in glist:
        g["products"] = []
        if not g["main"] and g["core"]:
            g["products"] = [page_core[i][0] for i in p_idx.covering(g["core"])][:1000]
        g["score"] = sum(sorted((Q[q]["score"] for q in g["queries"] if not Q[q]["check"]), reverse=True)[:10])
    glist = [g for g in glist if g["queries"]]
    # своя страница не из меню, которую никто не ищет: в группе одна фраза - её же название, подсказок нет (карточки
    # «Кантри-кухня в шалфейно-зелёном» у lk-fabrika - 93 такие группы из 216) - не группа
    # пункт меню, по которому ищут только его название («seo-продвижение сайтов в германии»): страница есть, группа
    # остаётся, но «Продвигать эту страницу» - неправда, спроса не видно (hightime.agency)
    for g in glist:
        if g["main"] and g.get("level", 9) < 2 and len(g["queries"]) == 1 and Q[g["queries"][0]]["src"] <= {"раздел сайта"}:
            g["no_demand"] = True
    for g in [g for g in glist if g["main"] and g.get("level", 9) >= 2 and not g.get("niche") and len(g["queries"]) == 1]:
        if Q[g["queries"][0]]["src"] <= {"раздел сайта"}:
            glist.remove(g)
            dropped += [(q, "нет спроса: только название страницы сайта", "раздел сайта") for q in g["queries"]]
    # раздел конкурента, который никто не ищет: в группе только его название, подсказок нет — не группа
    for g in [g for g in glist if not g["main"] and g["rivals"] and not g.get("niche")]:
        if all(Q[q]["src"] <= {"раздел конкурента"} for q in g["queries"]):
            glist.remove(g)
            dropped += [(q, "нет спроса: только название раздела конкурента", "раздел конкурента") for q in g["queries"]]
    return glist


def _keyset(g):
    return {_canon(k) for k in g["core"]}


def _set_todos(glist, other, seeds, sec_group, new):
    """Что делать с группой: g["page"], g["near"], g["todo"], g["prio"]."""
    mine = [g for g in glist if g["main"]]
    if new:   # вложенность разделов у конкурентов: какой группе принадлежит раздел-родитель
        for g in glist:
            up = {}
            for ph in g["phrases"]:
                for host, secs in seeds[ph]["sites"].items():
                    for s_ in secs:
                        pg = sec_group.get((host, s_.get("parent")))
                        if pg is not None and pg is not g:
                            up[id(pg)] = (up.get(id(pg), (0, pg))[0] + 1, pg)
            g["_up"] = list(up.values())
    for g in glist:
        ph = min(g["phrases"], key=len) if g["phrases"] else ""
        if not g["main"] and len(g["name"].split()) < len(ph.split()):
            g["name"] = ph[:1].upper() + ph[1:]   # «Настенные» → «Настенные газовые котлы»
        g["page"], g["near"] = (g["main"][0] if g["main"] else ""), ""
        if new and g is not other:
            _todo_new(g, glist, other, _keyset)
        elif g is other:
            g["todo"], g["prio"] = "Разобрать вручную: запросы не подошли ни к одному разделу", 4
        elif g["main"] and g.get("no_demand"):
            # приоритет 1, как у страницы: 4 - это «Без группы» (export.PRIO_KIND), страница пропала бы из дерева сайта,
            # проверки title/H1 и решений
            g["todo"], g["prio"] = "Спроса не видно: ищут только название страницы - продвигать по другим словам", 1
        elif g["main"]:
            g["todo"], g["prio"] = "Продвигать эту страницу", 1
        else:
            ks = _keyset(g)
            parent = max((m for m in mine if _keyset(m) < ks), key=lambda m: len(m["core"]), default=None)
            wider = min((m for m in mine if _keyset(m) > ks), key=lambda m: len(m["core"]), default=None)
            if parent:
                g["todo"], g["prio"], g["near"] = f"Создать подраздел в «{parent['name']}»", 2, parent["main"][0]
            elif wider:
                g["todo"], g["prio"] = f"Вести на «{wider['name']}» или создать общий раздел", 2
                g["near"] = wider["main"][0]
            elif g["products"]:
                g["todo"], g["prio"] = f"Создать раздел: на сайте есть подходящие товары ({len(g['products'])})", 2
                g["near"] = g["products"][0]
            elif g.get("niche"):
                g["todo"], g["prio"] = "Люди ищут, а страницы под это на сайте нет - решить, нужна ли страница", 3
            else:
                g["todo"], g["prio"] = "На сайте такого нет, у конкурента есть - решить, нужна ли страница", 3
    for g in glist:   # новый сайт: петля «раздел в подразделе самого себя» (по словам и по меню) - разрываем
        x, seen = g.get("_parent"), {id(g)}
        while x is not None and id(x) not in seen:
            seen.add(id(x))
            x = x.get("_parent")
        if x is g:
            del g["_parent"]
            g["todo"] = "Создать раздел"
    for g in glist:
        g.pop("_up", None)
        p = g.pop("_parent", None)
        if p:
            g["todo"] = f"Создать подраздел в «{p['name']}»"
