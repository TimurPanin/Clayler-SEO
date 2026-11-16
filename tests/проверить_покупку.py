"""Автотест: «Что мешает покупать» по тексту страниц (seocrawler/shop.py, analyze/checks/buy.py).
Страницы - придуманные куски HTML; пример с сайта пользователя: товар за 1 ₽ «Под заказ» и крошки с повтором.
Запуск: py -3 tests/проверить_покупку.py"""
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


HEAD = ('<header class="header"><a href="tel:+73472000000">+7 (347) 200-00-00</a> <div class="city">Ваш город: Уфа</div>'
        '<div class="header-cart">Корзина <span class="price">0 ₽</span></div></header>')
FOOT = ('<footer><a href="tel:+73472000000">+7 (347) 200-00-00</a> © 2015-2026 Магазин'
        '<form><input name="phone" type="tel"><button>Заказать звонок</button>'
        '<p>Нажимая кнопку, вы соглашаетесь на обработку персональных данных</p></form></footer>')


def product(name, price, status="В наличии", old=None, sprice=None, extra="", crumbs=("Главная", "Каталог")):
    ld = ("" if sprice is None else
          '<script type="application/ld+json">{"@type":"Product","name":"%s","offers":{"@type":"Offer","price":"%s"}}'
          '</script>' % (name, sprice))
    cr = "".join(f'<a href="/">{c}</a> / ' for c in crumbs)
    oldp = f'<span class="price-old">{old} ₽</span>' if old else ""
    return (f'<html><head>{ld}</head><body>{HEAD}<div class="breadcrumbs">{cr}<span>{name}</span></div>'
            f'<h1>{name}</h1><div class="product-price"><span class="price">{price} ₽</span>{oldp}</div>'
            f'<div class="stock">{status}</div><button class="btn">В корзину</button>'
            f'<a class="one" href="#">Купить в 1 клик</a>{extra}'
            f'<div class="related"><div class="price">99 000 ₽</div></div>{FOOT}</body></html>')


# пример пользователя: 1 ₽, «Под заказ», крошки «Системы безопасности котла в Уфе» дважды
f = json.loads(shop.facts(product("Автомат. Воздухоотводчик taco ener+ CHAFFOTEAUX", "1", "Под заказ", sprice="1",
                                  crumbs=("Главная", "Каталог", "Системы безопасности котла в Уфе",
                                          "Системы безопасности котла в Уфе"))))
check(f.get("price") == 1 and f.get("sprice") == 1, f"цена товара (мини-корзина «0 ₽» в шапке не считается): {f}")
check(f.get("status") == "под заказ" and f.get("buy") == 2 and f.get("one_click") == 1, f"наличие и кнопки: {f}")
check(f.get("crumbs", [])[2:4] == ["Системы безопасности котла в Уфе"] * 2, f"крошки: {f.get('crumbs')}")
check(f.get("copy") == 2026 and f.get("city") == "Уфа", f"© и город: {f}")
check(f.get("forms") == [{"phone": 1, "consent": True, "btn": "Заказать звонок"}], f"форма с согласием: {f.get('forms')}")
check(f.get("hphones") == ["+73472000000"] and f.get("fphones") == ["+73472000000"], "телефоны шапки и подвала")

f = json.loads(shop.facts(product("Котёл", "45 000", old="40 000", sprice="47000",
                                  extra='<img src="/upload/no-photo.png"><div class="product-props"></div>'
                                        '<a href="https://wa.me/7XXXXXXXXXX">WhatsApp</a> <a href="https://t.me/">TG</a>'
                                        '<form><input type="email" name="email"><button>Подписаться</button></form>'
                                        '<p>{price}</p>')))
check(f.get("price") == 45000 and f.get("old") == 40000 and f.get("sprice") == 47000, f"цены: {f}")
check(f.get("ph_img") == 1 and f.get("spec_empty") == "блок характеристик пустой", f"заглушка и характеристики: {f}")
check(len(f.get("msg") or []) == 2, f"битые мессенджеры: {f.get('msg')}")
check({"email": 1, "btn": "Подписаться"} in (f.get("forms") or []), f"форма без согласия: {f.get('forms')}")
check(f.get("junk") == ["{price}"], f"остатки шаблона: {f.get('junk')}")

# спрятанная заготовка для скрипта (#name#) и «Товар 1» в списке - не остатки шаблона; товар «Тест» - остаток
f = json.loads(shop.facts('<h1>Контакты</h1><div style="display:none"><span>#name#</span></div><a href="/1">Товар 1</a>'))
check("junk" not in f, f"спрятанное и список: {f}")
f = json.loads(shop.facts('<h1>Тестовый товар</h1>'))
check(f.get("junk") == ["Тестовый товар"], f"товар-заглушка: {f}")

