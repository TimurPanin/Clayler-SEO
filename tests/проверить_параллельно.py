"""Автотест: ваш сайт и конкуренты проверяются одновременно (window/job.py, Job._run_parallel).

Три тестовых сайта, одновременно не больше 2 (PARALLEL подменяется): третий ждёт очереди, у каждого сайта свой
журнал и ход, ваш сайт первым в сравнении, сравнение с конкурентами собирается, когда закончат все.
Запуск: py -3 tests/проверить_параллельно.py"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from проверить_всё import wait_up  # noqa: E402

SITES = [("htmlsite", 8781), ("imgsite", 8782), ("testsite", 8783)]


def main():
    tmp = tempfile.mkdtemp(prefix="clayler-par-")
    os.environ.update(CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1",
                      CLAYLER_NO_SPEED_LAB="1")
    from seocrawler.window import job as J
    J.REPORTS = tmp  # файлы «стоп» и состояния - тоже во временной папке
    J.PARALLEL = 2
    from seocrawler import telegram
    telegram.notify_job = lambda job: None  # в Telegram из теста ничего не уходит
    fails = []

    def check(cond, text):
        if not cond:
            fails.append(text)

    # конкуренту - вдвое меньше потоков, не меньше 2; пауза между запросами та же
    check(J._fewer_threads(["--threads", "8", "--delay", "1"]) == ["--threads", "4", "--delay", "1"], "потоки 8 → 4")
    check(J._fewer_threads(["--threads", "2"]) == ["--threads", "2"], "потоки 2 → 2")
    check(J._fewer_threads(["--delay", "0.2"]) == ["--delay", "0.2", "--threads", "2"], "по умолчанию 2 потока")

    srvs = [subprocess.Popen([sys.executable, os.path.join(HERE, f"{n}.py"), str(p)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for n, p in SITES]
    try:
        for n, p in SITES:
            if not wait_up(p):
                print(f"✗ параллельная проверка: тестовый сайт {n} не запустился (порт {p} занят?)")
                sys.exit(1)
        job = J.Job()
        sites = [f"http://127.0.0.1:{p}/" for _, p in SITES]
        job.start(sites, ["--max-pages", "15", "--delay", "0", "--no-external"])
        t0, most, waited = time.time(), 0, False
        while job.running and time.time() - t0 < 400:
            s = job.status()
            states = [r["state"] for r in s.get("runs") or []]
            most = max(most, states.count("run"))
            waited = waited or ("wait" in states and states.count("run") >= 1)
            if states and states[0] == "done" and "run" in states[1:]:  # ваш сайт готов, конкурент идёт
                check(s.get("own_done") and s.get("prog_line") == job.subs[0].prog_line(),
                      "плитки вашего сайта берут строку прогресса не вашего сайта")
                check(s.get("overall_all") is not None and s["overall_all"] < 100,
                      f"«всей проверки сделано» {s.get('overall_all')} %, хотя конкурент ещё идёт")
            time.sleep(0.3)
        s = job.status()
        check(not s["running"], "проверка не закончилась за 400 с")
        check(most == 2, f"одновременно шло сайтов: {most}, а должно 2 (лимит)")
        check(waited, "третий сайт не ждал очереди")
        runs = s.get("runs") or []
        check(len(runs) == 3 and all(r["state"] == "done" for r in runs),
              "не все сайты готовы: " + ", ".join(f"{r['site']} {r['state']}" for r in runs))
        for r, (_, p) in zip(runs, SITES):  # журнал у каждого свой
            log = "\n".join(r["log"] or [])
            check(f"127.0.0.1:{p}" in log and all(f"127.0.0.1:{q}/" not in log for _, q in SITES if q != p),
                  f"журнал сайта {p} смешан с другими или пуст")
            check(bool(r["report"]), f"у сайта {p} нет отчёта")
        check(len(job.dirs) == 3 and "8781" in os.path.basename(job.dirs[0]), "ваш сайт не первым в сравнении")
        check(bool(s["competitors"]) and os.path.exists(job.competitors_report), "сравнение с конкурентами не собралось")
        check(s["report"] and "8781" in s["report"], "главная карточка показывает не ваш сайт")
        check(len(s["site_pages"]) == 3, "нет числа страниц по каждому сайту")
        check(job.run_status(9) is None and job.run_status(2)["who"] == "конкурент", "run_status")
        # «Остановить» останавливает все сайты сразу, тот, что ждал очереди, не начинается
        job = J.Job()
        job.start(sites, ["--max-pages", "200", "--delay", "0.5", "--no-external"])
        t1 = time.time()
        while time.time() - t1 < 60 and sum(r["state"] == "run" for r in job.status().get("runs") or []) < 2:
            time.sleep(0.2)
        time.sleep(2)
        job.stop()
        while job.running and time.time() - t1 < 300:
            time.sleep(0.3)
        s = job.status()
        states = [r["state"] for r in s.get("runs") or []]
        check(not s["running"] and s["stopped"], "после «Остановить» проверка не остановилась")
        check(states[2] == "skipped", f"сайт из очереди после «Остановить»: {states[2]}, а должен быть не начат")
        check(not s["competitors"], "после «Остановить» сравнение не нужно")
    finally:
        for p in srvs:
            p.terminate()
    if fails:
        print("✗ параллельная проверка:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ параллельная проверка: 3 сайта, не больше 2 сразу, свои журналы, сравнение собрано, {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
