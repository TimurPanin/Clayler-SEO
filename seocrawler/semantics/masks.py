"""Маски семантики: с каких фраз собирать подсказки (по просьбе Тимура, 07.10.2026).

Программа предлагает маски из готовой проверки сайта (seeds.load): тема главной, разделы меню, разделы каталога,
подразделы, карточки товаров. У маски - уровень:
  1 - главная и меню (тема главной и разделы, на которые ссылается почти каждая страница),
  2 - разделы (каталог и подразделы первого уровня),
  3 - подразделы глубже и карточки товаров (карточки - только по выбору, по умолчанию выключены).
Человек видит маски на странице «Семантика», правит текст, выключает лишние, добавляет свои и подтверждает.
После подтверждения сбор идёт только по включённым маскам: подсказки по выключенным не спрашиваются, Вордстат
на их запросы не тратится. Пока маски не подтверждены, сбор - как раньше, по всем разделам.

Здесь же стоп-слова клиента: слова и фразы, запросы с которыми не нужны этому сайту («оптом», «аренда», чужой
бренд). Запросы с ними уходят в «Отсеяно» при сборе и сразу пропадают из семантики и очереди Вордстата
(export.load), собирать заново не нужно. Чужие города, «бесплатно», «своими руками», «б/у» отсеиваются всегда.

Файл - на сайт, не на проверку: «решения семантики/<сайт> - маски.json», не теряется при новой проверке."""
import os
import re
import time

from .. import jsonfile
from .stem import stem

LEVELS = {1: "Главная и меню", 2: "Разделы", 3: "Подразделы и карточки"}
MENU_SHARE = 0.3      # раздел меню: на него ссылается хотя бы такая доля страниц сайта
CARDS_MAX = 200       # карточек товаров в списке масок (самые связанные ссылками)
OWN_MAX = 300         # своих масок
BIG_LEVEL = 300       # разделов больше - сайт большой: разделы предлагаются выключенными, сначала собирается ядро
STOP_MAX = 500
# версия правил, по которым предлагаются маски (seeds.py, words.SERVICE_NAMES). Поменялись правила - старые маски
# той же проверки устарели: окно предлагает обновить их (ручные правки сохраняются). 2 - 28.10.2026: меню сайта со
# страницами в корне, кейсы, словарь и кнопки - не разделы (hightime.agency собирался по маскам 23.10)
# 3 - 28.10.2026 вечер: пункт меню не про тему - по H1 («США и Европа» → «SEO-продвижение сайтов в США»), «Тарифы» - не раздел
# 4 - 28.10.2026 ночь: тема главной из пунктов меню («продвижение сайтов»), когда в заголовках главной её нет
RULES = 4
# похоже на служебную страницу, а не на товар или услугу: предлагается выключенной
SERVICE_RX = re.compile(r"(?<![а-яa-z])(услови|сертификат|как сделать|как оформить|как купить|как заказать|обмен|возврат|магазин[ыа]\b|"
                        r"адреса|пункт\w* выдачи|самовывоз|лояльност|бонус|подарочн|правил|договор|оферт|cookie|"
                        r"персональн|реквизит|вакансии|контакт|о компании|о нас|доставк|оплат|гаранти|отзыв|новост|"
                        r"стать[ия]|блог|акци|скидк|распродаж|франшиз|партн[её]р|оптов)", re.I)


def _path(host):
    from . import decisions
    return decisions.site_file(host, " - маски")


def load(host):
    d = jsonfile.load(_path(host))
    return d if isinstance(d, dict) else {}


def save(host, d):
    from . import decisions
    decisions.save_site_file(host, " - маски", d, indent=0)


def norm(s):
    s = str(s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s\-/+.]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -./")[:120]


# ---------- предложить маски по проверке

SMALL = {"для", "в", "на", "и", "с", "по", "от", "до", "из", "под", "без", "к", "у", "о"}


def _words(t):
    return frozenset(stem(w) for w in t.split() if w not in SMALL)


def _word_depth(ws, all_ws, memo):
    """Вложенность по словам: «запчасти baxi» внутри «запчасти», даже если адреса у них рядом, а не вложены."""
    if ws in memo:
        return memo[ws]
    memo[ws] = 0
    par = [p for p in all_ws if p and p < ws]
    memo[ws] = 1 + max(_word_depth(p, all_ws, memo) for p in par) if par else 0
    return memo[ws]


def _level(sec, by_name, menu_min, wdepth=0):
    depth, p, seen = 0, sec.get("parent"), set()
    while p and p in by_name and p not in seen:
        seen.add(p)
        depth += 1
        p = by_name[p].get("parent")
    depth = max(depth, wdepth)
    if depth == 0 and sec["links"] >= menu_min:
        return 1, "меню"
    if depth <= 1:
        return 2, "раздел" if depth == 0 else "подраздел"
    return 3, "подраздел"


