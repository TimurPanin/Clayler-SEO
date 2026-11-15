"""Коммерческие факторы Яндекса: есть ли на сайте то, по чему посетитель (и Яндекс) понимает, что здесь можно
спокойно купить или заказать: цены, телефон, кнопка заказа, доставка, оплата, гарантия, отзывы, реквизиты,
режим работы, мессенджеры. Считается по тексту страниц и ссылкам. Некоммерческие сайты
(нет ни цен, ни кнопок заказа) не проверяются. С 23.10.2026 в таблице - что именно нашлось (кусок текста или
ссылка): по нему видно, то ли это, и копия страницы из отчёта обводит именно его."""
import re

from ... import calltrack
from ..common import NOTE, page_json, unpack_blocks

PRICE = re.compile(r"\d[\d\s ]*\s?(₽|руб\b|руб\.|р\.)", re.I)
ORDER = re.compile(r"в корзину|купить|заказать|оформить заказ|оставить заявку|записаться|получить консультацию|"
                   r"рассчитать стоимость|узнать цену", re.I)
MAIL = re.compile(r"[\w.-]+@[\w-]+\.[a-zа-я]{2,}", re.I)
SCHEMA_SHOP = re.compile(r"\b(?:Product|Offer|AggregateOffer)\b")
# Цена, кнопка или раздел отзывов на сайте - короткая строка (ценник «1 990 ₽», кнопка «Купить», заголовок «Отзывы»).
# Те же слова внутри длинного абзаца - рассказ, а не элемент сайта: «часть товаров передавалась с ценой 1 ₽»,
# «действия «В корзину» и «Купить» в кейсе портфолио (timurpanin.ru) - сайт по ним не продаёт.
# Считаются только слова из букв: в строке прайса «смартфоны - 250 / 373 / 496 руб. за единицу» цифры не в счёт.
SHORT = {"Цены": 6, "Кнопка": 6, "Отзывы": 6}
_LETTERS = re.compile(r"[^\W\d_]{2,}")

# (фактор, где искать: text / link, регулярное выражение, зачем)
FACTORS = [
    ("Страница о доставке", "link", r"доставк|/dostavk|/delivery", "Покупатель ищет, как и за сколько получит товар; Яндекс проверяет, есть ли такая информация."),
    ("Способы оплаты", "link|text", r"способ\w* оплаты|оплата картой|оплата при получении|безналичн|/oplat", "Оплата картой, по счёту, при получении - снимает сомнения перед покупкой."),
    ("Гарантия и возврат", "link", r"гаранти|возврат|/garant|/vozvrat", "Условия гарантии и возврата - сильный сигнал доверия для покупателя и Яндекса."),
    ("Отзывы", "link|text", r"отзыв", "Отзывы покупателей на сайте повышают доверие и конверсию."),
    ("Реквизиты компании (ИНН, ОГРН)", "text", r"\bинн\b|\bогрн", "Реквизиты показывают, что за сайтом стоит настоящая компания."),
    # «понедельник» в тексте статьи - не режим работы (hightime.agency): нужен диапазон дней («пн-пт»,
    # «вт–вс», «с понедельника по пятницу»), «ежедневно 10-22», «круглосуточно», «24/7», «без выходных» или сами слова
    # «режим / часы / график работы»
    ("Режим работы", "text", r"режим работы|часы работы|график работы|без выходных|круглосуточн|\b24\s*/\s*7\b|"
                             r"\b(?:пн|вт|ср|чт|пт|сб|вс)\.?\s*[-–—]\s*(?:пн|вт|ср|чт|пт|сб|вс)\b|"
                             r"\bс понедельника по\b|понедельник\w*\s*[-–—]\s*(?:пятниц|суббот|воскресен)|"
                             r"ежедневно[\s:,]*(?:с\s*)?\d",
     "Когда можно позвонить или приехать."),
    ("Электронная почта", "mail", r"", "Второй способ связи помимо телефона."),
    ("Мессенджеры и соцсети", "linkdst", r"t\.me/|wa\.me/|whatsapp|viber|vk\.com/|max\.ru/", "Многие пишут в мессенджер, а не звонят."),
    ("Страница «О компании»", "link", r"\bо компании\b|\bо нас\b|/about|/o-kompanii|/o-nas", "Кто продаёт: история, фото, сотрудники. Это повышает доверие."),
]


def _snippet(text, m):
    """Кусок строки текста вокруг найденного - так, как он стоит на странице (копия страницы ищет по нему)."""
    # найденное может захватить перевод строки («2 500\n1 990 ₽»): берём строку, где оно кончается, - один блок
    end = m.end()
    start = max(m.start(), text.rfind("\n", 0, end) + 1)
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", end)
    line = text[a:b if b >= 0 else len(text)]
    i, j = start - a, end - a
    lo = line.rfind(" ", 0, i - 30) + 1 if i > 30 else 0
    return line[lo:max(lo + 80, j + 10)].strip()


class _Short:
    """Ищет rx только в строках текста не длиннее words слов (см. SHORT); search() - как у регулярного выражения."""
    def __init__(self, rx, words):
        self.rx, self.words = rx, words

    def search(self, text):
        for m in self.rx.finditer(text):
            a = text.rfind("\n", 0, m.start()) + 1
            b = text.find("\n", m.end())
            if len(_LETTERS.findall(text[a:b if b >= 0 else len(text)])) <= self.words:
                return m
        return None


