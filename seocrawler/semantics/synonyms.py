"""Синонимы сайта: «бойлер» и «водонагреватель», «сто» и «автосервис», «ноут» и «ноутбук».

Словарь - на странице «Словарь» (dictionary.py): темы «Общий» → ниша → подтема, виды «Синонимы», «Единицы и цифры»,
«Опечатки и раскладка» работают здесь одинаково. Одно слово в разных нишах значит разное: «батарея» у котлов -
радиатор, у телефонов - аккумулятор; «сто» у автосервиса - автосервис, а не 100.

Здесь:
- apply - синонимы держатся в одной группе (при чтении семантика.json), строки не склеиваются, как формы слова
  (forms.py): у них своя частота, и обе фразы нужны в тексте;
- suggest - пары, которые программа нашла сама: слова с одинаковыми хвостами в запросах («ремонт X уфа» и
  «ремонт Y уфа»), одно звучание латиницей и по-русски (vin = вин), сокращение (пк = персональный компьютер).
  Человек отвечает «да, это одно» (строка в словарь темы сайта) или «нет» (больше не предлагать).
Короткие слова (3 буквы и меньше: «сто», «ми», «се») заменяются, только если в запросе нет цифр: «100 литров» -
не автосервис."""
import functools
import itertools
import re

from . import City, _canon, keys, norm, tokens
from . import dicts as DI
from . import dictionary as D
from .stem import sound, stem

SHORT = 3            # слово такой длины и короче - осторожно (омонимы: «сто», «ми», «лед»)
SUGGEST = 40         # столько пар показывать
MIN_SCORE = 0.25     # меньше - не показывать
NEG = {"без", "не", "нет"}
# служебные слова, стандарты и документы - не синонимы ничему
SERVICE = set("""гост снип сп ту окпд оквэд косгу кбк тн вэд iso din en отзывы отзыв называется пишется значит означает
это такое фото видео схема схемы чертеж чертежи размеры размер характеристики инструкция цена цены стоимость купить
заказать отзыв рейтинг лучший лучшие официальный сайт адрес телефон номер""".split())
CTX_MAX = 40         # «хвост», с которым встречается больше слов, слишком общий («купить X»)
pair_key, tidy, detect = D.pair_key, D.tidy, D.detect


def niche_of(data, st=None):
    """(тема сайта, выбрана ли человеком). Пустая - только «Общий»."""
    return D.site_node(data, st)


def lines_for(data, st=None):
    """Действующие строки синонимов, единиц и опечаток сайта: «Общий» → ниша → подтема."""
    return D.lines(data, D.SYN_KINDS, st)


# ---------- применить: синонимы - в одну группу

def words(lines):
    """assign.Words со словарями «не учитывать» и синонимами (общими и этими)."""
    from .assign import Words
    d = DI.load()
    return Words(dict(d, synonyms=list(d["synonyms"]) + list(lines)))


