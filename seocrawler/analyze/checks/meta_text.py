"""Заготовки для готовых заголовков (meta_suggest): чистка текста, сокращение, город и бренд, предложение для
описания, товар и цена. Состояния здесь нет, только функции."""
import html
import random
import re
from collections import Counter

from ..common import page_json, unpack_blocks

PAGE_N = re.compile(r"(?:[?&](?:PAGEN_\d+|page|p|pg|str)=|/page[/-]?)(\d+)", re.I)
GENERIC_ANCHOR = re.compile(r"^(подробнее|далее|читать( далее| полностью)?|перейти|смотреть( все)?|все|ещё|еще|купить|"
                            r"в корзину|заказать|каталог|главная|назад|вперёд|вперед|\d+|>|<|»|«|→|←|…|\.\.\.|"
                            r"узнать больше|показать( все| ещё)?|см\.? также|тут|здесь|ссылка|по ссылке)$", re.I)
INFO = re.compile(r"/(blog|news|novost\w*|stat\w*|articles?|info|journal|zhurnal|poleznoe|sovety|faq|voprosy|"
                  r"wiki|spravka|press|events?|meropriyat\w*)(/|$)", re.I)
SERVICE = re.compile(r"/(kontakt\w*|contacts?|o-kompanii|o_kompanii|about|o-nas|company|dostavka|delivery|oplata|"
                     r"payment|garanti\w*|vozvrat|rekvizit\w*|vakansi\w*|vacanc\w*|career|otzyv\w*|reviews?|"
                     r"politik\w*|privacy|policy|soglas\w*|oferta|partners?|sertifikat\w*)(/|$)", re.I)
BUY = re.compile(r"купит|цен[аыу]|стоимост|заказ|₽|руб", re.I)
JUNK_LINE = re.compile(r"cookie|куки|\+7|8\s?\(\d{3}|@|©|политик|согласи|корзин|войти|регистрац|адрес|\bул\.|"
                       r"ваш город|выберите город|предполагаем|"
                       r"^(главная|каталог)\b", re.I)
# не для описания: отзывы покупателей, поздравления, «я/мне» - это не о странице
NOT_DESC = re.compile(r"\b(я|мне|мой|моя|мою|остал(ся|ась|ись)|довол(ен|ьна|ьны)|спасибо|благодар\w*|рекомендую|"
                      r"поздравля\w*|новым годом|рождеств\w*|с праздник\w*|отзыв\w*)\b", re.I)
SENT = re.compile(r"(?<=[.!?…])\s+")
CITY_RX = re.compile(r"\bв[о]?\s+([А-ЯЁ][а-яё]{2,}(?:[-\s][А-ЯЁ][а-яё]+)?)\b")
TEMPLATE_SAMPLE = 400
SHOP_URL = re.compile(r"/(catalog|katalog|shop|magazin|products?|tovary?|goods|zapchast\w*|store|category|"
                      r"collections?|uslugi|services?)(/|$)", re.I)
PRICE = re.compile(r"\d[\d\s\xa0]*\s?(₽|руб\b|руб\.|р\.)", re.I)
SERVICE_URL = re.compile(r"/(uslugi|services?)(/|$)", re.I)   # в SHOP_URL для «коммерческий ли сайт», но это услуги
# признаки витрины магазина: «Заказать»/«Купить» есть и у услуг (агентство, сервис) - по ним раздел магазина не ставим
STORE = re.compile(r"в корзину|в наличии|нет в наличии|артикул|под заказ", re.I)
CART = re.compile(r"в корзину|купить|заказать|под заказ|в наличии|нет в наличии|артикул", re.I)
# адрес карточки товара (WooCommerce /product/…, /tovar/…): у rsmarket24 нет разметки товара, а «похожие товары» с
# ценами
# на каждой карточке - по ценам товар не узнать, и 146 карточек получали пустое «Подробнее - на сайте …»
PROD_URL = re.compile(r"/(product|tovar|item|goods)/[^/]+/?$", re.I)
SKU = re.compile(r"\bартикул[:\s№]*([A-Za-zА-Яа-я0-9][\w./-]{2,24})", re.I)
# ошибки знаков, которые попадают в готовое описание из своего текста сайта: «Магазин RS Market, предлагает»
# (запятая между подлежащим и сказуемым), «место где» (нет запятой перед «где»)
COMMA_VERB = re.compile(r"^((?:[^,.!?]*?[\s-])?(?:магазин|компания|фирма|салон|сервис|центр|студия|сайт|"
                        r"мы)\b[^,.!?]{0,40}),"
                        r"\s+(предлага\w*|продаё?\w*|работа\w*|занима\w*|оказыва\w*|производ\w*|осуществля\w*)", re.I)
