"""Мелочи для отчётов: текст для HTML и числа с пробелами между тысячами."""
import html
import re

_PCT_HIGH = re.compile(r"(?:%[89a-fA-F][0-9a-fA-F])+")       # байты букв не латиницей (UTF-8)
_HOST = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*://(?:[^/?#@]*@)?)([^/?#:]+)")


def pretty_url(u):
    """Адрес так, как его показывает браузер (30.10.2026, по просьбе пользователя: в отчёте стояло
    /image/catalog/%D0%91%D0%BB%D0%BE%D0%B3/..., а в браузере /image/catalog/Блог/...): русские и другие буквы
    вместо %D0%91…, домен .рф по-русски. Служебные знаки (%20, %2F, %3F…) остаются закодированными, как и
    пробелы и невидимые символы. Только для показа: ссылка (href) - прежний адрес."""
    s = "" if u is None else str(u)
    if "%" not in s and "xn--" not in s.lower():
        return s

    def dec(m):
        try:
            t = bytes.fromhex(m.group(0).replace("%", "")).decode("utf-8")
        except UnicodeDecodeError:
            return m.group(0)
        return t if all(ch.isprintable() and not ch.isspace() for ch in t) else m.group(0)
    def host(m):
        try:
            return m.group(1) + ".".join(p.encode("ascii").decode("idna") if p.lower().startswith("xn--") else p
                                         for p in m.group(2).split("."))
        except UnicodeError:
            return m.group(0)
    # строка меняется только в этих местах: остальное (пустой «?» в конце, порт, регистр) - как было
    return _HOST.sub(host, _PCT_HIGH.sub(dec, s), count=1)


def esc(x):
    """Текст для вставки в HTML: None — пусто, <, >, &, кавычки экранируются."""
    return html.escape("" if x is None else str(x))


def num(x):
    """12345 -> «12 345»."""
    return f"{x:,}".replace(",", " ")


def when(x):
    """«2026-10-28 23:11:00» → «28.10.2026 23:11» (как принято у нас, без секунд); не дата - как есть."""
    s = "" if x is None else str(x)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}.{s[5:7]}.{s[:4]}" + (" " + s[11:16] if len(s) >= 16 else "")
    return s


def when_range(a, b):
    """Начало и конец проверки: «28.10.2026 23:11 - 23:25»; в разные дни - обе даты целиком (29.10.2026, по просьбе
    пользователя: в отчёте стояло «2026-10-28 23:11:00 - 2026-10-28 23:25:12»)."""
    a, b = when(a), when(b)
    if not a or not b:
        return a or b
    return f"{a} - {b[11:]}" if a[:10] == b[:10] and len(b) > 11 else f"{a} - {b}"


def approx(n):
    """Круглое число для примерного счёта: 9016 -> 9000, 1460 -> 1500, 437 -> 440, до 100 - как есть."""
    n = int(n or 0)
    if abs(n) < 100:
        return n
    k = 10 ** max(1, len(str(abs(n))) - 2)
    return int(n / k + (0.5 if n > 0 else -0.5)) * k


def plural(n, one, few, many):
    """Слово в нужной форме для числа: plural(5, "страница", "страницы", "страниц") -> «страниц»."""
    n = abs(n) % 100
    if 10 < n < 20:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def quote(x):
    """Текст сайта в кавычках: «…». Кавычки внутри — «лапки» „…“, чтобы не было «««Электра», Тумба»»."""
    import re
    t = re.sub(r"«([^«»]*)»|\"([^\"]*)\"", lambda m: "„" + (m.group(1) or m.group(2) or "") + "“",
               "" if x is None else str(x))
    return "«" + t.replace("«", "„").replace("»", "“").replace('"', "“") + "»"


def balance_quotes(x):
    """«Диадема»» → «Диадема»: лишние непарные кавычки из текста сайта убираются."""
    out, depth = [], 0
    for ch in "" if x is None else str(x):
        if ch == "«":
            depth += 1
        elif ch == "»":
            if not depth:
                continue
            depth -= 1
        out.append(ch)
    t = "".join(out)
    while depth:  # незакрытые «
        i = t.rfind("«")
        t, depth = t[:i] + t[i + 1:], depth - 1
    return t.replace('""', '"') if t.count('"') % 2 == 0 else t.replace('"', "")
