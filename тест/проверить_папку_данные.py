"""Автотест: ваши файлы - в папке «данные», а не в корне программы (28.10.2026, без сети).
- старые файлы из корня (доступы, очередь, логотип, «решения семантики», папка «очередь» со списками) при первом
  запуске переезжают в «данные» сами; файл, который уже есть в «данные», не заменяется;
- все модули берут эти файлы из «данные» (seocrawler/paths.py), ни один не собирает путь к ним от корня программы.
Запуск: py -3 тест/проверить_папку_данные.py (и из проверить_всё.py)."""
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="clayler-data-")
os.environ["CLAYLER_DATA_DIR"] = os.path.join(TMP, "подмена")   # импорт не трогает настоящие файлы
from seocrawler import paths as P  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# 1. перенос из корня
app = os.path.join(TMP, "программа")
os.makedirs(os.path.join(app, "очередь"))
os.makedirs(os.path.join(app, "решения семантики"))
os.makedirs(os.path.join(app, "данные"))
for name, text in (("доступы.json", "старые доступы"), ("наблюдение.json", "в корне"), ("логотип.png", "картинка"),
                   ("доступы.json.испорчен-20261028-120000", "копия"), ("журнал программы.txt", "журнал"),
                   (os.path.join("очередь", "Москва.txt"), "site.ru"),
                   (os.path.join("решения семантики", "site.ru - маски.json"), "{}")):
    with open(os.path.join(app, name), "w", encoding="utf-8") as f:
        f.write(text)
with open(os.path.join(app, "данные", "наблюдение.json"), "w", encoding="utf-8") as f:
    f.write("уже в данных")
del os.environ["CLAYLER_DATA_DIR"]
P.APP, P.DATA = app, os.path.join(app, "данные")
# пока окно не переносило файлы (проверку запустило окно на старом коде) - читается старое место в корне
check(P.data("доступы.json") == os.path.join(app, "доступы.json"), f"до переноса - не старое место: {P.data('доступы.json')}")
check(P.data("списки сайтов", "Москва.txt") == os.path.join(app, "очередь", "Москва.txt"), "списки до переноса")
# «данные/списки сайтов» уже есть (из git) - свои списки из старой «очередь» всё равно переезжают, по файлам
os.makedirs(os.path.join(app, "данные", "списки сайтов"))
with open(os.path.join(app, "данные", "списки сайтов", "из git.txt"), "w", encoding="utf-8") as f:
    f.write("git")
P.migrate()
P.migrate()   # второй запуск ничего не ломает


def read(*p):
    try:
        with open(os.path.join(app, *p), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


check(read("данные", "доступы.json") == "старые доступы" and read("доступы.json") is None, "доступы.json не переехал")
check(read("данные", "логотип.png") == "картинка", "логотип не переехал")
check(read("данные", "доступы.json.испорчен-20261028-120000") == "копия", "копия испорченного файла доступов не переехала")
check(read("данные", "журнал программы.txt") == "журнал", "журнал не переехал")
check(read("данные", "списки сайтов", "Москва.txt") == "site.ru" and not os.path.exists(os.path.join(app, "очередь")),
      "папка «очередь» не стала «данные/списки сайтов»")
check(read("данные", "решения семантики", "site.ru - маски.json") == "{}", "«решения семантики» не переехали")
check(read("данные", "списки сайтов", "из git.txt") == "git", "файл из git в «списки сайтов» пропал")
check(P.data("доступы.json") == os.path.join(app, "данные", "доступы.json"), "после переноса - не «данные»")
check(read("данные", "наблюдение.json") == "уже в данных" and read("наблюдение.json") == "в корне",
      "файл в «данные» заменён старым из корня")

# 2. модули берут файлы из «данные»
for k in [k for k in os.environ if k.startswith("CLAYLER_")]:
    del os.environ[k]
import importlib  # noqa: E402
P.APP, P.DATA = ROOT, os.path.join(ROOT, "данные")
want = {"seocrawler.accounts": "FILE", "seocrawler.watch": "FILE", "seocrawler.site_queue": "FILE",
        "seocrawler.settings": "USER_FILE", "seocrawler.brand": "FILE", "seocrawler.labels": "FILE",
        "seocrawler.extract": "FILE", "seocrawler.semantics.decisions": "DIR", "seocrawler.semantics.dicts": "FILE",
        "seocrawler.semantics.dictionary": "FILE", "seocrawler.semantics.words": "STOP_FILE",
        "seocrawler.window.reports_list": "FAV"}
for mod, attr in want.items():
    v = getattr(importlib.import_module(mod), attr)
    check(os.path.abspath(v).startswith(os.path.abspath(P.DATA) + os.sep), f"{mod}.{attr} не в «данные»: {v}")
from seocrawler import applog, site_queue  # noqa: E402
check(os.path.dirname(applog.path()) == P.DATA, f"журнал не в «данные»: {applog.path()}")
check(site_queue.LISTS == os.path.join(P.DATA, "списки сайтов"), f"списки сайтов: {site_queue.LISTS}")

# 3. никто не собирает путь к этим файлам от корня программы мимо paths.py
names = [n for n in P.MOVED if "." in n]
for d, _dirs, fs in os.walk(os.path.join(ROOT, "seocrawler")):
    for fn in fs:
        if not fn.endswith(".py") or fn == "paths.py":
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if "os.path.join(" in line and "paths." not in line and any(f'"{n}"' in line for n in names) and \
                        re.search(r"__file__|HERE|ROOT|APP", line):
                    fails.append(f"{fn}:{i}: путь к личному файлу от корня программы: {line.strip()[:120]}")

shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("✗ папка «данные»:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ папка «данные»: старые файлы переезжают сами, уже перенесённые не заменяются, все модули берут файлы оттуда")