NO_COMMA_WHERE = re.compile(r"(?<=[а-яёa-z0-9»)])\s+(где|куда|откуда|который|которая|которое|которые)\s", re.I)


def _fix_punct(s):
    """Поправить частые ошибки знаков в каждом предложении (общее правило, не под один сайт)."""
    out = []
    for part in SENT.split(s):
        part = COMMA_VERB.sub(r"\1 \2", part)
        # перед «где», «который» нужна запятая, кроме «и где», «а где», «не знаю где» → «не знаю, где» тоже верно
        part = NO_COMMA_WHERE.sub(lambda m: m.group(0)
                                  if part[:m.start()].split()[-1].lower() in ("и", "а", "но", "или", "вот")
                                  else ", " + m.group(1) + " ", part)
        out.append(part)
    return " ".join(out)


def _clean(s):
    return " ".join(html.unescape(s or "").replace("\xa0", " ").split())


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


# после них фраза не кончается: «…дизайна для», «…Испании и»
FUNC_WORDS = {"для", "при", "без", "под", "над", "про", "через", "после", "перед", "около", "между", "из-за", "из-под",
              "или", "либо", "что", "чтобы", "как", "когда", "где", "который", "которая", "которые", "также", "так",
              "его", "её", "их", "наш", "наши", "ваш", "ваши", "свой", "свои", "этот", "эти", "это", "все", "всех",
              "and", "or", "for", "with", "the", "of", "to", "in", "on", "by", "from", "a", "an",
              # подпись без значения: «… WHIRLPOOL AWOC 0614 Артикул»
              "артикул", "арт", "код", "модель", "цвет", "размер"}
# год как план или срок («задачи на 2022 год», «к 2022», «до 2022») - устаревает; «работаем с 2012 года» - нет
STALE_YEAR = re.compile(r"\b(?:на|к|до)\s+(20[0-3]\d)\b", re.I)
# начало придаточного: до него предложение законченное
CLAUSE = re.compile(r",\s+(?:который|которая|которое|которые|которых|где|когда|если|чтобы|потому что|так как|"
                    r"поэтому)\b",
                    re.I)
# прилагательное без своего существительного: «…в Испании и Латинской» (Америке отрезали)
# только явно прилагательные окончания (-ской, -ового, -ный): «доставкой», «санаторий», «водой» - не они
ADJ_END = re.compile(r"(?:[сц]к|[ое]в)(?:[ыиоа]й|ая|яя|ую|юю|[ыи]е|[ыи]х|[ое]го|[ое]му|[ыи]ми)$"
                     r"|н(?:ый|ая|яя|ую|юю|ые|ых|ого|его|ому|ему|ыми|ими)$", re.I)   # не -ние/-ний: продвижение


CUT_TAIL = " ,;:\u2014–-"    # что не должно оставаться на конце обрезанного текста
NAME_EDGE = " ,\u2014–-|"   # что снимается по краям названия страницы


def _drop_weak_tail(words):
    """Снять с конца короткие и служебные слова."""
    while words and (len(words[-1]) <= 2 or words[-1].lower() in FUNC_WORDS):
        words.pop()


def _cut(s, n):
    """Обрезать по слову, без висящих запятых, предлогов, союзов и прилагательных без существительного."""
    if len(s) <= n:
        return s
    s = s[:n + 1].rsplit(" ", 1)[0].rstrip(CUT_TAIL)
    words = s.split()
    _drop_weak_tail(words)   # «… для», «… и», «… в»
    if len(words) > 2 and ADJ_END.search(words[-1]) and words[-1][-1].isalpha():
        words.pop()
        _drop_weak_tail(words)
    s = " ".join(words).rstrip(CUT_TAIL)
    if s.count("(") > s.count(")"):              # «… (бухта» - без незакрытой скобки
        s = s[:s.rfind("(")].rstrip(CUT_TAIL)
    head, colon, tail = s.rpartition(": ")       # «…слов: интервальные» - огрызок после двоеточия не нужен
    if colon and len(tail.split()) <= 2 and len(head) >= 20:
        s = head
    return s


def _norm(s):
    """Для сравнения названий: «3D-программа» = «3d программа»."""
    return " ".join(re.sub(r"[-‐–\u2014]", " ", s.lower()).split())


