"""Автотест трёх ложных находок на некоммерческом сайте (портфолио timurpanin.ru), без сети:
слово в коротких кавычках - пример, а не опечатка; коммерческие факторы - только у сайта, который продаёт, и не по
словам из абзаца статьи; свой sitemap.xml не делаем, если карта сайта уже такая же и без проблем."""
import os
import sqlite3
import sys
import types
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import fix_files, speller  # noqa: E402
from seocrawler.analyze.checks import commercial  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# 1. Орфография: короткий кусок в кавычках не проверяем, длинную фразу в кавычках - проверяем
t = speller.unquoted("В метаописании обнаружено «французкого» вместо «французского» и \"отввечает\".")
check("французкого" not in t and "отввечает" not in t and "обнаружено" in t, f"короткие кавычки: {t!r}")
t = speller.unquoted("Слоган «мы делаем лучшие окна в городе Уфа» на главной")
check("лучшие" in t, f"длинная фраза в кавычках пропала: {t!r}")


# 2. Коммерческие факторы
def comm(pages, links=(), schema=""):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE links (src, dst, anchor, kind)")
    db.executemany("INSERT INTO links VALUES (?, ?, ?, 'a')", links)
    idx = [{"url": u, "blocks": zlib.compress(t.encode()), "schema_types": schema, "contacts": "{}"}
           for u, t in pages.items()]
    res = []
    commercial.run(types.SimpleNamespace(db=db, indexable=idx, add=lambda *a, **k: res.append(a)))
    return res[0] if res else None


case = ("Фильтр брендов сам создавал 16 ссылок на 404, а часть товаров передавалась с ценой 1 ₽\n"
        "2. Цена 1 ₽ передавалась как цена товара\n"
        "При этом действия «В корзину» и «Купить в один клик» в проверенном сценарии открывали форму заявки.\n"
        "Тексты пользовательских отзывов отделялись от редакционного контента.")
check(comm({"https://p.ru/": case, "https://p.ru/c/": "Кейсы и разборы сайтов"}) is None,
      "портфолио с рассказом о ценах и корзине получило «Коммерческие факторы»")
shop = comm({"https://s.ru/a": "Холодильник LG\n12 500 ₽\nВ корзину", "https://s.ru/b": "Плита\n9 990 ₽\nВ корзину\n"
             "RS Market получает положительные отзывы от покупателей много лет подряд и дорожит ими."})
check(shop is not None, "магазин без «Коммерческих факторов»")
if shop:
    rows = {r[0]: r for r in shop[7]}
    check(rows["Цены"][1].startswith("на 2 из 2"), f"цены магазина: {rows['Цены'][1]}")
    check(rows["Отзывы"][1] == "не найдено", "«отзывы» из длинного абзаца засчитаны как раздел отзывов")
check(comm({"https://s.ru/a": "Товар"}, schema="Product, Offer") is not None, "разметка товара не считается продажей")
check(comm({"https://s.ru/a": "Услуги"}, links=[("https://s.ru/a", "https://s.ru/z", "Оставить заявку")]) is not None,
      "ссылка «Оставить заявку» не считается продажей")
price_list = "смартфоны - 250 / 373 / 496 руб. за единицу ;"
check(commercial._Short(commercial.PRICE, 6).search(price_list), "строка прайса с цифрами не считается ценой")


# 3. Своя карта сайта в порядке - свой sitemap.xml не нужен
class St:
    def __init__(self, urls):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE sitemap (url TEXT PRIMARY KEY)")
        self.db.executemany("INSERT INTO sitemap VALUES (?)", [(u,) for u in urls])


sm = ["https://p.ru/", "https://p.ru/a/"]
check(fix_files.own_sitemap_ok(St(sm), [], sm), "та же карта без проблем - а sitemap.xml всё равно делаем")
check(not fix_files.own_sitemap_ok(St(sm[:1]), [], sm), "в своей карте не хватает страницы - а sitemap.xml не делаем")
check(not fix_files.own_sitemap_ok(St([]), [], sm), "карты на сайте нет - а sitemap.xml не делаем")
bad = Issue("sitemap_redirect", "warning", "Sitemap", "", "", "", ["Адрес"], [["https://p.ru/old"]])
check(not fix_files.own_sitemap_ok(St(sm), [bad], sm), "в карте редиректы - а sitemap.xml не делаем")
html = fix_files.html_block([{"file": "", "key": "sitemap_ok", "n": 0, "what": "Карта в порядке."}])
check("Карта в порядке." in html and "Папка:" not in html, f"строка без файла в отчёте: {html}")

