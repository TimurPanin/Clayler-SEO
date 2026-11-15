"""Один запрос в разных формах слова, другом порядке слов или с «ё» - одна строка семантики.

«группа безопасности» и «группы безопасности», «предохранительные клапаны» и «клапаны предохранительные»:
Вордстат без операторов считает такие фразы вместе, поэтому две строки - это дубль. Остаётся одна строка
(с наибольшей оценкой спроса), остальные формы - рядом с ней в колонке r[14], а не выкинуты: форма иногда
значит разное (одна страница или каталог). Частота не складывается, а берётся наибольшая. Показы и переходы
из Вебмастера и Search Console - настоящие разные запросы, они складываются.
Накладывается при чтении семантика.json (export.load), поэтому работает и для уже собранной семантики."""
from . import tokens, keys, norm, _canon

FORMS = 14   # номер колонки строки запроса с другими формами


def key(q):
    """«газовые котлы» = «котел газовый» = «газовый котёл»: основы слов без порядка."""
    # «онлайн-клубы» - два слова, иначе от них осталась бы одна основа
    return tuple(sorted(_canon(keys(w)) for t in tokens(norm(q)) for w in t.split("-") if w))


def _best(rows):
    # строка без «возможно, про другое», с показами, с большей оценкой, короче
    return min(rows, key=lambda r: (bool(r[7]), -(r[6] or 0), -(r[3] or 0), len(r[0]), r[0]))


def _low(vals):
    vals = [v for v in vals if v]
    return min(vals) if vals else 0


def merge(data):
    """Склеить формы во всех группах. Строка может переехать в группу главной формы."""
    if not data or not data.get("groups") or data.get("forms_merged") is not None:
        return data
    by = {}
    for g in data["groups"]:
        for r in g.get("q") or []:
            while len(r) < FORMS:
                r.append(0)
            if len(r) == FORMS:
                r.append([])
            k = key(r[0])
            if k:
                by.setdefault(k, []).append((g, r))
    gone, n = set(), 0
    left = {id(g): len(g.get("q") or []) for g in data["groups"]}
    for lst in by.values():
        if len(lst) < 2:
            continue
        main = _best([r for _, r in lst])
        mg = next(g for g, r in lst if r is main)
        others = []
        for g, r in lst:
            # строка из другой группы, если она там последняя, остаётся: группу не теряем
            if r is not main and (g is mg or left[id(g)] > 1):
                others.append(r)
                left[id(g)] -= 1
        if not others:
            continue
        rows = [main] + others
        main[3] = max(r[3] or 0 for r in rows)
        for i in (4, 5, 8, 12, 13):          # места: лучшее
            main[i] = _low(r[i] for r in rows)
        main[6] = sum(r[6] or 0 for r in rows)
        main[10] = sum(r[10] or 0 for r in rows)
        main[11] = max(r[11] or 0 for r in rows)
        main[9] = main[9] or next((r[9] for r in others if r[9]), "")
        main[FORMS] = list(dict.fromkeys(f for r in others for f in [r[0]] + list(r[FORMS] or []) if f != main[0]))
        gone |= {id(r) for r in others}
        n += len(others)
    if n:
        for g in data["groups"]:
            g["q"] = [r for r in g.get("q") or [] if id(r) not in gone]
        data["total"] = max(0, (data.get("total") or 0) - n)
    data["forms_merged"] = n
    return data