def apply(data, store=None):
    """Запросы, которые отличаются только синонимом («бойлер косвенного нагрева» и «водонагреватель косвенного
    нагрева»), - в одну группу: туда, где их больше (при равенстве - где запрос с большей оценкой). Группа, из которой
    уходит последний запрос, его не отдаёт. Строки не склеиваются. Что переехало - data["syn"]["moved"]."""
    if not data or not data.get("groups") or data.get("syn") is not None:
        return data
    st = store or D._load()
    nid, own = niche_of(data, st)
    lines = lines_for(data, st)
    data["syn"] = {"niche": nid, "own": own, "moved": []}
    W, P = words(lines), words([])
    by = {}
    for g in data["groups"]:
        for r in g.get("q") or []:
            k = W.of(r[0])
            if k:   # «без дымохода» и «для дымохода» - разное, хотя «без» и «для» не учитываются
                by.setdefault((k, bool(NEG & set(tokens(norm(r[0]))))), []).append((g, r))
    left = {id(g): len(g.get("q") or []) for g in data["groups"]}
    multi = [lst for lst in by.values() if len({id(g) for g, _ in lst}) > 1 and len({P.of(r[0]) for _, r in lst}) > 1]
    # куда переносить - одинаково для всех запросов пары групп: в группу, где таких запросов больше всего по всему
    # сайту (иначе «Газовые колонки» и «Проточные водонагреватели» обменялись бы запросами)
    pull = {}
    for lst in multi:
        for g, r in lst:
            pull[id(g)] = pull.get(id(g), 0) + 1
    moves = []
    for lst in multi:
        gs = {id(g): g for g, _ in lst}
        real = [g for g in gs.values() if g.get("kind") != "manual"] or list(gs.values())
        n = {}
        for g, _ in lst:
            n[id(g)] = n.get(id(g), 0) + 1
        top = max((r for _, r in lst), key=lambda r: r[3] or 0)[0]
        W.of(top)
        first = W.first.get(top)    # главное слово запроса - в названии группы: «дымоход для колонки» - в «Дымоходы»
        to = max(real, key=lambda g: (first in W.of(g["name"]), n[id(g)], pull[id(g)], g.get("score") or 0,
                                      -data["groups"].index(g)))
        for g, r in lst:
            if g is not to and left[id(g)] > 1:
                left[id(g)] -= 1
                moves.append((g, r, to))
    for g, r, to in moves:
        g["q"].remove(r)
        to["q"].append(r)
        data["syn"]["moved"].append([r[0], g["name"], to["name"]])
    for g in {id(to): to for _, _, to in moves}.values():
        g["q"].sort(key=lambda r: (bool(r[7]) if len(r) > 7 else False, -(r[3] or 0)))
    return data


# ---------- найти пары «похоже на синонимы»

ADJ_END = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ого", "его", "ых", "их")
LAT = re.compile(r"[a-z]")


def _adj(w):
    return " " not in w and w.endswith(ADJ_END) and len(w) > 4


def _why(a, b):
    """Особая примета пары: одно слово латиницей и по-русски, сокращение, короткое название («циркуляционник»)."""
    sa, sb = a.split(), b.split()
    if len(sa) == 1 and len(sb) == 1:
        if bool(LAT.search(a)) != bool(LAT.search(b)) and sound(a) == sound(b):
            return "пишут латиницей и по-русски"
        return ""
    one, two = (a, sb) if len(sa) == 1 else (b, sa) if len(sb) == 1 else (None, None)
    if not one or len(two) != 2:
        return ""
    if 2 <= len(one) <= 4 and "".join(w[0] for w in two) == one:
        return "сокращение"
    st = stem(one)
    if len(two[0]) >= 6 and st.endswith("к") and not _adj(two[1]) and one.startswith(two[0][:6]) and stem(two[0]) != st:
        return "короткое название"
    return ""


@functools.lru_cache(maxsize=200_000)
def _cn(t):
    return _canon(keys(t))


QUOTE_RX = [
    re.compile(r"([а-яёa-z][а-яёa-z\- ]{1,60}?)\s*\(([а-яёa-z][а-яёa-z\- ]{1,40})\)"),
    re.compile(r"([а-яёa-z][а-яёa-z\- ]{1,60}?),?\s+(?:он|она|оно|они) же\s+([а-яёa-z][а-яёa-z\- ]{1,40})"),
    re.compile(r"([а-яёa-z][а-яёa-z\- ]{1,60}?),?\s+(?:то есть|иначе говоря|иначе|по-другому|в народе|так называемый|"
               r"так называемая|также называют)\s+([а-яёa-z][а-яёa-z\- ]{1,40})"),
]
_TEXTS = {}


def _texts(folder):
    """Заголовки, H1, описания, начало текста и подписи картинок страниц проверки (crawl.db)."""
    import os
    import sqlite3
    db = os.path.join(folder, "crawl.db")
    try:
        mt = os.path.getmtime(db)
    except OSError:
        return []
    if _TEXTS.get(db, (None,))[0] == mt:
        return _TEXTS[db][1]
    out, seen = [], set()
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for row in c.execute("SELECT url, title, h1, description, text_sample FROM pages WHERE status = 200"):
            for t in row[1:]:
                if t and "(" in t or t and " же " in t or t and "то есть" in t:
                    if t not in seen:
                        seen.add(t)
                        out.append((row[0], str(t)))
        c.close()
    except sqlite3.Error:
        pass
    _TEXTS[db] = (mt, out)
    return out


