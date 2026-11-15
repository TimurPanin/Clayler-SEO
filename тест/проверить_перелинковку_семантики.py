"""План перелинковки по «Запрос → страница» Семантики (план, раздел 9.1): тексты ссылок - уточнения главного
запроса, а не соседние темы и не вопросы; страница группы без ссылок со словами запроса получает ссылки;
«Не та страница» ссылок не получает; новая страница («Создать») - адрес из семантики и ссылки из раздела, в котором
её создать. Без обхода: маленькая база в памяти и семантика.json во временной папке.
Запуск: python тест/проверить_перелинковку_семантики.py (и из проверить_всё.py)."""
import json
import os
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def q(text, intent="Общий"):
    return [text, "", intent, 10, 1, 1, 0, "", 0, "", 0, 0, 0, 0]


def anchors():
    from seocrawler.analyze.checks.link_plan import group_anchors
    g = {"name": "Радиаторы отопления", "a": {"main": "радиаторы отопления"},
         "q": [q("радиаторы отопления"), q("отопления радиаторы"), q("запорная арматура для радиатора отопления"),
               q("радиаторы отопления какие лучше"), q("радиаторы отопления виды", "Информация"),
               q("радиаторы отопления для частного дома"), q("радиаторы отопления отзывы"),
               q("радиаторы отопления биметаллические")]}
    got = group_anchors(g, set())
    check(got == ["радиаторы отопления", "радиаторы отопления для частного дома", "радиаторы отопления биметаллические"],
          f"тексты ссылок из запросов группы: {got}")


