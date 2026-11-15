"""Микроразметка и Open Graph подробно (версия 7.1): заполнено ли то, из чего Яндекс и Google строят
расширенный сниппет (цена, наличие, звёзды, хлебные крошки) и превью ссылки в мессенджерах.
Старые проверки (без колонки schema_info и без meta og_images) этих проверок не получают."""

from ..common import NOTE, WARN, page_json, unpack_blocks
from .commercial import PRICE

FIELDS = {"price": "цены", "currency": "валюты", "availability": "наличия", "image": "картинки", "name": "названия"}
OG_MIN = 200            # меньше — Telegram и ВКонтакте показывают крошечное превью или не показывают вовсе
OG_GOOD = (1200, 630)   # рекомендуемый размер


def run(ctx):
    add, indexable = ctx.add, ctx.indexable
    info = []
    for p in indexable:
        data = page_json(p, "schema_info")
        if data is not None:
            info.append((p, data))
    if info:
        _product(add, info)
        _crumbs(add, info)
        _org(add, info)
    _og(ctx)


def _price_on_page(p):
    """Видна ли на странице цена («1 990 ₽», «500 руб.»); None - текста по блокам нет (старая проверка)."""
    blocks = unpack_blocks(p)
    return None if blocks is None else bool(PRICE.search("\n".join(blocks)))


def _product(add, info):
    no_price, no_price_anywhere, partial = [], [], []
    for p, s in info:
        pr = s.get("product")
        if not pr:
            continue
        if not pr.get("price"):
            row = [p["url"], pr.get("src", ""), "нет блока Offer" if not pr.get("offers") else "в Offer нет price"]
            # цены нет и на самой странице (техническая карточка производителя, oidbearing.ru): цену в
            # разметку не добавишь - разметка должна совпадать с тем, что видно на странице
            (no_price_anywhere if _price_on_page(p) is False else no_price).append(row)
        miss = [FIELDS[k] for k in ("currency", "availability", "image", "name") if not pr.get(k)]
        if pr.get("price") and miss:
            partial.append([p["url"], pr.get("src", ""), ", ".join(miss)])
    add("rich_no_price", WARN, "Микроразметка", "Товар размечен без цены",
        "На странице есть микроразметка товара (Product), но цены в ней нет. Без цены Яндекс и Google не покажут в "
        "выдаче цену и наличие, а товарный сниппет не построится: разметка есть, а пользы от неё нет.",
        "Передайте разработчику: в разметку товара добавить блок offers (Offer) с price, priceCurrency (RUB) и "
        "availability (InStock / OutOfStock). Проверить - validator.schema.org или «Проверка микроразметки» в Вебмастере.",
        ["Адрес", "Вид разметки", "Чего нет"], no_price)
    add("rich_no_price_page", NOTE, "Микроразметка", "Товар размечен без цены, и на странице цены нет",
        "На странице есть микроразметка товара (Product), но цены нет ни в ней, ни на самой странице. Добавить цену "
        "только в разметку нельзя: Яндекс и Google требуют, чтобы разметка совпадала с тем, что видит посетитель. "
        "Товарного сниппета с ценой в выдаче не будет.",
        "Если цены на сайте не показываются намеренно (опт, цена по запросу), ничего делать не нужно. Если цены есть, "
        "но не выводятся на странице, - показать цену на странице и добавить её в разметку (offers: price, "
        "priceCurrency, availability).",
        ["Адрес", "Вид разметки", "Чего нет"], no_price_anywhere)
    add("rich_partial", NOTE, "Микроразметка", "Разметка товара заполнена не полностью",
        "Цена в разметке товара есть, но не хватает других полей: валюты, наличия, картинки или названия. Google без "
        "валюты и наличия считает разметку неполной и может не показать её в выдаче.",
        "Передайте разработчику: заполнить в разметке товара недостающие поля (см. колонку «Чего нет»).",
        ["Адрес", "Вид разметки", "Чего нет"], partial)


