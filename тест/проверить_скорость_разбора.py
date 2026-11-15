"""Ускорения разбора страницы (01.11.2026, страница товара thehome.ru: ~300 мс → ~200 мс) не меняют результат:
- одно чтение страницы для двух разборов (parser._Both): «Что мешает покупать» то же, что отдельным разбором; разбор,
  упавший с ошибкой, дальше ничего не получает, второй дочитывает страницу;
- счётчики с предпроверкой подстрокой - те же, что полным поиском шаблонами;
- классы элементов в shop._cls_marks запоминаются - то же, что разбор каждого класса заново;
- облегчённый разбор исходника при JavaScript (light) - те же поля для сравнения «до и после скриптов».
Без сети. Запуск: py -3 тест/проверить_скорость_разбора.py (и из проверить_всё.py)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seocrawler import parser as P  # noqa: E402
from seocrawler import shop as S  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


SHOP = """<html><head><title>Диван Модена купить</title><meta name="description" content="Диван">
<link rel="canonical" href="https://shop.test/divan/"><meta name="robots" content="index, follow">
<script>ym(12345678, "init", {});</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script></head>
<body><header class="site-header"><a href="tel:+74951234567">+7 495 123-45-67</a>
<div class="mini-cart">Корзина 0 ₽</div><nav><a href="/">Главная</a><a href="/divany/">Диваны</a></nav></header>
<div class="breadcrumbs"><a href="/">Главная</a> / <a href="/divany/">Диваны</a> / <span>Модена</span></div>
<h1>Диван <b>Модена</b></h1><div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Модена</span>
<div class="product-price"><span class="price-old">59 990 ₽</span><span class="price">49 990 ₽</span></div>
<p class="stock">В наличии</p><button class="btn-buy">Купить</button><button>Купить в 1 клик</button>
<div class="characteristics"><h2>Характеристики</h2><p>Ширина 200 см</p></div>
<div class="related" itemprop="isSimilarTo"><div class="price">10 000 ₽</div></div></div>
<form><input name="phone" type="tel"><input type="checkbox" name="agree">Согласие на обработку персональных данных
<button type="submit">Отправить</button></form>
<footer class="footer-main"><a href="tel:88001234567">8 800 123-45-67</a> © 2026 <a href="https://vk.com/shop">VK</a>
</footer></body></html>"""
PLAIN = "<html><head><title>Статья</title></head><body><h1>Про котлы</h1><p>" + "Текст о котлах. " * 80 + \
        "</p><a href='/a'>a</a></body></html>"
BROKEN = "<html><head><title>Битая</title></head><body><div class='price'>1 000 ₽<table><tr><td>" + \
         "<p>незакрытые теги <a href='/x'>ссылка" * 30 + "</body>"


def naive_counters(html_text):
    """Как было до предпроверки: все шаблоны по всей странице."""
    out = {}
    ym = sorted({m for rx in P._YM for m in rx.findall(html_text)})
    if ym or P._YM_ANY.search(html_text):
        out["ym"] = ym or ["?"]
    ga = sorted({m for rx in P._GA for m in rx.findall(html_text)})
    if ga:
        out["ga"] = ga
    gtm = sorted(set(P._GTM.findall(html_text)))
    if gtm:
        out["gtm"] = gtm
    return json.dumps(out)


def naive_marks(cls, zone):
    toks = cls.split() if zone else []
    return (any(S.HEADER_CLS.match(t) for t in toks), any(S.FOOTER_CLS.match(t) for t in toks),
            any(S.CART_CLS.match(t) for t in toks), bool(S.PRICE_CLS.search(cls)), bool(S.OLD_CLS.search(cls)),
            bool(S.SPEC_BOX.search(cls)), bool(S.CRUMB_CLS.search(cls)))


def main():
    # 1. одно чтение для двух разборов - «Что мешает покупать» как отдельным разбором
    for name, doc in (("магазин", SHOP), ("статья", PLAIN), ("битая разметка", BROKEN)):
        got = P.parse_html(doc.encode("utf-8"), "text/html; charset=utf-8")["shop"]
        check(got == S.facts(doc), f"{name}: «Что мешает покупать» при общем чтении другое")
    shop = json.loads(P.parse_html(SHOP.encode("utf-8"), "text/html; charset=utf-8")["shop"] or "{}")
    check(shop.get("price") == 49990, f"магазин: цена {shop.get('price')}, ждали 49990")

    # 2. упавший разбор отключается, второй дочитывает страницу
    class Boom:
        n = 0

        def handle_starttag(self, tag, attrs):
            self.n += 1
            if self.n == 3:
                raise ValueError("сбой")

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            pass

        def handle_data(self, data):
            pass
    boom, ex = Boom(), P._Extractor()
    both = P._Both(boom, ex)
    both.feed(SHOP)
    both.close()
    check(boom.n == 3, f"упавший разбор получил {boom.n} тегов после сбоя, ждали остановку на 3")
    check(ex.titles == ["Диван Модена купить"] and len(ex.links) >= 5, "второй разбор не дочитал страницу после сбоя первого")

    # 3. счётчики: предпроверка подстрокой не теряет и не добавляет
    samples = [SHOP, PLAIN, "<script>yaCounter87654321.reachGoal('x')</script>",
               "<img src='https://mc.yandex.ru/watch/11223344'>", "<script src='https://mc.yandex.ru/metrika/tag.js'>",
               "gtag('config', 'UA-1234-5'); GTM-ABCD12 (GTM-XYZ)", "ym (123) gtm-abcd mc.yandex", ""]
    for s in samples:
        check(P.counters(s) == naive_counters(s), f"счётчики разошлись: {s[:60]!r}")

    # 4. классы запоминаются - результат как без запоминания
    for cls in ("site-header", "header__menu  ", "footer-main x", "mini-cart", "cart-btn", "product-price price-old",
                "characteristics", "breadcrumbs", "topbar", "page-footer", "", "btn btn-buy", "basketBlock"):
        for zone in (True, False):
            check(S._cls_marks(cls, zone) == naive_marks(cls, zone), f"классы «{cls}» ({zone}) разошлись")
            check(S._cls_marks(cls, zone) == naive_marks(cls, zone), f"классы «{cls}» из памяти разошлись")

    # 5. облегчённый разбор исходника: поля для сравнения те же, лишнее не считается
    full = P.parse_html(SHOP.encode("utf-8"), "text/html; charset=utf-8")
    light = P.parse_html(SHOP.encode("utf-8"), "text/html; charset=utf-8", light=True)
    for k in ("titles", "descriptions", "h1", "canonicals", "robots", "refresh_url", "base", "links", "text",
              "word_count", "calltrack", "contacts", "encoding", "encoding_source", "bad_chars", "html_counts",
              "dup_ids", "head_break", "after_break", "images", "resources", "hreflang"):
        check(full[k] == light[k], f"облегчённый разбор: поле {k} другое")
    check(light["shop"] == "" and light["minhash"] == "" and light["blocks"] is None and light["counters"] == "{}",
          "облегчённый разбор посчитал лишнее (цены, отпечаток, блоки, счётчики)")
    check(full["shop"] and full["blocks"] and full["counters"] != "{}", "полный разбор не посчитал цены, блоки, счётчики")

    if fails:
        print("✗ скорость разбора:\n   " + "\n   ".join(fails[:15]))
        sys.exit(1)
    print("✓ скорость разбора: общее чтение, счётчики, классы и облегчённый разбор - результат прежний")


if __name__ == "__main__":
    main()
