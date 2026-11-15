"""Отпечатки своего текста страниц на нескольких ядрах (analyze/common.own_text): на большом сайте
считаются в других процессах, результат и порядок - как на одном ядре. Из постороннего скрипта (не crawl.py и не
app.py) несколько ядер не включаются: новый процесс в Windows заново выполняет главный файл, и скрипт без
«if __name__» прошёл бы целиком в каждом процессе. Без сети. Запуск: py -3 tests/проверить_ядра_анализа.py."""
import os
import random
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def pages(n):
    rnd = random.Random(7)
    words = "диван кресло стол шкаф полка зеркало кровать тумба комод стул светильник ковёр доставка цена".split()
    out = []
    for i in range(n):
        own = [" ".join(rnd.choice(words) for _ in range(rnd.randint(40, 200))) for _ in range(3)]
        out.append({"url": f"https://shop.test/p{i}/",
                    "blocks": zlib.compress("\n".join(["Меню", "Каталог", "Контакты"] + own).encode("utf-8"))})
    return out


def main():
    if "--child" in sys.argv:   # посторонний скрипт без crawl.py: должно посчитаться одним ядром
        from seocrawler.analyze import common as C
        C.PARALLEL_MIN = 1
        print("ядер:", "одно" if C._parallel(len, ["a", "bb"]) is None else "несколько")
        return
    from seocrawler.analyze import common as C
    ps = pages(400)
    blocks = C.own_blocks(ps)
    C.PARALLEL_MIN = 10 ** 9
    one = C.own_text(ps, blocks)
    os.environ["CLAYLER_PARALLEL"] = "1"
    C.PARALLEL_MIN = 1
    many = C.own_text(ps, blocks)
    check(len(one) == 400, f"отпечатков {len(one)}, ждали 400")
    check(one == many, "на нескольких ядрах отпечатки другие, чем на одном")
    check(list(one) == list(many), "на нескольких ядрах другой порядок страниц")
    check(C._parallel(len, ["a", "bb"]) == [1, 2], "несколько ядер не включились по CLAYLER_PARALLEL=1")
    # сколько процессов: не больше настоящих ядер и 6, меньше - когда процессор занят или мало свободной памяти
    n = os.cpu_count() or 2
    top = max(1, min(6, n // 2))
    for busy, free, want in ((0, 10 ** 6, top), (50, 10 ** 6, min(top, max(1, int(n * 0.5 / 2)))),
                             (95, 10 ** 6, 1), (0, 3500, min(top, 3)), (0, 1500, 1)):
        got = C.workers_now(busy=busy, free=free)
        check(got == want, f"процессов при занятости {busy}% и {free} МБ свободно: {got}, ждали {want}")
    check(1 <= C.workers_now() <= 6, f"процессов сейчас: {C.workers_now()}")
    env = {k: v for k, v in os.environ.items() if k != "CLAYLER_PARALLEL"}
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child"], env=dict(env, PYTHONIOENCODING="utf-8"),
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    check("ядер: одно" in r.stdout, f"из постороннего скрипта включились несколько ядер: {r.stdout.strip()} {r.stderr[-300:]}")
    if fails:
        print("✗ ядра анализа:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ ядра анализа: отпечатки на нескольких ядрах те же и в том же порядке, посторонний скрипт - одно ядро")


if __name__ == "__main__":
    main()
