"""Страна сайта по признакам с самого сайта (seocrawler/country.py) и флаг картинкой.
Было: страны в отчёте не было; dog-comfort.kz (Казахстан, но og:locale ru_RU и lang ru-RU от конструктора)
легко принять за российский сайт.

1) Код страны по домену и по телефону: +7 7xx и 6xx - Казахстан, остальные +7 - Россия, +375 - Беларусь…
2) Страна по базе проверки: домен, телефоны, валюта цен, регион в языке; ru_RU от конструктора не перебивает
   .kz, телефоны и тенге; общая зона .com без признаков - страны нет.
3) Где стоит сервер: страна сети; за Cloudflare - «сервер скрыт».
4) Флаг: у каждой страны справочника - своя картинка SVG, правильный XML; неизвестная страна - плашка с кодом.
5) Строки в отчёте, «На чём сделан сайт» и карточке.
Запуск: py -3 tests/проверить_страну.py (и из проверить_всё.py)."""
import json
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seocrawler import country as C  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def db_with(pages):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE urls (url TEXT, internal INTEGER, kind TEXT, depth INTEGER)")
    db.execute("CREATE TABLE pages (url TEXT, status INTEGER, lang TEXT, hreflang TEXT, og TEXT, contacts TEXT, blocks BLOB)")
    for i, p in enumerate(pages):
        url = f"https://x/{i}"
        db.execute("INSERT INTO urls VALUES (?, 1, 'page', 1)", (url,))
        db.execute("INSERT INTO pages VALUES (?, 200, ?, ?, ?, ?, ?)",
                   (url, p.get("lang", ""), p.get("hreflang", ""), json.dumps(p.get("og", {})),
                    json.dumps({"phones": p.get("phones", []), "addresses": []}),
                    zlib.compress(p.get("text", "").encode("utf-8"))))
    return db


def main():
    for host, code in (("dog-comfort.kz", "KZ"), ("shop.com.kz", "KZ"), ("site.ru", "RU"), ("xn--p1ai", "RU"),
                       ("магазин.рф", "RU"), ("site.co.uk", "GB"), ("site.by", "BY"), ("site.com", None),
                       ("startup.io", None), ("site.online", None)):
        check(C.tld_country(host)[0] == code, f"зона {host}: {C.tld_country(host)} вместо {code}")
    for num, code in (("77011234567", "KZ"), ("77272123456", "KZ"), ("76001234567", "KZ"), ("79161234567", "RU"),
                      ("74951234567", "RU"), ("78001234567", "RU"), ("375291234567", "BY"), ("380441234567", "UA"),
                      ("998901234567", "UZ"), ("996555123456", "KG"), ("12025550123", "US"), ("4930123456", "DE")):
        check(C.phone_country(num) == code, f"телефон +{num}: {C.phone_country(num)} вместо {code}")

    # конструктор поставил ru_RU, а бизнес - в Казахстане
    kz = db_with([{"lang": "ru-RU", "og": {"og:locale": "ru_RU"}, "phones": ["+77476005026"],
                   "text": "Вольер 3x2 - 450 000 ₸\nБудка 85 000 тг\nДоставка по Алматы 5 000 тенге"}] * 3)
    c = C.detect(kz, "https://dog-comfort.kz/", {"net": {"country": "KZ", "holder": "MEGAHOST_KZ"}, "hosting": ""})
    check(c and c["code"] == "KZ" and c["sure"], f"Казахстан: {c}")
    check(c and any("тенге" in w for w in c["why"]) and any(".kz" in w for w in c["why"]), f"признаки: {c and c['why']}")
    check(c and c["server"]["code"] == "KZ" and "Казахстан" in C.server_text(c["server"]), f"сервер: {c and c['server']}")
    # .com с белорусскими телефонами и ценами
    by = db_with([{"phones": [], "text": "Звоните +375 (29) 123-45-67, цена 120 BYN, доставка 15 бел. руб."}] * 2)
    c = C.detect(by, "https://shop.com/")
    check(c and c["code"] == "BY", f"Беларусь на .com: {c}")
    # обычный российский сайт
    ru = db_with([{"lang": "ru", "og": {"og:locale": "ru_RU"}, "phones": ["+74951234567"], "text": "Цена 1 990 ₽"}])
    c = C.detect(ru, "https://www.franmeb.ru/")
    check(c and c["code"] == "RU" and c["sure"], f"Россия: {c}")
    # признаков нет - страны нет (флаг не рисуется)
    none = db_with([{"lang": "en", "text": "Hello world"}])
    c = C.detect(none, "https://site.com/")
    check(c is None, f"нет признаков, а страна есть: {c}")
    # hreflang и язык без региона
    ua = db_with([{"lang": "uk", "hreflang": "uk-UA https://x/; ru-UA https://x/ru/", "text": "Ціна 500 грн"}])
    c = C.detect(ua, "https://shop.com/")
    check(c and c["code"] == "UA", f"Украина по hreflang и гривнам: {c}")
    # цифры рядом со словами, похожими на валюту, не считаются ценой
    c = C.detect(db_with([{"text": "Комплект: 2 батареи, 10 ft кабель, 3 сомнения"}]), "https://site.com/")
    check(c is None, f"ложная валюта: {c}")
    # сервер за Cloudflare
    s = C.server_info({"net": {"country": "US", "holder": "CLOUDFLARENET"}, "shields": [{"name": "Cloudflare"}]})
    check("скрыт за Cloudflare" in C.server_text(s), f"сервер за Cloudflare: {C.server_text(s)}")

    for code in list(C.COUNTRIES) + ["XX"]:
        svg = C.flag_svg(code)
        try:
            ET.fromstring(svg)
        except ET.ParseError as e:
            fails.append(f"флаг {code}: неправильный SVG ({e})")
        if code != "XX":
            check(code in C.FLAGS, f"у страны {code} нет флага")
    check(">XX<" in C.flag_svg("XX"), "неизвестная страна - плашка с кодом")

    from seocrawler import report, site_tech
    c = C.detect(kz, "https://dog-comfort.kz/")
    sub = report._country_sub({"country": c})
    check("<svg" in sub and "Казахстан" in sub and "тенге" in sub, f"строка под заголовком отчёта: {sub[:200]}")
    t = site_tech.report_html(None, report._e, country=c)
    check("Страна сайта" in t and "<svg" in t, "строка «Страна сайта» в «На чём сделан сайт»")
    t = site_tech.audit_html(None, report._e, country=c)
    check("Страна сайта" in t and "<svg" not in t, "в аудите (PDF, Word) страна без картинки флага")

    if fails:
        print("✗ страна сайта:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print(f"✓ страна сайта: домен, телефоны, валюта, язык; сервер; флаги {len(C.FLAGS)} стран")


if __name__ == "__main__":
    main()
