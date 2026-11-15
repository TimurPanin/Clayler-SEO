"""Автотест: ваши файлы - в папке «data», отчёты - в «reports», а не в корне программы и не в старых папках (без сети).
- старые файлы из корня (доступы, очередь, логотип, «решения семантики», папка «очередь» со списками) при первом
  запуске переезжают в «data» сами; файл, который уже есть в «data», не заменяется;
- старые папки «данные» и «отчёты» сами становятся «data» и «reports» (вместе с «отчёты/архив» → «reports/archive»);
  если «data» уже есть (из git), старая «данные» сливается с ней по файлам, своё не теряется;
- все модули берут эти файлы из «data» (seocrawler/paths.py), ни один не собирает путь к ним от корня программы.
Запуск: py -3 tests/проверить_папку_данные.py (и из проверить_всё.py)."""
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
os.makedirs(os.path.join(app, "data"))
for name, text in (("доступы.json", "старые доступы"), ("наблюдение.json", "в корне"), ("логотип.png", "картинка"),
                   ("доступы.json.испорчен-20261028-120000", "копия"), ("журнал программы.txt", "журнал"),
                   (os.path.join("очередь", "Москва.txt"), "site.ru"),
                   (os.path.join("решения семантики", "site.ru - маски.json"), "{}")):
    with open(os.path.join(app, name), "w", encoding="utf-8") as f:
        f.write(text)
with open(os.path.join(app, "data", "наблюдение.json"), "w", encoding="utf-8") as f:
    f.write("уже в данных")
del os.environ["CLAYLER_DATA_DIR"]
P.APP, P.DATA = app, os.path.join(app, "data")
# пока окно не переносило файлы (проверку запустило окно на старом коде) - читается старое место в корне
check(P.data("доступы.json") == os.path.join(app, "доступы.json"), f"до переноса - не старое место: {P.data('доступы.json')}")
check(P.data("списки сайтов", "Москва.txt") == os.path.join(app, "очередь", "Москва.txt"), "списки до переноса")
# «data/списки сайтов» уже есть (из git) - свои списки из старой «очередь» всё равно переезжают, по файлам
os.makedirs(os.path.join(app, "data", "списки сайтов"))
with open(os.path.join(app, "data", "списки сайтов", "из git.txt"), "w", encoding="utf-8") as f:
    f.write("git")
P.migrate()
P.migrate()   # второй запуск ничего не ломает


def read(*p):
    try:
        with open(os.path.join(app, *p), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


check(read("data", "доступы.json") == "старые доступы" and read("доступы.json") is None, "доступы.json не переехал")
check(read("data", "логотип.png") == "картинка", "логотип не переехал")
check(read("data", "доступы.json.испорчен-20261028-120000") == "копия", "копия испорченного файла доступов не переехала")
check(read("data", "журнал программы.txt") == "журнал", "журнал не переехал")
check(read("data", "списки сайтов", "Москва.txt") == "site.ru" and not os.path.exists(os.path.join(app, "очередь")),
      "папка «очередь» не стала «data/списки сайтов»")
check(read("data", "решения семантики", "site.ru - маски.json") == "{}", "«решения семантики» не переехали")
check(read("data", "списки сайтов", "из git.txt") == "git", "файл из git в «списки сайтов» пропал")
check(P.data("доступы.json") == os.path.join(app, "data", "доступы.json"), "после переноса - не «data»")
check(read("data", "наблюдение.json") == "уже в данных" and read("наблюдение.json") == "в корне",
      "файл в «data» заменён старым из корня")

# 1б. старые русские папки «данные» и «отчёты» переезжают в «data» и «reports»
app2 = os.path.join(TMP, "программа2")
for name, text in ((os.path.join("данные", "доступы.json"), "мои доступы"),
                   (os.path.join("данные", "решения семантики", "site.ru - маски.json"), "{}"),
                   (os.path.join("data", "иконка.png"), "из git"),
                   (os.path.join("отчёты", "site.ru_2026-10-01_10-00-00", "crawl.db"), "база"),
                   (os.path.join("отчёты", "архив", "old.ru_2026-09-01_10-00-00", "crawl.db"), "в архиве")):
    os.makedirs(os.path.dirname(os.path.join(app2, name)), exist_ok=True)
    with open(os.path.join(app2, name), "w", encoding="utf-8") as f:
        f.write(text)
P.APP = app2
check(P.reports_dir() == os.path.join(app2, "отчёты"), f"до переноса отчёты не в старой папке: {P.reports_dir()}")
P.migrate_folders()
P.migrate_folders()   # второй запуск ничего не ломает


def read2(*p):
    try:
        with open(os.path.join(app2, *p), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


check(read2("data", "доступы.json") == "мои доступы", "«данные» не слились с «data»")
check(read2("data", "решения семантики", "site.ru - маски.json") == "{}", "папка внутри «данные» не переехала")
check(read2("data", "иконка.png") == "из git", "файл из git в «data» заменён")
check(not os.path.exists(os.path.join(app2, "данные")), "старая «данные» осталась после переноса")
check(read2("reports", "site.ru_2026-10-01_10-00-00", "crawl.db") == "база", "«отчёты» не стали «reports»")
check(read2("reports", "archive", "old.ru_2026-09-01_10-00-00", "crawl.db") == "в архиве", "архив не стал «reports/archive»")
check(not os.path.exists(os.path.join(app2, "отчёты")), "старая «отчёты» осталась после переноса")
check(P.reports_dir() == os.path.join(app2, "reports") and P.DATA == os.path.join(app2, "data"),
      f"после переноса пути не новые: {P.reports_dir()} {P.DATA}")

# 2. модули берут файлы из «data»
for k in [k for k in os.environ if k.startswith("CLAYLER_")]:
    del os.environ[k]
import importlib  # noqa: E402
P.APP, P.DATA = ROOT, os.path.join(ROOT, "data")
want = {"seocrawler.accounts": "FILE", "seocrawler.watch": "FILE", "seocrawler.site_queue": "FILE",
        "seocrawler.settings": "USER_FILE", "seocrawler.brand": "FILE", "seocrawler.labels": "FILE",
        "seocrawler.extract": "FILE", "seocrawler.semantics.decisions": "DIR", "seocrawler.semantics.dicts": "FILE",
        "seocrawler.semantics.dictionary": "FILE", "seocrawler.semantics.words": "STOP_FILE",
        "seocrawler.window.reports_list": "FAV"}
for mod, attr in want.items():
    v = getattr(importlib.import_module(mod), attr)
    check(os.path.abspath(v).startswith(os.path.abspath(P.DATA) + os.sep), f"{mod}.{attr} не в «data»: {v}")
from seocrawler import applog, site_queue  # noqa: E402
check(os.path.dirname(applog.path()) == P.DATA, f"журнал не в «data»: {applog.path()}")
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
    print("✗ папка «data»:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ папка «data»: старые файлы переезжают сами, уже перенесённые не заменяются, все модули берут файлы оттуда")
