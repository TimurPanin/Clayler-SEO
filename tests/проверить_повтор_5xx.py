"""Автотест колонки «Повторная проверка» у ошибок сервера 5xx (без сети).
После обхода адреса с 500/503 открываются ещё раз (crawler/extra_passes.recheck_errors); с 22.10 обход записывает,
где ошибка повторилась (meta errors_rechecked.repeated). Проверяет analyze/checks/codes.recheck_marks:
- новая проверка: «повторилась (500)» по списку, адрес не из списка - «не перепроверялась»;
- старая проверка без списка: перепроверено меньше предела - все оставшиеся 5xx «повторились»;
- проверка без перепроверки - «не перепроверялась»; 501 (не временная ошибка) не считается перепроверенной.
Запуск: py -3 tests/проверить_повтор_5xx.py (и из проверить_всё.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler.analyze.checks.codes import recheck_marks  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class Meta:
    def __init__(self, v):
        self.v = v

    def get_meta(self, key, default=None):
        return self.v if key == "errors_rechecked" else default


rows = [{"url": "/a", "status": 500}, {"url": "/b", "status": 503}, {"url": "/c", "status": 501}]
m = recheck_marks(Meta({"checked": 3, "fixed": 1, "limit": 400, "repeated": {"/a": 500}}), rows)
check(m == {"/a": "повторилась (500)", "/b": "не перепроверялась", "/c": "не перепроверялась"}, f"новая проверка: {m}")
m = recheck_marks(Meta({"checked": 14, "fixed": 0}), rows)
check(m["/a"] == "повторилась (500)" and m["/b"] == "повторилась (503)" and m["/c"] == "не перепроверялась",
      f"старая проверка: {m}")
m = recheck_marks(Meta({"checked": 400, "fixed": 0}), rows)
check(m["/a"] == "не перепроверялась", f"старая проверка с пределом 400 - не все перепроверены: {m}")
m = recheck_marks(Meta(None), rows)
check(set(m.values()) == {"не перепроверялась"}, f"без перепроверки: {m}")

if fails:
    print("✗ повтор ошибок 5xx:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ повтор ошибок 5xx: колонка «Повторная проверка» для новых и старых проверок")
