"""Автотест решений по семантике (semantics/decisions.py): смешанные группы («Разделить», «Оставить как есть»),
группы из текста кнопок («Убрать в отсеянное»), «Похоже, не та страница», страницы, которые мешают друг другу,
галочки и запись решений в файл. Без сети и без настоящих проверок: маленькая выдуманная семантика.
Решения пишутся во временную папку, «решения семантики» не трогаются."""
import copy
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-dec-")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.semantics import decisions as D  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def q(text, score=10):
    """Строка запроса как в семантика.json: запрос, уточнение, намерение, частота, ..., [7] - пометка «проверить»."""
    return [text, "", "Покупка", score, 1, 1, 0, "", 0]


S = "https://test.ru"
DATA = {
    "site": S + "/", "host": "test.ru", "city": "", "total": 13, "dropped": {},
    "groups": [
        {"name": "Курсы английского", "kind": "page", "page": S + "/kursy/", "todo": "Продвигать эту страницу",
         "a": {"now": {"title": "Курсы английского языка", "h1": "Курсы английского"}},
         "q": [q("курсы английского онлайн", 30), q("английский онлайн курсы", 20), q("курсы английского дистанционно"),
               q("курсы английского офлайн", 25), q("курсы английского очно", 15), q("английский в классе"),
               q("курсы английского", 50), q("курсы английского языка цена")]},
        {"name": "Подробнее о нас", "kind": "page", "page": S + "/about/", "a": {"now": {"title": "О нас", "h1": "О нас"}},
         "q": [q("подробнее о нас"), q("подробнее о компании")]},
        {"name": "Ремонт котлов", "kind": "page", "page": S + "/contacts/",
         "a": {"now": {"title": "Контакты", "h1": "Как нас найти"}},
         "q": [q("ремонт котлов", 40), q("ремонт газовых котлов"), q("ремонт котлов цена")]},
    ],
    "cannibal": [{"why": "Несколько разделов под одну группу «Ремонт котлов»", "main": S + "/kotly/",
                  "pages": [{"url": S + "/kotly/", "title": "Ремонт котлов", "h1": "Ремонт котлов"},
                            {"url": S + "/remont/", "title": "Ремонт котлов", "h1": "Ремонт"}]}],
}
FOLDER = os.path.join(TMP, "test.ru_проверка")   # без crawl.db: кандидатов в страницы нет, это нормально
os.makedirs(FOLDER)
KURSY, JUNK, KOTLY = (D._gkey(g["name"]) for g in DATA["groups"])
CASE = D.case_key(DATA["cannibal"][0])


def apply():
    before = copy.deepcopy(DATA)
    out = D.apply(DATA, FOLDER)
    check(DATA == before, "apply поменял исходную семантику")
    return out, {g["name"]: g for g in out["groups"]}


def set_dec(fn):
    D.update("test.ru", fn)


# 1. Решений нет: программа сама находит смесь, кнопочную группу, не ту страницу; случай не решён
out, g = apply()
mx = g["Курсы английского"].get("mixed") or {}
check(mx.get("axis") == "format", f"смешанная группа не найдена: {mx}")
check(sorted(p["n"] for p in mx.get("parts") or []) == [3, 5], f"части смешанной группы: {mx.get('parts')}")
check(g["Подробнее о нас"].get("junk") is True, "группа из текста кнопки не помечена")
check("нет слов группы" in (g["Ремонт котлов"].get("landing") or {}).get("why", ""), "«не та страница» не найдена")
# сравнение страниц для «Похоже, не та страница» (29.10.2026): слов группы в title и H1, про что, занята ли
from seocrawler.semantics import decisions as DC  # noqa: E402
P = DC._Pages.__new__(DC._Pages)
P._stems = {}
P.rows = [(S + "/contacts/", "как нас найти контакты", 1), (S + "/kotly/", "ремонт котлов в уфе", 1),
          (S + "/online/", "онлайн курсы ремонт котлов", 2)]
cmp = P.compare([S + "/contacts/", S + "/kotly/", S + "/online/"], DC._core_stems("Ремонт котлов", DC.AXES[0]),
                {S + "/kotly/": "Котлы", S + "/contacts/": "Ремонт котлов"}, "Ремонт котлов")
