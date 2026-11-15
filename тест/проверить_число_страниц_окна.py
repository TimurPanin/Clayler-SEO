"""Автотест: на готовой проверке окно показывает итоговое число страниц из «Проверено страниц сайта: N», а не
последнюю строку обхода «Страниц сайта: … из …» (30.10.2026, vsekuhni.ru: в окне 2 061, в отчёте 2 064 - строка
пишется раз в несколько секунд, последние 3 страницы обхода закончились после неё). Пока проверка идёт - число из строки обхода, как раньше.
Запуск: py -3 тест/проверить_число_страниц_окна.py (и из проверить_всё.py)."""
import os
import sys
import tempfile

os.environ["CLAYLER_JOURNAL_DIR"] = tempfile.mkdtemp(prefix="clayler-pages-")   # журнал программы - не ваш
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.window import job as J  # noqa: E402

fails = []
job = J.Job()
job.site = "https://site.ru/"
for line in ("Шаг 3 из 4. Обхожу сайт по ссылкам, начиная с главной.",
             "Страниц сайта: 2 061 из 200 000 | картинок и файлов: 1 407 | ждут проверки: 0 | 6.5 адр/с",
             "Шаг 4 из 4. Проверки и отчёт",
             "   Проверено страниц сайта: 2064"):
    job.add(line)
s = job.status()
if s["running"] or not s["progress"] or s["progress"][0] != 2064:
    fails.append(f"готовая проверка: в окне {s['progress']}, а должно 2064 (итог проверки)")

job = J.Job()
job.add("Страниц сайта: 150 из 200 000 | картинок и файлов: 10 | ждут проверки: 5 | 6.5 адр/с")
s = job.status()
if not s["progress"] or s["progress"][0] != 150:
    fails.append(f"без итоговой строки: в окне {s['progress']}, а должно 150")

if fails:
    print("✗ число страниц в окне:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ число страниц в окне: на готовой проверке - итог из журнала, а не последняя строка обхода")
