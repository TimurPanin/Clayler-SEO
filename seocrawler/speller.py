"""Орфография через бесплатный сервис Яндекс.Спеллер (speller.yandex.net).

Со всех страниц сайта собираются уникальные русские слова (только написанные строчными — имена и названия
с большой буквы не проверяем), отправляются пачками до 10 000 знаков. Результат — в meta «spelling»:
{"checked": слов проверено, "errors": {слово: [варианты]}, "error": текст ошибки сервиса}.
Делается при сборке отчёта (в том числе «Обновить отчёт»), один раз на проверку."""
import json
import re
import urllib.parse
import urllib.request
import zlib
from collections import Counter

from . import sysproxy

URL = "https://speller.yandex.net/services/spellservice.json/checkText"
_WORD = re.compile(r"[А-ЯЁа-яё]+")
_LOWER = re.compile(r"^[а-яё]{4,}$")
OPTIONS = 2 | 4  # не проверять слова с цифрами и адреса
_QUOTES = str.maketrans("", "", "«»„“”\"'")
# Короткий кусок в кавычках (1-3 слова): так пишут цитату или пример слова - «французкого» вместо «французского»
# в разборе чужих ошибок (timurpanin.ru). Это не опечатка сайта, такие слова не проверяем. Длинные
# фразы в кавычках проверяем как обычный текст: там опечатка сайта - настоящая.
_SHORT_QUOTED = re.compile(r"«[^«»\n]{1,40}»|„[^„“”\n]{1,40}[“”]|“[^“”\n]{1,40}”|\"[^\"\n]{1,40}\"")


def unquoted(text):
    """Текст без коротких кусков в кавычках (до 3 слов)."""
    return _SHORT_QUOTED.sub(lambda m: " " if len(m.group(0).split()) <= 3 else m.group(0), text)


def site_words(db):
    """Счётчик: слово → на скольких страницах. Только индексируемые рабочие страницы своего сайта."""
    cnt = Counter()
    for (b,) in db.execute("""SELECT p.blocks FROM pages p JOIN urls u ON u.url=p.url
                               WHERE u.internal=1 AND u.kind='page' AND p.status=200 AND p.indexable=1
                               AND p.blocks IS NOT NULL"""):
        try:
            text = unquoted(zlib.decompress(b).decode("utf-8"))
        except Exception:
            continue
        cnt.update({w for w in _WORD.findall(text) if _LOWER.match(w)})
    return cnt


def check_words(words, log=print, timeout=20):
    """{слово: [варианты]} для слов с ошибкой. Бросает исключение, если сервис недоступен."""
    errors, batch, size = {}, [], 0
    batches = []
    for w in words:
        if size + len(w) + 1 > 9000:
            batches.append(batch)
            batch, size = [], 0
        batch.append(w)
        size += len(w) + 1
    if batch:
        batches.append(batch)
    for i, b in enumerate(batches, 1):
        data = urllib.parse.urlencode({"text": "\n".join(b), "lang": "ru", "options": OPTIONS}).encode()
        req = urllib.request.Request(URL, data=data, headers={"User-Agent": "ClaylerSEO"})
        with sysproxy.urlopen(req, timeout=timeout) as r:
            for e in json.loads(r.read().decode("utf-8")):
                if e.get("word") and e.get("s"):
                    errors[e["word"].lower()] = e["s"][:3]
        if len(batches) > 3 and i % 10 == 0:
            log(f"   орфография: проверено {i} из {len(batches)} пачек слов")
    return errors


def contexts(db, words):
    """{слово: кусок текста сайта вокруг него (до 4 слов с каждой стороны)} - для перепроверки в предложении."""
    left, out = set(words), {}
    for (b,) in db.execute("""SELECT p.blocks FROM pages p JOIN urls u ON u.url=p.url
                               WHERE u.internal=1 AND u.kind='page' AND p.status=200 AND p.indexable=1
                               AND p.blocks IS NOT NULL"""):
        if not left:
            break
        try:
            text = unquoted(zlib.decompress(b).decode("utf-8"))
        except Exception:
            continue
        for line in text.splitlines():
            toks = line.split()
            for i, t in enumerate(toks):
                w = "".join(_WORD.findall(t))
                if w in left:
                    # без кавычек: слово в кавычках Спеллер пропускает, а опечатка в «...» - тоже опечатка
                    out[w] = " ".join(toks[max(0, i - 4): i + 5]).translate(_QUOTES)
                    left.discard(w)
    return out


def confirm(errors, ctx, timeout=20):
    """Оставляет слова, которые Спеллер считает ошибкой и внутри предложения. Слово в отдельной строке он иногда
    считает опечаткой, а в тексте - нет («пользователям», «изображениям»: timurpanin.ru)."""
    lines = [ctx[w] for w in errors if w in ctx]
    if not lines:
        return errors
    flagged, batch, size = set(), [], 0
    for ln in lines + [None]:
        if ln is None or size + len(ln) + 1 > 9000:
            data = urllib.parse.urlencode({"text": "\n".join(batch), "lang": "ru", "options": OPTIONS}).encode()
            req = urllib.request.Request(URL, data=data, headers={"User-Agent": "ClaylerSEO"})
            with sysproxy.urlopen(req, timeout=timeout) as r:
                flagged |= {e["word"].lower() for e in json.loads(r.read().decode("utf-8")) if e.get("word")}
            batch, size = [], 0
        if ln is not None:
            batch.append(ln)
            size += len(ln) + 1
    return {w: s for w, s in errors.items() if w not in ctx or w in flagged}


def ensure(store, log=print):
    """Проверить орфографию, если в этой проверке ещё не проверяли."""
    if store.get_meta("spelling", None) is not None:
        return
    try:
        cols = {r[1] for r in store.db.execute("PRAGMA table_info(pages)")}
        if "blocks" not in cols:
            return  # старая проверка — текста по блокам нет
        words = site_words(store.db)
        if not words:
            return
        log(f"Проверяю орфографию (Яндекс.Спеллер): {len(words)} разных слов...")
        errors = check_words(sorted(words), log)
        if errors:
            errors = confirm(errors, contexts(store.db, errors))
        store.set_meta("spelling", {"checked": len(words), "errors": errors, "error": ""})
        log(f"   слов с ошибками: {len(errors)}")
    except Exception as e:
        store.set_meta("spelling", {"checked": 0, "errors": {}, "error": str(e)[:150]})
        log("Орфографию проверить не получилось (нет интернета или сервис недоступен): " + str(e)[:100])
    store.commit()