def propose(folder, log=print):
    """Маски из проверки (папка folder). Прежние правки человека сохраняются: текст, вкл/выкл, уровень, свои маски.
    Появились новые маски - их надо подтвердить ещё раз. Возвращает словарь файла масок."""
    from . import seeds as S
    t0 = time.time()
    log("маски: читаю разделы сайта из проверки (на большом сайте это до минуты)…")
    main = S.load(folder, cards=CARDS_MAX)
    host = main["host"]
    log(f"маски: разделов {len(main['sections'])}, карточек для выбора {len(main.get('cards') or [])} "
        f"({round(time.time() - t0)} с)")
    menu_min = max(S.MIN_LINKING_PAGES, MENU_SHARE * (main.get("pages") or 0))
    by_name = {s["name"]: s for s in main["sections"]}
    found = []
    for t in main.get("topic") or []:
        found.append({"k": "t:" + norm(t), "t": norm(t), "name": t, "lv": 1, "src": "главная", "url": main["site"],
                      "links": 0})
    texts = {s["url"]: norm(S.query_form(s)) for s in main["sections"]}
    all_ws, memo = {_words(t) for t in texts.values()}, {}
    for s in sorted(main["sections"], key=lambda s: -s["links"]):
        lv, src = _level(s, by_name, menu_min, _word_depth(_words(texts[s["url"]]), all_ws, memo))
        found.append({"k": "u:" + s["url"], "t": texts[s["url"]], "name": s["name"], "lv": lv, "src": src,
                      "url": s["url"], "links": s["links"]})
    try:   # бренды и серии из названий товаров: «оправа christian lacroix», «acuvue oasys» (models.py)
        from . import models
        for x in models.seeds(folder):
            found.append({"k": "m:" + x["t"], "t": x["t"], "name": x["t"], "lv": 3, "src": x["src"], "url": "",
                          "links": x["n"], "on": True, "note": f"товаров {x['n']}, например «{x['ex'][:80]}»"})
    except Exception as e:   # noqa: BLE001 - без них маски всё равно нужны
        log(f"маски: бренды и серии из названий товаров не разобраны ({str(e)[:100]})")
    for c in main.get("cards") or []:
        found.append({"k": "c:" + c["url"], "t": norm(c["name"]), "name": c["name"], "lv": 3, "src": "карточка",
                      "url": c["url"], "links": c["links"], "on": False})
    # одна маска на одну фразу: «котлы газовые» и «газовые котлы» - одно (первой - с большим числом ссылок)
    seen, uniq = {}, []
    for m in found:
        key = frozenset(stem(w) for w in m["t"].split())
        if not m["t"]:
            continue
        if key in seen:   # та же фраза у другой страницы: страница идёт вместе с первой маской
            if m["k"].startswith("u:"):
                seen[key].setdefault("also", []).append(m["k"])
            continue
        seen[key] = m
        if "on" not in m:
            m["on"] = m["lv"] <= 2 and not SERVICE_RX.search(m["name"])
            if SERVICE_RX.search(m["name"]):
                m["note"] = "похоже на служебную страницу"
        uniq.append(m)
    # большой сайт: сначала ядро (главная и меню), разделы - вторым сбором, когда ядро уже видно
    if sum(1 for m in uniq if m["lv"] == 2) > BIG_LEVEL:
        for m in uniq:
            if m["lv"] == 2 and m["on"]:
                m["on"] = False
    old = load(host)
    prev = {m["k"]: m for m in old.get("masks") or []}
    fresh = 0
    out = []
    for m in uniq:
        p = prev.get(m["k"])
        if p:   # человек уже видел: его текст, вкл/выкл и уровень
            m.update(on=p.get("on", m["on"]), lv=p.get("lv", m["lv"]))
            if p.get("edited"):
                m.update(t=p["t"], edited=True)
        else:
            m["new"] = bool(prev)
            fresh += bool(prev)
        out.append(m)
    out += [m for m in old.get("masks") or [] if m.get("src") == "своя"]
    # маска, текст которой человек правил, а новые правила её больше не предлагают (кейсы, «Тарифы»), - остаётся:
    # окно обещает «Ваши правки сохранятся» (проверка кода 28.10.2026)
    have = {m["k"] for m in out}
    out += [m for m in old.get("masks") or [] if m.get("edited") and m.get("src") != "своя" and m["k"] not in have]
    d = {"host": host, "site": main["site"], "folder": os.path.basename(os.path.normpath(folder)),
         "made": time.strftime("%d.%m.%Y %H:%M"), "rules": RULES, "masks": out, "stop": old.get("stop") or [],
         "confirmed": bool(old.get("confirmed")) and not fresh, "at": old.get("at") if not fresh else ""}
    save(host, d)
    n = {lv: sum(1 for m in out if m["lv"] == lv and m["on"]) for lv in LEVELS}
    all3 = sum(1 for m in out if m["lv"] == 3)
    # «подразделы и карточки 0» читалось как ошибка: пишем, нашлись ли они вообще (17.10.2026)
    deep = ("подразделов и карточек на сайте не нашлось (структура плоская)" if not all3 else
            f"подразделы и карточки - {all3}, включено {n[3]} (их включают по выбору)" if n[3] < all3 else
            f"подразделы и карточки - {all3}")
    log(f"маски готовы: {len(out)} - главная и меню {n[1]}, разделы {n[2]}, {deep}"
        + (f"; новых с прошлого раза {fresh}" if fresh else ""))
    return d


