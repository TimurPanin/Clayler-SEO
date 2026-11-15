"""Автотест сметы и плана работ (seocrawler/estimate.py): этапы по важности, часы с потолком,
проблема «на всём сайте» - один раз, служебные проблемы не попадают, деньги - только если указана ставка,
тексты для клиента без длинного тире и «программы». Без сети, выдуманные проблемы."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import estimate as E  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def iss(key, sev, n, sitewide="", gain=0.0):
    i = Issue(key, sev, "", f"Проблема {key}", "", f"Исправить {key}. Программа открыла страницы.", ["Адрес"],
              [[f"https://site.ru/{k}"] for k in range(n)])
    i.sitewide, i.gain = sitewide, gain
    return i


issues = [iss("title_dup", "warning", 50, gain=3), iss("4xx", "critical", 10_000), iss("no_compress", "notice", 900,
          sitewide="на всём сайте (900 из 900 стр.)"), iss("skipped", "notice", 5), iss("h1_missing", "warning", 4, gain=8),
          iss("unknown_key", "warning", 3)]
w = E.build(issues)
keys = [x["key"] for x in w]
check(keys == ["4xx", "h1_missing", "title_dup", "no_compress"], f"порядок и состав: {keys}")
h = {x["key"]: x["hours"] for x in w}
check(h["4xx"] == 6, f"потолок часов: {h['4xx']}")
check(h["no_compress"] == 1, f"на всём сайте - один раз: {h['no_compress']}")
check(h["title_dup"] == 1.5 and h["h1_missing"] == 0.5, f"часы по строкам: {h}")
check(all(x["hours"] * 2 == int(x["hours"] * 2) for x in w), "часы не кратны получасу")
check("Мы открыли" in w[0]["fix"], "тексты не прошли замены для клиента (client_text)")
t = E.totals(w, 1500)
check(t["hours"] == 9 and t["money"] == 13500 and len(t["stages"]) == 3, f"итого: {t}")
block = E.html_block(w, 0)
check("₽" not in block and "около 9 ч" in block, "без ставки в блоке не должно быть денег")
check("13 500 ₽" in E.html_block(w, 1500), "со ставкой - сумма с пробелом между тысячами")
doc = E._doc("site.ru", "04.10.2026", w, 1500)
check("—" not in doc + block and "рограмм" not in doc.split("<main>")[1], "длинное тире или «программа» в смете")
check(E.build([iss("skipped", "notice", 5), iss("program_fail", "notice", 2)]) == [], "служебные проблемы в смете")

tmp = tempfile.mkdtemp()
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
got = E.write(tmp, {"start": "https://site.ru/", "finished_at": "2026-10-04 12:00:00"}, issues, pdf=False)
check(len(got) == 4 and os.path.exists(os.path.join(tmp, "смета.xlsx")), "смета.xlsx не записана")

if fails:
    print("ОШИБКИ в смете:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ смета и план работ: этапы, часы, «на всём сайте», ставка, тексты для клиента")