def _crumbs(add, info):
    deep = [p for p, _s in info if (p.get("depth") or 0) >= 2]
    if len(deep) < 20 or any(s.get("crumbs") for _p, s in info):
        return
    add("rich_no_crumbs", NOTE, "Микроразметка", "Нет разметки хлебных крошек",
        "Ни на одной странице нет разметки BreadcrumbList. По ней Яндекс и Google показывают в выдаче путь по разделам "
        "(«Главная › Каталог › Раздел») вместо длинного адреса - сниппет понятнее, по нему чаще кликают.",
        "Передайте разработчику: разметить блок хлебных крошек в шаблоне (JSON-LD BreadcrumbList или microdata). "
        "Если самих крошек на сайте нет, сначала добавить их на внутренние страницы.",
        ["Пример страницы в глубине сайта"], [[p["url"]] for p in deep[:20]], page_col=None)


def _org(add, info):
    rows = []
    for p, s in info:
        o = s.get("org")
        if o and not (o.get("address") and o.get("phone")):
            rows.append([p["url"], ", ".join(x for x, k in (("адреса", "address"), ("телефона", "phone"), ("названия", "name"))
                                              if not o.get(k))])
    if len(rows) > 5:  # разметка в шаблоне — одна правка на весь сайт
        miss = rows[0][1]
        rows = [[f"на {len(rows)} страницах (разметка в шаблоне сайта), например:\n" + "\n".join(r[0] for r in rows[:3]), miss]]
    add("rich_org_partial", NOTE, "Микроразметка", "В разметке организации нет адреса или телефона",
        "Разметка Organization / LocalBusiness есть, но без адреса или телефона. Именно эти поля поисковики берут для "
        "карточки организации и быстрых ответов «где находится», «как позвонить».",
        "Передайте разработчику: добавить в разметку address (PostalAddress) и telephone - те же, что в Яндекс Бизнесе.",
        ["Адрес страницы", "Чего нет"], rows[:50], page_col=None)


def _og(ctx):
    imgs = ctx.store.get_meta("og_images", None)
    if not imgs:
        return
    bad, small, rel = [], [], []
    for x in imgs:
        st = x.get("status")
        is_img = str(x.get("type") or "").startswith("image/") or x.get("w")
        if st != 200 or not is_img:
            bad.append([x["url"], x["pages"], st if st != 200 else f"не картинка ({x.get('type') or 'тип не указан'})"])
        elif x.get("w") and x.get("h") and (x["w"] < OG_MIN or x["h"] < OG_MIN):
            small.append([x["url"], x["pages"], f"{x['w']}×{x['h']}"])
        if x.get("relative"):
            rel.append([x["url"], x["pages"]])
    ctx.add("og_image_bad", WARN, "Соцсети", "Картинка для превью ссылки не открывается",
            "В og:image указана картинка, которая не открывается (ошибка или это не картинка). Когда ссылкой на страницу "
            "делятся в Telegram, ВКонтакте или WhatsApp, превью выходит без картинки - по такой ссылке кликают реже.",
            "Передайте разработчику: в og:image указать рабочий полный адрес картинки (https://…), 1200×630 пикселей.",
            ["Картинка", "На скольких страницах", "Что не так"], bad, page_col=None)
    ctx.add("og_image_small", NOTE, "Соцсети", "Картинка для превью ссылки слишком маленькая",
            f"Картинка в og:image меньше {OG_MIN}×{OG_MIN} пикселей. Мессенджеры показывают её крошечной или "
            f"не показывают вовсе. Рекомендуемый размер - {OG_GOOD[0]}×{OG_GOOD[1]}.",
            f"Передайте разработчику: сделать картинку для превью {OG_GOOD[0]}×{OG_GOOD[1]} (логотип на фоне или фото товара).",
            ["Картинка", "На скольких страницах", "Размер"], small, page_col=None)
    ctx.add("og_image_relative", NOTE, "Соцсети", "Адрес картинки для превью указан не полностью",
            "В og:image адрес без https:// и домена (например, /images/logo.png). Часть мессенджеров и соцсетей такой "
            "адрес не понимает, и превью выходит без картинки.",
            "Передайте разработчику: писать в og:image полный адрес - https://сайт/путь/к/картинке.jpg.",
            ["Картинка", "На скольких страницах"], rel, page_col=None)
