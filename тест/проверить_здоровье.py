"""Автотест «Здоровья» (15.10.2026): одна причина на всём сайте не обнуляет оценку.
- битая ссылка из меню (на 100 из 100 страниц) - проблема всего сайта: -10%, а не 0%;
- битая ссылка только на одной странице - портит только эту страницу;
- проблема почти на всех страницах (тяжёлые страницы на 95 из 100) - -5% вместо 5%;
- на маленьком сайте (меньше 20 страниц) так не делается: там каждая страница на счету;
- штраф не больше 30%; прирост здоровья (gain) у проблемы всего сайта - её штраф.
Без сети: выдуманные проблемы."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.analyze import health as H  # noqa: E402
from seocrawler.analyze.common import Issue, CRIT, WARN  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def score(issues, base):
    per, site, _why = H._page_sets(issues, base)
    bad = set().union(*per.values()) if per else set()
    pen = min(H.SITE_PENALTY_MAX, sum(site.values()))
    return max(0, round(100 * (1 - len(bad) / len(base))) - pen), site


pages = [f"https://s.ru/p{i}/" for i in range(100)]
base = set(pages)
menu = [[p, "https://s.ru/old/", "Каталог", 404] for p in pages]
one = [[pages[5], "https://s.ru/gone/", "тут", 404]]
broken = Issue("broken_links", CRIT, "Ссылки", "Битые ссылки", "", "", ["Страница", "Куда", "Текст", "Код"], menu + one)
h, site = score([broken], base)
check(h == 89 and id(broken) in site, f"битая ссылка в меню: {h}, ожидалось 89 (99% страниц - 10%)")

heavy = Issue("page_weight", WARN, "Скорость", "Тяжёлые страницы", "", "", ["Страница"], [[p] for p in pages[:95]])
h, site = score([heavy], base)
check(h == 95, f"тяжёлые почти все: {h}, ожидалось 95")

few = Issue("page_weight", WARN, "Скорость", "Тяжёлые страницы", "", "", ["Страница"], [[p] for p in pages[:30]])
h, site = score([few], base)
check(h == 70 and not site, f"тяжёлые 30 из 100: {h}, ожидалось 70 (по страницам)")

small = set(pages[:10])
h, site = score([Issue("page_weight", WARN, "", "", "", "", ["Страница"], [[p] for p in pages[:10]])], small)
check(h == 0 and not site, f"маленький сайт: {h}, ожидалось 0")

many = [Issue(f"x{i}", CRIT, "", "", "", "", ["Страница"], [[p] for p in pages]) for i in range(5)]
h, site = score(many, base)
check(h == 70 and len(site) == 5, f"штраф больше 30%: {h}, ожидалось 70")

if fails:
    print("✗ здоровье:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ здоровье: ссылка из меню и проблема почти на всех страницах - штраф, а не 0%")
