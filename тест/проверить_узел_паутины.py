"""Автотест наведения на узел живой паутины (05.10.2026, seocrawler/window/web_node.py): n-я готовая страница по
порядку проверки, ближайший адрес с ошибкой или переадресацией, главная проблема по ответу страницы, пока отчёта
нет. Без сети и без окна."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.window import web_node as W  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


root = tempfile.mkdtemp()
W.REPORTS = root
os.makedirs(os.path.join(root, "site"))
st = Store(os.path.join(root, "site", "crawl.db"))
html = "text/html; charset=utf-8"
rows = [("https://site.ru/", 200, "page", 1, {"title": "Главная", "h1": "Главная"}),
        ("https://site.ru/img.jpg", 404, "resource", 1, {}),
        ("https://site.ru/a", 200, "page", 1, {"title": "", "h1": "А"}),
        ("https://site.ru/old", 301, "page", 1, {"location": "https://site.ru/a"}),
        ("https://other.ru/", 200, "external", 0, {}),
        ("https://site.ru/b", 500, "page", 1, {}),
        ("https://site.ru/c", 200, "page", 1, {"title": "Ц", "h1": "Ц"})]
for url, code, kind, internal, extra in rows:
    st.enqueue(url, 1, bool(internal), kind, "https://site.ru/", "done")
    st.save_page(dict({"url": url, "status": code, "content_type": html if kind == "page" else "image/jpeg",
                       "indexable": 1}, **extra))
st.commit()
st.db.close()

pages = [W.lookup("site", "page", n)["url"] for n in range(6)]
check(pages == ["https://site.ru/", "https://site.ru/a", "https://site.ru/old", "https://site.ru/b", "https://site.ru/c",
                "https://site.ru/c"], f"порядок страниц: {pages}")
a = W.lookup("site", "page", 1)
check(a["sev"] == "warn" and "title" in a["problem"] and not a["report"], f"страница без title: {a}")
b = W.lookup("site", "page", 3)
check(b["sev"] == "crit" and "500" in b["problem"], f"страница 500: {b}")
e = W.lookup("site", "err", 1)  # около /a ближайший битый адрес - картинка перед ней
check(e["url"] == "https://site.ru/img.jpg" and e["where"].startswith("Картинка") and "404" in e["problem"], f"ошибка: {e}")
r = W.lookup("site", "warn", 0)
check(r["url"] == "https://site.ru/old" and "Переадресация 301" in r["problem"], f"переадресация: {r}")
check(W.lookup("нет", "page", 0).get("note"), "нет папки")
check("—" not in "".join(str(x) for x in (a, b, e, r)), "длинное тире")

src = open(os.path.join(os.path.dirname(W.__file__), "..", "report.py"), encoding="utf-8").read()
check('id="pagef"' in src and "get('issues')" in src, "в отчёте нет показа проблем одной страницы (#page=)")

if fails:
    print("ОШИБКИ в узле паутины:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ узел паутины: страница по ходу проверки, ближайшая ошибка, главная проблема")
