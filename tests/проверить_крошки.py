"""Автотест проверки «Хлебные крошки» (analyze/checks/crumbs.py, без сети).
Сбор (shop.facts): видимые крошки отдельно от разметки, их ссылки, адреса JSON-LD BreadcrumbList. Проверка: крошки
есть не на всех страницах раздела; видны, но не размечены; ссылка на 404 и на редирект (одна строка на адрес, сколько
страниц); последний пункт - ссылка на саму страницу; старые проверки без новых данных - только «не везде»; нет
крошек на сайте вовсе - ничего. Тексты без длинного тире. Запуск: py -3 tests/проверить_крошки.py (и из проверить_всё.py)."""
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import shop  # noqa: E402
from seocrawler.analyze.checks import crumbs as C  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# ---------- сбор со страницы
f = json.loads(shop.facts(
    "<html><body><nav class='breadcrumbs'><a href='/'>Главная</a> / <a href='/catalog/'>Каталог</a> / "
    "<a href='/catalog/kotly/'>Котлы</a></nav><nav class='breadcrumbs mobile'><a href='/'>Главная</a></nav>"
    "<h1>Котлы</h1><script type='application/ld+json'>{\"@type\": \"BreadcrumbList\", \"itemListElement\": ["
    "{\"@type\": \"ListItem\", \"position\": 1, \"name\": \"Главная\", \"item\": \"https://site.ru/\"},"
    "{\"@type\": \"ListItem\", \"position\": 2, \"name\": \"Каталог\", \"item\": {\"@id\": \"https://site.ru/catalog/\"}}]}"
    "</script></body></html>"))
check(f.get("crumbs_html") == 4, f"видимых пунктов: {f.get('crumbs_html')}")
check(f.get("crumb_urls") == ["/", "/catalog/", "/catalog/kotly/"], f"ссылки крошек: {f.get('crumb_urls')}")
check(f.get("crumb_ld_urls") == ["https://site.ru/", "https://site.ru/catalog/"], f"адреса разметки: {f.get('crumb_ld_urls')}")
check(f.get("crumbs") == ["Главная", "Каталог"], f"названия - из разметки, как раньше: {f.get('crumbs')}")
check("crumbs_html" not in json.loads(shop.facts("<html><body><h1>Нет крошек</h1><p>Текст</p></body></html>") or "{}"),
      "без крошек - нет и поля")
check(f.get("crumb_last") == "/", f"последний пункт - из последнего блока: {f.get('crumb_last')}")
f = json.loads(shop.facts("<html><body><ul class='breadcrumb'><li><a href='/'>Главная</a></li>"
                          "<li><a href='/k/'>Котлы</a><ul><li><a href='/b/'>Бойлеры</a></li></ul></li>"
                          "<li><a href='/k/navien/'>Navien</a><ul><li><a href='/k/baxi/'>Baxi</a></li></ul></li>"
                          "</ul><h1>Navien</h1></body></html>"))
check(f.get("crumb_last") == "/k/navien/", f"ссылка последнего пункта, не выпадающего списка: {f.get('crumb_last')}")


# ---------- проверка
S = "https://site.ru"


def page(url, crumbs=None, html=0, urls=None, ld_urls=None, markup=0, old=False, last=""):
    sh = {}
    if crumbs:
        sh["crumbs"] = crumbs
    if not old:
        if html:
            sh["crumbs_html"] = html
        if urls:
            sh["crumb_urls"] = urls
        if ld_urls:
            sh["crumb_ld_urls"] = ld_urls
        if last:
            sh["crumb_last"] = last
        sh.setdefault("h1", "x")   # новая проверка: поле shop есть у каждой страницы
    return {"url": url, "shop": json.dumps(sh, ensure_ascii=False) if sh else None,
            "schema_info": json.dumps({"crumbs": markup} if markup else {})}


def run(pages, status=None, redir=None, issues=()):
    got = {}
    status = status or {}
    redir = redir or {}

    def add(key, sev, cat, title, why, fix, columns, rows, page_col=0, show_col=None):
        if rows:
            got[key] = Issue(key, sev, cat, title, why, fix, columns, rows, page_col, show_col=show_col)

    def follow(u):
        chain = [u]
        while chain[-1] in redir:
            chain.append(redir[chain[-1]])
        return chain, False
    ctx = SimpleNamespace(indexable=pages, status=status, follow=follow, add=add, issues=list(issues),
                          store=SimpleNamespace(get_meta=lambda k, d=None: S + "/" if k == "start" else d))
    for p in pages:
        status.setdefault(p["url"], (200, None))
    C.run(ctx)
    return got