def update(host, masks=None, stop=None, confirmed=None):
    """Правки со страницы «Семантика»: маски целиком (текст, уровень, вкл/выкл, свои), стоп-слова, подтверждение."""
    d = load(host)
    d.setdefault("host", host)
    if masks is not None:
        prev = {m["k"]: m for m in d.get("masks") or []}
        out, keys = [], set()
        for x in masks:
            if not isinstance(x, dict):
                continue
            t = norm(x.get("t"))
            k = str(x.get("k") or "")
            if not t or (k and k in keys):
                continue
            if not k or k.startswith("o:") or k not in prev:   # своя маска
                k = "o:" + t
                if k in keys or sum(1 for m in out if m.get("src") == "своя") >= OWN_MAX:
                    continue
                m = {"k": k, "t": t, "name": t, "src": "своя", "url": "", "links": 0}
            else:
                m = dict(prev[k])
                if t != m["t"]:
                    m.update(t=t, edited=True)
            lv = x.get("lv")
            m["lv"] = lv if lv in LEVELS else m.get("lv", 2)
            m["on"] = bool(x.get("on", True))
            m.pop("new", None)
            keys.add(k)
            out.append(m)
        d["masks"] = out
    if stop is not None:
        words = []
        for w in stop:
            w = norm(w)
            if w and w not in words:
                words.append(w)
        d["stop"] = words[:STOP_MAX]
    if confirmed is not None:
        d["confirmed"] = bool(confirmed)
        d["at"] = time.strftime("%d.%m.%Y %H:%M") if confirmed else ""
    save(host, d)
    return d


# ---------- маски в сборе (semantics.build)

def for_build(main, log=print, light=False):
    """Подтверждённые маски → разделы и тема сайта для сбора (main меняется на месте). Нет подтверждения - None,
    сбор как раньше. Возвращает {уровень: включено}.
    light - быстрый сбор очереди сайтов: маски и без подтверждения (как предложила программа), только уровни 1-2."""
    d = load(main["host"])
    if not d.get("masks") or not (d.get("confirmed") or light):
        return None
    every = d["masks"]
    if light:
        d = dict(d, masks=[m for m in d["masks"] if (m.get("lv") or 2) <= 2])
    on = {m["k"]: m for m in d["masks"] if m.get("on")}
    for m in list(on.values()):   # страницы с той же фразой, что у маски (masks.propose: «also»)
        for k in m.get("also") or []:
            on.setdefault(k, m)
    known = {k for m in every for k in [m["k"]] + (m.get("also") or [])}
    secs, unknown = [], 0
    for s in main["sections"]:
        k = "u:" + s["url"]
        if k in on:   # текст маски, который человек не правил, - как сейчас считает программа (seeds.query_form:
            # 15.10.2026 короткие пункты меню получили слово темы - старые маски «детские» сами станут «детская мебель…»)
            from .seeds import query_form
            q = on[k]["t"] if on[k].get("edited") or on[k]["k"] != k else norm(query_form(s))
            secs.append(dict(s, q=q, lv=on[k]["lv"]))
        elif k not in known:
            unknown += 1
    active = [m for m in d["masks"] if m.get("on")]
    for m in active:
        if m["k"].startswith("c:"):
            secs.append({"name": m["name"], "url": m["url"], "links": m.get("links") or 0, "h1": "", "parent": None,
                         "q": m["t"], "lv": m["lv"]})
    main["sections"] = secs
    main["topic"] = [m["t"] for m in active if m["k"].startswith("t:")]
    main["own"] = [(m["t"], m["lv"]) for m in active if m["k"].startswith("o:")]
    main["models"] = [m["t"] for m in active if m["k"].startswith("m:")]
    n = {lv: sum(1 for m in active if m["lv"] == lv) for lv in LEVELS}
    off = len(d["masks"]) - len(active)
    log(("Быстрый сбор: только главная и разделы. " if light else "")
        + (f"Маски подтверждены {d.get('at') or ''}" if d.get("confirmed") else "Маски предложены программой и ещё не подтверждены")
        + f": включено {len(active)} (главная и меню {n[1]}, разделы {n[2]}, "
        f"подразделы и карточки {n[3]}), выключено {off} - по ним подсказки не собираются."
        + (f" Разделов, которых нет в масках: {unknown} - они не собираются; чтобы их увидеть, предложите маски заново."
           if unknown else ""))
    return n