# 4. «Нет в наличии»: раздел каталога, где у одной карточки «Снято с производства», а у остальных «В наличии», -
# не товар не в наличии (dom-primer.ru: 289 из 305 строк); страница самого товара - да
from seocrawler.analyze.checks import stock  # noqa: E402


def oos(pages):
    idx = [{"url": u, "title": u, "blocks": zlib.compress("\n".join(t).encode())} for u, t in pages.items()]
    got = {}
    stock.run(types.SimpleNamespace(indexable=idx, add=lambda key, *a, **k: got.__setitem__(key, a[-1])))
    return [r[0] for r in got.get("out_of_stock", [])]


card = ["Купить в 1 клик", "Артикул: 1"]
listing = ["Зеркальные шкафы"] + ["Шкаф " + str(i) for i in range(30)] + ["В наличии Много"] * 20 + \
          ["Под заказ"] * 5 + ["Снято с производства"] + card
filler = {f"https://s.ru/p{i}/": ["Страница " + str(i), "текст " * i] for i in range(40)}   # чтобы шаблон считался
# товар: надпись дважды (блоки для компьютера и телефона) и карусель похожих, у каждой карточки «В наличии»
twice = ["Шкаф Ravak", "Нет в наличии", "Нет в наличии", "12 990 ₽"] + card + ["Похожие товары"] + ["В наличии Много"] * 6
got = oos(dict(filler, **{"https://s.ru/catalog/shkafy/": listing,
                          "https://s.ru/product/1/": ["Шкаф Roca", "Снято с производства", "45 990 ₽"] + card,
                          "https://s.ru/product/2/": twice}))
check("https://s.ru/catalog/shkafy/" not in got, f"раздел каталога с одной снятой карточкой - «нет в наличии»: {got}")
check("https://s.ru/product/1/" in got, f"снятый с производства товар не найден: {got}")
check("https://s.ru/product/2/" in got, f"товар с надписью дважды и каруселью похожих не найден: {got}")

# 5. Готовые description: у товара - бренд и страна со страницы (не из «Похожих товаров»); странице
# удалённого товара («не найдена» при коде 200) заголовки не сочиняются - пометка «сначала 404 или 301»
from seocrawler.analyze.checks import meta_suggest  # noqa: E402


def pg(u, t, h, lines):
    return {"url": u, "title": t, "h1": h, "h1_count": 1 if h else 0, "description": "", "depth": 2,
            "blocks": zlib.compress("\n".join(lines).encode()), "schema_info": "{}"}


card = ["Купить", "В корзину", "Артикул: 22225", "Производитель", "Marazzi", "Страна", "Италия", "Похожие товары",
        "Производитель", "Roca", "Страна", "Испания"]
pages = [pg(f"https://s.ru/product/item{i}-{1000 + i}/", f"Плитка {i} купить | S.ru", f"Плитка номер {i}", card)
         for i in range(8)] + [pg("https://s.ru/product/old-2000/", "", "", ["Элемент не найден"])]
ctx = types.SimpleNamespace(indexable=pages, html_ok=pages, add=lambda *a, **k: None,
                            store=types.SimpleNamespace(path=os.path.join(os.sep, "нет", "crawl.db")),
                            soft404={"https://s.ru/product/old-2000/"}, home_copies=set(), issues=[])
meta_suggest.run(ctx)
d = next((r.get("desc") or "" for r in ctx.meta_suggest if r["url"].endswith("item0-1000/")), "")
check("Marazzi, Италия" in d and "Roca" not in d, f"описание товара без бренда и страны: {d!r}")
check(not any(r["url"].endswith("old-2000/") for r in ctx.meta_suggest)
      and any(r["url"].endswith("old-2000/") and "404" in r.get("what", "") for r in ctx.meta_manual),
      "странице удалённого товара сочинены заголовки")

if fails:
    print("ОШИБКИ в ложных находках:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ ложные находки: слова в кавычках, коммерческие факторы у некоммерческого сайта, своя карта сайта в порядке")