def _shorter(name):
    """Название и его сокращения по смыслу: «кухни, спальни, кровати, стенки» → «кухни, спальни, кровати» → …
    Не короче двух пунктов перечисления: огрызок «Мебель для дома: кухни» хуже, чем без «купить, цены»."""
    yield name
    if "(" in name:   # сначала без уточнений в скобках: запятые внутри скобок - не пункты перечисления
        name = " ".join(re.sub(r"\s*\([^()]*\)", " ", name).split())
        yield name
    sent = SENT.split(name)[0].rstrip(".!?…")   # «… контекст. Секреты от преподавателей» - первое предложение
    if sent != name and len(sent) >= 20:
        name = sent
        yield name
    parts = [x.strip() for x in name.split(",")]
    for k in range(len(parts) - 1, 1, -1):
        yield ", ".join(parts[:k])


def _short(name, n):
    """Сократить длинное название товара: сначала убрать уточнения в скобках, потом хвост после запятой,
    и только потом резать по слову."""
    while len(name) > n and "(" in name:
        new = re.sub(r"\s*\([^()]*\)\s*", " ", name, count=1).strip()
        if new == name:
            break
        name = " ".join(new.split())
    if len(name) > n and "," in name:
        fit = next((x for x in _shorter(name) if len(x) <= n), "")
        head = name.split(",")[0].strip()
        if fit:
            name = fit
        elif len(head) >= 20:
            name = head
    return _cut(name, n)


def _city(pages):
    """Город в предложном падеже («Уфе»), если сайт продвигается как местный: стоит в title у многих страниц."""
    c = Counter()
    for p in pages:
        for m in CITY_RX.findall(p.get("title") or ""):
            c[m] += 1
    if not c:
        return ""
    city, n = c.most_common(1)[0]
    return city if n >= max(10, 0.2 * len(pages)) else ""


def _brand(pages):
    """Название компании - хвост title у многих страниц («… | ГазПрофСервис»)."""
    tails = Counter()
    for p in pages:
        parts = re.split(r"\s[|\u2014–]\s", _clean(p.get("title")))
        if len(parts) > 1:
            tails[parts[-1].strip()] += 1
    if not tails:
        return ""
    t, n = tails.most_common(1)[0]
    return t if n >= max(10, 0.2 * len(pages)) and len(t.split()) <= 4 and len(t) <= 30 else ""


def _template(pages):
    """Строки текста, которые есть на многих страницах (меню, подвал) - не свой текст страницы."""
    sample = [p for p in pages if p.get("blocks")]
    random.Random(1).shuffle(sample)
    sample = sample[:TEMPLATE_SAMPLE]
    df = Counter()
    for p in sample:
        df.update({x.lower() for x in unpack_blocks(p) or ()})
    return {t for t, n in df.items() if n >= max(5, 0.2 * len(sample))}


_CYR_WORD = re.compile(r"[а-яё,.:;!?«»()-]+")   # слово русскими буквами (_sentence; заранее - вызывается миллионы раз)


def _sentence(p, template, name):
    """Первое осмысленное предложение своего текста страницы (не меню, не заголовок, не телефон)."""
    lines = unpack_blocks(p)
    if lines is None:
        return ""
    low_name = name.lower()
    # предложение должно быть о странице: хоть одно слово названия («Тумбы для обуви» - «тумб…», «обув…»)
    topic = {x[:5] for x in re.findall(r"[а-яёa-z]{4,}", low_name)}
    for ln in lines:
        ln = _clean(ln)
        if ln.lower() in template or len(ln.split()) < 8 or JUNK_LINE.search(ln) or ln.lower() == low_name:
            continue
        s = SENT.split(ln)[0].strip()
        w = s.split()
        cyr = [x for x in w if _CYR_WORD.fullmatch(x.lower())]
        if (len(w) >= 8 and len(s) <= 220 and not s.isupper() and len(cyr) >= 0.6 * len(w)
                and len(set(x.lower() for x in w)) >= 0.75 * len(w) and not PRICE.search(s)
                and sum(1 for x in w[1:] if x[:1].isupper()) < 0.3 * len(w)   # не хлебные крошки
                and not s.rstrip(".!…").endswith((":", ";", ",", "-"))       # обрывок «…акций:.»
                and not NOT_DESC.search(s)
                and (not topic or any(x in s.lower() for x in topic))):
            return s if s.endswith("?") else s.rstrip(".!…") + "."   # без «?.»
    return ""


