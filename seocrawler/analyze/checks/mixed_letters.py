"""Смешанные буквы: в одном слове и русские, и латинские («Cтроительство» с латинской C,
«кoтел» с латинской o). Глазом не видно, но для поиска это другое слово — страница не находится
по запросу «строительство». Проверяются title, описание, H1 и текст страницы."""
import re
import zlib

from ..common import NOTE, WARN, defaultdict

# «Слово» вместе с цифрами и тем, что приклеено через дефис, слеш или точку: EPS1010S, BB-20, SL10/5 — целиком
_TOKEN = re.compile(r"[^\W_]+(?:[-/.][^\W_]+)*")
_WORD = re.compile(r"[^\W\d_]+")
_CYR = re.compile(r"[а-яёА-ЯЁ]")
_LAT = re.compile(r"[a-zA-Z]")


# Буквы, которые в русском и латинском алфавите выглядят одинаково: их и путают при наборе и копировании
_LOOK_LAT = set("ABCEHKMOPTXYaceopxy")
_LOOK_CYR = set("АВСЕНКМОРТХУасеорху")


def _minority(word):
    cyr = _CYR.findall(word)
    lat = _LAT.findall(word)
    return (lat, _LOOK_LAT, "латинск") if len(cyr) >= len(lat) else (cyr, _LOOK_CYR, "русск")


def mixed_words(text):
    """Слова, где есть и кириллица, и латиница, причём «чужие» буквы — двойники (С/C, о/o, Р/P…).
    Склеенные слова без пробела («Dнасоса», «Qмакс», «типаValve») не считаем: там буквы не двойники.
    Артикулы и модели с цифрами (ЕРРВВ2005, EPS1010S, ВВ-20) не считаем: их пишут как у производителя,
    и для покупателя это название, а не слово с опечаткой."""
    out = []
    for tok in _TOKEN.findall(text or ""):
        # нет русских букв (одни ASCII) или нет латинских - смешанного слова тут быть не может; таких слов почти все,
        # и одна проверка вместо разбора на части - в разы быстрее на большом сайте
        if tok.isascii() or not _LAT.search(tok):
            continue
        if any(ch.isdigit() for ch in tok):
            continue
        for w in _WORD.findall(tok):
            if len(w) >= 2 and _CYR.search(w) and _LAT.search(w):
                odd, look, _ = _minority(w)
                if all(ch in look for ch in odd):
                    out.append(w)
    return out


def mark(word):
    """«[C]троительство (латинская C)»: чужие буквы — в скобках, по большинству букв слова."""
    odd, _, name = _minority(word)
    letters = sorted(set(odd))
    shown = "".join(f"[{ch}]" if ch in letters else ch for ch in word)
    return f"{shown} ({name}{'ая' if len(letters) == 1 else 'ие'} {', '.join(letters)})"


def run(ctx):
    add, indexable = ctx.add, ctx.indexable
    meta_rows = []
    text_words = defaultdict(set)   # (слово) -> страницы
    for p in indexable:
        for where, val in (("title", p.get("title")), ("описание", p.get("description")), ("H1", p.get("h1"))):
            for w in mixed_words(val):
                meta_rows.append([p["url"], where, mark(w), val])
        b = p.get("blocks")
        if b:
            try:
                text = zlib.decompress(b).decode("utf-8")
            except Exception:
                text = ""
            for w in set(mixed_words(text)):
                text_words[w].add(p["url"])
    add("mixed_letters_meta", WARN, "Контент", "В title, описании или H1 смешаны русские и латинские буквы",
        "В слове есть буквы из другого алфавита, которые выглядят одинаково: латинская C вместо русской С, "
        "латинская o вместо о и т. п. Глазом не отличить, но для поисковика «Cтроительство» с латинской C - "
        "другое слово: страница хуже находится по нужному запросу, а в сниппете слово может не подсветиться.",
        "Перепечатайте отмеченные буквы (в квадратных скобках) на нужной раскладке. Обычно так бывает после "
        "копирования текста из документов или при наборе с английской раскладкой.",
        ["Адрес", "Где", "Слово", "Текст целиком"], meta_rows)
    rows = sorted(([mark(w), len(u), "\n".join(sorted(u)[:3])] for w, u in text_words.items()),
                  key=lambda r: (-r[1], r[0]))
    add("mixed_letters_text", NOTE, "Контент", "В тексте страниц есть слова со смешанными русскими и латинскими буквами",
        "Те же подменённые буквы, но в тексте страницы. Поисковик не сопоставит такое слово с запросом. "
        "Если слово на многих страницах, оно в меню или подвале: исправляется один раз в шаблоне.",
        "Перепечатайте отмеченные буквы. Слова через дефис («SEO-продвижение») программа не отмечает; "
        "если в списке окажется название, которое так и пишется слитно, его можно оставить.",
        ["Слово", "На скольких страницах", "Например, здесь"], rows, page_col=None)
