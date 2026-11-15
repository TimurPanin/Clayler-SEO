"""Закон сохранения (04.11.2026): каждый проверенный адрес своего сайта - ровно в одном ящике (analyze/checks/codes.bucket),
ни один не пропадает молча. Раньше адреса с кодами 204, 206, 304, 399, 999 или редирект без адреса не попадали ни в
один пункт отчёта - их не было видно. Без сети, около минуты:
- перебор: все коды 0-999 (и пустой), с ошибкой загрузки и без, с адресом перехода и без - у каждого есть ящик и
  объяснение «Что это значит»; у каждого ящика-проблемы есть свой пункт отчёта;
- готовые проверки в папке «отчёты» (только чтение, если есть): сумма ящиков = числу проверенных адресов, адресов без
  ящика нет; сводка «Что отвечают страницы» (health._by_status) сходится с числом страниц.
Сквозная сверка с пунктами отчёта на настоящем обходе - в тест/проверить_коды_ответа.py.
Запуск: py -3 тест/проверить_закон_сохранения.py (и из проверить_всё.py)."""
import glob
import os
import re
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler.analyze.checks import codes as C  # noqa: E402
from seocrawler.analyze.health import _by_status  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# ---------- перебор всех кодов
lost = []
for st in [None] + list(range(0, 1000)):
    for err in ("", "Таймаут"):
        for loc in ("", "http://x.ru/new/"):
            b = C.bucket(st, err, loc)
            if b not in C.BUCKETS:
                lost.append((st, err, loc, b))
            if st and not C.meaning(st):
                lost.append((st, "нет объяснения"))
            elif st and not C.odd(st) and "необычн" in C.meaning(st):
                lost.append((st, "обычный код назван необычным: " + C.meaning(st)))
check(not lost, f"коды без ящика или объяснения: {lost[:10]} (всего {len(lost)})")
check(C.bucket(200) == "ok" and C.bucket(200, "Загрузка дольше 45 с - прервана") == "noresp"
      and C.bucket(404, "Таймаут") == "4xx" and C.bucket(0) == "noresp" and C.bucket(301) == "redirect_noloc"
      and C.bucket(301, "", "/x") == "redirect" and C.bucket(429) == "too_many_requests" and C.bucket(999) == "odd_codes"
      and C.bucket(399, "", "/x") == "odd_codes" and C.bucket(520) == "5xx", "ящики частых случаев")
check(all(C.label(st) for st in range(1, 1000)), "у кода нет короткой подписи для сводки")
# «не открывается»: правило для базы (NOT_OPEN_SQL, битые ссылки) = правило в коде (not_open) на всех сочетаниях
mem = sqlite3.connect(":memory:")
mem.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, status INTEGER, error TEXT, location TEXT)")
combos = [(st, err, loc) for st in [None] + list(range(0, 1000)) for err in ("", "Таймаут", None)
          for loc in ("", None, "http://x.ru/new/")]
mem.executemany("INSERT INTO pages (status, error, location) VALUES (?, ?, ?)", combos)
by_sql = {i for (i,) in mem.execute(f"SELECT id FROM pages p WHERE {C.NOT_OPEN_SQL}")}
diff = [c for i, c in enumerate(combos, 1) if (i in by_sql) != C.not_open(c[0], c[1] or "", c[2] or "")]
check(not diff, f"правило для базы и в коде расходятся: {diff[:8]} (всего {len(diff)})")
check(C.not_open(404) and C.not_open(200, "Таймаут") and C.not_open(301, "", "") and not C.not_open(301)
      and not C.not_open(429) and not C.not_open(204) and not C.not_open(200), "«не открывается» в частых случаях")
# у каждого ящика-проблемы есть пункт отчёта с тем же ключом
src = "".join(open(os.path.join(ROOT, "seocrawler", "analyze", "checks", f), encoding="utf-8").read()
              for f in ("codes.py", "redirects.py"))
keys = set(re.findall(r'\badd\(\s*"([a-z0-9_]+)"', src))
check(set(C.BUCKETS) - {"ok", "redirect"} <= keys, f"ящики без пункта отчёта: {set(C.BUCKETS) - {'ok', 'redirect'} - keys}")

# ---------- готовые проверки
seen = 0
for db in sorted(glob.glob(os.path.join(ROOT, "отчёты", "*", "crawl.db"))):
    name = os.path.basename(os.path.dirname(db))
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        own = c.execute("""SELECT p.url, p.status, p.error, p.location, u.kind FROM pages p JOIN urls u ON u.url=p.url
                           WHERE u.internal=1 AND u.kind<>'sitemap'""").fetchall()
    except sqlite3.Error as e:
        check(False, f"{name}: база не читается ({e})")
        continue
    seen += 1
    box = Counter(C.bucket(r["status"], r["error"], r["location"]) for r in own)
    check("unknown" not in box, f"{name}: адреса без ящика - {box['unknown']}")
    check(sum(box.values()) == len(own), f"{name}: ящиков {sum(box.values())}, адресов {len(own)}")
    pages = [r for r in own if r["kind"] == "page"]
    check(sum(x["n"] for x in _by_status(pages)) == len(pages), f"{name}: сводка кодов не сходится с числом страниц")
    c.close()

if fails:
    print("✗ закон сохранения:\n   " + "\n   ".join(fails))
    sys.exit(1)
print(f"✓ закон сохранения: все коды 0-999 в своих ящиках с объяснением, готовых проверок сошлось: {seen}")
