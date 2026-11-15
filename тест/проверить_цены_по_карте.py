"""Автотест: цена по клубной карте или по акции и «экономия» (05.10.2026, seocrawler/shop.py discount,
analyze/checks/buy.py _discount_checks). Пример с сайта пользователя (gasprofservice): «72 990 ₽», ниже «Цена с
картой клуба · 69 341 ₽ · экономия 3 649 ₽» - всё сходится. Ошибки: экономия не равна разнице, цена по карте выше
обычной, отрицательная экономия, скидка 95%, у одного товара раздела 50% при 5% у остальных, цена по карте в разметке.
Запуск: py -3 тест/проверить_цены_по_карте.py"""
import json
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seocrawler import shop  # noqa: E402
from seocrawler.analyze.checks import buy  # noqa: E402

fails = []


def check(cond, text):
    if not cond:
        fails.append(text)


HEAD = '<header class="header"><div class="header-cart">Корзина <span class="price">0 ₽</span></div></header>'
FOOT = '<footer>© 2026 Магазин <a href="/club/">Клуб клиентов</a></footer>'


def card(name, price, club_block="", sprice=None, old=None, related=True):
    """Карточка как на gasprofservice: цена, под ней строка с ценой по карте."""
    sp = price.replace(" ", "") if sprice is None else sprice
    oldp = f'<span class="price-old">{old} ₽</span>' if old else ""
    rel = ('<div class="related"><h3>Похожие товары</h3><div class="item"><div class="price">50 000 ₽</div>'
           '<div class="price-club">Цена с картой клуба · 47 500 ₽ · экономия 9 999 ₽</div></div></div>') if related else ""
    return (f'<html><body>{HEAD}<h1>{name}</h1><div class="buy"><div class="price-row" itemprop="offers" itemscope '
            f'itemtype="https://schema.org/Offer"><div class="card__price"><span itemprop="price" content="{sp}">{price}'
            f'</span> ₽</div>{oldp}</div>{club_block}<div class="stock">Под заказ</div>'
            f'<a href="#" class="btn">В КОРЗИНУ</a></div><div itemscope itemtype="https://schema.org/Product">'
            f'<meta itemprop="name" content="{name}"></div>{rel}{FOOT}</body></html>')


def club(c, save):
    return f'<div class="card__price-club"> Цена с картой клуба · {c} ₽ · экономия {save} ₽</div>'


# разбор одной страницы
f = json.loads(shop.facts(card("Котёл Baxi Eco 24", "72 990", club("69 341", "3 649"), related=False)))
check(f.get("price") == 72990, f"цена товара: {f.get('price')} (ждали 72 990, а не цену по карте)")
check(f.get("prices") == 1, f"цена по карте не считается второй ценой товара: {f.get('prices')}")
d = f.get("disc") or {}
check(d.get("club") == 69341 and d.get("save") == 3649, f"цена по карте и экономия: {d}")
# «1 290 ₽ по карте», значок «−5%», «скидка до 30%» - реклама
d = json.loads(shop.facts(card("Котёл A", "1 358", '<div class="card">1 290 ₽ по карте <b>−5%</b></div>'))).get("disc") or {}
check(d.get("club") == 1290 and d.get("pct") == 5, f"цена после слов и значок: {d}")
d = json.loads(shop.facts(card("Котёл B", "10 000", '<p>Скидка до 30% по акции выходного дня</p>', related=False))
               ).get("disc") or {}
check(not d, f"«скидка до 30%» - не скидка товара: {d}")
# обычная скидка со старой ценой: экономия считается от старой цены
d = json.loads(shop.facts(card("Котёл C", "9 000", '<div>Экономия 1 000 ₽</div>', old="10 000"))).get("disc") or {}
check(d.get("save") == 1000 and "club" not in d, f"экономия при старой цене: {d}")

pages_html = {
    # пример пользователя: всё сходится
    "https://s.ru/kotly/a/baxi/": card("Котёл Baxi Eco 24", "72 990", club("69 341", "3 649")),
    # экономия не равна разнице
    "https://s.ru/kotly/a/navien/": card("Котёл Navien 20", "40 000", club("38 000", "3 000")),
    # клубная цена выше обычной, а «экономия» есть
    "https://s.ru/kotly/a/bosch/": card("Котёл Bosch 6000", "50 000", club("52 500", "2 500")),
    # отрицательная экономия
    "https://s.ru/kotly/a/vaillant/": card("Котёл Vaillant 24", "60 000",
                                           '<div class="price-club">Цена по карте 63 000 ₽, экономия −3 000 ₽</div>'),
    # скидка 95%
    "https://s.ru/kotly/b/ariston/": card("Котёл Ariston 24", "80 000", club("4 000", "76 000")),
    # в разметке цена по карте
    "https://s.ru/kotly/b/protherm/": card("Котёл Protherm 24", "30 000", club("28 500", "1 500"), sprice="28500"),
    # старая цена и правильная экономия - не ошибка
    "https://s.ru/kotly/b/kiturami/": card("Котёл Kiturami 24", "9 000", '<div>Экономия 1 000 ₽</div>', old="10 000"),
}
# пример пользователя (gasprofservice, запчасти BAXI): на странице товара 16 132 ₽, зачёркнута 15 064 ₽, по карте
# 15 325 ₽ - по карте дороже зачёркнутой; в разделе каталога «Цена 15 064 Р. по карте клуба 15 325 Р.»
pages_html["https://s.ru/zapchasti/to/luna3/"] = card("Теплообменник Baxi Luna-3", "16 132", club("15 325", "807"),
                                                          old="15 064", related=False)
