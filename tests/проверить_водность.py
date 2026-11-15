"""Автотест: водность и тошнота текста (seocrawler/textstat.py, analyze/checks/text_quality.py, ТЗ копирайтеру).
Запуск: py -3 tests/проверить_водность.py"""
import os
import random
import re
import sys
import zlib
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"

from seocrawler import textstat as T  # noqa: E402
from seocrawler.analyze.checks import text_quality as TQ  # noqa: E402
from seocrawler.semantics import pages as SP  # noqa: E402
from seocrawler.semantics.brief_docx import water_line  # noqa: E402

fails = []


def check(cond, text):
    if not cond:
        fails.append(text)


# живой текст: 40 предложений из разных слов (слова - из слогов, повторяются редко)
_rnd = random.Random(5)
_SYL = ["ка", "ро", "ми", "ту", "ле", "на", "зо", "ви", "пу", "ше", "да", "бо"]
CLEAN = " ".join(" ".join("".join(_rnd.choice(_SYL) for _ in range(3)) for _ in range(10)).capitalize() + "."
                 for _ in range(40))
WORDS = "дом кухня сад гараж баня крыша окно дверь стена пол".split()
# переспам: «котёл» в каждом предложении по три раза, разными формами
SPAM = " ".join(f"Купить газовый котёл: котлы и котлов {WORDS[i % 10]} много, котёл недорого." for i in range(40))
# вода: местоимения, вводные слова и общие фразы
WATER = " ".join("Конечно, это очень важно, ведь мы всегда просто стараемся сделать всё именно для вас, "
                 "и данный вопрос является для нас действительно самым главным." for _ in range(15))

c, s, w = T.stats(CLEAN), T.stats(SPAM), T.stats(WATER)
check(c["water"] < 10 and s["classic"] > 7 and s["academic"] > 15, f"цифры: чистый {c}, спам {s}")
check(w["water"] > 40, f"вода в «водяном» тексте {w['water']}")
# «котлы» и «котлов» - одно слово (беглую «ё» в «котёл» стеммер не склеивает, это нормально)
check(("котлы", 80) in s["top"], f"формы слова «котлы» не склеились: {s['top']}")
check(T.stats("Короткий текст.", 200) is None, "у короткого текста не должно быть цифр")
check(T.fmt(7.0) == "7" and T.fmt(5.34) == "5,3", "формат чисел")

# абзацы: названия товаров и цены без конца предложения не текст
blocks = ["Celtic-DS Platinum 3.13 котёл настенный газовый двухконтурный белый", "45 000 руб",
          "Это обычное предложение из текста страницы, в нём больше восьми слов."]
par = TQ.paragraphs(blocks)
check(par == blocks[2], f"абзацы выбраны неверно: {par!r}")

# проверка в отчёте: проблемы и поля страниц
def page(u, text):
    return {"url": u, "blocks": zlib.compress("\n".join(re.split(r"(?<=[.]) ", text)).encode("utf-8")), "indexable": 1}


pages = [page("https://a.ru/clean", CLEAN), page("https://a.ru/spam", SPAM), page("https://a.ru/water", WATER)]
got = {}
ctx = SimpleNamespace(indexable=pages, pages=pages,
                      add=lambda key, sev, cat, title, why, fix, cols, rows, page_col=0: got.__setitem__(key, rows))
TQ.run(ctx)
nz = [r[0] for r in got.get("text_nausea", [])]  # «водяной» текст - одна фраза 15 раз, он тоже переспам
check(nz[:1] == ["https://a.ru/spam"] and "https://a.ru/clean" not in nz, f"переспам: {got.get('text_nausea')}")
check([r[0] for r in got.get("text_water", [])] == ["https://a.ru/water"], f"вода: {got.get('text_water')}")
check(pages[0].get("water") is not None and pages[0].get("nausea") is not None, "у страницы нет полей воды и тошноты")
check("котлы - 80" in got["text_nausea"][0][4], f"«Чаще всего»: {got['text_nausea'][0]}")

# ТЗ копирайтеру: замечания с цифрами конкурента и строка нормы
pr = SP.text_problems(s, c)
check(len(pr) == 1 and "у конкурента" in pr[0] and "Чаще всего" in pr[0], f"замечания ТЗ: {pr}")
check(SP.text_problems(c) == [], "у чистого текста замечаний быть не должно")
line = water_line({"water": 27.0, "classic": 8.1, "academic": 18.0}, {"water": 14.0, "classic": 4.2, "academic": 9.0})
check(line.startswith("норма: вода до 20%, тошнота до 7, академическая до 15%") and "сейчас: вода 27%" in line
      and "у конкурента: вода 14%, тошнота 4,2" in line and "—" not in line, f"строка ТЗ: {line}")

# порог классической тошноты растёт с длиной текста; орфография не считает ошибкой профессиональные слова
from seocrawler.analyze.checks.text_quality import classic_max  # noqa: E402
from seocrawler.analyze.checks.spelling import JARGON  # noqa: E402
check(classic_max(500) == 7 and 9.5 < classic_max(5528) < 12.5 and classic_max(2224) > 7.1,
      f"порог тошноты: {classic_max(500)}, {classic_max(2224)}, {classic_max(5528)}")
check(all(JARGON.match(w) for w in ("маркетплейсы", "ретаргетинг", "видеоразбора", "ревью", "блогеры", "нишам"))
      and not any(JARGON.match(w) for w in ("ретагетинг", "удовлетвороенность", "спецеиалистов")),
      "словарь профессиональных слов для орфографии")

if fails:
    print("✗ водность и тошнота:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ водность и тошнота: цифры, абзацы без названий товаров, проблемы в отчёте, ТЗ с конкурентом")