def _evidence(data, seen, bw=frozenset()):
    """[(слово, слово, примета, цитата)]: сокращения из запросов и пары из текста своего сайта и конкурентов.
    seen - слова и фразы из двух слов, которые есть в запросах: {основы: как пишут}."""
    import os
    from ..window import REPORTS
    from .plan import _rival_folders
    by = {}
    for u, w in seen.items():
        by[u] = w
    out = []
    # сокращение: короткое слово = первые буквы 2-4 слов подряд из других запросов
    qs = [tokens(norm(r[0])) for g in data.get("groups") or [] for r in g.get("q") or []]
    rest = lambda q, i, n: frozenset(_cn(t) for t in q[:i] + q[i + n:])
    short = {}
    for q in qs:
        for i, t in enumerate(q):
            if 2 <= len(t) <= 4 and t.isalpha() and len(q) > 1:
                short.setdefault(t, set()).add(rest(q, i, 1))
    found = {}
    for q in qs:
        for n in (2, 3, 4):
            for i in range(len(q) - n + 1):
                ws = q[i:i + n]
                ab = "".join(w[0] for w in ws)
                if ab in short and all(len(w) >= 3 for w in ws) and ab not in ws and len(q) > n                         and rest(q, i, n) in short[ab]:
                    found[(ab, " ".join(ws))] = 1
    cnt = {}
    for q in qs:
        j = " ".join(q)
        for a, b in found:
            if f" {a} " in f" {j} ":
                cnt[a] = cnt.get(a, 0) + 1
            if f" {b} " in f" {j} ":
                cnt[b] = cnt.get(b, 0) + 1
    city = City().stems
    for a, b in found:
        ws = b.split()
        if cnt.get(a, 0) < 2 or cnt.get(b, 0) < 2:   # и сокращение, и полное название ищут не один раз
            continue
        if not all(w.isalpha() for w in ws) or any(keys(w) & city for w in ws) or any(_cn(w) in bw for w in ws):
            continue        # «ру = рено уфа», «лг = лада гранта»
        out.append((a, b, "сокращение", ""))
    # текст сайта и конкурентов: «X (Y)», «X, он же Y», «X, то есть Y»
    folders = list(_rival_folders(REPORTS, [data.get("host") or ""] + list(data.get("competitors") or [])).values())
    canon = lambda s: tuple(_cn(t) for t in tokens(norm(s)))
    done = set()
    for f in folders:
        for url, text in _texts(f):
            low = text.lower().replace("ё", "е")
            for rx in QUOTE_RX:
                for m in rx.finditer(low):
                    xs, ys = canon(m.group(1)), canon(m.group(2))
                    for i in range(1, min(2, len(xs)) + 1):
                        for j in range(1, min(2, len(ys)) + 1):
                            a, b = xs[-i:], ys[:j]
                            if a in by and b in by and a != b and not set(a) & set(b) and (a, b) not in done                                     and _adj(by[a].split()[-1]) == _adj(by[b].split()[-1]):
                                done.add((a, b))
                                q = text[max(0, m.start() - 30):m.end() + 30].strip()
                                out.append((by[a], by[b], "так написано на сайте", f"«{q}» - {url}"))
    return out