cr = ["Главная", "Каталог", "Котлы"]
ok_links = ["/", "/catalog/"]
pages = [page(f"{S}/catalog/k{i}/", cr, 3, ok_links, markup=3 if i < 3 else 0) for i in range(5)]
pages.append(page(f"{S}/catalog/k9/"))                              # раздел с крошками, а у этой нет
pages.append(page(f"{S}/catalog/k7/", cr, 3, ["/", "/old-catalog/"], markup=3))          # 404
pages.append(page(f"{S}/catalog/k8/", cr, 3, ["/", "/old-catalog/"], markup=3))          # та же 404 - одна строка
pages.append(page(f"{S}/catalog/k6/", cr, 3, ["/", "http://site.ru/catalog"], markup=3))  # редирект
pages.append(page(f"{S}/catalog/k5/", cr, 3, ["/", "/catalog/", "/catalog/k5/"], markup=3, last="/catalog/k5/"))  # на себя
# выпадающий список соседних разделов: среди ссылок блока есть и сама страница, но последний пункт - текстом
pages.append(page(f"{S}/catalog/k12/", cr, 3, ["/", "/catalog/", "/catalog/k12/", "/catalog/k0/"], markup=3))
pages.append(page(f"{S}/catalog/k11/", cr, 3, ["/", "/personal/"], markup=3))   # 302 на вход - не проблема
pages.append(page(f"{S}/catalog/k10/", cr, 3, ok_links, ld_urls=[f"{S}/gone/"], markup=3))   # 404 в разметке
pages += [page(f"{S}/contacts/"), page(f"{S}/about/")]              # одиночные разделы - не оцениваются
status = {f"{S}/": (200, None), f"{S}/catalog/": (200, None), f"{S}/old-catalog/": (404, None),
          "http://site.ru/catalog": (301, None), f"{S}/gone/": (404, None), f"{S}/personal/": (302, None)}
got = run(pages, status, {"http://site.ru/catalog": f"{S}/catalog/"})

m = got.get("crumbs_missing")
check(m and [r[0] for r in m.rows] == [f"{S}/catalog/k9/"], f"нет крошек в разделе: {m and m.rows}")
check(m and m.rows[0][1] == "/catalog/" and m.rows[0][2] == "12 из 13", f"раздел и доля: {m and m.rows}")
nm = got.get("crumbs_no_markup")
check(nm and sorted(r[0] for r in nm.rows) == [f"{S}/catalog/k3/", f"{S}/catalog/k4/"], f"видны без разметки: {nm and nm.rows}")
b = got.get("crumbs_broken")
rows = {(r[0], r[3]): r for r in (b.rows if b else [])}
check(len(rows) == 2 and rows.get((f"{S}/old-catalog/", "на странице"), [0] * 6)[4] == 2
      and (f"{S}/gone/", "в разметке BreadcrumbList") in rows, f"ссылки на 404: {b and b.rows}")
rd = got.get("crumbs_redirect")
check(rd and len(rd.rows) == 1 and rd.rows[0][0] == "http://site.ru/catalog" and rd.rows[0][2] == f"{S}/catalog/",
      f"редирект (302 на вход - нет): {rd and rd.rows}")
sl = got.get("crumbs_self_link")
check(sl and [r[0] for r in sl.rows] == [f"{S}/catalog/k5/"], f"ссылка на себя: {sl and sl.rows}")
for i in got.values():
    text = " ".join([i.title, i.why, i.fix] + i.columns)
    check("—" not in text, f"длинное тире в {i.key}")

# разметки нет ни на одной странице, а про это уже есть rich_no_crumbs - не повторяем
pg = [page(f"{S}/catalog/k{i}/", cr, 3, ok_links) for i in range(6)]
got = run(pg, issues=[SimpleNamespace(key="rich_no_crumbs")])
check("crumbs_no_markup" not in got, "повтор rich_no_crumbs")
got = run(pg)
check(len(got.get("crumbs_no_markup", SimpleNamespace(rows=[])).rows) == 6, "маленький сайт без разметки вовсе")

# крошки только в разметке, видимого блока программа не узнала: ссылки разметки всё равно проверяются
ld = [page(f"{S}/catalog/k{i}/", ["Главная", "Каталог"], ld_urls=[f"{S}/", f"{S}/gone/"], markup=2) for i in range(3)]
got = run(ld, {f"{S}/": (200, None), f"{S}/gone/": (404, None)})
check("crumbs_broken" in got and got["crumbs_broken"].rows[0][4] == 3, f"только разметка: {got}")

# старая проверка: только названия крошек - «не везде» есть, остального нет
old = [page(f"{S}/catalog/k{i}/", cr, old=True) for i in range(5)] + [page(f"{S}/catalog/k9/", old=True)]
got = run(old)
check(set(got) == {"crumbs_missing"}, f"старая проверка: {set(got)}")
# крошек на сайте нет вовсе, а вложенные страницы есть - «Хлебных крошек нет на сайте» (primerline.agency:
# /cases/…, /glossary/…, отчёт молчал); плоский сайт - ничего; уже есть rich_no_crumbs - не повторяем
got = run([page(f"{S}/catalog/k{i}/") for i in range(6)])
check(set(got) == {"crumbs_none"} and got["crumbs_none"].rows[0][:2] == ["/catalog/", 6], f"сайт без крошек: {got}")
check(not run([page(f"{S}/k{i}/") for i in range(6)]), "плоский сайт без крошек - находка")
# крошки не искали (старая проверка без колонки shop) - «крошек нет» не говорим
check(not run([page(f"{S}/catalog/k{i}/", old=True) for i in range(6)]), "крошки не искали, а находка есть")
check(not run([page(f"{S}/catalog/k{i}/") for i in range(6)], issues=[SimpleNamespace(key="rich_no_crumbs")]),
      "повтор rich_no_crumbs")

if fails:
    print("✗ хлебные крошки:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ хлебные крошки: не на всех страницах раздела, без разметки, ссылки на 404 и редирект, ссылка на себя")
