"""Автотест склейки форм запроса (semantics/forms.py): «группа безопасности» и «группы безопасности»,
порядок слов, «ё» - одна строка, остальные формы рядом; частота Директа - наибольшая, а не сумма."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import direct
from seocrawler.semantics import export, forms

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def row(q, score, shows=0, check_="", freq=0, place=0):
    return [q, "", "Общий", score, 3, 0, shows, check_, place, "", 0, freq, 0, 0]


data = {"host": "teplo-dom.ru", "city": None, "total": 9, "groups": [
    {"name": "Газовые котлы", "q": [row("газовые котлы", 20, shows=10, place=7.5), row("газовый котёл", 15),
                                     row("котел газовый", 12, shows=5, place=4.2), row("газовые котлы купить", 9),
                                     row("онлайн-котлы", 3)]},
    {"name": "Котлы", "q": [row("котлы газовые", 25, check_="возможно, про другое"), row("котлы", 30),
                            row("онлайн котлы", 2)]},
    {"name": "Газовым котлом", "q": [row("газовым котлом", 1)]}]}
d = forms.merge(json.loads(json.dumps(data)))
rows = {r[0]: r for g in d["groups"] for r in g["q"]}
check(set(rows) == {"газовые котлы", "газовые котлы купить", "котлы", "онлайн-котлы", "газовым котлом"},
      f"склейка форм, порядка и ё: {sorted(rows)}")
m = rows.get("газовые котлы") or [0] * 15
check(sorted(m[14]) == sorted(["газовый котёл", "котел газовый", "котлы газовые"]),
      f"другие формы рядом: {m[14]}")
check(m[3] == 25 and m[6] == 15 and m[8] == 4.2, f"оценка - наибольшая, показы - сумма, место - лучшее: {m}")
check(rows.get("онлайн-котлы", [0] * 15)[14] == ["онлайн котлы"], "«онлайн-котлы» = «онлайн котлы», но не «котлы»")
check(len(d["groups"]) == 3, "последняя строка группы не уходит в другую группу")
check(d["forms_merged"] == 4 and d["total"] == 5, f"счётчики: {d['forms_merged']}, {d['total']}")
check(forms.merge(d)["forms_merged"] == 4, "повторная склейка ничего не ломает")

# частота из Директа: у главной формы нет, у другой есть - берётся наибольшая, не сумма
TMP = tempfile.mkdtemp(prefix="clayler-forms-")
with open(os.path.join(TMP, export.JSON_NAME), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
lr, _ = direct.region_of(None)
direct.load = lambda host: {str(lr): {"phr": {"газовый котел": (900, "01.10.2026"), "котел газовый": (700, "01.10.2026"),
                                              "котлы": (5000, "01.10.2026")}}}
d = export.load(TMP)
rows = {r[0]: r for g in d["groups"] for r in g["q"]}
check(rows["газовые котлы"][11] == 900, f"частота формы - наибольшая: {rows['газовые котлы'][11]}")
check(rows["котлы"][11] == 5000, "частота одиночного запроса")
shutil.rmtree(TMP, ignore_errors=True)

if fails:
    print("ФОРМЫ ЗАПРОСОВ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Формы запросов (склейка дублей): всё в порядке")
