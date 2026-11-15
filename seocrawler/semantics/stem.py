"""Основа русского слова (стеммер Портера, Snowball) и «звучание» латинских слов,
чтобы «газовые котлы» и «газовый котел», «Lemax» и «лемакс» считались одним и тем же."""
import re
from functools import lru_cache

VOWELS = "аеиоуыэюя"

PERF1 = ("вшись", "вши", "в")                     # после а/я
PERF2 = ("ившись", "ывшись", "ивши", "ывши", "ив", "ыв")
REFL = ("ся", "сь")
ADJ = ("ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие", "ые", "ое", "ей", "ий", "ый", "ой", "ем", "им",
       "ым", "ом", "их", "ых", "ую", "юю", "ая", "яя", "ою", "ею")
PART1 = ("ем", "нн", "вш", "ющ", "щ")               # после а/я
PART2 = ("ивш", "ывш", "ующ")
VERB1 = ("ете", "йте", "ешь", "нно", "ла", "на", "ли", "ем", "ло", "но", "ет", "ют", "ны", "ть", "й", "л", "н")
VERB2 = ("ейте", "уйте", "ила", "ыла", "ена", "ите", "или", "ыли", "ило", "ыло", "ено", "ует", "уют", "ены",
         "ить", "ыть", "ишь", "ей", "уй", "ил", "ыл", "им", "ым", "ен", "ят", "ит", "ыт", "ую", "ю")
NOUN = ("иями", "ями", "ами", "ией", "иям", "ием", "иях", "ев", "ов", "ие", "ье", "еи", "ии", "ей", "ой", "ий",
        "ям", "ем", "ам", "ом", "ах", "ях", "ию", "ью", "ия", "ья", "а", "е", "и", "й", "о", "у", "ы", "ь", "ю", "я")


def _by_len(t):
    return tuple(sorted(t, key=len, reverse=True))


PERF1, PERF2, REFL, ADJ, PART1, PART2, VERB1, VERB2, NOUN = map(
    _by_len, (PERF1, PERF2, REFL, ADJ, PART1, PART2, VERB1, VERB2, NOUN))


def _regions(w):
    rv = r1 = r2 = len(w)
    for i, ch in enumerate(w):
        if ch in VOWELS:
            rv = i + 1
            break
    for i in range(1, len(w)):
        if w[i - 1] in VOWELS and w[i] not in VOWELS:
            r1 = i + 1
            break
    for i in range(r1 + 1, len(w)):
        if w[i - 1] in VOWELS and w[i] not in VOWELS:
            r2 = i + 1
            break
    return rv, r1, r2


def _cut(rv, ends, after_a=False):
    """Отрезать самое длинное окончание из ends внутри rv. after_a — окончание должно стоять после а/я."""
    for e in ends:
        if rv.endswith(e):
            if after_a:
                if len(rv) > len(e) and rv[-len(e) - 1] in "ая":
                    return rv[:-len(e)]
            else:
                return rv[:-len(e)]
    return None


@lru_cache(maxsize=200_000)
def stem(word):
    w = word.lower().replace("ё", "е")
    if not re.fullmatch(r"[а-я]+", w) or len(w) < 3:
        return w
    rv_i, _, r2_i = _regions(w)
    head, rv = w[:rv_i], w[rv_i:]
    # шаг 1
    r = _cut(rv, PERF2) or _cut(rv, PERF1, True)
    if r is not None:
        rv = r
    else:
        r = _cut(rv, REFL)
        if r is not None:
            rv = r
        r = _cut(rv, ADJ)
        if r is not None:
            rv = r
            p = _cut(rv, PART2) or _cut(rv, PART1, True)
            if p is not None:
                rv = p
        else:
            r = _cut(rv, VERB2) or _cut(rv, VERB1, True)
            if r is not None:
                rv = r
            else:
                r = _cut(rv, NOUN)
                if r is not None:
                    rv = r
    # шаг 2
    if rv.endswith("и"):
        rv = rv[:-1]
    # шаг 3: словообразовательные окончания в R2
    word2 = head + rv
    for e in ("ость", "ост"):
        if word2.endswith(e) and len(word2) - len(e) >= r2_i:
            rv = rv[:-len(e)]
            break
    # шаг 4
    if rv.endswith("нн"):
        rv = rv[:-1]
    else:
        for e in ("ейше", "ейш"):
            if rv.endswith(e):
                rv = rv[:-len(e)]
                if rv.endswith("нн"):
                    rv = rv[:-1]
                break
        else:
            if rv.endswith("ь"):
                rv = rv[:-1]
    return head + rv


TRANSLIT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "i",
            "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
            "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e",
            "ю": "yu", "я": "ya", "ё": "e"}


@lru_cache(maxsize=200_000)
def sound(word):
    """Грубое «звучание» слова латиницей: Lemax = лемакс, Baxi = бакси, Protherm = протерм, Bosch = бош."""
    w = "".join(TRANSLIT.get(ch, ch) for ch in word.lower())
    for a, b in (("sch", "sh"), ("th", "t"), ("ph", "f"), ("ck", "k"), ("x", "ks"), ("w", "v"), ("c", "k"),
                 ("q", "k"), ("y", "i"), ("z", "s"), ("j", "i"), ("h", ""), ("ie", "e")):
        w = w.replace(a, b)
    w = re.sub(r"(.)\1+", r"\1", w)          # двойные буквы
    w = re.sub(r"[^a-z0-9]", "", w)
    return w
