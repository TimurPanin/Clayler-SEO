"""Автотест «Что изменилось с прошлой проверки»: списки «исправлено» и «появилось» для отчёта клиенту,
новые критичные ошибки и падение здоровья для тревоги в Telegram, график здоровья. Без сети, выдуманные данные."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import compare as C, telegram as T  # noqa: E402
from seocrawler.analyze import CRIT, WARN, NOTE  # noqa: E402
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def iss(title, sev, old, new, fixed, added, sitewide=False):
    return {"title": title, "severity": sev, "old": old, "new": new, "fixed": [[f"u{k}"] for k in range(fixed)],
            "added": [[f"a{k}"] for k in range(added)], "sitewide": sitewide}


res = {"issues": [iss("Битые ссылки", CRIT, 0, 5, 0, 5), iss("Нет H1", WARN, 10, 4, 6, 0),
                  iss("Дубли", WARN, 16, 17, 8, 9), iss("Нет сжатия", WARN, 1, 0, 1, 0, sitewide=True),
                  iss("Мелочь", NOTE, 3, 0, 3, 0)]}
fixed, added, new_crit = C._brief(res)
check([x["title"] for x in fixed] == ["Нет H1", "Нет сжатия"], f"исправлено: {fixed}")
check([x["title"] for x in added] == ["Битые ссылки", "Дубли"], f"появилось: {added}")  # 16 → 17 - стало хуже
check(new_crit == ["Битые ссылки"], f"новые критичные: {new_crit}")

cmp = {"fixed": 7, "added": 5, "health_old": 70, "health_new": 55, "old_finished": "2026-09-30 17:17:54",
       "top_fixed": fixed, "top_added": added, "new_crit": new_crit}
broke = T._broke(cmp)
check(len(broke) == 2 and "Битые ссылки" in broke[0] and "упало на 15" in broke[1], f"тревога: {broke}")
check(T._broke(dict(cmp, new_crit=[], health_new=65)) == [], "тревога без причины")
lines = T._changes(cmp)
check(lines[0] == "С прошлой проверки: исправлено 7, новых 5", f"строка в Telegram: {lines[0]}")

doc = C.client_html(cmp, [("2026-09-28 21:08:55", 54), ("2026-09-30 17:17:54", 70), ("2026-09-30 19:09:08", 55)])
check("Здоровье сайта снизилось: <b>70% → 55%</b>" in doc and "30.09.2026" in doc, "текст блока для клиента")
check(">28.09<" in doc and ">30.09<" in doc and ">19:09<" in doc, "подписи графика (вторая проверка дня - время)")
check("—" not in doc and "рограмм" not in doc, "длинное тире или «программа» в тексте для клиента")
check(C.client_html(None) == "" and C._chart([("2026-09-30", 50)]) == "", "без сравнения и с одной точкой - пусто")

# Старая проверка без части данных (старая версия программы): кеширования и вида на телефоне в ней нет.
# Эти проблемы не «новые», а «в прошлый раз не делались»; настоящая новая проблема (одинаковый title) - новая.
def crawl_imgsite():
    import glob
    import shutil
    import sqlite3
    import subprocess
    import tempfile
    import time
    import urllib.request
    here = os.path.dirname(os.path.abspath(__file__))
    tmp = tempfile.mkdtemp(prefix="clayler-cmp-")
    env = dict(os.environ, PYTHONUTF8="1", CLAYLER_REPORTS=tmp, CLAYLER_NO_USER_SETTINGS="1", CLAYLER_NO_SPELLER="1",
               CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1")
    srv = subprocess.Popen([sys.executable, os.path.join(here, "imgsite.py"), "8797"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen("http://127.0.0.1:8797/", timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.1)
        subprocess.run([sys.executable, os.path.join(os.path.dirname(here), "crawl.py"), "http://127.0.0.1:8797/",
                        "--no-open", "--delay", "0"], env=env, capture_output=True, timeout=300)
    finally:
        srv.terminate()
    new = sorted(glob.glob(os.path.join(tmp, "127.0.0.1_8797_*")))[-1]
    old = os.path.join(tmp, "старая")
    os.makedirs(old)
    for f in glob.glob(os.path.join(new, "crawl.db*")):
        shutil.copy(f, old)
    db = sqlite3.connect(os.path.join(old, "crawl.db"))
    db.execute("UPDATE pages SET cache_control=NULL")
    db.execute("DELETE FROM meta WHERE key IN ('mobile_view', 'mobile_diff')")
    db.execute("UPDATE pages SET title = title || ' ' || url WHERE title IS NOT NULL")
    db.commit()
    db.close()
    return old, new


from seocrawler.storage import Store  # noqa: E402
old_dir, new_dir = crawl_imgsite()
cache = os.path.join(new_dir, ".анализ.pickle")
before = os.path.getmtime(cache) if os.path.exists(cache) else None
r = C.compare(Store(os.path.join(old_dir, "crawl.db")), Store(os.path.join(new_dir, "crawl.db")))
nc = [x["title"] for x in r["not_collected"]]
by = {i["title"]: i for i in r["issues"]}
check("Браузеру не велено запоминать картинки, стили и скрипты" in nc and "На телефоне страница шире экрана" in nc,
      f"«не делались»: {nc}")
check(by["Одинаковый title у разных страниц"]["added"] and "Одинаковый title у разных страниц" not in nc,
      "настоящая новая проблема попала в «не делались»")
check(not by["Браузеру не велено запоминать картинки, стили и скрипты"]["added"], "кеширование считается новым")
info = C.write_compare(new_dir, r)
check(info["not_collected"] == nc and not any(x["title"] in nc for x in info["top_added"]), f"сводка: {info}")
check("Эти проверки в прошлый раз не делались" in open(os.path.join(new_dir, "сравнение.html"), encoding="utf-8").read(),
      "в сравнение.html нет блока «не делались»")
doc = C.client_html(dict(info, top_fixed=[], top_added=[]))
check(C.NOT_COLLECTED_TEXT in doc and "рограмм" not in doc and "—" not in doc, "блок «не делались» для клиента")
check(before is None or os.path.getmtime(cache) == before, "повторный анализ испортил кеш анализа проверки")

# «Обновить отчёт», когда прошлой проверки уже нет (удалили или убрали в архив): старое сравнение.html с ней
# убирается, иначе в окне и карточке оставалась кнопка «Что изменилось» про чужие данные
import subprocess  # noqa: E402
subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crawl.py"),
                "--report", new_dir, "--no-open"], capture_output=True, timeout=300,
               env=dict(os.environ, PYTHONUTF8="1", CLAYLER_REPORTS=os.path.dirname(new_dir), CLAYLER_NO_USER_SETTINGS="1",
                        CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1"))
check(os.path.exists(os.path.join(new_dir, "отчёт.html")) and
      not any(os.path.exists(os.path.join(new_dir, f)) for f in ("сравнение.html", "сравнение.csv")),
      "после «Обновить отчёт» без прошлой проверки осталось старое сравнение.html")

# «Обновить отчёт» прошлой проверки не заменяет её данные Вебмастера, Search Console и Метрики сегодняшними
# (а последней проверки - заменяет; если данных не было - загружает)
import tempfile  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.run.build import _fetch_extra  # noqa: E402 (сборка отчёта - в run/, раньше crawl.py)
from seocrawler.run.history import later_crawl  # noqa: E402
from seocrawler import webmaster, search_console, metrika  # noqa: E402
base = tempfile.mkdtemp(prefix="clayler-wm-")
was_env = {k: os.environ.get(k) for k in ("CLAYLER_NO_USER_SETTINGS", "CLAYLER_NO_SPELLER", "CLAYLER_NO_SITE_TECH",
                                          "CLAYLER_NO_SECURITY", "CLAYLER_NO_SHOP", "CLAYLER_NO_MOBILE_VIEW")}
os.environ.update(CLAYLER_NO_USER_SETTINGS="0", CLAYLER_NO_SPELLER="1", CLAYLER_NO_SITE_TECH="1", CLAYLER_NO_SECURITY="1",
                  CLAYLER_NO_SHOP="1", CLAYLER_NO_MOBILE_VIEW="1")
webmaster.fetch = lambda start: {"fetched": "сегодня"}
search_console.fetch = lambda start, imp: {"fetched": "сегодня"}
metrika.fetch = lambda start: {"fetched": "сегодня"}
try:
    # 15.09: загрузка тогда была с одними ошибками - это не данные, их можно загрузить заново
    got, runs = {}, (("site.ru_2026-09-01_10-00-00", {"fetched": "01.09.2026", "summary": {"x": 1}}),
                     ("site.ru_2026-09-15_10-00-00", {"fetched": "15.09.2026", "errors": ["нет доступа"]}),
                     ("site.ru_2026-10-01_10-00-00", {"fetched": "01.10.2026", "summary": {"x": 1}}))
    for name, had in runs:   # сначала все три проверки, потом «Обновить отчёт» каждой
        os.makedirs(os.path.join(base, name))
        st = Store(os.path.join(base, name, "crawl.db"))
        st.set_meta("start", "https://site.ru/")
        for k in ("webmaster", "gsc", "metrika"):
            st.set_meta(k, had)
        st.commit()
        st.db.close()
    for name, _ in runs:
        d = os.path.join(base, name)
        st = Store(os.path.join(d, "crawl.db"))
        _fetch_extra(st, d, lambda *a, **k: None)
        got[name[8:18]] = {k: (st.get_meta(k) or {}).get("fetched") for k in ("webmaster", "gsc", "metrika")}
        st.db.close()
    check(set(got["2026-09-01"].values()) == {"01.09.2026"}, f"прошлой проверке заменили данные сегодняшними: {got}")
    check(set(got["2026-09-15"].values()) == {"сегодня"}, f"прошлой проверке без данных они не загрузились: {got}")
    check(set(got["2026-10-01"].values()) == {"сегодня"}, f"последней проверке данные не обновились: {got}")
    # проверка в архиве видит более новую в «reports» (и наоборот)
    import shutil  # noqa: E402
    arch = os.path.join(base, "archive")
    os.makedirs(arch)
    shutil.move(os.path.join(base, "site.ru_2026-09-01_10-00-00"), arch)
    check(later_crawl(os.path.join(arch, "site.ru_2026-09-01_10-00-00")) ==
          os.path.join(base, "site.ru_2026-10-01_10-00-00"), "проверка в архиве не видит более новую")
    shutil.move(os.path.join(base, "site.ru_2026-10-01_10-00-00"), arch)
    check(later_crawl(os.path.join(base, "site.ru_2026-09-15_10-00-00")) ==
          os.path.join(arch, "site.ru_2026-10-01_10-00-00"), "более новая проверка в архиве не найдена")
finally:
    for k, v in was_env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

if fails:
    print("ОШИБКИ в сравнении проверок:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ сравнение с прошлой проверкой: списки, тревога в Telegram, график, «в прошлый раз не делались»")
