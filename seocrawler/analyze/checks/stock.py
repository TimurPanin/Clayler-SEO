"""Магазины (версия 7.1): пустые разделы каталога и товары «нет в наличии», открытые для поиска.
Ищется по тексту страниц без шаблона сайта (фраза в фильтре или в меню на всех страницах не считается)
и по разметке товара (availability: OutOfStock). Работает и на старых проверках — текст страниц в них есть."""
import re

from ..common import NOTE, WARN, TEMPLATE_MIN_PAGES, TEMPLATE_SHARE, defaultdict, page_json, unpack_blocks
from ...fmt import quote

EMPTY = re.compile(r"(товар\w* не найден|нет товаров|товар\w* нет\b|раздел пуст|категория пуста|"
                   r"в (?:этом|данном) (?:разделе|категории|каталоге) (?:пока )?(?:нет|отсутству)|"
                   r"товары отсутствуют|ничего не найдено|по вашему запросу ничего)", re.I)
OUT = re.compile(r"(нет в наличии|товар закончился|нет на складе|снят с производства|снято с производства|"
                 r"отсутствует на складе|временно отсутствует|распродан|sold out|out of stock)", re.I)
OUT_SCHEMA = {"OutOfStock", "SoldOut", "Discontinued"}
# любая надпись о наличии у товара: у страницы товара она одна, в разделе каталога - у каждой карточки своя
STATUS = re.compile(r"(в наличии|под заказ|предзаказ|ожидается|в пути|на складе|in stock)", re.I)
_BELOW = re.compile(r"(похожие товары|вы смотрели|с этим товаром|рекомендуем|аналоги|сопутствующие)", re.I)
PRODUCT_HINT = re.compile(r"(\d[\d\s]*(?:₽|руб)|в корзину|купить|заказать|артикул)", re.I)
SEARCH = re.compile(r"(search|poisk|/find|[?&](q|s|query|search)=)", re.I)


def run(ctx):
    pages = [p for p in ctx.indexable if p.get("blocks")]
    if not pages:
        return
    texts = {}
    for p in pages:
        blocks = unpack_blocks(p)
        if blocks is not None:
            texts[p["url"]] = blocks
    df = defaultdict(int)
    for bl in texts.values():
        for t in set(x.lower() for x in bl):
            df[t] += 1
    limit = max(TEMPLATE_MIN_PAGES, int(TEMPLATE_SHARE * len(texts)))
    empty, out = [], []
    for p in pages:
        own = [x for x in texts.get(p["url"], []) if df[x.lower()] < limit]
        avail = ((page_json(p, "schema_info") or {}).get("product") or {}).get("availability") or ""
        # «Нет в наличии» — короткая надпись-статус у товара, а не фраза внутри абзаца («если товара нет в наличии…»)
        hit_out = next((m.group(0) for x in own if len(x) <= 40 for m in [OUT.search(x)] if m), "")
        # Раздел каталога - не товар: «Снято с производства» у одной карточки из 35 - не про страницу (thehome.ru
        #: 289 из 305 строк - разделы, где у одной карточки такая надпись, а у остальных «В наличии»).
        # Три надписи о наличии и больше - это список товаров, по тексту страницу товаром не считаем. У самого товара
        # их одна-две (блоки для компьютера и телефона, «Нет в наличии» + «Ожидается»), у раздела - по одной на каждую
        # карточку. Считаем по всему тексту (не по own: «В наличии Много» стоит на тысячах страниц и в own не попадает)
        # и только до «Похожих товаров»: карусель с наличием чужих карточек - не про эту страницу (ревью)
        if hit_out:
            n = 0
            for x in texts.get(p["url"], []):
                if _BELOW.match(x.strip()):
                    break
                n += len(x) <= 40 and bool(OUT.search(x) or STATUS.search(x))
            if n >= 3:
                hit_out = ""
        is_product = bool(avail) or any(PRODUCT_HINT.search(x) for x in own)
        if avail in OUT_SCHEMA or (hit_out and is_product and avail != "InStock"):
            out.append([p["url"], p.get("title") or "", f"в разметке: {avail}" if avail in OUT_SCHEMA else f"в тексте: {quote(hit_out)}"])
            continue
        if SEARCH.search(p["url"]):
            continue
        for x in own:
            m = EMPTY.search(x)
            if m and len(x) < 200:  # короткая строка «Товаров не найдено», а не абзац текста, где эти слова встретились
                empty.append([p["url"], p.get("title") or "", x[:120]])
                break
    ctx.add("empty_category", WARN, "Магазин", "Пустые разделы каталога открыты для поиска",
            "На странице раздела написано, что товаров нет («Товаров не найдено», «В этом разделе пока нет товаров»). "
            "Для поиска это пустая страница: Яндекс считает такие малополезными, и они тянут вниз оценку всего сайта, "
            "а посетитель из поиска сразу уходит.",
            "Наполнить раздел товарами. Если товаров не будет, закрыть раздел от индексации (noindex) и убрать из меню и "
            "sitemap, или удалить (404/410) и поставить 301 на соседний раздел.",
            ["Адрес", "Title", "Что написано на странице"], empty)
    ctx.add("out_of_stock", NOTE, "Магазин", "Товары «нет в наличии» открыты для поиска",
            "Это не ошибка: страницу товара, который скоро снова появится, лучше оставить - она уже в поиске. Но если "
            "таких товаров много или они не вернутся (сняты с производства), посетитель из поиска попадает в тупик. "
            "Список нужен, чтобы решить по каждому товару.",
            "Временно нет - оставить страницу, показать срок поставки, похожие товары и «Сообщить о поступлении». "
            "Снят с производства навсегда - 301 на замену или на раздел. В разметке указать availability: OutOfStock.",
            ["Адрес", "Title", "Признак"], out)