def run(ctx):
    add, db, indexable = ctx.add, ctx.db, ctx.indexable
    texts = {}
    for p in indexable:
        blocks = unpack_blocks(p)
        if blocks is not None:
            texts[p["url"]] = "\n".join(blocks)
    if not texts:
        return  # старая проверка — текста по блокам нет
    price, order = _Short(PRICE, SHORT["Цены"]), _Short(ORDER, SHORT["Кнопка"])
    price_pages = [u for u, t in texts.items() if price.search(t)]
    order_pages = [u for u, t in texts.items() if order.search(t)]
    links = db.execute("SELECT dst, anchor, MIN(src) FROM links WHERE kind='a' GROUP BY dst, anchor").fetchall()
    order_link = next((s for d, a, s in links if a and order.search(a)), None)
    schema = any(SCHEMA_SHOP.search(p.get("schema_types") or "") for p in indexable)
    # сайт не продаёт - коммерческие факторы не про него. Цена на одной странице - ещё не продажа: это может быть
    # заголовок статьи («Цена 1 ₽ передавалась как цена товара» в кейсе портфолио). Нужна кнопка или ссылка заказа,
    # разметка товара (Product, Offer) или цены хотя бы на двух страницах.
    if not order_pages and not order_link and not schema and len(price_pages) < 2:
        return

    def seen(rx, u):   # что именно нашлось на странице u
        m = rx.search(texts.get(u, "")) if u else None
        return _snippet(texts[u], m) if m else ""

    n = len(texts)
    has_contacts = any(p.get("contacts") for p in indexable)  # проверки до 29.09 телефоны не собирали
    phones = 0
    for p in indexable:
        ct = calltrack.load(p) or {}   # номер подменяет коллтрекинг - телефон всё равно есть (в HTML от сервера)
        if (page_json(p, "contacts") or {}).get("phones") or ct.get("raw") or ct.get("js"):
            phones += 1
    rows = [
        ["Цены", f"на {len(price_pages)} из {n} стр." if price_pages else "не найдено",
         seen(price, price_pages[0] if price_pages else ""), price_pages[0] if price_pages else "",
         "Страницы товаров и услуг без цены Яндекс считает менее полезными: посетитель уходит к тем, у кого цена есть."],
        ["Кнопка заказа («купить», «заказать», «оставить заявку»)",
         f"на {len(order_pages)} из {n} стр." if order_pages else ("есть (ссылка)" if order_link else "не найдено"),
         seen(order, order_pages[0] if order_pages else ""),
         (order_pages or [order_link or ""])[0], "Когда понятно, как купить, меньше людей уходит."],
        ["Телефон на всех страницах (шапка или подвал)",
         (f"на {phones} из {len(indexable)} стр." if phones else "не найдено") if has_contacts else "нет данных",
         "", "", "Телефон должен быть виден сразу, на любой странице."],
    ]
    missing = [r[0] for r in rows if r[1] == "не найдено" or (r[0].startswith("Телефон") and has_contacts
                                                               and phones < 0.5 * len(indexable))]
    for name, where, rx, why in FACTORS:
        found, what = "", ""   # на какой странице и что именно (кусок текста или адрес ссылки)
        r = re.compile(rx, re.I) if rx else None
        if name in SHORT:   # «Отзывы» - раздел или заголовок, а не слово «отзывов» в статье
            r = _Short(r, SHORT[name])
        if "text" in where:
            found = next((u for u, t in texts.items() if r.search(t)), "")
            what = seen(r, found)
        how = ""
        if not found and where.startswith("link"):
            # ссылка-пункт меню («Доставка», «Оплата и доставка»), а не слово в длинном тексте ссылки из статьи
            hit = next(((d, s, a) for d, a, s in links
                        if (a and r.search(a) and len(a.split()) <= 4) or r.search(d or "")), None)
            if hit:
                what, found = hit[0], hit[1]   # адрес ссылки: по нему копия страницы обведёт саму ссылку
                how = f" (ссылка «{hit[2]}»)" if hit[2] else ""
        if where == "linkdst":
            hit = next(((d, s) for d, a, s in links if d and r.search(d)), None)
            if hit:
                what, found = hit
        if where == "mail":
            hit = next(((d, s) for d, a, s in links if (d or "").lower().startswith("mailto:")), None)
            if hit:
                what, found = hit
            else:
                found = next((u for u, t in texts.items() if MAIL.search(t)), "")
                what = seen(MAIL, found)
        rows.append([name, ("есть" + how) if found else "не найдено", what or "", found, why])
        if not found:
            missing.append(name)
    if not missing:
        return
    add("commercial", NOTE, "Коммерческие факторы",
        f"Коммерческие факторы: не хватает {len(missing)} из {len(rows)}",
        "Яндекс ранжирует коммерческие сайты с учётом того, насколько удобно и безопасно на них покупать: цены, "
        "телефон, доставка, оплата, гарантии, реквизиты, отзывы. Ниже - что программа нашла на сайте и чего нет. "
        "В колонке «Что нашлось» - сам кусок текста или ссылка: по нему видно, то ли это (слово «доставка» в статье - "
        "ещё не страница о доставке). Если что-то есть, но в картинке или подгружается скриптом, программа это не увидит.",
        "Добавьте недостающее: отдельные страницы «Доставка», «Оплата», «Гарантия и возврат», «Отзывы», реквизиты "
        "и режим работы - в подвал сайта, цены - на страницы товаров и услуг. Для услуг без доставки страница "
        "«Доставка» не нужна - такую строку пропустите. Сравните с конкурентами из выдачи.",
        # «Например, здесь» - где нашлось, а не страница с проблемой: в здоровье и шаблонах она не в счёт (page_col None),
        # но в отчёте по клику на неё открывается копия с обведённым найденным (show_col)
        ["Фактор", "На сайте", "Что нашлось", "Например, здесь", "Зачем"], rows, page_col=None, show_col=3)
