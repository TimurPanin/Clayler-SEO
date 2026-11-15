"""Автотест снимков телефона при сборке отчёта (05.10.2026, seocrawler/mobile_view.ensure): у проверок без снимков
(сделанных до 30.09 или где обход их не сделал) они снимаются при «Обновить отчёт», уже снятые не переснимаются,
пропавшая папка снимается заново, недоступный сайт не запоминается и не держит сборку долго."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import mobile_view as MV  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


class Store:
    def __init__(self, meta=None):
        self.meta = dict(meta or {})
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE pages(url, status, content_type)")
        self.db.execute("CREATE TABLE urls(url, internal, kind, depth)")
        for i in range(20):
            u = f"https://site.ru/p{i}/"
            self.db.execute("INSERT INTO pages VALUES(?,200,'text/html')", (u,))
            self.db.execute("INSERT INTO urls VALUES(?,1,'page',?)", (u, i))

    def get_meta(self, k, d=None):
        return self.meta.get(k, d)

    def set_meta(self, k, v):
        self.meta[k] = v

    def commit(self):
        pass


calls = []


def fake_check(urls, shots_dir, log=print, give_up_after=None, **kw):
    calls.append(list(urls))
    os.makedirs(shots_dir, exist_ok=True)
    rows = []
    for i, u in enumerate(urls, 1):
        open(os.path.join(shots_dir, f"{i:02d}.jpg"), "wb").close()
        rows.append({"url": u, "shot": f"{i:02d}.jpg", "bytes": 1000})
    return rows


os.environ.pop("CLAYLER_NO_MOBILE_VIEW", None)
MV.available = lambda: True
MV.check_pages = fake_check
quiet = lambda *a: None  # noqa: E731
with tempfile.TemporaryDirectory() as out:
    st = Store()
    res = MV.ensure(st, out, log=quiet)
    check(len(calls) == 1 and len(calls[0]) == 15, f"старая проверка без снимков: открыто {calls}")
    check(res and len(st.meta.get("mobile_view", {}).get("pages", [])) == 15, "снимки не записаны в проверку")
    check(calls and calls[0][:3] == ["https://site.ru/p0/", "https://site.ru/p1/", "https://site.ru/p2/"],
          "первыми должны быть страницы ближе к главной")
    MV.ensure(st, out, log=quiet)
    check(len(calls) == 1, "уже снятые снимки снимаются заново")
    os.remove(os.path.join(out, MV.DIR, "03.jpg"))
    MV.ensure(st, out, log=quiet)
    check(len(calls) == 2, "пропавший снимок не снят заново")
    os.environ["CLAYLER_NO_MOBILE_VIEW"] = "1"
    st2 = Store()
    MV.ensure(st2, out, log=quiet)
    check(len(calls) == 2 and "mobile_view" not in st2.meta, "CLAYLER_NO_MOBILE_VIEW=1 не выключает снимки")
    os.environ.pop("CLAYLER_NO_MOBILE_VIEW")

    MV.check_pages = lambda urls, d, **kw: [{"url": u, "error": "net::ERR_CONNECTION_REFUSED"} for u in urls[:2]]
    st3 = Store()
    MV.ensure(st3, out, log=quiet)
    check("mobile_view" not in st3.meta, "недоступный сайт запомнен: при следующей сборке снимки не попробуются")

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# сборка отчёта - в seocrawler/run/build.py (раньше - в crawl.py, разделён 28.10.2026)
with open(os.path.join(here, "seocrawler", "run", "build.py"), encoding="utf-8") as f:
    src = f.read()
# снимки - в _fetch_extra (данные до анализа), а она вызывается в build_report раньше поиска проблем
fetch = src[src.find("def _fetch_extra("):]
fetch = fetch[:fetch.find("\ndef ", 1)]
check("mobile_view.ensure(store, out_dir)" in fetch
      and 0 < src.find("    _fetch_extra(store, out_dir, stage)") < src.find("cached_analyze(store)"),
      "run/build.py: снимки телефона должны сниматься до поиска проблем (проблемы «Мобильная версия» берутся из них)")

if fails:
    print("ОШИБКИ в снимках телефона:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ снимки телефона: снимаются у старых проверок, не переснимаются, недоступный сайт не запоминается")