def suggest(data, store=None, limit=SUGGEST):
    """Пары слов или фраз из двух слов, которые встречаются в запросах с одинаковыми хвостами и не вместе.
    [{a, b, why, n, ex: [[запрос с a, запрос с b], …], short}] - самые вероятные первыми."""
    st = store or D._load()
    no = D.rejected(data, st)
    known = words(D.all_lines(st))   # уже записано в любую тему (вин = vin у автосервиса) - не предлагать
    homo = D.homonyms(st)
    N = D.nodes(st)
    site_nid = D.site_node(data, st)[0] or D.ROOT
    hstem = {stem(w): w for w in homo if " " not in w}
    W = words(lines_for(data, st))
    d = DI.load()
    ign = set()
    for w in DI.active(d["ignore"]):
        for t in tokens(w):
            ign |= keys(t)
    city = City().stems
    info = DI.Markers(d["info"])
    ctx_units, unit_ctx, word, ex, cooc, ugroup = {}, {}, {}, {}, {}, {}
    # слова брендов из всех тем: слово сразу после бренда - модель («уаз буханка», «лада приора»), не синоним
    bw = {_canon(keys(t)) for line in D.all_lines(st, ("brand",)) for t in tokens(norm(line.replace("=", ",")))}
    after = {}
    gname = {}
    for g in data.get("groups") or []:
        for r in g.get("q") or []:
            q = r[0]
            toks = [(t, _canon(keys(t))) for t in tokens(norm(q))
                    if not (keys(t) & ign or keys(t) & city or (len(t) == 1 and not t.isdigit()))]
            if len(toks) < 2:
                continue
            cs = [c for _, c in toks]
            units = [((cs[i],), cs[:i] + cs[i + 1:], t) for i, (t, _) in enumerate(toks) if not any(ch.isdigit() for ch in t)]
            units += [((cs[i], cs[i + 1]), cs[:i] + cs[i + 2:], toks[i][0] + " " + toks[i + 1][0])
                      for i in range(len(toks) - 1) if not any(ch.isdigit() for ch in toks[i][0] + toks[i + 1][0])]
            for i, (t, c) in enumerate(toks):
                a = after.setdefault((c,), [0, 0])
                a[1] += 1
                if i and (toks[i - 1][1] in bw or LAT.search(toks[i - 1][0])):
                    a[0] += 1
            for u, ctx, w in units:
                if not ctx:
                    continue
                ctx = tuple(sorted(ctx))
                ctx_units.setdefault(ctx, set()).add(u)
                unit_ctx.setdefault(u, set()).add(ctx)
                word.setdefault(u, {}).setdefault(w, 0)
                word[u][w] += 1
                ugroup.setdefault(u, {}).setdefault(g["name"], 0)
                ugroup[u][g["name"]] += 1
                ex.setdefault((ctx, u), q)
            for a, b in itertools.combinations({u for u, _, _ in units}, 2):
                cooc[(a, b)] = cooc[(b, a)] = cooc.get((a, b), 0) + 1
    lat = {sound(w) for ws in word.values() for w in ws if " " not in w and LAT.search(w)}

    def own_group(u):
        """Группа, где почти все запросы с этим словом и оно есть в её названии."""
        gs = ugroup.get(u) or {}
        if not gs:
            return None
        top = max(gs, key=gs.get)
        if gs[top] < 0.6 * sum(gs.values()):
            return None
        if top not in gname:
            gname[top] = {_canon(keys(t)) for t in tokens(norm(top))}
        return top if set(u) <= gname[top] else None

    def brand(w):
        return " " not in w and (bool(LAT.search(w)) or sound(w) in lat)
    shared = {}
    for ctx, us in ctx_units.items():
        if len(us) > CTX_MAX:
            continue
        for a, b in itertools.combinations(sorted(us), 2):
            if not set(a) & set(b):
                shared.setdefault((a, b), []).append(ctx)
    deg = {}             # со сколькими словами слово делит хвосты: у синонима пара-две, у «испанского» - все языки
    for (a, b), ctxs in shared.items():
        if len(ctxs) >= 2:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
    out = []
    for (a, b), ctxs in shared.items():
        wa = max(word[a], key=word[a].get)
        wb = max(word[b], key=word[b].get)
        if pair_key(wa, wb) in no or known.of(wa) == known.of(wb):
            continue
        why = _why(wa, wb)
        n = len(ctxs)
        short = any(" " not in w and len(w) <= SHORT and not LAT.search(w) for w in (wa, wb)) and not why
        if n < (1 if why == "пишут латиницей и по-русски" else 2 if why else 4 if short else 3):
            continue
        if not why and (brand(wa) or brand(wb)):   # разные бренды: honda и yamaha, бакси и навьен
            continue
        if bool(info.find(wa)) != bool(info.find(wb)):   # «как выбрать» и «штиль»: вопрос и товар
            continue
        if W.of(wa) == W.of(wb):    # уже синонимы или одно слово
            continue
        jac = n / (len(unit_ctx[a]) + len(unit_ctx[b]) - n)
        if not why:
            # строгий отбор: у синонимов обычно два варианта, а у вещей одного ряда - много
            if jac < 0.12 or cooc.get((a, b), 0) >= 2:   # не раз вместе в одном запросе - разные вещи
                continue
            if any(len(u) == 1 and after.get(u, [0, 1])[0] * 2 >= after.get(u, [0, 1])[1] for u in (a, b)):
                continue        # модели после бренда: «уаз буханка» и «уаз патриот»
            if bw & (set(a) | set(b)):   # сам бренд
                continue
            if deg.get(a, 0) >= 3 or deg.get(b, 0) >= 3:   # «испанского» делит хвосты со всеми языками
                continue
            if sum(1 for c in ctxs if len(ctx_units[c]) >= 3) * 2 >= n:   # на этом месте в запросе 3+ разных слова
                continue
            if own_group(a) and own_group(b) and own_group(a) != own_group(b):   # у каждого своя группа
                continue
            if set(wa.split()) & SERVICE or set(wb.split()) & SERVICE:   # гост, отзывы, называется
                continue
        score = n * jac + (5 if why else 0)
        if _adj(wa) and _adj(wb) and not why:   # газовый и электрический - разные котлы
            score *= 0.4
        if len(a) == 2 and len(b) == 2:
            score *= 0.7
        if score < MIN_SCORE:
            continue
        exs = sorted(ctxs, key=lambda c: -len(c))[:3]
        hw = next((w for w in (wa, wb) if w in homo or stem(w) in hstem), None)
        exq = [q for c in ctxs for q in (ex[(c, a)], ex[(c, b)])]
        out.append({"a": wa, "b": wb, "why": why, "n": n, "short": short and not hw, "score": round(score, 3),
                    "node": D.niche_for(exq, site_nid, N),
                    "homonym": f"{hw}: {homo.get(hw) or homo.get(hstem.get(stem(hw), ''), '')}" if hw else "",
                    "ex": [[ex[(c, a)], ex[(c, b)]] for c in exs]})
    # доказательства сверх написания: сокращение из 2-4 слов (гбм = группа быстрого монтажа) и текст сайта и
    # конкурентов («циркуляционный насос (циркуляционник)», «экспанзомат, он же расширительный бак»)
    have = {(x["a"], x["b"]) for x in out}
    seen = {}
    for u, ws in word.items():
        seen[u] = max(ws, key=ws.get)
    cu = {w: u for u, w in seen.items()}

    def shared_w(a, b):
        ua, ub = cu.get(a), cu.get(b)
        return bool(ua and ub and (shared.get((ua, ub)) or shared.get((ub, ua))))
    for a, b, why, quote in _evidence(data, seen, bw):
        if pair_key(a, b) in no or known.of(a) == known.of(b) or W.of(a) == W.of(b):
            continue
        x = next((y for y in out if {y["a"], y["b"]} == {a, b}), None)
        if x:
            x["why"], x["quote"], x["score"] = x["why"] or why, quote, x["score"] + 5
        elif (a, b) not in have and (why == "сокращение" or shared_w(a, b)):
            out.append({"a": a, "b": b, "why": why, "n": 0, "short": False, "score": 5, "node": site_nid,
                        "homonym": "", "quote": quote, "ex": []})
    out = [x for x in out if x["why"]]   # без доказательства пару не показывать: одно место в запросе - не довод
    out.sort(key=lambda x: (-x["score"], x["a"]))
    res = []
    for x in out:      # одно слово - не больше чем в трёх парах (иначе «ремонт» займёт весь список)
        if sum(1 for y in res if x["a"] in (y["a"], y["b"]) or x["b"] in (y["a"], y["b"])) >= 3:
            continue
        wa, wb = set(x["a"].split()), set(x["b"].split())
        if (len(wa) > 1 or len(wb) > 1) and any({y["a"], y["b"]} <= wa | wb and not {y["a"], y["b"]} <= wa
                                                and not {y["a"], y["b"]} <= wb for y in res):
            continue       # «вставка газа = муфта водонагревателя», когда уже есть «вставка = муфта»
        res.append(x)
        if len(res) >= limit:
            break
    return res


