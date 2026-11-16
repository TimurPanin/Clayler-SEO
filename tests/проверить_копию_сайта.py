"""Автотест копии сайта с www (без сети). На yazyk-primer.ru www.yazyk-primer.ru открывался сам, без
редиректа, одна ссылка с главной вела туда, и программа обошла сайт дважды: все числа в отчёте вдвое.
Проверяет:
- mirror_copy.twin_host: копия - только вариант с www (или без) той же схемы, открывшийся с кодом 200;
- обход (QueueMixin.consider): страница копии записывается «не проверялась» с причиной mirror_copy.SKIP,
  картинка с копии и страница главного адреса проверяются как обычно;
- готовая проверка («Обновить отчёт», mirror_copy.drop_from_store): страницы копии убраны из pages, ссылки
  и картинки с них - тоже, всё лежит в mirror_bak_*, повторный вызов ничего не делает;
- анализ: проблема «Ссылки на копию сайта» со ссылкой с главного адреса, страницы копии нет в «не открывала
  из-за ограничений».
Запуск: py -3 tests/проверить_копию_сайта.py (и из проверить_всё.py)."""
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import mirror_copy  # noqa: E402
from seocrawler.analyze import analyze  # noqa: E402
from seocrawler.crawler.queue import QueueMixin  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


MAIN, TWIN = "https://site.test/", "https://www.site.test/"
MIRRORS = {"main": MAIN, "variants": [
    {"variant": TWIN, "chain": [[TWIN, 200]], "canonical": TWIN},
    {"variant": "http://site.test/", "chain": [["http://site.test/", 301], [MAIN, 200]]}]}

check(mirror_copy.twin_host(MIRRORS) == "www.site.test", "копия с www не найдена")
check(mirror_copy.twin_host({"main": MAIN, "variants": [{"variant": TWIN, "chain": [[TWIN, 301], [MAIN, 200]]}]}) == "",
      "копией посчитан www с редиректом 301")
check(mirror_copy.twin_host({"main": TWIN, "variants": [{"variant": MAIN, "chain": [[MAIN, 200]]}]}) == "site.test",
      "главный адрес с www: копия без www не найдена")
check(mirror_copy.twin_host(None) == "", "без данных о склейке найдена копия")

tmp = tempfile.mkdtemp(prefix="clayler_копия_")


def page(store, url, title, links=()):
    store.enqueue(url, 1, True, "page", MAIN, "done")
    store.save_page({"url": url, "status": 200, "content_type": "text/html", "title": title, "h1": title,
                     "description": title, "indexable": 1, "indexability": "Индексируется"})
    store.add_links([(url, d, None, "ссылка", 0, "a", 1) for d in links])
    store.add_images([(url, url + "logo.png", "", 1, None, 0, 0)])


# --- обход: страницы копии не открываются
store = Store(os.path.join(tmp, "обход.db"))
store.set_meta("mirrors", MIRRORS)
q = QueueMixin()
q.store, q.root_host, q.exclude, q.robots = store, "site.test", [], {}
q.cfg = types.SimpleNamespace(crawl_subdomains=False, check_resources=True, check_external=False, max_depth=50,
                              max_params=3, respect_robots=False, use_clean_param=False)
q.in_scope = lambda u: True
q.log = lambda *a: None
q.consider(TWIN + "catalog/", 1, MAIN)
q.consider(TWIN + "upload/logo.png", 1, MAIN, "resource")
q.consider(MAIN + "catalog/", 1, MAIN)
st = {r[0]: (r[1], r[2]) for r in store.db.execute("SELECT url, state, skip_reason FROM urls")}
check(st.get(TWIN + "catalog/") == ("skipped", mirror_copy.SKIP), f"страница копии в очереди: {st.get(TWIN + 'catalog/')}")
check(st.get(TWIN + "upload/logo.png", ("",))[0] == "queued", "картинка с копии не проверяется")
check(st.get(MAIN + "catalog/", ("",))[0] == "queued", "страница главного адреса не в очереди")

# --- готовая проверка, где копия уже обойдена
store = Store(os.path.join(tmp, "готовая.db"))
store.set_meta("mirrors", MIRRORS)
store.set_meta("start", MAIN)
page(store, MAIN, "Главная", [MAIN + "a/", TWIN + "?q=eltex"])
page(store, MAIN + "a/", "Страница А", [MAIN])
page(store, TWIN + "?q=eltex", "Поиск", [TWIN, TWIN + "a/"])
page(store, TWIN, "Главная", [TWIN + "a/"])
page(store, TWIN + "a/", "Страница А", [TWIN])
store.commit()
n = mirror_copy.drop_from_store(store, log=lambda *a: None)
check(n == 3, f"убрано страниц копии {n}, а не 3")
left = sorted(r[0] for r in store.db.execute("SELECT url FROM pages"))
check(left == [MAIN, MAIN + "a/"], f"в расчёте остались {left}")
check(store.db.execute("SELECT COUNT(*) FROM mirror_bak_pages").fetchone()[0] == 3, "страницы копии не сохранены")
check(not store.db.execute("SELECT 1 FROM links WHERE src LIKE ?", (TWIN + "%",)).fetchone(), "остались ссылки с копии")
check(not store.db.execute("SELECT 1 FROM images WHERE page LIKE ?", (TWIN + "%",)).fetchone(), "остались картинки с копии")
check(store.db.execute("SELECT COUNT(*) FROM urls WHERE skip_reason=?", (mirror_copy.SKIP,)).fetchone()[0] == 3,
      "страницы копии не помечены «не проверялись»")
check(mirror_copy.drop_from_store(store, log=lambda *a: None) == 0, "повторный вызов снова что-то убрал")
check((store.get_meta("mirror_dropped") or {}).get("pages") == 3, "нет отметки mirror_dropped")

issues, pages, summary = analyze(store)
by = {i.key: i for i in issues}
ml = by.get("mirror_links")
check(ml is not None and [r[:2] for r in ml.rows] == [[MAIN, TWIN + "?q=eltex"]],
      f"«Ссылки на копию сайта»: {ml.rows if ml else 'нет проблемы'}")
check("mirror_dup" in by, "нет проблемы «Вариант адреса сайта открывается без редиректа»")
sk = by.get("skipped")
check(not sk or not any(TWIN in r[0] for r in sk.rows), "страницы копии в «не открывала из-за ограничений»")
check("title_dup" not in by, "одинаковый title из-за копии сайта")
store.db.close()

if fails:
    print("✗ копия сайта с www:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ копия сайта с www: страницы копии не обходятся, в готовой проверке убираются из расчёта (сохранены в "
      "mirror_bak_*), ссылки на копию - отдельной проблемой")