# раздел каталога: старая цена второго товара - не старая цена первого
f = json.loads(shop.facts('<h1>Аксессуары</h1><div class="price">599 ₽</div><div class="price">'
                          '<span class="price-old">541 ₽</span> 500 ₽</div>'))
check(f.get("price") == 599 and "old" not in f, f"старая цена чужого товара: {f}")

# ссылки на мессенджеры: правильные не трогаем
for h in ("https://wa.me/79991234567", "https://api.whatsapp.com/send?phone=79991234567&text=Здравствуйте",
          "https://t.me/gasmaster_ufa", "https://t.me/+AbCdEf123", "tg://resolve?domain=gasmaster", "https://wa.me/message/ABC",
          "tg://resolve?domain=PrimerLineWebinar_bot&start=dl-17", "tg://resolve?phone=79991234567",
          "tg://join?invite=AbCdEf", "tg://msg?text=hi", "whatsapp://send?phone=79991234567", "https://t.me/+79991234567"):
    check(shop.messenger_problem(h) is None, f"правильная ссылка признана битой: {h}")
for h in ("https://wa.me/", "https://wa.me/7999", "https://api.whatsapp.com/send?phone=", "https://t.me/",
          "https://t.me/username", "https://t.me/ab", "tg://resolve"):
    check(shop.messenger_problem(h) is not None, f"битая ссылка не найдена: {h}")
# имя бота без «domain=» (primerline.agency): в причине - как исправить
pr = shop.messenger_problem("tg://resolve?PrimerLineWebinar_bot&start=dl-17")
check(pr and "domain=PrimerLineWebinar_bot" in pr[1], f"tg://resolve без domain=: {pr}")

# проверки по нескольким страницам
pages_html = {
    "https://s.ru/cat/a/taco/": product("Воздухоотводчик taco", "1", "Под заказ", sprice="1",
                                        crumbs=("Главная", "Каталог", "Системы", "Системы")),
    "https://s.ru/cat/a/kotel/": product("Котёл", "45 000", old="40 000", sprice="47000"),
    "https://s.ru/cat/a/net/": product("Насос", "5 000", "Нет в наличии"),
    "https://s.ru/about/": f'<html><body>{HEAD}<h1>О нас</h1><p>Мы работаем в Уфе</p>{FOOT}</body></html>',
    "https://s.ru/msk/": f'<html><body>{HEAD}<h1>Котлы в Москве</h1>{FOOT}</body></html>',
}
for i in range(10):  # раздел из одинаковых по цене товаров и один в 20 раз дешевле
    pages_html[f"https://s.ru/cat/b/item{i}/"] = product(f"Горелка {i}", "20 000" if i else "900", sprice="20000" if i else "900")
pages_html["https://s.ru/cat/c/"] = product("Котлы отопления", "29 000", sprice="47000").replace(
    '"name":"Котлы отопления"', '"name":"Котёл Baxi Eco 24"')  # раздел с разметкой первого товара - не товар
pages = [{"url": u, "title": "", "shop": shop.facts(h), "contacts": None} for u, h in pages_html.items()]
issues = []
ctx = SimpleNamespace(pages=pages, indexable=pages, issues=issues, store=SimpleNamespace(get_meta=lambda k, d=None: d),
                      add=lambda key, sev, cat, title, why, fix, cols, rows, page_col=0:
                      rows and issues.append(SimpleNamespace(key=key, sev=sev, rows=rows, why=why, fix=fix, title=title)))
buy.run(ctx)
got = {i.key: i for i in issues}
want = {"buy_price_zero": 1, "buy_stock_conflict": 2, "buy_schema_price": 1, "buy_old_price": 1,
        "buy_price_low": 1, "buy_crumbs_repeat": 1, "buy_city": 1}
for k, n in want.items():
    check(k in got and len(got[k].rows) == n, f"{k}: {len(got[k].rows) if k in got else 'нет'} (ждали {n})")
for k in ("buy_messenger", "buy_no_consent", "buy_copyright", "buy_phones_differ", "buy_junk", "buy_no_photo"):
    check(k not in got, f"{k}: лишнее срабатывание {got[k].rows if k in got else ''}")
check(got.get("buy_price_low") and got["buy_price_low"].rows[0][0].endswith("item0/"), "дешёвый товар раздела")
check(got.get("buy_city") and got["buy_city"].rows[0][0].endswith("/msk/"), "другой город в заголовке")
texts = " ".join(i.title + i.why + i.fix for i in issues)
check("—" not in texts and "рограмм" not in texts, "тексты: без длинного тире и «программа»")

if fails:
    print("✗ «Что мешает покупать»:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ «Что мешает покупать»: цена 1 ₽, под заказ с кнопкой, разметка, старая цена, дешёвый товар, крошки, город, "
      "мессенджеры, формы")
