"""Автотест «Здоровья» по частям: техника и контент (24.10.2026, без сети).
Проверяет analyze/health._health_parts и is_content:
- проблема Title портит только контент, битая ссылка - только технику; alt картинок - контент, размеры - техника;
- совет «Передайте разработчику: …» делает проблему технической в любом разделе (ревизия 24.10.2026);
- замечания (NOTE) не портят ни одну часть, штраф за проблему всего сайта идёт в свою часть;
- текст «техника N%, контент M%» в report.health_parts_text, у непроверенного сайта - пусто.
Запуск: py -3 тест/проверить_здоровье_по_частям.py (и из проверить_всё.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler.analyze.common import CRIT, NOTE, WARN, Issue  # noqa: E402
from seocrawler.analyze.health import _health_parts, is_content  # noqa: E402
from seocrawler.report import health_parts_text  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def iss(key, sev, cat):
    return Issue(key, sev, cat, key, "", "", ["Адрес"], [["/x"]])


base = {f"/p{i}" for i in range(10)}
t = iss("title_long", WARN, "Title")
b = iss("broken_links", CRIT, "Ссылки")
a = iss("img_alt_missing", WARN, "Картинки")
s = iss("img_no_size", WARN, "Картинки")
n = iss("keywords", NOTE, "Контент")
check(is_content(t) and is_content(a) and not is_content(b) and not is_content(s), "что считается контентом")
dev = Issue("title_multi", WARN, "Title", "Несколько тегов title", "", "Передайте разработчику: оставить один тег title.",
            ["Адрес"], [["/x"]])
check(not is_content(dev), "совет «Передайте разработчику» в разделе Title - это техника")
per = {id(t): {"/p0", "/p1"}, id(b): {"/p2"}, id(a): {"/p1", "/p3"}, id(s): set()}
hp = _health_parts([t, b, a, s, n], per, {id(s): 5}, base)
check(hp == {"tech": 85, "content": 70}, f"части: {hp} (ждали техника 90-5=85, контент 70)")
check(health_parts_text({"health_parts": hp}) == "техника 85%, контент 70%", "текст частей")
check(health_parts_text({"health_parts": hp, "unchecked": True}) == "", "непроверенный сайт")
check(health_parts_text({}) == "", "старая проверка без частей")
check(_health_parts([], {}, {}, set()) is None, "нет страниц")

if fails:
    print("✗ здоровье по частям:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ здоровье по частям: техника и контент считаются отдельно, замечания не учитываются")
