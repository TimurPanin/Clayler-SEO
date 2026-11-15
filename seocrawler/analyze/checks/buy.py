"""«Что мешает покупать»: что видно при чтении страниц магазина или услуги - цена-заглушка, цена в разы
ниже соседних товаров, «нет в наличии» с кнопкой «В корзину», расхождение с микроразметкой, старая цена ниже новой,
фото-заглушки, пустые характеристики, разные телефоны, битые ссылки на WhatsApp и Telegram, формы без согласия на
обработку персональных данных, устаревший год в «©», остатки шаблона, другой город, повторы в крошках.
Данные — pages.shop (seocrawler/shop.py). Ложных срабатываний должно быть мало: товар — только страница с
разметкой товара или с одной-тремя кнопками покупки и ценой после H1; спорное — замечанием."""
import datetime
import re
import statistics
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from ..common import CRIT, NOTE, WARN, page_json, unpack_blocks
from ...fmt import num as _n, quote
from ... import shop
from ...buy_clicks import problem as buy_problem
from ...regions import mentions

CAT = "Что мешает покупать"
NOT_AVAILABLE = {"нет в наличии", "отсутствует", "нет на складе", "временно отсутствует", "снят с производства",
                 "товар закончился", "распродан", "под заказ", "ожидается"}
CONTACTS_URL = re.compile(r"/(?:contacts?|kontakty?|kontakti|контакты)(?:[/.?]|$)", re.I)
LOCATIVE = re.compile(r"\bв\s+(?:г\.\s*)?([А-ЯЁ][а-яё]{2,}(?:[\s\-][А-ЯЁ][а-яё]+)?)")
NOT_CITY = {"наличии", "корзину", "корзине", "каталоге", "россии", "рф", "москве и области", "подарок", "кредит",
            "рассрочку", "интернет", "наличие", "день", "течение", "том", "этом", "нашем", "вашем"}


JUNK_CONTEXT = 80   # столько знаков текста вокруг остатка шаблона (столько же ищет копия страницы, window/highlight)
JUNK_LABEL = 30     # подпись рядом («Коллекция») - короткий блок прямо перед текстом


