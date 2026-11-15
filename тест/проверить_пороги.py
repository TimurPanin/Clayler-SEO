"""Автотест экрана «Пороги и проверки» (21.10.2026, без сети):
- каждый порог с экрана (settings.UI) используется в коде программы, а не только в названии проблемы;
- список проверок (window/settings_ui.catalog) собран из всех файлов проверок: у каждой есть название, раздел и
  важность, раздел - короткое название, а не кусок пояснения (так было у «Что мешает покупать»), нет пропавших
  проверок (buy_copyright, server_versions, новые проверки взлома).
Запуск: py -3 тест/проверить_пороги.py (и из проверить_всё.py)."""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import settings  # noqa: E402
from seocrawler.window import settings_ui  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


code = {}
for path in glob.glob(os.path.join(ROOT, "seocrawler", "**", "*.py"), recursive=True):
    name = os.path.relpath(path, ROOT).replace(os.sep, "/")
    if name not in ("seocrawler/settings.py", "seocrawler/window/settings_ui.py"):
        code[name] = open(path, encoding="utf-8").read()
for key, _label, _unit in settings.UI:
    rx = re.compile(r"\b" + key + r"\b")
    used = [n for n, src in code.items() if rx.search(src)]
    check(used, f"порог {key} с экрана нигде в проверках не используется")

cat = settings_ui.catalog()
keys = [x["key"] for x in cat]
check(len(keys) == len(set(keys)), "в списке проверок есть повторы")
# все ключи add("...") из файлов проверок есть в списке
want = set()
for path in glob.glob(os.path.join(settings_ui.CHECKS_DIR, "*.py")):
    want |= set(re.findall(r'\badd\(\s*"([a-z0-9_]+)"', open(path, encoding="utf-8").read()))
lost = sorted(want - set(keys))
check(not lost, f"проверки пропали из списка: {lost}")
# ключи, собранные в цикле (f"counter_{key}_missing", key из списка): до ревизии 22.10.2026 их не было в списке
for k in ("buy_copyright", "server_versions", "hacked_hidden_links", "hacked_spam_links", "soft404",
          "counter_ym_missing", "counter_ga_missing", "lab_lcp", "lab_cls", "lab_tbt"):
    check(k in keys, f"нет проверки {k} в списке")
cats = {x["category"] for x in cat}
for x in cat:
    if not (x["title"] and x["category"] and x["severity"]):
        check(False, f"у проверки {x['key']} пусто: {x}")
    elif len(x["category"]) > 40 or x["category"].endswith("."):
        check(False, f"у {x['key']} вместо раздела кусок текста: {x['category'][:60]}")
check("Что мешает покупать" in cats, "нет раздела «Что мешает покупать»")
buy = [x for x in cat if x["key"].startswith("buy_")]
check(buy and all(x["category"] == "Что мешает покупать" for x in buy if x["key"] != "buy_click"),
      "у проверок покупки раздел не «Что мешает покупать»: "
      + ", ".join(f"{x['key']}={x['category']}" for x in buy if x["category"] != "Что мешает покупать"))
check(any("70" in x["title"] for x in cat if x["key"] == "title_long"),
      "в названии длинного title нет текущего порога 70")

if fails:
    print("✗ пороги и проверки:\n   " + "\n   ".join(fails))
    sys.exit(1)
from seocrawler.fmt import plural  # noqa: E402
n = len(settings.UI)
print(f"✓ пороги и проверки: {n} {plural(n, 'порог', 'порога', 'порогов')} - все используются в коде, в списке {len(cat)} проверок, "
      "у всех название, раздел и важность")
