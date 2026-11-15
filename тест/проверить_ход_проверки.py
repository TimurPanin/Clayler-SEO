"""Автотест: окно и журнал показывают правду о ходе проверки (разбор скорости thehome.ru, 06.11.2026).
- скорость - за последнюю минуту, а не средняя с начала шага: на смене быстрых адресов на медленные это разные числа;
- своя короткая пауза для картинок, а «Бережно» она не трогает; такая пауза не сокращается ещё вдвое;
- строка в файле «ход проверки.txt» пишется раз в 5 минут и считает скорость страниц и картинок отдельно;
- при сборке отчёта окно показывает процент сборки, а не счётчик прошлого шага («600 из 600»).
Запуск: py -3 тест/проверить_ход_проверки.py"""
import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace

os.environ["CLAYLER_JOURNAL_DIR"] = tempfile.mkdtemp(prefix="clayler-hod-")   # журнал программы - не настоящий
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.crawler.common import RateLimiter, res_delay  # noqa: E402
from seocrawler.crawler.main_loop import JOURNAL_FILE, MainLoopMixin, speed_now  # noqa: E402
from seocrawler.window import job as J  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# скорость: 600 с шли по 4 адр/с, последнюю минуту по 1,5. Среднее сказало бы 3,8
points = [(600 + i * 3, 2400 + int(i * 3 * 1.5)) for i in range(21)]
check(abs(speed_now(points) - 1.5) < 0.05, f"скорость за минуту: {speed_now(points)}")
check(speed_now(points[:1]) == 0.0, "одна отметка: скорости ещё нет")

# пауза картинок
check(res_delay(0.2) == 0.05 and res_delay(0.05) == 0.05, "обычная и быстрая скорость: пауза картинок 0,05 с")
check(res_delay(1) == 1, "«Бережно»: пауза картинок прежняя")
lim = RateLimiter(res_delay(0.2), speed_up=False)
for _ in range(100):
    lim.success(0.01)
check(lim.delay == 0.05, f"короткая пауза не сокращается: {lim.delay}")
lim.backoff(0)
check(lim.delay >= 0.5, f"сайт просит подождать: пауза растёт, {lim.delay}")
fast = RateLimiter(0.2)
for _ in range(100):
    fast.success(0.01)
check(abs(fast.delay - 0.1) < 0.001, f"пауза страниц ускоряется как раньше: {fast.delay}")

# ход проверки на диске
with tempfile.TemporaryDirectory() as tmp:
    done = {"page": {"done": 100, "queued": 900}, "resource": {"done": 500, "queued": 50}}
    run = SimpleNamespace(store=SimpleNamespace(progress=lambda: done), store_path=os.path.join(tmp, "crawl.db"),
                          log=print)
    MainLoopMixin.note_progress(run, "обход", 100, 6.2)
    MainLoopMixin.note_progress(run, "обход", 101, 6.2)   # раньше 5 минут - не пишем
    run._journal_at, run._journal_last = time.time() - 301, (40, 200, time.time() - 300)
    MainLoopMixin.note_progress(run, "обход", 100, 6.2)
    with open(os.path.join(tmp, JOURNAL_FILE), encoding="utf-8") as f:
        lines = f.read().splitlines()
    check(len(lines) == 2, f"строк в журнале: {lines}")
    check("страниц 100 (0.20/с)" in lines[1] and "картинок и файлов 500 (1.00/с)" in lines[1]
          and "ждут 950" in lines[1],
          f"строка журнала: {lines[1]}")

    # процент сборки отчёта в окне
    path = os.path.join(tmp, "status.json")
    job = J.Job()
    job.active, job.status_file, job.started = True, path, time.time()

    def state(**kw):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kw, f, ensure_ascii=False)
        return job.status()
    s = state(step="Собираю отчёт: ищу проблемы по всему сайту", report_frac=0.402, unit="slow", pages=600, limit=600)
    check(s["report_pct"] == 40, f"сборка отчёта: {s['report_pct']}")
    check(not s["progress"], f"сборка отчёта без счётчика прошлого шага: {s['progress']}")
    s = state(step="Обновляю отчёт: собираю отчёт.xlsx", report_frac=0.94)
    check(s["report_pct"] == 94, f"обновить отчёт: {s['report_pct']}")
    s = state(step="Шаг 4 из 4: адреса из sitemap", unit="sitemap", pages=10, limit=100)
    check(s["report_pct"] is None and s["progress"] == [10, 100], f"обход: {s['report_pct']}, {s['progress']}")
    job.active = False

if fails:
    print("✗ ход проверки:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ ход проверки: скорость за минуту, пауза картинок, файл хода проверки, процент сборки отчёта")