check([r["words"] for r in cmp] == ["0 из 2", "2 из 2", "2 из 2"], f"слов группы: {cmp}")
check([r["busy"] for r in cmp] == ["", "Котлы", ""], f"занята другой группой (своя - нет): {cmp}")
check(cmp[2]["side"] == "онлайн" and cmp[1]["side"] == "", f"про что: {[r['side'] for r in cmp]}")
check(out["decisions"]["cannibal"] == {"decided": 0, "total": 1, "hidden": 0}, f"итог случаев: {out['decisions']}")
check(not out["cannibal"][0].get("decision") and not out["cannibal"][0]["task"], "у нерешённого случая есть решение")

# 2. «Разделить на две группы», вторая часть - «создать новую»
set_dec(lambda d: d["mixed"].update({KURSY: {"format": {"choice": "split", "page": "new", "at": "04.10"}}}))
out, g = apply()
parts = [x for x in out["groups"] if (x.get("split") or {}).get("from") == "Курсы английского"]
check(len(parts) == 2, f"после «Разделить» частей {len(parts)}")
check(len(out["groups"]) == 4, f"групп после разделения {len(out['groups'])}")
new = [x for x in parts if x["kind"] == "create"]
check(len(new) == 1 and len(new[0]["q"]) == 3 and "Создать страницу" in new[0]["todo"], f"вторая часть: {new}")
check(not any(x.get("mixed") for x in parts), "у частей снова предлагается разделить")
check(sum(len(x["q"]) for x in parts) == 8, "при разделении потерялись запросы")

# 3. «Оставить как есть»
set_dec(lambda d: d["mixed"].update({KURSY: {"format": {"choice": "keep", "at": "04.10"}}}))
out, g = apply()
k = g["Курсы английского"]
check(not k.get("mixed") and [x["axis"] for x in k.get("mixed_kept") or []] == ["format"], f"«Оставить как есть»: {k}")

# 4. «Убрать в отсеянное»
set_dec(lambda d: d["junk"].update({JUNK: {"at": "04.10"}}))
out, g = apply()
check("Подробнее о нас" not in g, "убранная группа осталась")
check(out["dropped"].get(D.JUNK_REASON) == ["подробнее о нас", "подробнее о компании"], f"отсеянное: {out['dropped']}")
check(out["total"] == 11 and [x["name"] for x in out["junk_removed"]] == ["Подробнее о нас"], "итог после отсева")

# 5. «Похоже, не та страница»: выбрана другая страница
set_dec(lambda d: d["landing"].update({KOTLY: {"choice": "page", "page": S + "/kotly/", "at": "04.10"}}))
out, g = apply()
r = g["Ремонт котлов"]
check(r["page"] == S + "/kotly/" and r.get("landing_set", {}).get("choice") == "page" and not r.get("landing"),
      f"выбранная страница: {r.get('page')} {r.get('landing_set')}")

# 6. Страницы мешают друг другу: «склеить», «главная», «не проблема»
for choice, need in (("merge", "301"), ("main", "Главная страница по теме «Ремонт котлов»")):
    set_dec(lambda d: d["cannibal"].update({CASE: {"choice": choice, "main": S + "/kotly/", "at": "04.10"}}))
    out, g = apply()
    c = out["cannibal"][0]
    check(c.get("decision") == choice and need in c["task"], f"случай «{choice}»: {c.get('decision')} {c['task'][:80]}")
    check(out["decisions"]["cannibal"]["decided"] == 1, f"итог после «{choice}»: {out['decisions']}")
set_dec(lambda d: d["cannibal"].update({CASE: {"choice": "ok", "at": "04.10"}}))
out, g = apply()
check(out["decisions"]["cannibal"] == {"decided": 1, "total": 1, "hidden": 1}, f"«не проблема»: {out['decisions']}")

# 7. Галочка «сделано» и запись в файл: решения читаются заново из файла
set_dec(lambda d: d["done"].update({"t1": "04.10"}))
saved = D.load("test.ru")
check(saved["done"] == {"t1": "04.10"} and KURSY in saved["mixed"] and JUNK in saved["junk"], f"файл решений: {saved}")
check(os.path.isfile(D._path("test.ru")) and not os.path.exists(D._path("test.ru") + ".tmp"), "файл решений не записан")
out, g = apply()
check(out["decisions"]["done"] == {"t1": "04.10"}, "галочки не видны в семантике")

if fails:
    print("✗ решения по семантике:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ решения по семантике: разделить, оставить, отсеять, другая страница, мешающие страницы, галочки")
