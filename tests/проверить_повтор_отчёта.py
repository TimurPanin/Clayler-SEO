"""Автотест: отчёт одной и той же проверки, собранный несколько раз, одинаковый.
Раньше «План перелинковки» (franmeb: 820 или 819 страниц), список файлов «Шаблон сайта сам весит», подразделы
на карте сайта и связи разделов в паутине менялись от запуска к запуску: среди равных (одинаковое число ссылок,
страниц, размер файла) порядок зависел от перебора множеств Python. Здесь выдуманный сайт, где таких равных много,
отчёт собирается в отдельных процессах с разным PYTHONHASHSEED - как три запуска «Обновить отчёт».
Запуск: py -3 tests/проверить_повтор_отчёта.py (и из проверить_всё.py)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from seocrawler.storage import Store  # noqa: E402

B = "https://tie.test"
TMP = tempfile.mkdtemp(prefix="clayler-repeat-")
SRC = os.path.join(TMP, "tie.test_2026-10-17_10-00-00")
os.makedirs(SRC)
st = Store(os.path.join(SRC, "crawl.db"))
st.set_meta("start", B + "/")
st.set_meta("started_at", "2026-10-17 10:00:00")
st.set_meta("finished_at", "2026-10-17 10:05:00")

JS = [f"{B}/js/f{i:02d}.js" for i in range(30)]   # шаблон: 30 файлов одного размера на всех страницах, 1,5 МБ
pages, links = [], []


def page(u, depth, title, h1=None):
    pages.append((u, depth, title, h1 or title))


page(B + "/", 0, "Мебель на заказ")
page(B + "/katalog/", 1, "Каталог мебели")
SUBS = [f"s{i:02d}" for i in range(12)]   # 12 одинаковых подразделов, а показываются 10
for s in SUBS:
    page(f"{B}/katalog/{s}/", 2, f"Шкафы дуб серия {s}")
    links.append((B + "/katalog/", f"{B}/katalog/{s}/", f"Серия {s}"))
    for k in range(5):
        u = f"{B}/katalog/{s}/item{k}/"
        page(u, 3 + (k % 2), f"Шкаф дуб купе {s} модель {k}")
        links.append((f"{B}/katalog/{s}/", u, f"Модель {k}"))
for sec in ("blog", "uslugi", "otzyvy"):   # разделы, которые ссылаются друг на друга: связи в паутине
    page(f"{B}/{sec}/", 1, f"Раздел {sec}")
    for k in range(6):
        page(f"{B}/{sec}/p{k}/", 2, f"Страница {sec} номер {k}")
        links.append((f"{B}/{sec}/", f"{B}/{sec}/p{k}/", f"Номер {k}"))
for k in range(6):
    links.append((f"{B}/blog/p{k}/", f"{B}/uslugi/p{k}/", "Услуга"))
    links.append((f"{B}/uslugi/p{k}/", f"{B}/otzyvy/p{k}/", "Отзыв"))
    links.append((f"{B}/otzyvy/p{k}/", f"{B}/blog/p{k}/", "Статья"))
for dst in (B + "/katalog/", B + "/blog/", B + "/uslugi/", B + "/otzyvy/"):
    links.append((B + "/", dst, "Меню"))

for u, depth, title, h1 in pages:
    st.enqueue(u, depth, 1, "page", B + "/")
    st.mark(u, "done")
    st.save_page({"url": u, "status": 200, "content_type": "text/html", "size": 20000, "elapsed": 0.2,
                  "indexable": 1, "indexability": "", "title": title + " - купить в Москве", "title_count": 1,
                  "description": "Описание страницы " + title + " с подробностями для покупателя.",
                  "description_count": 1, "h1": h1, "h1_count": 1, "h2_count": 2, "word_count": 300})
for f in JS:
    st.enqueue(f, 1, 1, "resource", B + "/")
    st.mark(f, "done")
    st.save_page({"url": f, "status": 200, "content_type": "application/javascript", "size": 51200, "elapsed": 0.1})
st.add_resources([(u, f, "js") for u, *_ in pages for f in JS])
st.add_links([(s, d, d, a, 0, "a", 1) for s, d, a in links])
st.commit()
st.db.close()

ENV = dict(os.environ, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1", CLAYLER_NO_SITE_TECH="1",
           CLAYLER_NO_SECURITY="1", CLAYLER_NO_SHOP="1", CLAYLER_NO_PROBLEM_SHOTS="1", CLAYLER_NO_PDF="1",
           CLAYLER_NO_MOBILE_VIEW="1", CLAYLER_NO_SOUND="1", CLAYLER_JOURNAL_DIR=TMP, PYTHONIOENCODING="utf-8")
DATE = re.compile(r"\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2}(:\d{2})?)?|\d{4}-\d{2}-\d{2}[ T_]\d{2}[:-]\d{2}([:-]\d{2})?(\.\d+)?")


def build(seed):
    """Отчёт копии проверки в отдельном процессе; {файл: текст без дат}."""
    dst = os.path.join(TMP, f"run{seed}", os.path.basename(SRC))
    shutil.copytree(SRC, dst)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), "--report", dst, "--no-open"], cwd=ROOT,
                       env=dict(ENV, PYTHONHASHSEED=str(seed)), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    out = {}
    for d, _, fs in os.walk(dst):
        for f in fs:
            if f.endswith((".html", ".csv")):
                p = os.path.join(d, f)
                with open(p, encoding="utf-8", errors="replace") as fh:
                    out[os.path.relpath(p, dst)] = DATE.sub("DATE", fh.read())
    return out, r


fails = []
first, r = build(1)
if "перелинковка.csv" not in first or not os.path.exists(os.path.join(TMP, "run1", os.path.basename(SRC), "проблемы",
                                                                       "template_weight.csv")):
    fails.append("на выдуманном сайте нет плана перелинковки или тяжёлого шаблона - тест ничего не проверяет:\n"
                 + (r.stdout + r.stderr)[-1500:])
for seed in (2, 3):
    other, r = build(seed)
    for name in sorted(set(first) | set(other)):
        if first.get(name) != other.get(name):
            fails.append(f"«{name}» другой при повторной сборке (PYTHONHASHSEED 1 и {seed})")
# список проблемы, которой после «Обновить отчёт» больше нет (выключили в «Порогах», исправили), убирается
dst = os.path.join(TMP, "run3", os.path.basename(SRC))
for ext in (".csv", ".html"):
    open(os.path.join(dst, "проблемы", "старая_проблема" + ext), "w").close()
subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), "--report", dst, "--no-open"], cwd=ROOT, env=ENV,
               capture_output=True)
left = os.listdir(os.path.join(dst, "проблемы"))
if any(f.startswith("старая_проблема") for f in left) or "template_weight.csv" not in left:
    fails.append(f"в «проблемы» остался список проблемы, которой больше нет, или пропал нужный: {sorted(left)[:8]}")
shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("✗ повтор отчёта:\n  " + "\n  ".join(fails))
    sys.exit(1)
print("✓ повтор отчёта: план перелинковки, вес шаблона, карта разделов и паутина одинаковые при каждой сборке")