# ---------- стоп-слова клиента

def matcher(words):
    """Стоп-слова → функция «запрос → какое стоп-слово в нём» (или ""). Слово от 5 букв - по основе
    («бесплатно» ловит «бесплатный»), короче - точно; фраза - целиком подряд."""
    exact, stems, phrases = {}, {}, []
    for w in words or []:
        w = norm(w)
        if not w:
            continue
        if " " in w:
            phrases.append(w)
        elif len(w) >= 5 and re.fullmatch(r"[а-я]+", w):
            stems[stem(w)] = w
        else:
            exact[w] = w
    if not (exact or stems or phrases):
        return None

    def hit(q):
        q = norm(q)
        for t in re.findall(r"[a-zа-я0-9]+(?:[-/][a-zа-я0-9]+)*", q):
            if t in exact:
                return exact[t]
            if stems and len(t) >= 5 and stem(t) in stems:
                return stems[stem(t)]
        pad = f" {q} "
        return next((p for p in phrases if f" {p} " in pad), "")
    return hit


def set_ok(host, add=(), remove=()):
    """Слова «это про нас» (15.10.2026): запросы с ними не уходят в «Отсеяно → слов нет на сайтах», хотя на страницах
    сайта этих слов нет («пурмо» - марка радиаторов, которую сайт может привезти). Возвращает список слов."""
    d = load(host)
    d.setdefault("host", host)
    cur = [w for w in d.get("ok") or [] if w not in {norm(x) for x in remove}]
    for w in add:
        w = norm(w)
        if w and w not in cur:
            cur.append(w)
    d["ok"] = cur[:STOP_MAX]
    save(host, d)
    return d["ok"]


def stop_hit(host):
    return matcher(load(host).get("stop") or [])


def drop_stopped(data):
    """Семантика при чтении (export.load): запросы со стоп-словами клиента - в «Отсеяно». Так стоп-слово действует
    сразу: в окне, в отчётах и в очереди Вордстата, без нового сбора."""
    if not data or not data.get("groups") or not data.get("host"):
        return data
    hit = stop_hit(data["host"])
    if not hit:
        return data
    gone = []
    for g in data["groups"]:
        keep = []
        for r in g.get("q") or []:
            w = hit(r[0])
            if w:
                gone.append(r[0])
            else:
                keep.append(r)
        g["q"] = keep
    if gone:
        dr = data.setdefault("dropped", {})
        dr["стоп-слово клиента"] = sorted(set(dr.get("стоп-слово клиента") or []) | set(gone))
        data["total"] = max(0, (data.get("total") or 0) - len(gone))
    return data


def stop_candidates(data, limit=20):
    """Подсказка для стоп-слов: слова из запросов «возможно, про другое» (их нет на страницах сайтов), частые первыми."""
    if not data:
        return []
    cnt = {}
    for g in data.get("groups") or []:
        for r in g.get("q") or []:
            m = re.search(r"«([^»]+)»", r[7] or "") if len(r) > 7 and r[7] else None
            for w in (m.group(1).split(", ") if m else []):
                w = norm(w)
                if len(w) > 2:
                    cnt[w] = cnt.get(w, 0) + 1
    d = load(data.get("host") or "")
    have = set(d.get("stop") or []) | set(d.get("ok") or [])   # и уже отмеченные «про нас»
    from .words import INTENT, MODIFIERS   # вопросы и «купить» - не про другое, а про намерение
    info = INTENT[0][1]
    skip = MODIFIERS | {"такое", "значит", "состоит", "фирмы", "фирма", "это", "лучше", "какая", "какие", "каких"}
    return [w for w, n in sorted(cnt.items(), key=lambda x: -x[1])
            if n >= 2 and w not in have and w not in skip and not info.search(w)][:limit]


def view(host, folder="", sem=None):
    """Для окна: маски сайта, устарели ли (есть проверка новее), подсказки стоп-слов."""
    d = load(host)
    return {"host": host, "masks": d.get("masks") or [], "stop": d.get("stop") or [], "confirmed": bool(d.get("confirmed")),
            "at": d.get("at") or "", "made": d.get("made") or "", "folder": d.get("folder") or "",
            "stale": bool(d.get("masks")) and (bool(folder) and d.get("folder") != os.path.basename(os.path.normpath(folder))
                                               or (d.get("rules") or 1) < RULES),
            "stale_rules": bool(d.get("masks")) and (d.get("rules") or 1) < RULES,
            "levels": LEVELS, "candidates": stop_candidates(sem), "ok": d.get("ok") or []}