CARDS = "".join(f'<div class="cat_item"><div class="artikul">Артикул: {a}</div><h3>Теплообменник {a}</h3>'
                f'<div class="price_bl old_price"><div class="price"><span>Цена</span>{p}<div class="rouble">Р.</div>'
                f'</div></div><div class="price_bl club_price"><span>по карте клуба</span><div class="price">{c}'
                f'<div class="rouble">Р.</div></div></div><a class="o_btn">Купить</a></div>'
                for a, p, c in (("5681190", "15 064", "15 325"), ("5680990", "15 480", "16 018"),
                                ("5677660", "15 307", "15 839"), ("1111111", "20 000", "19 000")))
pages_html["https://s.ru/zapchasti/to/"] = f'<html><body>{HEAD}<h1>Теплообменники</h1>{CARDS}{FOOT}</body></html>'
pages_html["https://s.ru/zapchasti/to/?page=1"] = f'<html><body>{HEAD}<h1>Теплообменники</h1>{CARDS}{FOOT}</body></html>'
# раздел: у 6 товаров 5%, у одного 50%
for i in range(6):
    pages_html[f"https://s.ru/kolonki/k{i}/"] = card(f"Колонка {i}", "20 000", club("19 000", "1 000"))
pages_html["https://s.ru/kolonki/k9/"] = card("Колонка 9", "20 000", club("10 000", "10 000"))

pages = [{"url": u, "title": "", "shop": shop.facts(h), "contacts": None} for u, h in pages_html.items()]
issues = []
ctx = SimpleNamespace(pages=pages, indexable=pages, issues=issues, store=SimpleNamespace(get_meta=lambda k, d=None: d),
                      add=lambda key, sev, cat, title, why, fix, cols, rows, page_col=0:
                      rows and issues.append(SimpleNamespace(key=key, sev=sev, rows=rows, cols=cols, why=why, fix=fix,
                                                             title=title)))
buy.run(ctx)
got = {i.key: i for i in issues}
want = {"buy_club_save": ["navien"], "buy_club_higher": ["bosch", "vaillant", "luna3"], "buy_discount_odd": ["vaillant", "ariston"],
        "buy_schema_club": ["protherm"], "buy_discount_outlier": ["k9"]}
for k, names in want.items():
    rows = got[k].rows if k in got else []
    urls = sorted(r[0] for r in rows)
    check(len(rows) == len(names) and all(any(n in u for u in urls) for n in names),
          f"{k}: {urls} (ждали {names})")
    for r in rows:
        check(len(r) == len(got[k].cols), f"{k}: столбцов {len(r)}, заголовков {len(got[k].cols)}")
lst = got.get("buy_club_higher_list")
check(lst and sorted(r[0].split("Артикул: ")[1][:7] for r in lst.rows) == ["5677660", "5680990", "5681190"]
      and all(r[3] == 2 for r in lst.rows), f"карточки раздела: {lst.rows if lst else 'нет'}")
check("buy_schema_price" not in got, f"цена по карте в разметке не дублируется в buy_schema_price: "
      f"{got['buy_schema_price'].rows if 'buy_schema_price' in got else ''}")
check([r[0] for r in got["buy_old_price"].rows] == ["https://s.ru/zapchasti/to/luna3/"] if "buy_old_price" in got
      else False, "старая цена ниже новой - только у запчасти Luna-3")
for i in issues:
    for r in i.rows if i.key in want else []:
        check("baxi" not in r[0] and "kiturami" not in r[0], f"{i.key}: лишнее срабатывание {r}")
save = got.get("buy_club_save")
check(save and save.rows[0][3] == "3 000 ₽" and save.rows[0][4] == "2 000 ₽", f"экономия и как должно быть: "
      f"{save.rows if save else ''}")
texts = " ".join(i.title + i.why + i.fix for i in issues)
check("—" not in texts and "рограмм" not in texts, "тексты: без длинного тире и «программа»")

if fails:
    print("✗ Цены по карте и экономия:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ Цены по карте и экономия: пример с gasprofservice сходится; экономия не та, цена по карте выше, "
      "отрицательная, 95%, скидка не как у раздела, цена по карте в разметке")