# ---------- ответы человека

def view(data):
    """Для вкладки «Разложить новые»: тема сайта, её синонимы, пары «похоже на синонимы», что переехало в одну группу."""
    st = D._load()
    nid, own = D.site_node(data, st)
    auto, share = D.detect(data)
    N = D.nodes(st)
    return {"niche": nid, "own": own, "auto": auto, "share": round(share, 3),
            "niches": [{"id": x, "name": D.path(x, N).replace("Общий → ", "")} for x in N if x != D.ROOT],
            "lines": D.active(D.node_lines(nid or D.ROOT, "syn", st)), "path": D.path(nid or D.ROOT, N),
            "suggest": suggest(data, st), "moved": (data.get("syn") or {}).get("moved") or []}


# ---------- пары, которые копятся сами (очередь сайтов, 10.10.2026)
# Пары ищутся дольше, чем открывается страница (gasprofservice - 8 с), а сайтов из очереди - десятки. Поэтому после
# каждого сбора семантики пары сохраняются в папку проверки («пары синонимов.json»), а «Словарь → Ждут подтверждения»
# показывает их сразу, без «Показать пары», и убирает те, на которые уже ответили («да», «нет» или они уже в словаре).

PAIRS_NAME = "пары синонимов.json"


def save_pairs(folder, data, pairs=None):
    """Найти пары по семантике (с решениями человека) и запомнить в папке. Возвращает число пар."""
    import os
    import time
    from .. import jsonfile
    pairs = suggest(data, limit=SUGGEST * 3) if pairs is None else pairs
    sem = os.path.join(folder, "семантика.json")
    jsonfile.save(os.path.join(folder, PAIRS_NAME), {"sem": os.path.getmtime(sem) if os.path.exists(sem) else 0,
                                                    "made": time.strftime("%d.%m.%Y %H:%M"), "suggest": pairs}, indent=0)
    return len(pairs)


