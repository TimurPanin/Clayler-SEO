"""Автотест «Товар размечен без цены» (analyze/checks/rich.py, без сети).
Цены нет в разметке, но она видна на странице - предупреждение rich_no_price. Цены нет и на странице (техническая
карточка производителя, podshipnik-primer.ru) - только замечание rich_no_price_page, на здоровье не влияет. Старая проверка
без текста по блокам - как раньше, предупреждение. Запуск: py -3 tests/проверить_разметку_цены.py (и из проверить_всё.py)."""
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler.analyze.checks import rich  # noqa: E402

fails = []
NO_OFFER = json.dumps({"product": {"src": "json-ld", "name": True, "image": True}})


def page(url, text):
    return {"url": url, "schema_info": NO_OFFER, "blocks": zlib.compress(text.encode("utf-8")) if text is not None else None}


pages = [page("/visible/", "Подшипник 6204\nЦена\n1 990 ₽\nВ корзину"),
         page("/card/", "Техническая карточка OID 11204 ETN9\nd 20\nD 47\nB 40\nMass 0.18\nСвязаться с OID"),
         page("/old/", None)]
got = {}


def add(key, level, section, title, why, fix, cols, rows):
    got[key] = (level, [r[0] for r in rows])


rich._product(add, [(p, json.loads(p["schema_info"])) for p in pages])
if got.get("rich_no_price") != (rich.WARN, ["/visible/", "/old/"]):
    fails.append(f"предупреждение «без цены»: {got.get('rich_no_price')}, ждали /visible/ и /old/")
if got.get("rich_no_price_page") != (rich.NOTE, ["/card/"]):
    fails.append(f"замечание «цены нет и на странице»: {got.get('rich_no_price_page')}, ждали /card/")

# microdata по объектам: свойства разных товаров не складываются в один
from seocrawler.parser import parse_html  # noqa: E402


def product(body):
    return json.loads(parse_html(f"<html><body>{body}</body></html>".encode("utf-8"))["schema_info"]).get("product")


A = '<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Стул</span></div>'
B_OFFER = ('<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="100">'
           '<meta itemprop="priceCurrency" content="RUB"><link itemprop="availability" href="https://schema.org/InStock">'
           '</div>')
p = product(A + '<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Стол</span>' + B_OFFER + '</div>')
if not (p and p["price"] and p["currency"] and p["availability"] == "InStock" and p.get("count") == 2):
    fails.append(f"два товара - лучший целиком, со своим Offer: {p}")
p = product(A)
if not p or p["price"] or p["offers"]:
    fails.append(f"один товар без цены - без цены: {p}")
# валюта «похожего товара» внутри карточки - не валюта самого товара
p = product('<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Стул</span>'
            '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="5"></div>'
            '<div itemprop="isRelatedTo" itemscope itemtype="https://schema.org/Product"><span itemprop="name">Стол</span>'
            '<meta itemprop="priceCurrency" content="RUB"></div></div>')
if not p or not p["price"] or p["currency"] or "count" in p:
    fails.append(f"свойства вложенного товара приписаны основному: {p}")
# незакрытые теги внутри товара не роняют объект раньше времени, и товар после него - отдельный
p = product('<div itemscope itemtype="https://schema.org/Product"><p>текст<span itemprop="name">Стул</span>'
            '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="5">'
            '<meta itemprop="priceCurrency" content="RUB"></div></div>' + A)
if not p or not (p["price"] and p["currency"] and p["name"]) or p.get("count") != 2:
    fails.append(f"кривой HTML внутри товара: {p}")
# правильная разметка не теряет цену: варианты ProductGroup, Offer → itemOffered, itemref
OFF = ('<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="5">'
       '<meta itemprop="priceCurrency" content="RUB"></div>')
for what, body in (
        ("варианты hasVariant", '<div itemscope itemtype="https://schema.org/ProductGroup"><span itemprop="name">X</span>'
                                '<div itemprop="hasVariant" itemscope itemtype="https://schema.org/Product">' + OFF + '</div></div>'),
        ("Offer → itemOffered", '<div itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="5">'
                                '<meta itemprop="priceCurrency" content="RUB"><div itemprop="itemOffered" itemscope '
                                'itemtype="https://schema.org/Product"><span itemprop="name">X</span></div></div>'),
        ("itemref", '<div itemscope itemtype="https://schema.org/Product" itemref="o1"><span itemprop="name">X</span></div>'
                    '<div id="o1" itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" '
                    'content="5"><meta itemprop="priceCurrency" content="RUB"></div>')):
    p = product(body)
    if not p or not (p["price"] and p["currency"] and p["offers"]):
        fails.append(f"{what}: цена потерялась - {p}")
# без itemscope (бывает) - как раньше, по всей странице
p = product('<div itemtype="https://schema.org/Product"><span itemprop="name">X</span><meta itemprop="price" content="1"></div>')
if not p or not (p["name"] and p["price"]):
    fails.append(f"разметка без itemscope: {p}")

if fails:
    print("✗ разметка товара без цены:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ разметка товара без цены: на странице цена есть - предупреждение, нет - замечание")