def _own_facts(p, template):
    """По своему тексту страницы (без меню и подвала): сколько цен, есть ли «в корзину»/«купить»/«артикул»,
    и цена, если она одна («10 165 руб.» → «10 165 ₽»). У карточки товара цена одна-две, у раздела - много."""
    blocks = unpack_blocks(p)
    if blocks is None:
        return 0, False, "", False
    own = [x for x in blocks if x.lower() not in template]
    txt = "\n".join(own)
    found = [re.sub(r"\D", "", m.group(0).split("₽")[0].split("р")[0]) for m in PRICE.finditer(txt)]
    found = [x for x in found if x and int(x) > 0]
    one = f"{int(found[0]):,}".replace(",", " ") + " ₽" if len(set(found)) == 1 else ""
    return len(found), bool(CART.search(txt)), one, bool(STORE.search(txt))


def _sku(p):
    """Артикул из текста страницы («Артикул: 2207060h33») - первый, до блока «похожие товары»."""
    blocks = unpack_blocks(p)
    m = SKU.search("\n".join(blocks)) if blocks is not None else None
    return m.group(1).rstrip(".,") if m else ""


# характеристики товара для описания: «Производитель» → «Marazzi», «Страна» → «Италия» - строкой
# «Подпись: значение» или подпись и значение двумя строками. Только до блока похожих товаров: там чужие характеристики
_FACT_LABEL = {"производитель": "brand", "бренд": "brand", "торговая марка": "brand", "страна": "country",
               "страна производства": "country", "страна производитель": "country", "страна-производитель": "country"}
_FACT_STOP = re.compile(r"^(похожие товары|вы смотрели|с этим товаром|рекомендуем|аналоги|сопутствующие)", re.I)


def _facts(p):
    """{"brand": …, "country": …} из своих характеристик страницы товара."""
    lines = unpack_blocks(p) or []
    out = {}
    for i, ln in enumerate(lines):
        if _FACT_STOP.match(ln.strip()):
            break
        lab, _, val = ln.partition(":")
        key = _FACT_LABEL.get(lab.strip().lower())
        if not key:
            continue
        val = (val if _ else (lines[i + 1] if i + 1 < len(lines) else "")).strip().rstrip(".,;")
        if key not in out and 2 <= len(val) <= 30 and re.search(r"[A-Za-zА-Яа-яЁё]", val) \
                and val.lower() not in _FACT_LABEL and "," not in val:
            out[key] = val
    return out


def _product(p):
    info = page_json(p, "schema_info") or {}
    return info.get("product") if isinstance(info, dict) else None


def _price(prod):
    if not prod:
        return ""
    v = str(prod.get("price") or "").replace(",", ".").strip()
    try:
        f = float(v)
    except ValueError:
        return ""
    if f <= 0:
        return ""
    cur = (prod.get("currency") or "RUB").upper()
    num = f"{f:,.0f}".replace(",", " ") if f == int(f) else f"{f:,.2f}".replace(",", " ")
    return num + (" ₽" if cur in ("RUB", "RUR", "") else " " + cur)


def _strip_tail(name, brand, city):
    """«Газовые котлы в Уфе - купить | Бренд» → «Газовые котлы»."""
    parts = [x.strip() for x in re.split(r"\s*\|\s*|\s[\u2014–-]\s", name) if x.strip()]
    name = parts[0] if parts else name
    # «Все внимание – на обивку: сравнение диванов»: первая часть одна - огрызок, вторая - продолжение мысли
    if (len(parts) > 1 and len(name) < 20 and len(parts[1].split()) >= 2 and len(name) + len(parts[1]) <= 70
            and not BUY.search(parts[1]) and not (brand and brand.lower() in parts[1].lower())
            and not (city and city.lower() in parts[1].lower())):
        name = f"{name} - {parts[1]}"
    if brand and name.lower().endswith(brand.lower()):
        name = name[: -len(brand)].strip(NAME_EDGE)
    if city:
        name = re.sub(r"\s+в[о]?\s+" + re.escape(city) + r"\b.*$", "", name)
    if "?" not in name:   # вопрос («Как выбрать и купить кровать?») - суть статьи, «купить» в нём не хвост
        name = re.sub(r"\s*[-\u2014–,]?\s*(купить|цена|цены|недорого|заказать)\b.*$", "", name, flags=re.I)
    # «Прихожие: каталог»
    name = re.sub(r"\s*[:,]?\s*(каталог|ассортимент)$", "", name.strip(NAME_EDGE + ":"), flags=re.I)
    return name.strip(NAME_EDGE + ":")