def cached_pairs(folder, host, nid=None, st=None, known=None):
    """Запомненные пары сайта без уже решённых. None - пар не искали или семантику с тех пор собрали заново."""
    import json
    import os
    try:
        with open(os.path.join(folder, PAIRS_NAME), encoding="utf-8") as f:
            c = json.load(f)
        if abs(c.get("sem", 0) - os.path.getmtime(os.path.join(folder, "семантика.json"))) > 1:
            return None
    except (OSError, ValueError):
        return None
    st = st or D._load()
    N = D.nodes(st)
    nid = nid if nid is not None else (st["sites"].get(D.site_key(host)) or D.ROOT)
    no = {k for x in D.chain(nid or D.ROOT, N) for k in st["no"].get(x) or []} | set(st["done"].get(D.site_key(host)) or [])
    known = known or words(D.all_lines(st))
    return [p for p in c.get("suggest") or []
            if pair_key(p["a"], p["b"]) not in no and known.of(p["a"]) != known.of(p["b"])]


def view_cached(folder, data):
    """view(), но пары - из запомненных, если они свежие (иначе найти и запомнить)."""
    import os
    pairs = cached_pairs(folder, data.get("host"), D.site_node(data)[0])
    if pairs is None:
        try:
            save_pairs(folder, data)
            pairs = cached_pairs(folder, data.get("host"), D.site_node(data)[0])
        except OSError:
            pairs = None
        if pairs is None:
            return dict(view(data), folder=os.path.basename(folder))
    pairs = pairs[:SUGGEST]
    st = D._load()
    N = D.nodes(st)
    nid, own = D.site_node(data, st)
    auto, share = D.detect(data)
    return {"niche": nid, "own": own, "auto": auto, "share": round(share, 3),
            "niches": [{"id": x, "name": D.path(x, N).replace("Общий → ", "")} for x in N if x != D.ROOT],
            "lines": D.active(D.node_lines(nid or D.ROOT, "syn", st)), "path": D.path(nid or D.ROOT, N),
            "suggest": pairs, "moved": (data.get("syn") or {}).get("moved") or [], "folder": os.path.basename(folder)}