def plan():
    from seocrawler.analyze.checks import link_plan
    site = "https://linkplan.test"
    pages = [{"url": f"{site}/", "title": "Главная", "h1": "Магазин", "depth": 0}]
    pages.append({"url": f"{site}/katalog/", "title": "Каталог", "h1": "Каталог", "depth": 1})
    pages.append({"url": f"{site}/katalog/radiatory/", "title": "Радиаторы", "h1": "Радиаторы", "depth": 2})
    pages.append({"url": f"{site}/katalog/kotly/", "title": "Газовые котлы", "h1": "Газовые котлы", "depth": 2})
    pages.append({"url": f"{site}/katalog/nasosy/", "title": "Насосы", "h1": "Насосы", "depth": 2})
    pages.append({"url": f"{site}/katalog/boilery/", "title": "Бойлеры", "h1": "Бойлеры", "depth": 2})
    for i in range(6):
        pages.append({"url": f"{site}/katalog/kotly/baxi-{i}/", "title": f"Газовые котлы Baxi серия {i}",
                      "h1": f"Газовые котлы Baxi серия {i}", "depth": 2})
    for i in range(14):
        pages.append({"url": f"{site}/stati/{i}/", "title": f"Статья номер {i}", "h1": f"Статья {i}", "depth": 2})
    inl = {p["url"]: {f"{site}/", f"{site}/katalog/"} for p in pages}
    # на страницу группы ведут 8 ссылок, но все - «Каталог», без слов запроса
    inl[f"{site}/katalog/kotly/"] = {f"{site}/stati/{k}/" for k in range(8)}
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE pages(url, title, h1, status, indexable); CREATE TABLE urls(url, depth, internal, kind);"
                     "CREATE TABLE links(src, dst, anchor, kind, internal);")
    for u, ss in inl.items():
        for s in ss:
            db.execute("INSERT INTO links VALUES(?,?,?,?,1)", (s, u, "Каталог", "a"))
    groups = [
        {"name": "Газовые котлы", "kind": "page", "page": f"{site}/katalog/kotly/", "near": "", "score": 50,
         "todo": "", "a": {"main": "газовые котлы", "problems": []}, "q": [q("газовые котлы"), q("газовые котлы baxi")]},
        {"name": "Насосы", "kind": "page", "page": f"{site}/katalog/nasosy/", "near": "", "score": 40, "todo": "",
         "landing": {"why": "не та", "candidates": []}, "a": {"main": "насосы"}, "q": [q("насосы")]},
        {"name": "Радиаторы отопления", "kind": "create", "page": "", "near": f"{site}/katalog/radiatory/", "score": 30,
         "todo": "Создать подраздел в «Радиаторы»", "a": {"main": "радиаторы отопления", "h1": "Радиаторы отопления",
                                                       "title": "Радиаторы отопления - купить"},
         "q": [q("радиаторы отопления"), q("радиаторы отопления для частного дома")]},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "семантика.json"), "w", encoding="utf-8") as f:
            json.dump({"site": site + "/", "host": "linkplan.test", "groups": groups}, f, ensure_ascii=False)
        ctx = SimpleNamespace(indexable=pages, inl=inl, db=db, soft404=set(), home_copies=set(),
                              store=SimpleNamespace(path=os.path.join(tmp, "crawl.db"), legacy_links=True))
        link_plan.run(ctx)
        check(link_plan.sem_sig(tmp) is not None, "подпись кеша учитывает семантику")
    by = {x["url"]: x for x in ctx.link_plan}
    k = by.get(f"{site}/katalog/kotly/")
    check(k and "не содержит запрос «газовые котлы»" in k["why"], f"страница группы без ссылок со словами запроса: {k}")
    check(k and k["links"][0]["anchor"] == "газовые котлы", f"текст первой ссылки - главный запрос: {k}")
    check(f"{site}/katalog/nasosy/" not in by, "«Не та страница» не получает ссылок")
    new = [x for x in ctx.link_plan if x.get("new")]
    check(len(new) == 1 and new[0]["url"] == f"{site}/katalog/radiatory/radiatory-otopleniya/",
          f"адрес новой страницы из семантики: {[x['url'] for x in new]}")
    if new:
        check(new[0]["links"][0]["from"] == f"{site}/katalog/radiatory/"
              and new[0]["links"][0]["reason"] == "раздел, в котором создать страницу",
              f"ссылка на новую страницу из её раздела: {new[0]['links']}")
    # один текст ссылки на разные страницы: «газовые котлы» ведут на раздел котлов и на бойлеры
    for k in range(6):
        db.execute("INSERT INTO links VALUES(?,?,?,?,1)", (f"{site}/stati/{k}/", f"{site}/katalog/kotly/", "Газовые котлы", "a"))
    for k in range(6, 9):
        db.execute("INSERT INTO links VALUES(?,?,?,?,1)", (f"{site}/stati/{k}/", f"{site}/katalog/boilery/", "Газовые котлы", "a"))
    for k in range(4):     # одинаковое название у двух товаров - не сюда (мало ссылок)
        db.execute("INSERT INTO links VALUES(?,?,?,?,1)", (f"{site}/stati/{k}/", f"{site}/katalog/kotly/baxi-{k % 2}/", "Котел Baxi", "a"))
    from seocrawler.analyze.checks import anchors as A
    found = []
    texts = {}
    ctx.add = lambda key, *a, **kw: (found.append((key, a[-1])), texts.__setitem__(key, a[3] + " " + a[4]))
    ctx.sem_groups = None
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "семантика.json"), "w", encoding="utf-8") as f:
            json.dump({"site": site + "/", "host": "linkplan.test", "groups": groups}, f, ensure_ascii=False)
        ctx.store.path = os.path.join(tmp, "crawl.db")
        A.many_pages(ctx, __import__("re").compile("^подробнее$"))
    rows = dict(found).get("anchor_many_pages") or []
    check(len(rows) == 1 and rows[0][0] == "Газовые котлы" and rows[0][1] == 2
          and rows[0][3] == f"{site}/katalog/kotly/ (среди этих)", f"один текст на разные страницы: {rows}")
    t = texts.get("anchor_many_pages", "")   # пример в совете - с этого сайта, не зашитый «Газовые котлы Baxi»
    check("«Газовые котлы»" in t and "Baxi" not in t, f"пример с сайта в совете: {t}")
    # страница группы, которой мало силы ссылок: добавляется в план позже (вес считается после проверок)
    n0 = len(ctx.link_plan)
    ctx.link_plan[:] = [x for x in ctx.link_plan if x["url"] != f"{site}/katalog/kotly/"]
    x = ctx.link_more(f"{site}/katalog/kotly/", ["мало силы"])
    check(x and x["links"] and len(ctx.link_plan) == n0, f"страница с малым весом добавлена в план: {x}")
    from seocrawler import suggest_out
    html = suggest_out.links_html({"link_plan": ctx.link_plan})
    check("новая →" in html, "в отчёте новая страница помечена")
    rows = suggest_out.link_rows({"link_plan": ctx.link_plan})
    check(any(r[4] == "новая страница" for r in rows), "в таблице новая страница помечена")


if __name__ == "__main__":
    anchors()
    plan()
    if fails:
        print("ОШИБКИ:")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("Перелинковка по семантике: всё в порядке")
