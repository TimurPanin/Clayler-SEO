"""Автотест: восемь ошибок из разбора кода 16.11.2026 не вернулись (без сети, меньше секунды).
- robots.txt с невидимым знаком BOM в начале: запреты не теряются;
- «Disallow: /catalog/$» не закрывает «/catalog/?page=2», а сам «/catalog/» закрывает;
- «max-image-preview:none» (и с пробелом) - не запрет «none», а «none» и «noindex, none» - запрет;
- %25, %2F, %3F, %23 в пути остаются как есть, повторная нормализация адрес не меняет;
- Robots.allowed возвращает пару, и GEO-проверка берёт из неё [0];
- непонятная переменная прокси не роняет проверку;
- sitemap: свой предел 50 МБ, а не общий 5 МБ;
- код читается старым Python: нет f-строк с теми же кавычками внутри (так можно только с Python 3.12).
Запуск: py -3 tests/проверить_мелкие_функции.py (и из проверить_всё.py)."""
import glob
import io
import os
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import sysproxy  # noqa: E402
from seocrawler.crawler.sitemaps import SITEMAP_MAX  # noqa: E402
from seocrawler.robots import Robots, says_none  # noqa: E402
from seocrawler.urls import normalize  # noqa: E402

fails = []


def check(got, want, what):
    if got != want:
        fails.append(f"{what}: {got!r}, ждали {want!r}")


# 1. robots.txt с BOM
r = Robots("﻿User-agent: *\nDisallow: /secret/\n", "Googlebot")
check(r.allowed("https://a.ru/secret/x")[0], False, "BOM: запрет потерялся")
check(r.allowed("https://a.ru/open/")[0], True, "BOM: открытая страница")

# 2. знак $ в robots.txt
r = Robots("User-agent: *\nDisallow: /catalog/$\n", "Googlebot")
check(r.allowed("https://a.ru/catalog/")[0], False, "$: сам адрес")
check(r.allowed("https://a.ru/catalog/?page=2")[0], True, "$: адрес с параметрами")
r = Robots("User-agent: *\nDisallow: /каталог/\n", "Googlebot")
check(r.allowed("https://a.ru/%D0%BA%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3/x")[0], False, "русский путь в %XX")

# 3. meta robots «none»
for text, want in (("index, follow, max-image-preview:none", False), ("index, follow, max-image-preview: none", False),
                   ("max-video-preview:-1, max-image-preview:none, nofollow", False), ("nonetheless", False),
                   ("none", True), ("noindex, none", True), ("NONE", True), ("googlebot: none", True)):
    check(says_none(text), want, f"none в «{text}»")

# 4. процент в пути
for url in ("https://a.ru/skidka-100%25/", "https://a.ru/a%2Fb/", "https://a.ru/x%3Fy", "https://a.ru/x%23y"):
    check(normalize(url), url, "знак в пути раскрылся")
check(normalize(normalize("https://a.ru/x%2541")), "https://a.ru/x%2541", "повторная нормализация")
check(normalize("https://a.ru/%d0%ba"), "https://a.ru/%D0%BA", "обычное кодирование")

# 5. allowed - пара, GEO берёт [0]
check(Robots("User-agent: *\nDisallow: /\n", "GPTBot").allowed("https://a.ru/")[0], False, "GPTBot закрыт")
geo = open(os.path.join(ROOT, "seocrawler", "semantics", "geo.py"), encoding="utf-8").read()
check(".allowed(u)[0]" in geo, True, "GEO проверяет «разрешено», а не всю пару")

# 6. прокси
check(sysproxy._dead("::1,10.0.0.0/8,[::1]:8080"), False, "непонятная переменная прокси")

# 7. sitemap
check(SITEMAP_MAX >= 50_000_000, True, "предел sitemap")

# 8. f-строки для Python 3.9-3.11: внутри f-строки нет строки с теми же кавычками
def _quote(token):
    """Кавычки строки: ' или " или тройные."""
    body = token.lstrip("rRfFbBuU")
    return body[:3] if body[:3] in ("\'\'\'", '"""') else body[:1]


bad = []
for path in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
    if os.sep + "." in path:
        continue
    src = open(path, encoding="utf-8").read()
    stack = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            name = tokenize.tok_name[t.type]
            if name == "FSTRING_START":
                q = _quote(t.string)
                if stack and q == stack[-1]:
                    bad.append(f"{os.path.relpath(path, ROOT)}:{t.start[0]}")
                stack.append(q)
            elif name == "FSTRING_END":
                stack.pop()
            elif name == "STRING" and stack:
                if _quote(t.string) == stack[-1]:
                    bad.append(f"{os.path.relpath(path, ROOT)}:{t.start[0]}")
    except (tokenize.TokenError, SyntaxError):
        continue
check(bad, [], "f-строки, которые не прочитает Python 3.9-3.11")

if fails:
    print("НЕ ПРОШЛО:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("Мелкие функции: всё в порядке")