def _junk_where(page, found):
    """Где на странице виден остаток шаблона: «Chrome#Classic#Vanda II» (рядом: Коллекция), а не «#Classic#» три раза
    без места: на thehome.ru такой кусок на странице не находился глазами. Один кусок - один раз."""
    blocks = unpack_blocks(page) or []
    out = []
    for token in dict.fromkeys(found):
        k = next((i for i, b in enumerate(blocks) if token in b), None)
        if k is None:
            out.append(quote(token))
            continue
        text = blocks[k].strip()
        if len(text) > JUNK_CONTEXT:
            at = max(0, text.index(token) - (JUNK_CONTEXT - len(token)) // 2)
            text = text[at:at + JUNK_CONTEXT].strip()
        label = blocks[k - 1].strip().rstrip(":") if k and len(blocks[k - 1].strip()) <= JUNK_LABEL else ""
        out.append(quote(text) + (f" (рядом: {label})" if label else ""))
    return ", ".join(out)


def _price(v):
    return f"{_n(round(v)) if v == int(v) else str(v).replace('.', ',')} ₽"


def _sec(url):
    parts = urlsplit(url).path.strip("/").split("/")
    return "/".join(parts[:-1])


def _same(a, b, tol=1.0):
    return a is not None and b is not None and abs(a - b) <= tol


def _pct(v):
    return f"{_n(round(v)) if abs(v - round(v)) < 0.05 else str(round(v, 1)).replace('.', ',')}%"


def _discount_checks(add, products, name, facts):
    """Цена по клубной карте или по акции и «экономия»: экономия не равна
    разнице цен, цена по карте не ниже обычной, экономия 0 или меньше, скидка больше 90%, скидка товара сильно
    не такая, как у остальных товаров раздела, в разметке для поиска цена по карте вместо обычной.
    Старая цена ниже новой — buy_old_price, её не повторяем."""
    save_bad, higher, odd, schema, pcts = [], [], [], [], defaultdict(list)
    for u, f in products.items():
        d = f.get("disc") or {}
        if not d:
            continue
        price, club, old = f["price"], d.get("club"), f.get("old")
        save, pct, txt = d.get("save"), d.get("pct"), quote(d.get("txt", ""))
        if club is not None and club >= price:
            higher.append([u, name(u, f), _price(price), _price(club), txt])
        elif club is not None and old is not None and old < price and club >= old:  # по карте дороже зачёркнутой
            higher.append([u, name(u, f), f"{_price(price)}, зачёркнута {_price(old)}", _price(club), txt])
        if club is not None and _same(f.get("sprice"), club) and not _same(club, price):
            schema.append([u, name(u, f), _price(price), _price(club)])
        # с чем сравнивать экономию: обычная цена минус цена по карте, старая цена минус новая
        exp = []
        if club is not None and club < price:
            exp.append((price - club, (price - club) * 100 / price))
        if old is not None and old > price:
            exp.append((old - price, (old - price) * 100 / old))
        if save is not None and save <= 0 or pct is not None and pct <= 0:
            odd.append([u, name(u, f), _price(price), txt, "экономия или скидка 0 или меньше нуля"])
            continue
        if exp:
            real = exp[0][1]
            if real > 90:
                odd.append([u, name(u, f), _price(price), txt, f"скидка {_pct(real)} - больше 90%"])
                continue
            pcts[_sec(u)].append((real, u))
            if club is not None and club >= price:
                continue  # уже в «цена по карте не ниже обычной»
            if save is not None and not any(_same(save, e) for e, _ in exp):
                save_bad.append([u, name(u, f), txt, _price(save), " или ".join(_price(round(e)) for e, _ in exp)])
            elif pct is not None and save is None and not any(abs(pct - p) <= 1 for _, p in exp):
                save_bad.append([u, name(u, f), txt, _pct(pct), " или ".join(_pct(p) for _, p in exp)])
        elif save is not None and club is None and old is None and pct is None and save >= price:
            odd.append([u, name(u, f), _price(price), txt, "экономия больше самой цены"])
    add("buy_club_higher", WARN, CAT, "Цена по карте или по акции не ниже обычной, а написано «экономия»",
        "Рядом с обычной ценой стоит цена по клубной карте или по акции, и она такая же или выше обычной, хотя "
        "рядом обещана экономия. Покупатель видит, что «выгода» обманная, и перестаёт доверять ценам магазина; "
        "участник клуба переплачивает.",
        "Передайте разработчику: цена по карте считается от обычной цены, проверьте формулу и товары из списка "
        "(часто обычную цену поменяли, а цену по карте забыли).",
        ["Адрес", "Товар", "Обычная цена", "Цена по карте или акции", "Как написано"], higher)
    # карточки в разделах каталога и поиске: «Цена 15 064 Р. по карте клуба 15 325 Р.»
    cards = defaultdict(list)
    for u, f in facts.items():
        own = (f.get("disc") or {}).get("club")
        for v, c, t in f.get("club_bad") or []:
            if u in products and _same(c, own):
                continue  # цена этого товара - уже выше
            cards[(v, c)].append((u, t))  # одна карточка на разных страницах (раздел, бренд, поиск)
    add("buy_club_higher_list", WARN, CAT, "В карточках каталога цена по карте клуба выше обычной",
        "В списке товаров (раздел каталога, поиск, «похожие товары») у товара обычная цена ниже, чем цена по "
        "клубной карте. Участник клуба видит, что с картой дороже, а остальные - что клуб ничего не даёт; доверия к "
        "ценам и к клубу меньше.",
        "Передайте разработчику: в карточке списка выводится не та цена (часто старая или без наценки), а цена по "
        "карте считается от другой. Обе цены в карточке должны браться из тех же полей, что и на странице товара.",
        ["Карточка (как написано)", "Цена", "Цена по карте", "На скольких страницах", "Например"],
        [[us[0][1], _price(v), _price(c), len({u for u, _ in us}), us[0][0]]
         for (v, c), us in sorted(cards.items(), key=lambda kv: -len(kv[1]))],
        page_col=None)
    add("buy_club_save", WARN, CAT, "«Экономия» не равна разнице цен",
        "На странице написана экономия или скидка, но она не совпадает с разницей между обычной ценой и ценой по "
        "карте (или старой и новой ценой). Покупатель сам считает разницу, видит другое число и думает, что магазин "
        "ошибается или хитрит.",
        "Передайте разработчику: экономию нужно считать на сайте из тех же двух цен, что показаны рядом, а не "
        "хранить отдельным числом.",
        ["Адрес", "Товар", "Как написано", "Экономия на странице", "Должно быть"], save_bad)
    add("buy_discount_odd", WARN, CAT, "Скидка или экономия 0, меньше нуля или больше 90%",
        "У товара написана нулевая или отрицательная экономия либо скидка больше 90%. Почти всегда это ошибка в "
        "ценах: товар продают себе в убыток или показывают «экономию», которой нет.",
        "Сверьте обычную цену, цену по карте и старую цену этих товаров с 1С или МойСкладом; если скидки нет, "
        "не выводите надпись «экономия».",
        ["Адрес", "Товар", "Цена", "Как написано", "Что не так"], odd)
    out = []
    for sec, items in pcts.items():
        if len(items) < 5:
            continue
        common, n = Counter(round(p) for p, _ in items).most_common(1)[0]
        if n < len(items) * 0.6:
            continue
        for p, u in items:
            if abs(p - common) >= 10:
                out.append([u, name(u, products[u]), _pct(p), f"{_pct(common)} у {_n(n)} из {_n(len(items))}"])
    add("buy_discount_outlier", NOTE, CAT, "Скидка товара сильно отличается от скидки остальных товаров раздела",
        "У большинства товаров раздела одинаковая скидка (например, 5% по карте), а у этого заметно другая. "
        "Бывает так задумано, но чаще это опечатка в цене: магазин теряет деньги или покупатель не видит обещанной "
        "скидки.",
        "Проверьте цены этих товаров. Если скидка особая, напишите об этом рядом с ценой («Специальная цена»).",
        ["Адрес", "Товар", "Скидка у товара", "Обычно в разделе"], out)
    add("buy_schema_club", WARN, CAT, "В разметке для поиска стоит цена по карте, а не обычная",
        "В микроразметке (её Яндекс и Google показывают в сниппете и товарной выдаче) указана цена по клубной карте "
        "или по акции, а не та, что доступна всем. Человек приходит из поиска на одну цену, а без карты платит "
        "больше; поисковик за такое расхождение может убрать цену из сниппета.",
        "Передайте разработчику: в offers.price - обычная цена, цену по карте можно указать отдельно "
        "(priceSpecification с пометкой, что она для участников клуба) или не указывать.",
        ["Адрес", "Товар", "Обычная цена", "Цена в разметке (по карте)"], schema)


def consent(ctx):
    """Согласие на персональные данные в формах и виджетах, открытых в браузере (seocrawler/consent_forms.py)."""
    res = ctx.store.get_meta("consent_forms", None) or {}
    forms = res.get("forms") or []
    op = res.get("operator") or {}
    if not forms and not op.get("docs"):
        return
    add = ctx.add
    req = lambda d: ", ".join([f"ИНН {x}" for x in d.get("inn") or []] + [f"ОГРН {x}" for x in d.get("ogrn") or []]) or "не указаны"
    docs = op.get("docs") or []
    add("buy_policy_company", WARN, CAT, "В политике конфиденциальности реквизиты другой компании",
        "ИНН или ОГРН в политике обработки персональных данных не совпадает с реквизитами на сайте (в подвале или на "
        "странице контактов). Обычно политику скопировали с другого сайта или компания сменилась, а документ нет. "
        "Тогда по документу данные посетителей обрабатывает чужая компания, и такое согласие легко оспорить.",
        "Обновите политику: в ней должны быть название, ИНН и ОГРН той компании, которая принимает заявки с сайта, "
        "те же, что в подвале и на странице контактов.",
        ["Документ", "Реквизиты в документе", "Реквизиты на сайте"],
        [[d["url"], req(d), req(op.get("site") or {})] for d in docs if d.get("problem") == "other"], page_col=None)
    add("buy_policy_noop", NOTE, CAT, "В политике конфиденциальности не указано, какая компания обрабатывает данные",
        "В тексте политики обработки персональных данных нет названия компании, ИНН и ОГРН. Из документа непонятно, "
        "кто оператор персональных данных, то есть кому посетитель отдаёт свой телефон и почту.",
        "Впишите в начало политики полное название компании (или ИП), ИНН, ОГРН и адрес - те же, что в "
        "реквизитах сайта.",
        ["Документ"], [[d["url"]] for d in docs if d.get("problem") == "none"], page_col=None)
    label = lambda f: quote(f["btn"]) if f.get("btn") else f"с полями: {f.get('fields') or 'контакты'}"
    links = {}
    for f in forms:
        for lk in f.get("links") or []:
            if lk.get("problems"):
                k = (lk.get("text") or "", lk.get("raw") or "")
                r = links.setdefault(k, {"why": lk["problems"], "forms": [], "pages": set()})
                r["forms"].append(f"{label(f)} ({f['where']})")
                r["pages"].update(f.get("pages") or [f["url"]])
    add("buy_consent_link", WARN, CAT, "Ссылки на политику и согласие в формах не открывают документ",
        "В строке согласия под формой или в виджете чата есть ссылки на политику обработки персональных данных и "
        "на текст согласия, но по ним не открывается документ: в адресе лишние символы («», кавычки, пробелы), "
        "адрес ведёт на ошибку 404, на главную или на другой сайт. Человек не может прочитать, на что соглашается. "
        "По закону 152-ФЗ (статья 18.1) политика должна быть опубликована и доступна, а согласие без доступного "
        "текста легко оспорить; за это штрафуют.",
        "Передайте разработчику: в настройках формы или виджета чата (там, где задан текст согласия) поставить полные "
        "адреса документов вида https://сайт/privacy-policy/ - без кавычек, пробелов и лишних символов. После правки "
        "открыть форму на сайте и нажать на каждую ссылку.",
        ["Ссылка", "Адрес в коде", "Что не так", "Форма", "На скольких страницах", "Например"],
        [[t or "без текста", raw or "пусто", "; ".join(r["why"]), ", ".join(dict.fromkeys(r["forms"])),
          len(r["pages"]), sorted(r["pages"])[0]] for (t, raw), r in sorted(links.items(), key=lambda kv: -len(kv[1]["pages"]))],
        page_col=None)
    add("buy_consent_form", WARN, CAT, "Согласие в формах и виджетах оформлено с ошибкой",
        "Форма или виджет (чат, «перезвоним», всплывающее окно) просит телефон или почту, но согласие на обработку "
        "персональных данных оформлено неправильно: его нет совсем, галочка уже стоит заранее или в строке согласия "
        "нет ссылки на документ. По закону 152-ФЗ согласие должно быть конкретным, осознанным и однозначным: "
        "заранее поставленная галочка за такое не считается, а форма без согласия - нарушение, за которое штрафуют.",
        "Передайте разработчику: в каждой форме и в настройках виджета чата - строка «Я даю согласие на обработку "
        "персональных данных» со ссылкой на текст согласия и на политику, галочка по умолчанию не отмечена.",
        ["Адрес", "Форма", "Где", "Что не так"],
        [[f["url"], label(f), f["where"], "; ".join(f["problems"])] for f in forms if f.get("problems")])
    add("buy_consent_nobox", NOTE, CAT, "В формах согласие дают нажатием кнопки, без галочки",
        "Под формой написано «Нажимая кнопку, вы соглашаетесь…», отдельной галочки нет. Закон галочку прямо не "
        "требует, но доказать, что человек согласился осознанно, проще, когда он сам ставит отдельную галочку.",
        "Если сайт собирает заявки от частных лиц, добавьте в формы галочку согласия, которая по умолчанию не стоит, и "
        "не давайте отправить форму без неё.",
        ["Адрес", "Форма", "Где", "Строка согласия"],
        [[f["url"], label(f), f["where"], f.get("consent") or ""] for f in forms if f.get("nobox")])


class _Shop:
    """Что нужно всем проверкам магазина: разобранные страницы и товары среди них."""

    def __init__(self, ctx, facts):
        self.ctx, self.add, self.facts = ctx, ctx.add, facts
        self.info = {p["url"]: p for p in ctx.pages}
        self.ok = {p["url"] for p in ctx.indexable}
        self.products = {u: f for u, f in facts.items() if u in self.ok and shop.is_product(f)}
        # цена-заглушка: такие товары в сравнении цен не участвуют
        self.zero = {u for u, f in self.products.items()
                     if f["price"] < 2 or (f.get("sprice") is not None and f["sprice"] < 2)}

    def name(self, url, facts):
        return facts.get("h1") or self.info.get(url, {}).get("title") or ""


def _check_zero_price(s):
    """Цена 0 ₽ или 1 ₽ - заглушка вместо цены (адреса таких товаров - s.zero)."""
    zero = [[u, s.name(u, f), _price(f["price"]), f.get("status", "")] for u, f in s.products.items() if u in s.zero]
    s.add("buy_price_zero", CRIT, CAT, "Цена-заглушка: товар стоит 0 ₽ или 1 ₽",
          "На странице товара цена 0 или 1 рубль. Так магазин ставит цену, когда её не знает, но посетитель видит "
          "«1 ₽», кладёт в корзину и потом узнаёт настоящую цену по телефону - обычно после этого уходит. Яндекс "
          "и Google "
          "тоже берут эту цену в сниппет и в товарную выдачу.",
          "Поставьте настоящую цену. Если цены нет, вместо нуля напишите «Цена по запросу» и замените кнопку «В "
          "корзину» "
          "на «Узнать цену», а в разметке не указывайте price.",
          ["Адрес", "Товар", "Цена на странице", "Наличие"], zero)


def _check_low_price(s):
    by_sec = defaultdict(list)
    for u, f in s.products.items():
        if u not in s.zero:
            by_sec[_sec(u)].append((f["price"], u))
    low = []
    for sec, items in by_sec.items():
        if len(items) < 8:
            continue
        prices = sorted(p for p, _ in items)
        q1 = prices[len(prices) // 4]
        med = statistics.median(prices)
        for p, u in items:
            if p * 10 <= q1:
                low.append([u, s.name(u, s.products[u]), _price(p), _price(med)])
    s.add("buy_price_low", WARN, CAT, "Цена товара в разы ниже похожих товаров раздела",
          "Цена этого товара в 10 и больше раз ниже, чем у большинства товаров того же раздела. Бывает ошибка при "
          "выгрузке (цена за штуку вместо упаковки, потерян ноль), а бывает и так задумано (мелкая деталь среди "
          "крупных). Если это ошибка, магазин продаёт себе в убыток или отказывает покупателю после заказа.",
          "Сверьте цены из списка с 1С или МойСкладом. Если всё верно, ничего делать не нужно.",
          ["Адрес", "Товар", "Цена", "Обычно в разделе"], low)


def _check_stock_conflict(s):
    conflict = [[u, s.name(u, f), quote(f["status"]), _price(f["price"])] for u, f in s.products.items()
                if f.get("status") in NOT_AVAILABLE and f.get("buy")]
    hard = any(r[2] != quote("под заказ") for r in conflict)
    s.add("buy_stock_conflict", WARN if hard else NOTE, CAT,
          "Товара нет в наличии или он под заказ, а цена и кнопка «В корзину» как у обычного",
          "На странице написано «Нет в наличии» или «Под заказ», но рядом обычная цена и кнопка покупки. Посетитель "
          "оформляет заказ и только потом узнаёт, что товара нет или ждать неделю, - это отказ и недовольный "
          "покупатель. Для товаров «нет в наличии» поисковик тоже видит противоречие.",
          "Нет в наличии: замените кнопку на «Сообщить о поступлении» и покажите похожие товары. Под заказ: "
          "напишите рядом с кнопкой срок поставки («Привезём за 5-7 дней») и честную цену.",
          ["Адрес", "Товар", "Надпись о наличии", "Цена"], conflict)


def _check_schema_price(s):
    diff = [[u, s.name(u, f), _price(f["price"]), _price(f["sprice"])] for u, f in s.products.items()
            if f.get("sprice") is not None and not f.get("slow") and u not in s.zero
            and abs(f["price"] - f["sprice"]) > max(1, 0.01 * f["price"])
            and not _same((f.get("disc") or {}).get("club"), f["sprice"])]  # цена по карте в разметке — ниже
    s.add("buy_schema_price", WARN, CAT, "Цена на странице не совпадает с ценой в микроразметке",
          "В тексте страницы одна цена, а в микроразметке (её видят Яндекс и Google и показывают в сниппете и товарной "
          "выдаче) другая. Покупатель приходит из поиска на одну цену и видит другую, а поисковик за такое расхождение "
          "может убрать цену из сниппета и товар из товарной выдачи.",
          "Передайте разработчику: цена в разметке (offers.price) должна выводиться из того же поля, что и цена на "
          "странице, с учётом скидки.",
          ["Адрес", "Товар", "Цена на странице", "Цена в разметке"], diff)


def _check_old_price(s):
    old = [[u, s.name(u, f), _price(f["old"]), _price(f["price"])] for u, f in s.products.items()
           if f.get("old") is not None and f["old"] < f["price"]]
    s.add("buy_old_price", WARN, CAT, "Зачёркнутая «старая» цена ниже новой",
          "Старая цена должна быть выше: так видно скидку. Здесь зачёркнута меньшая цена, и выглядит это как "
          "подорожание или ошибка - доверия к ценам магазина меньше.",
          "Проверьте цены и скидки у этих товаров: обычно старую цену забыли убрать после изменения цены.",
          ["Адрес", "Товар", "Старая цена", "Новая цена"], old)


def _check_no_photo(s):
    ph = [[u, s.name(u, f), f.get("ph_src", "")] for u, f in s.products.items() if f.get("ph_img")]
    s.add("buy_no_photo", WARN, CAT, "Товары без фото: вместо фото заглушка",
          "На странице товара вместо фотографии картинка-заглушка («нет фото»). Без фото товар покупают заметно реже, "
          "а Яндекс и Google не берут такие товары в товарную выдачу и в поиск по картинкам.",
          "Добавьте фотографии товаров, начиная с тех, что чаще смотрят и покупают. Можно взять у поставщика или "
          "производителя.",
          ["Адрес", "Товар", "Картинка-заглушка"], ph)


def _check_spec_empty(s):
    spec = [[u, s.name(u, f), f["spec_empty"]] for u, f in s.products.items() if f.get("spec_empty")]
    s.add("buy_spec_empty", WARN, CAT, "Пустые характеристики или описание товара",
          "У товара пустой блок характеристик или написано «Характеристики не указаны», «Описание отсутствует». "
          "Покупатель не может сравнить и сомневается, а для поиска это страница почти без текста.",
          "Заполните характеристики (размеры, мощность, совместимость, производитель) - их можно взять у поставщика. "
          "Если характеристик нет, уберите пустую вкладку.",
          ["Адрес", "Товар", "Что на странице"], spec)


def _check_phones(s):
    head = Counter(tuple(f.get("hphones") or ()) for f in s.facts.values() if f.get("hphones"))
    foot = Counter(tuple(f.get("fphones") or ()) for f in s.facts.values() if f.get("fphones"))
    rows = []
    if head and foot:
        h, nh = head.most_common(1)[0]
        f_, nf = foot.most_common(1)[0]
        ex_h = next(u for u, f in s.facts.items() if tuple(f.get("hphones") or ()) == h)
        ex_f = next(u for u, f in s.facts.items() if tuple(f.get("fphones") or ()) == f_)
        if not set(h) & set(f_):
            rows += [["Шапка сайта", ", ".join(h), ex_h], ["Подвал сайта", ", ".join(f_), ex_f]]
        cont = [(u, p) for u, p in s.info.items() if CONTACTS_URL.search(urlsplit(u).path) and p.get("contacts")]
        for u, p in cont[:1]:
            cp = set((page_json(p, "contacts") or {}).get("phones") or [])
            if cp and not cp & (set(h) | set(f_)):
                if not rows:
                    rows.append(["Шапка сайта", ", ".join(h), ex_h])
                rows.append(["Страница «Контакты»", ", ".join(sorted(cp)), u])
    s.add("buy_phones_differ", WARN, CAT, "В шапке, подвале и на странице «Контакты» разные телефоны",
          "Посетитель видит один номер в шапке и другой в подвале или в «Контактах» и не понимает, куда звонить. Часто "
          "это старый номер, который забыли поменять в одном месте, и по нему уже никто не отвечает.",
          "Оставьте один актуальный номер (или подпишите, какой для чего: «отдел продаж», «сервис») во всех местах "
          "сайта и в Яндекс Бизнесе, 2ГИС и Google Картах.",
          ["Где", "Телефоны", "Например, на странице"], rows, page_col=None)


def _check_messengers(s):
    msg = defaultdict(list)
    for u, f in s.facts.items():
        for href, who, why in f.get("msg") or []:
            msg[(href, who, why)].append(u)
    s.add("buy_messenger", CRIT, CAT, "Ссылки на WhatsApp или Telegram никуда не ведут",
          "Кнопка мессенджера на сайте открывает пустой чат, ошибку или чужой аккаунт: в ссылке нет номера, номер "
          "неполный или вместо имени аккаунта заглушка. Человек хотел написать, а написать некуда - и уходит "
          "к конкуренту.",
          "Поставьте правильные ссылки: WhatsApp - https://wa.me/79991234567 (номер целиком, без +, пробелов и "
          "скобок), "
          "Telegram - https://t.me/имя_аккаунта. Проверьте с телефона, что открывается нужный чат.",
          ["Ссылка", "Мессенджер", "Что не так", "На скольких страницах", "Например"],
          [[h, w, why, len(us), us[0]] for (h, w, why), us in sorted(msg.items(), key=lambda kv: -len(kv[1]))],
          page_col=None)


def _check_forms_no_consent(s):
    forms = defaultdict(list)
    for u, f in s.facts.items():
        for fm in f.get("forms") or []:
            if not fm.get("consent"):
                fields = ", ".join(n for k, n in (("name", "имя"), ("phone", "телефон"), ("email", "почта"),
                                                    ("text", "сообщение")) if fm.get(k))
                forms[(fm.get("btn") or "без надписи на кнопке", fields)].append(u)
    # найдено по коду страницы, без браузера: согласие может появляться скриптом или во всплывающем окне. Поэтому
    # «проверьте вручную» и без юридического вывода (разбор отчёта rsmarket24.ru: одна форма на 3 486 страницах)
    s.add("buy_no_consent", NOTE, CAT, "Формы без согласия на обработку персональных данных: проверьте вручную",
          "Форма просит телефон или почту, а в коде страницы рядом с ней не нашлось строки согласия на обработку "
          "персональных данных и ссылки на политику. Иногда согласие появляется позже, скриптом или во всплывающем "
          "окне, поэтому это повод проверить, а не вывод. Если согласия правда нет, это стоит исправить: осторожные "
          "посетители не оставляют контакты в формах без политики, а оформление согласия лучше уточнить у юриста "
          "(закон 152-ФЗ).",
          "Откройте форму на одной из страниц списка. Если согласия нет, добавьте под форму текст «Нажимая кнопку, вы "
          "соглашаетесь на обработку персональных данных» со ссылкой на политику (или галочку согласия) и опубликуйте "
          "саму политику на сайте.",
          ["Форма (надпись на кнопке)", "Что спрашивает", "На скольких страницах", "Например"],
          [[b, fl, len(us), us[0]] for (b, fl), us in sorted(forms.items(), key=lambda kv: -len(kv[1]))],
          page_col=None)


def _check_copyright(s):
    year = datetime.date.today().year
    years = Counter(f["copy"] for f in s.facts.values() if f.get("copy"))
    if years:
        y, n = years.most_common(1)[0]
        if y < year and n >= len(s.facts) * 0.5:
            ex = next(u for u, f in s.facts.items() if f.get("copy") == y)
            s.add("buy_copyright", NOTE, CAT, f"В подвале сайта устаревший год: «© {y}»",
                f"Сейчас {year} год, а в подвале написано © {y}. Посетитель считает, что сайт заброшен и не "
                f"обновлялся, "
                "и сомневается, работает ли магазин и актуальны ли цены.",
                "Передайте разработчику: выводить в подвале текущий год автоматически («© 2015-текущий год»).",
                ["Год в «©»", "На скольких страницах", "Например"], [[f"© {y}", n, ex]], page_col=None)


def _check_junk(s):
    junk = [[u, s.name(u, f), _junk_where(s.info[u], f["junk"])] for u, f in s.facts.items()
            if u in s.ok and f.get("junk")]
    s.add("buy_junk", WARN, CAT, "На странице видны остатки шаблона: {price}, Lorem ipsum, «tests»",
          "На странице виден служебный текст, который должен был замениться настоящим: {price}, #PRICE#, Lorem ipsum, "
          "undefined, «Тестовый товар», или значения, склеенные служебным знаком (Chrome#Classic#Vanda). Посетитель "
          "видит "
          "недоделанный сайт и не доверяет ему.",
          "Передайте разработчику: найти в шаблоне или в карточке товара этот текст и заменить на настоящий, тестовые "
          "товары и страницы удалить.",
          ["Адрес", "Страница", "Что видно"], junk)


def _check_city(s):
    cities = Counter(f["city"] for f in s.facts.values() if f.get("city"))
    city_rows = []
    if cities:
        city, n = cities.most_common(1)[0]
        if n >= len(s.facts) * 0.5:
            for u, f in s.facts.items():
                if u not in s.ok:
                    continue
                text = " ".join((f.get("h1") or "", s.info.get(u, {}).get("title") or ""))
                for m in LOCATIVE.finditer(text):
                    other = m.group(1)
                    if other.lower() in NOT_CITY or mentions(other, city) or mentions(text, city):
                        continue
                    city_rows.append([u, city, f"«в {other}»", text[:120]])
                    break
    s.add("buy_city", NOTE, CAT, "В шапке выбран один город, а в заголовках страниц написан другой",
          "Сайт показывает посетителю «Ваш город: …», а в заголовке страницы и в title стоит другой город. Человек из "
          "своего города сомневается, доставят ли ему и по какой цене.",
          "Если город выбирается автоматически, подставляйте его и в заголовки. Если сайт работает в одном городе, "
          "уберите выбор города или поставьте ваш город по умолчанию.",
          ["Адрес", "Город в шапке", "Город в заголовке", "Заголовок"], city_rows)


def _check_crumbs(s):
    crumbs = []
    for u, f in s.facts.items():
        items = [" ".join(x.lower().split()) for x in f.get("crumbs") or []]
        dup = [x for x, c in Counter(items).items() if c > 1]
        if dup and u in s.ok:
            crumbs.append([u, " → ".join(f["crumbs"])])
    s.add("buy_crumbs_repeat", NOTE, CAT, "В хлебных крошках один и тот же пункт повторяется",
          "В строке «Главная → Каталог → …» над заголовком один раздел написан два раза подряд. Выглядит как ошибка, "
          "посетитель путается, где находится, а поисковик показывает эти крошки в сниппете.",
          "Передайте разработчику: в крошках каждый раздел должен быть один раз. Обычно раздел попадает туда дважды "
          "из-за привязки товара сразу к разделу и его подразделу с тем же названием.",
          ["Адрес", "Крошки"], crumbs)


def _check_buttons(s):
    clicks = (s.ctx.store.get_meta("buy_clicks", None) or {}).get("items") or []
    s.add("buy_click", WARN, CAT,
          "Кнопки «Купить в один клик», «В корзину», «Заказать звонок» работают не так, как ждёт покупатель",
          "Эти кнопки нажали в браузере, как покупатель (формы не отправлялись). Кнопка ничего не делает, открывает "
          "общую форму «перезвоним» без названия товара или спрашивает город, который уже выбран в шапке. Покупатель "
          "не понимает, что именно он заказывает и сработала ли кнопка, и часто уходит. Снимки - в разделе «Кнопки "
          "покупки и заявки на снимках».",
          "Передайте разработчику список: кнопка «В корзину» должна сразу показывать, что товар добавлен; форма "
          "«Купить "
          "в один клик» - название, фото и цену товара; уже выбранный город в форму подставлять, а не спрашивать "
          "снова.",
          ["Адрес", "Кнопка", "Что произошло", "Что не так"],
          [[c["url"], c["button"], c["what"], c["problem"]] for c in clicks if buy_problem(c)])


def run(ctx):
    facts = {}
    for p in ctx.pages:
        shop_facts = page_json(p, "shop")
        if shop_facts is not None:
            facts[p["url"]] = shop_facts
    ctx.shop_pages = len(facts)
    consent(ctx)
    if not facts:
        return
    s = _Shop(ctx, facts)
    _check_zero_price(s)
    _check_low_price(s)
    _check_stock_conflict(s)
    _check_schema_price(s)
    _check_old_price(s)
    _discount_checks(s.add, s.products, s.name, {u: f for u, f in s.facts.items() if u in s.ok})
    _check_no_photo(s)
    _check_spec_empty(s)
    _check_phones(s)
    _check_messengers(s)
    _check_forms_no_consent(s)
    _check_copyright(s)
    _check_junk(s)
    _check_city(s)
    _check_crumbs(s)
    _check_buttons(s)
