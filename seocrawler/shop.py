"""«Что мешает покупать»: что видно при чтении страницы магазина или услуги.

facts(html) — короткая выжимка со страницы (JSON в pages.shop): цена товара и старая цена (первые после H1, без
шапки, меню, подвала и мини-корзины), цена в микроразметке, надпись о наличии, кнопки «В корзину» / «Купить в один
клик» / «Заказать звонок», фото-заглушки, пустые характеристики, формы с телефоном или почтой и есть ли у них
согласие на обработку персональных данных, год в «©», остатки шаблона ({price}, Lorem ipsum, #PRICE#), хлебные
крошки, телефоны в шапке и подвале, ссылки на WhatsApp и Telegram, выбранный город в шапке.
Собирается при обходе (parser.parse_html). У старых проверок данных нет - ensure при сборке отчёта один раз
дочитывает выборку страниц (по разделам, до SAMPLE) и пишет то же самое. Проверки — analyze/checks/buy.py."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlsplit

SAMPLE = 400   # страниц на дочитывание у старых проверок
VERSION = 3    # 3 - цены по карте и «экономия»: старые проверки перечитывают страницы с ценами

_NUM = r"\d{1,3}(?:[\s  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
PRICE = re.compile(r"(?<![\d.,])(" + _NUM + r")\s*(?:₽|руб(?:\.|лей|ля|ль)?(?![а-яё])|р\.(?![а-яё])|RUB\b)", re.I)
NUMBER = re.compile(r"(?<![\d.,])(" + _NUM + r")(?![\d])")
STATUS = re.compile(r"^\s*(?:статус:\s*|наличие:\s*)?(под заказ|нет в наличии|отсутствует|нет на складе|ожидается|"
                    r"временно отсутствует|снят с производства|товар закончился|распродан|"
                    r"в наличии|есть в наличии|на складе|много|мало|достаточно)\b", re.I)
BUY = re.compile(r"^\s*(?:в корзину|добавить в корзину|положить в корзину|купить|купить сейчас|оформить заказ|"
                 r"заказать|заказать товар|купить в (?:один|1) клик|быстрый заказ|заказать в (?:один|1) клик)\s*$", re.I)
ONE_CLICK = re.compile(r"(?:в (?:один|1) клик|быстрый заказ)", re.I)
CALLBACK = re.compile(r"^\s*(?:заказать звонок|обратный звонок|перезвоните мне|заказать обратный звонок|"
                      r"перезвонить мне|жду звонка)\s*$", re.I)
PLACEHOLDER = re.compile(r"(?:no[-_]?(?:image|photo|foto|img|picture|pic|preview)|nophoto|noimage|nofoto|noimg|"
                         r"placeholder|empty[-_](?:image|photo)|default[-_](?:image|product|photo)|zaglushka|"
                         r"/blank\.(?:png|jpe?g|gif))", re.I)
SPEC_EMPTY = re.compile(r"(характеристики (?:не указаны|отсутствуют|не заполнены|скоро появятся|уточняйте)|"
                        r"нет характеристик|описание (?:отсутствует|не заполнено|скоро появится)|"
                        r"описание товара (?:отсутствует|скоро появится)|нет описания)", re.I)
SPEC_BOX = re.compile(r"(?:character|harakter|specific|\bspecs?\b|props\b|properties|tech-?data|params-list)", re.I)
JUNK = re.compile(r"(\{\{?\s*[a-z_][a-z_0-9.]{1,30}\s*\}\}?|#[A-Z][A-Z_]{2,30}#|\blorem ipsum\b|\bundefined\b|"
                  r"\bNaN\b|\[%\s*\w+)", re.I)
JUNK_BLOCK = re.compile(r"^(?:test|тест|тестовый товар|test product|тестовая страница|товар 1|название товара|"
                        r"описание товара|product name|null)\.?$", re.I)
COPY = re.compile(r"(?:©|\(c\)|копирайт)\s*(?:(?:19|20)\d{2}\s*[-–—]\s*)?((?:19|20)\d{2})", re.I)
PHONE = re.compile(r"(?<![\d\w])(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?![\d])")
CITY = re.compile(r"(?:(?i:ваш|выбранный) (?i:город|регион)\s*[:\-]?|\b(?i:город)\s*:)\s*([А-ЯЁ][а-яё]+(?:[\s\-][А-ЯЁ][а-яё]+)?)")
CONSENT = re.compile(r"(персональн|согласи|политик|конфиденциальн|152[-\s]?фз|оферт)", re.I)
CHECK_CONSENT = re.compile(r"(agree|consent|policy|soglas|personal|privacy|accept|rules|license|pdn)", re.I)
OLD_CLS = re.compile(r"(?:old|was|cross|strike|prev|before|line-through|zachyork|discount-price__old)", re.I)
PRICE_CLS = re.compile(r"price|cost", re.I)
# цена по клубной карте или по акции и «экономия» рядом с ценой: «Цена с картой клуба · 69 341 ₽ ·
# экономия 3 649 ₽». CARD — слова перед ценой по карте; такая цена не считается ценой товара
CARD = re.compile(r"(?:по\s+(?:клубной\s+|бонусной\s+|дисконтной\s+|накопительной\s+)?карт[еыу]|"
                  r"с\s+(?:клубной\s+|бонусной\s+|дисконтной\s+)?картой|клубн\w*\s+цен\w*|цен\w*\s+(?:для\s+)?клуба|"
                  r"карт\w*\s+клуба|для\s+(?:член\w+|участник\w+)\s+клуба|для\s+участников|по\s+программе\s+лояльности|"
                  r"цен\w*\s+по\s+акции|акционн\w*\s+цен\w*|цен\w*\s+со\s+скидкой)", re.I)
SAVE_WORD = r"(?:экономия|выгода|экономите|сэкономите|скидка)"
SAVE = re.compile(SAVE_WORD + r"(\s*(?:составит|составляет|до)?\s*[:·]?\s*)([-−–]\s*)?(" + _NUM + r")\s*(₽|руб\.?|р\.|%)",
                  re.I)
BADGE = re.compile(r"(?<![\w\d])[-−–]\s?(\d{1,2})\s?%")
NOT_MAIN = re.compile(CARD.pattern + r"|" + SAVE_WORD, re.I)
OTHER_GOODS = re.compile(r"(?:похожие|рекомендуем|с этим товаром|аналоги|вы смотрели|сопутствующие|"
                         r"покупают вместе|купить вместе|вам может понравиться)", re.I)


def main_price(text):
    """Цена товара в тексте элемента: первая цена, перед которой (после прошлой цены) нет слов «по карте», «экономия»."""
    last = 0
    for m in PRICE.finditer(text or ""):
        if not NOT_MAIN.search(text[last:m.start()]):
            return _num(m.group(1))
        last = m.end()
    return None


def discount(text, pos, price, old=None):
    """Цена по карте или акции и «экономия» рядом с ценой товара (текст после H1, pos — где кончилась цена товара).
    {"club": цена по карте, "save": экономия в рублях (отрицательная, если со знаком минус), "pct": скидка в %,
    "txt": как написано} или {}."""
    if price is None or pos is None:
        return {}
    lo = max(0, pos - 300)
    w = text[lo:pos + 500]
    # только блок этого товара: до цены другого товара или до «Похожие товары» (там свои цены по карте)
    pm, left, right, last = pos - lo, 0, len(w), 0
    for m in PRICE.finditer(w):
        v = _num(m.group(1))
        foreign = v not in (price, old) and not NOT_MAIN.search(w[last:m.start()]) \
            and not CARD.match(w[m.end():m.end() + 60].lstrip(" ·:-–"))  # «1 290 ₽ по карте»
        last = m.end()
        if foreign and m.end() < pm - 1:
            left = m.end()
        elif foreign and m.start() > pm:
            right = m.start()
            break
    s = OTHER_GOODS.search(w, pm, right)
    if s:
        right = s.start()
    w, lo = w[left:right], lo + left
    out = {}
    for m in CARD.finditer(w):
        p = PRICE.search(w, m.end(), m.end() + 45)
        if p and not NOT_MAIN.search(w[m.end():p.start()]):
            v = _num(p.group(1))
            start, end = m.start(), p.end()
        else:  # «69 341 ₽ по карте»
            p = None
            for q in PRICE.finditer(w, max(0, m.start() - 30), m.start()):
                p = q
            if not p or len(w[p.end():m.start()].strip(" ·:-–")) > 0:
                continue
            v = _num(p.group(1))
            start, end = p.start(), m.end()
            if v == price:
                continue
        if v is None:
            continue
        out["club"], s0, s1 = v, start, end
        break
    else:
        s0 = s1 = pos - lo
    # экономия — рядом с ценой по карте (или с ценой товара, если цены по карте нет)
    for m in SAVE.finditer(w, max(0, s0 - 150), s1 + 150):
        if re.search(r"(?i)\bдо\b", m.group(1)):
            continue  # «скидка до 30%» — реклама, а не скидка товара
        v = _num(m.group(3))
        if v is None:
            continue
        if m.group(4) == "%":
            out.setdefault("pct", v)
        else:  # «Скидка −500 ₽» — так пишут скидку; минус у «экономии» — ошибка
            neg = bool(m.group(2)) and not m.group(0).lower().startswith("скидк")
            out.setdefault("save", -v if neg else v)
        s0, s1 = min(s0, m.start()), max(s1, m.end())
    if "pct" not in out and ("club" in out or old is not None):  # значок «−5%» рядом с ценой
        b = BADGE.search(w, max(0, pos - lo - 150), pos - lo + 150)
        if b:
            out["pct"] = float(b.group(1))
    if out:
        out["txt"] = " ".join(w[max(0, s0):s1].split())[:150]
    return out
# по отдельным классам элемента: «header», «header__menu», «site-header» — шапка; у <body class="header-fixed"> не
# смотрим (иначе вся страница считалась бы шапкой)
CART_CLS = re.compile(r"^(?:(?:header|small|top|mini|fly|bx)[-_]?)?(?:cart|basket|korzin|minicart)(?![-_]?(?:btn|button|add|buy))", re.I)
HEADER_CLS = re.compile(r"^(?:header|(?:site|page|main|top)[-_]header|top-?bar|topline)(?:$|[-_A-Z])", re.I)
FOOTER_CLS = re.compile(r"^(?:footer|(?:site|page|main)[-_]footer)(?:$|[-_A-Z])", re.I)
NO_ZONE = {"html", "body", "main"}
CRUMB_CLS = re.compile(r"(?:breadcrumb|crumbs|bread-crumbs|navigation-chain)", re.I)
RELATED_PROPS = {"isSimilarTo", "isRelatedTo", "itemListElement", "isAccessoryOrSparePartFor", "isConsumableFor"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "template", "svg"}
# Теги, на которых браузер разрывает текст (перенос строки и блоки): между словами по обе стороны - пробел.
# «SEO-продвижение сайтов<br>в США» - «сайтов в», а не «сайтовв» (hightime.agency); строчные теги
# (span, b, a) пробела не дают: «<span>Ко</span><span>тлы</span>» - одно слово. Один список с parser.py.
BREAK = {"p", "div", "li", "ul", "ol", "td", "th", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6",
         "section", "article", "header", "footer", "nav", "aside", "main", "form", "dd", "dt", "dl",
         "blockquote", "pre", "br", "option", "button", "label", "figcaption", "caption", "address", "hr"}


def _num(s):
    s = re.sub(r"[\s  ]", "", s).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def phone_norm(t):
    d = re.sub(r"\D", "", t)
    if len(d) == 11 and d[0] in "78":
        d = "7" + d[1:]
    elif len(d) == 10:
        d = "7" + d
    return "+" + d if len(d) == 11 else ""


# параметры tg://resolve - не имя аккаунта, даже если пустые (tg://resolve?domain=)
TG_PARAMS = {"domain", "phone", "start", "startgroup", "startchannel", "startapp", "appname", "text", "post", "thread",
             "comment", "admin", "game", "voicechat", "livestream", "videochat", "profile", "attach", "choose"}


def messenger_problem(href):
    """Ссылка на WhatsApp или Telegram, по которой ничего не откроется: (мессенджер, что не так) или None."""
    h = (href or "").strip()
    low = h.lower()
    if low.startswith(("https://wa.me", "http://wa.me", "wa.me", "https://api.whatsapp.com", "http://api.whatsapp.com",
                       "whatsapp://", "https://web.whatsapp.com", "https://whatsapp.com", "https://www.whatsapp.com")):
        sp = urlsplit(h if "://" in h else "https://" + h)
        q = parse_qs(sp.query)
        if "/send" in sp.path or sp.scheme == "whatsapp":
            raw = (q.get("phone") or [""])[0]
        else:
            raw = sp.path.strip("/")
        if "/channel/" in sp.path or sp.path.startswith("/channel") or "chat.whatsapp" in sp.netloc:
            return None
        if "/message/" in sp.path or sp.path.startswith("/catalog"):  # короткая ссылка на сообщение или каталог
            return None
        d = re.sub(r"\D", "", unquote(raw))
        if not d:
            return ("WhatsApp", "в ссылке нет номера телефона")
        if not 10 <= len(d) <= 15:
            return ("WhatsApp", f"неполный номер: {raw}")
        if re.search(r"x|х", unquote(raw), re.I) or len(set(d[1:])) <= 2:
            return ("WhatsApp", f"номер-заглушка: {raw}")
        return None
    if low.startswith(("https://t.me", "http://t.me", "t.me/", "tg://", "https://telegram.me", "http://telegram.me")):
        sp = urlsplit(h if "://" in h else "https://" + h)
        if sp.scheme == "tg":
            if sp.netloc.lower() != "resolve":   # tg://join, tg://msg, tg://addstickers и др. - своё устройство ссылки
                return None
            q = parse_qs(sp.query, keep_blank_values=True)
            if (q.get("domain") or [""])[0] or (q.get("phone") or [""])[0]:
                return None
            # tg://resolve?HighTimeBot&start=… - имя без «domain=»: Telegram откроется, но чат не найдёт
            bare = next((k for k, v in q.items() if v == [""] and k.lower() not in TG_PARAMS
                         and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", k)), "")
            if bare:
                return ("Telegram", f"пропущено «domain=»: нужно tg://resolve?domain={bare}")
            return ("Telegram", "в ссылке нет имени или номера")
        name = unquote(sp.path).strip("/").split("/")[0]
        if not name:
            return ("Telegram", "ссылка ведёт на сам Telegram, а не на ваш аккаунт")
        if name.startswith("+") or name in ("joinchat", "addstickers", "share", "proxy", "c", "s", "boost", "addlist"):
            return None
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", name):
            return ("Telegram", f"такого имени в Telegram быть не может: {name}")
        if name.lower() in ("username", "your_username", "yourname", "telegram", "test", "example", "name", "login"):
            return ("Telegram", f"имя-заглушка: {name}")
        return None
    return None


_COLLECT = frozenset("pNs")   # флаги элементов, которым нужен их текст (_Facts._close)
PRODUCT_TYPE = re.compile(r"schema[.]org/(?:Product|IndividualProduct|ProductModel)(?:$|[^A-Za-z])")
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_MARKS = {}


def _cls_marks(cls, zone):
    """Что говорят классы и id элемента: (шапка, подвал, мини-корзина, цена, старая цена, характеристики, крошки).
    Одни и те же классы повторяются на странице сотнями и на сайте тысячами - считаем один раз.
    zone - смотреть ли шапку, подвал и корзину (у html, body, main - нет)."""
    key = (cls, zone)
    m = _MARKS.get(key)
    if m is None:
        toks = cls.split() if zone else ()
        m = (any(HEADER_CLS.match(t) for t in toks), any(FOOTER_CLS.match(t) for t in toks),
             any(CART_CLS.match(t) for t in toks), bool(PRICE_CLS.search(cls)), bool(OLD_CLS.search(cls)),
             bool(SPEC_BOX.search(cls)), bool(CRUMB_CLS.search(cls)))
        if len(_MARKS) > 50_000:   # классы с номерами товаров (product-12345) не копятся без конца
            _MARKS.clear()
        _MARKS[key] = m
    return m


class _Facts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # [tag, flags, buf, found, номер элемента]
        # Скорость (thehome.ru: 170 мс на страницу товара, больше половины всего разбора): сколько
        # открытых элементов с каждым флагом - _ctx не перебирает весь стек; need - сколько открытых элементов
        # собирают свой текст (цена, название товара, характеристики). Нет таких - текст вложенных элементов
        # не склеивается заново на каждом уровне вложенности: он никому не нужен.
        self.on = {}
        self.need = 0
        self.serial = 0
        self.skip = 0
        self.after_h1 = False
        self.in_h1 = False
        self.h1 = ""
        self.prices, self.old = [], []
        self.seq = []             # цены по порядку: («n» — цена, «o» — старая цена, значение)
        self.sname = ""
        self.md_product = self.md_name_wait = False
        self.status = ""
        self.buy = self.one_click = self.callback = 0
        self.ph_img, self.ph_src = 0, ""
        self.spec_empty = ""
        self.forms = []
        self.form = None
        self.after_form = None    # форма закрылась: согласие бывает сразу под ней
        self.copy = 0
        self.junk = []
        self.crumbs = []
        self.crumb_item = None
        self.crumb_hrefs = []     # ссылки видимых крошек по порядку (проверка «Хлебные крошки», analyze/checks/crumbs.py)
        self.crumb_last = ""      # ссылка последнего пункта видимых крошек
        self.ld_crumb_urls = []   # адреса пунктов BreadcrumbList в JSON-LD
        self.hphones, self.fphones = set(), set()
        self.msg = []
        self.city = ""
        self.ld = None
        self.ld_items = []
        self.sprice, self.slow, self.md_price = None, False, None
        self.blk = []
        self.buytext, self.buylen, self.price_pos = [], 0, None  # текст после H1 — для цены по карте
        self.btn = None           # текст текущей кнопки или ссылки

    # флаги контекста: h — шапка, f — подвал/меню, c — мини-корзина, p — цена, o — старая цена, s — блок
    # характеристик, b — крошки
    def _ctx(self, ch):
        return self.on.get(ch, 0) > 0

    def _push(self, fr):
        self.stack.append(fr)
        for ch in set(fr[1]):
            self.on[ch] = self.on.get(ch, 0) + 1
        if _COLLECT.intersection(fr[1]):
            self.need += 1

    def _pop(self):
        fr = self.stack.pop()
        for ch in set(fr[1]):
            self.on[ch] -= 1
        if _COLLECT.intersection(fr[1]):
            self.need -= 1
        return fr

    def _gap(self):
        """Перенос строки или блок внутри текста - пробел, как в браузере: «Купить<br>в 1 клик» - не «Купитьв»."""
        if self.skip:
            return
        if self.in_h1 and self.h1:   # пустой H1 (логотип картинкой) пустым и остаётся: ниже ищется настоящий
            self.h1 += " "
        if self.need:
            self.stack[-1][2].append(" ")
        if self.form is not None:
            self.form["buf"].append(" ")
        if self.btn is not None:
            self.btn.append(" ")
        if self.crumb_item is not None:
            self.crumb_item[1].append(" ")

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        cls = " ".join((a.get("class", ""), a.get("id", "")))
        if tag in BREAK:
            self._gap()
        if tag in SKIP:
            self.skip += 1
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self.ld = []
        self._flush()
        # товар в микроразметке; «похожие» и «с этим покупают» (isSimilarTo, isRelatedTo, список) — не он
        related = self._ctx("x") or a.get("itemprop", "") in RELATED_PROPS
        product_type = a.get("itemtype") and PRODUCT_TYPE.search(a["itemtype"])
        if product_type and not related:
            self.md_product = True
        if a.get("itemprop") == "name" and self.md_product and not related and not self.sname and not self.md_name_wait:
            if a.get("content"):
                self.sname = " ".join(a["content"].split())[:150]
            elif tag not in VOID:
                self.md_name_wait = True
                a["data-clayler-name"] = "1"
        if a.get("itemprop") in ("price", "lowPrice") and not related:
            v = _num(re.sub(r"[^\d.,]", "", a.get("content", ""))) if a.get("content") else None
            if v is not None and self.md_price is None:
                self.md_price = v
        if tag == "img":
            src = " ".join((a.get("src", ""), a.get("data-src", ""), a.get("data-lazy-src", "")))
            if self.after_h1 and not self._ctx("h") and not self._ctx("f") and PLACEHOLDER.search(src):
                self.ph_img += 1
                self.ph_src = self.ph_src or src.split()[0]
            return
        if tag == "a":
            href = a.get("href", "")
            if href.lower().startswith("tel:"):
                p = phone_norm(href[4:])
                if p:
                    (self.hphones if self._ctx("h") else self.fphones if self._ctx("F") else set()).add(p)
            pr = messenger_problem(href)
            if pr and len(self.msg) < 5 and [href, *pr] not in self.msg:
                self.msg.append([href[:200], *pr])
        if tag == "input":
            t = a.get("type", "text").lower()
            if self.form is not None:
                name = " ".join((a.get("name", ""), a.get("id", ""), a.get("placeholder", ""))).lower()
                if t == "password":
                    self.form["login"] = 1
                elif t == "search" or re.fullmatch(r"(q|s|search|query|text|find|poisk)", a.get("name", "").lower() or "-"):
                    self.form["search"] = 1
                elif t == "tel" or re.search(r"phone|tel|телефон", name):
                    self.form["phone"] = 1
                elif t == "email" or re.search(r"mail|почт", name):
                    self.form["email"] = 1
                elif t == "checkbox" and CHECK_CONSENT.search(name):
                    self.form["consent"] = 1
                elif t == "text" and re.search(r"name|fio|имя|фио", name):
                    self.form["name"] = 1
            if t in ("submit", "button") and a.get("value"):
                if t == "submit" and self.form is not None and not self.form.get("submit"):
                    self.form["btn"], self.form["submit"] = " ".join(a["value"].split())[:40], 1
                self._button(a["value"])
            return
        if tag in VOID:
            return
        flags = ""
        hdr, ftr, cart, price, old, spec, crumb = _cls_marks(cls, tag not in NO_ZONE)
        if tag == "header" or hdr:
            flags += "h"
        if tag == "footer" or ftr:
            flags += "fF"
        if tag == "nav":
            flags += "f"
        if cart and not price:
            flags += "c"
        if price or a.get("itemprop") == "price":
            flags += "p"
        if tag in ("del", "s", "strike") or (old and (price or self._ctx("p"))):
            flags += "o"
        if spec and not self._ctx("s"):
            flags += "s"
        if crumb or a.get("aria-label", "").lower() in ("breadcrumb", "breadcrumbs", "хлебные крошки") \
                or "BreadcrumbList" in a.get("itemtype", ""):
            flags += "b"
        if a.get("data-clayler-name"):
            flags += "N"
        if "hidden" in a or a.get("aria-hidden") == "true" or tag == "template" \
                or (a.get("style") and HIDDEN_STYLE.search(a["style"])):
            flags += "H"  # спрятанный блок (заготовка для скрипта): его текст посетитель не видит
        if a.get("itemprop", "") in RELATED_PROPS:
            flags += "x"
        if tag == "form":
            self.form = {"phone": 0, "email": 0, "name": 0, "text": 0, "consent": 0, "login": 0, "search": 0,
                         "buf": [], "btn": ""}
        if tag == "textarea" and self.form is not None:
            self.form["text"] = 1
        if tag in ("button", "a"):
            self.btn = []
            self.btn_submit = tag == "button" and a.get("type", "submit").lower() == "submit"
        if tag == "h1" and not self.h1.strip():
            self.in_h1 = True
        if self._ctx("b") or "b" in flags:
            href = a.get("href", "").strip() if tag == "a" else ""
            if tag in ("a", "li", "span") and self.crumb_item is None:
                self.crumb_item = [tag, [], ""]   # [тег, текст, ссылка пункта]
            if href:
                self.crumb_hrefs.append(href)
                if self.crumb_item is not None and not self.crumb_item[2]:
                    self.crumb_item[2] = href     # первая ссылка пункта, а не выпадающий список соседних разделов
        self.serial += 1
        self._push([tag, flags, [], False, self.serial])

    def _button(self, text):
        t = " ".join(text.split())
        if not t or len(t) > 40:
            return
        if self.form is not None and not self.form["btn"]:
            self.form["btn"] = t
        if self._ctx("h") or self._ctx("F"):
            if CALLBACK.match(t):
                self.callback += 1
            return
        if BUY.match(t) and self.after_h1:
            self.buy += 1
            if ONE_CLICK.search(t):
                self.one_click += 1
        if CALLBACK.match(t):
            self.callback += 1

    def handle_endtag(self, tag):
        if tag in BREAK:
            self._gap()
        if tag in SKIP and self.skip:
            self.skip -= 1
        if tag == "script" and self.ld is not None:
            self._ld("".join(self.ld))
            self.ld = None
        self._flush()
        if tag in ("button", "a") and self.btn is not None:
            t = " ".join("".join(self.btn).split())
            if getattr(self, "btn_submit", False) and self.form is not None and not self.form.get("submit") and t:
                self.form["btn"], self.form["submit"] = t[:40], 1
            self._button(t)
            self.btn = None
        if self.crumb_item is not None and tag == self.crumb_item[0]:
            t = " ".join("".join(self.crumb_item[1]).split())
            if re.search(r"\w", t) and len(t) < 120:
                self.crumbs.append(t)
                self.crumb_last = self.crumb_item[2]   # ссылка последнего пункта ("" - текстом, без ссылки)
            self.crumb_item = None
        if tag == "h1" and self.in_h1:
            self.in_h1 = False
            self.after_h1 = True
        if tag == "form" and self.form is not None:
            f = self.form
            text = " ".join(f.pop("buf"))
            f["consent"] = f["consent"] or bool(CONSENT.search(text))
            f.pop("submit", None)
            self.form = None
            if (f["phone"] or f["email"]) and not f["login"] and not f["search"]:
                self.forms.append(f)
                self.after_form = [f, 0]
        # закрываем элемент (и всё незакрытое внутри него)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                while len(self.stack) > i:
                    self._close(self._pop())
                break

    def _close(self, fr):
        tag, flags, buf, found = fr[:4]
        if not self.need and not _COLLECT.intersection(flags):
            return   # ни этому элементу, ни тем, что снаружи, текст не нужен
        text = " ".join("".join(buf).split())
        parent = self.stack[-1] if self.stack else None
        old = False
        if "p" in flags and not found and not self._ctx("c") and "c" not in flags \
                and not self._ctx("h") and not self._ctx("f") and "h" not in flags and self.after_h1:
            v = main_price(text)  # «Цена с картой клуба · 69 341 ₽» — не цена товара
            if v is None and re.fullmatch(r"(?:от\s*)?" + _NUM, text or "-"):
                v = _num(text.replace("от", "").strip())
            if v is not None:
                old = "o" in flags or self._ctx("o")
                (self.old if old else self.prices).append(v)
                if not old and self.price_pos is None:
                    self.price_pos = self.buylen
                if len(self.seq) < 6:
                    self.seq.append(("o" if old else "n", v, tuple(x[4] for x in self.stack) + (fr[4],)))
                if not old:  # старая цена не мешает найти новую в том же блоке
                    for p in self.stack:
                        p[3] = True
        if parent is not None and not old:
            parent[2].append(" " + text + " ")
        if "N" in flags and not self.sname:
            self.sname = text[:150]
            self.md_name_wait = False
        if "s" in flags and self.after_h1 and not self.spec_empty:
            rest = re.sub(r"(?i)характеристики|технические|свойства|параметры|specifications?|[:\s]", "", text)
            if len(rest) < 3:
                self.spec_empty = "блок характеристик пустой"

    def handle_data(self, data):
        if self.ld is not None:
            self.ld.append(data)
        if self.skip:
            return
        if self.in_h1:
            self.h1 += data
        if self.need:
            self.stack[-1][2].append(data)
        if self.form is not None:
            self.form["buf"].append(data)
        elif self.after_form is not None:
            self.after_form[1] += len(data)
            if CONSENT.search(data):
                self.after_form[0]["consent"] = 1
            if self.after_form[1] > 300:
                self.after_form = None
        if self.btn is not None:
            self.btn.append(data)
        if self.crumb_item is not None:
            self.crumb_item[1].append(data)
        self.blk.append(data)

    def _flush(self):
        if not self.blk:
            return
        t = " ".join(" ".join(self.blk).split())
        self.blk = []
        if not t:
            return
        for m in COPY.finditer(t):
            self.copy = max(self.copy, int(m.group(1)))
        for m in PHONE.findall(t):
            p = phone_norm(m)
            if p:
                if self._ctx("h"):
                    self.hphones.add(p)
                elif self._ctx("F"):
                    self.fphones.add(p)
        if self._ctx("h") and not self.city:
            m = CITY.search(t)
            if m:
                self.city = m.group(1)
        if len(self.junk) < 3:
            m = None if self._ctx("H") else JUNK.search(t)
            if m and not re.search(r"\{\{\s*(?:\$|t\(|_\()", m.group(0)):
                self.junk.append(m.group(0)[:40])
        if self.after_h1 and not self._ctx("h") and not self._ctx("f"):
            if self.buylen < 8000 and not self._ctx("H") and not self._ctx("c"):
                self.buytext.append(t)
                self.buylen += len(t) + 1
            if not self.status and len(t) <= 40 and STATUS.match(t):
                self.status = STATUS.match(t).group(1).lower()
            if not self.spec_empty:
                m = SPEC_EMPTY.search(t)
                if m and len(t) < 200:
                    self.spec_empty = m.group(1)

    def _ld(self, raw):
        try:
            data = json.loads(raw.strip() or "null")
        except ValueError:
            return

        def walk(x, depth=0):
            if depth > 4:
                return
            if isinstance(x, list):
                for y in x:
                    walk(y, depth + 1)
                return
            if not isinstance(x, dict):
                return
            t = x.get("@type")
            ts = t if isinstance(t, list) else [t]
            if "BreadcrumbList" in ts and not self.ld_items:
                items = x.get("itemListElement") or []
                names = []
                for it in items if isinstance(items, list) else []:
                    if isinstance(it, dict):
                        n = it.get("name")
                        if not n and isinstance(it.get("item"), dict):
                            n = it["item"].get("name")
                        if isinstance(n, str) and n.strip():
                            names.append(" ".join(n.split()))
                        u = it.get("item")
                        u = (u.get("@id") or u.get("url")) if isinstance(u, dict) else u
                        if isinstance(u, str) and u.strip():
                            self.ld_crumb_urls.append(u.strip())
                self.ld_items = names
            if any(tt in ("Product", "IndividualProduct", "ProductModel") for tt in ts if isinstance(tt, str)) \
                    and self.sprice is None:
                o = x.get("offers")
                if isinstance(o, list):
                    o = o[0] if o else None
                if isinstance(x.get("name"), str):
                    self.sname = " ".join(x["name"].split())[:150]
                if isinstance(o, dict):
                    if o.get("lowPrice") not in (None, "") or o.get("@type") == "AggregateOffer":
                        self.slow = True
                    v = o.get("price", o.get("lowPrice"))
                    v = _num(str(v)) if v not in (None, "") else None
                    if v is not None:
                        self.sprice = v
            for k in ("@graph", "mainEntity", "itemListElement"):
                if k in x and k != "itemListElement":
                    walk(x[k], depth + 1)
        walk(data)


def _common(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _old_of_main(seq):
    """Старая цена товара: соседняя с первой ценой и ближе к ней по вложенности, чем к другой цене рядом
    (в разделе каталога старая цена второго товара стоит в его карточке, а не у первого)."""
    i = next((k for k, x in enumerate(seq) if x[0] == "n"), None)
    if i is None:
        return None
    main = seq[i][2]
    for j in (i + 1, i - 1):
        if not 0 <= j < len(seq) or seq[j][0] != "o":
            continue
        other = j + (j - i)  # цена по другую сторону от старой
        near = _common(seq[j][2], main)
        if 0 <= other < len(seq) and seq[other][0] == "n" and _common(seq[j][2], seq[other][2]) > near:
            continue
        return seq[j][1]
    return None


def club_cards(text):
    """Карточки товаров в списке (раздел каталога, поиск, «похожие»), где цена по карте не ниже цены рядом:
    «… Артикул: 5681190 … Цена 15 064 Р. по карте клуба 15 325 Р.». [[цена, цена по карте, как написано], …]"""
    text = text or ""
    ps = list(PRICE.finditer(text))
    club = []  # цена стоит сразу после «по карте клуба» (между ними нет другой цены)
    for i, m in enumerate(ps):
        lo = max(ps[i - 1].end() if i else 0, m.start() - 60)
        c = list(CARD.finditer(text, lo, m.start()))
        club.append(bool(c) and m.start() - c[-1].end() <= 45)
    out = []
    for i, m in enumerate(ps):
        if not club[i] or i == 0 or club[i - 1]:
            continue
        n = ps[i - 1]
        if m.start() - n.end() > 150 or re.search(SAVE_WORD, text[n.end():m.start()], re.I) \
                or re.search(SAVE_WORD + r"\s*[:·]?\s*$", text[max(0, n.start() - 25):n.start()], re.I):
            continue  # «экономия 807 ₽» — не цена
        v, c = _num(n.group(1)), _num(m.group(1))
        if v is None or c is None or c <= v:  # одинаковые - скидки по карте нет, это не ошибка
            continue
        start = ps[i - 2].end() if i >= 2 else 0
        lo = max(start, n.start() - 110)
        txt = " ".join(w for w in text[lo:m.end()].split() if w != "?")  # «?» — значок подсказки
        if lo > start and lo and text[lo - 1].isalnum():  # обрезанное первое слово
            txt = txt.split(" ", 1)[-1]
        if len(out) < 5:
            out.append([v, c, txt[-170:]])
    return out


def facts(html_text, p=None):
    """Выжимка со страницы для «Что мешает покупать». JSON-строка (короткая) или "" — нечего записать.
    p - уже прочитанный разбор (parser.parse_html читает страницу один раз сразу для двух разборов)."""
    if p is None:
        p = _Facts()
        try:
            p.feed(html_text)
            p.close()
        except Exception:
            pass
    p._flush()
    while p.stack:
        p._close(p._pop())
    crumbs = p.ld_items or p.crumbs
    h1 = " ".join(p.h1.split())
    if JUNK_BLOCK.match(h1) and len(p.junk) < 3:  # товар называется «Тест» или «Товар 1»
        p.junk.append(h1[:40])
    out = {
        "h1": " ".join(p.h1.split())[:150],
        "price": p.prices[0] if p.prices else None, "prices": len(p.prices),
        # старая цена — только рядом с ценой товара (в разделе каталога она бывает у второго товара)
        "old": _old_of_main(p.seq),
        "disc": discount(" ".join(p.buytext), p.price_pos, p.prices[0] if p.prices else None, _old_of_main(p.seq)),
        "club_bad": club_cards(" ".join(p.buytext)),
        "sname": p.sname,
        "sprice": p.sprice if p.sprice is not None else p.md_price, "slow": p.slow,
        "status": p.status, "buy": p.buy, "one_click": p.one_click, "callback": p.callback,
        "ph_img": p.ph_img, "ph_src": p.ph_src[:200], "spec_empty": p.spec_empty,
        "forms": [{k: v for k, v in f.items() if v} for f in p.forms][:5],
        "copy": p.copy, "junk": p.junk, "crumbs": crumbs[:12],
        # видимые крошки отдельно от разметки (crumbs - разметка, если есть): сколько пунктов и куда ведут ссылки
        "crumbs_html": len(p.crumbs), "crumb_urls": list(dict.fromkeys(p.crumb_hrefs))[:20], "crumb_last": p.crumb_last,
        "crumb_ld_urls": p.ld_crumb_urls[:12],
        "hphones": sorted(p.hphones)[:5], "fphones": sorted(p.fphones)[:5], "msg": p.msg, "city": p.city,
    }
    return json.dumps({k: v for k, v in out.items() if v not in (None, "", [], 0, False)}, ensure_ascii=False)


def _same_name(a, b):
    """Похожи ли название товара в разметке и H1: хотя бы половина слов H1 есть в названии."""
    wa = set(re.findall(r"[\wёЁ]{3,}", a.lower()))
    wb = set(re.findall(r"[\wёЁ]{3,}", b.lower()))
    return bool(wb) and len(wa & wb) * 2 >= len(wb)


def is_product(f):
    """Страница одного товара: цена после H1 и разметка товара (не раздел каталога со списком цен и кнопок)
    или, без разметки, одна-две кнопки покупки и одна-две цены (статья с парой товаров сбоку - не товар)."""
    if f.get("price") is None or not f.get("h1"):
        return False
    if f.get("sprice") is not None:
        if f.get("sname") and not _same_name(f["sname"], f["h1"]):
            return False  # в разметке товар с другим названием: это раздел каталога, а не страница товара
        return f.get("buy", 0) <= 6 and f.get("prices", 0) <= 8
    return 1 <= f.get("buy", 0) <= 2 and f.get("prices", 0) <= 2



STOP_AFTER = 8  # столько страниц подряд не открылось - сайт не отвечает, дочитывание останавливается


def ensure(store, fetch=None, log=print):
    """Старая проверка без pages.shop: один раз дочитать выборку страниц (по SAMPLE, разные разделы).
    Проверка, собранная до цен по карте (VERSION 1): один раз перечитать страницы товаров."""
    db = store.db
    cols = [r[1] for r in db.execute("PRAGMA table_info(pages)")]
    if "shop" not in cols:
        db.execute("ALTER TABLE pages ADD COLUMN shop TEXT")
    meta = store.get_meta("shop_sampled", None)
    if meta and not meta.get("pages") and meta.get("of") and not db.execute(
            "SELECT 1 FROM pages WHERE shop IS NOT NULL LIMIT 1").fetchone():
        meta = None   # прошлое дочитывание не открыло ни одной страницы (сайт не отвечал) - попробовать снова
    if meta is not None:
        if meta.get("v", 1) < VERSION:
            _reread_products(store, meta, fetch, log)
        return
    have = db.execute("SELECT COUNT(*) FROM pages WHERE shop IS NOT NULL").fetchone()[0]
    rows = db.execute("SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='page' "
                      "AND p.status=200 AND p.content_type IN ('text/html','application/xhtml+xml') "
                      "AND p.indexable=1 ORDER BY u.depth, p.url").fetchall()
    if have or not rows:
        store.set_meta("shop_sampled", {"pages": 0, "of": len(rows), "v": VERSION})
        store.commit()
        return
    urls = pick([r[0] for r in rows], SAMPLE)
    log(f"Что мешает покупать: дочитываю {len(urls)} страниц из {len(rows)} (в этой проверке цены и кнопки не собирались)...")
    done, stopped = _read(db, urls, fetch)
    if stopped and not done:
        log("Что мешает покупать: сайт не отвечает - страницы не дочитаны, попробую при следующем обновлении отчёта")
        store.commit()
        return
    if stopped:
        log(f"Что мешает покупать: сайт перестал отвечать, дочитано {done} страниц")
    store.set_meta("shop_sampled", {"pages": done, "of": len(rows), "v": VERSION})
    store.commit()


def _reread_products(store, meta, fetch, log):
    """Цены по карте и «экономия» раньше не читались: один раз перечитать прочитанные страницы
    (товары и разделы каталога, до SAMPLE)."""
    db = store.db
    urls = [r[0] for r in db.execute("SELECT url FROM pages WHERE shop IS NOT NULL AND shop LIKE '%price%' ORDER BY url")]
    if urls:
        urls = pick(urls, SAMPLE)
        log(f"Что мешает покупать: перечитываю {len(urls)} страниц с ценами (цены по карте и экономия)...")
        done, stopped = _read(db, urls, fetch)
        if stopped and not done:
            log("Что мешает покупать: сайт не отвечает - страницы не перечитаны, попробую при следующем обновлении")
            return
    import time
    # время перечитывания — в meta: по нему отчёт видит, что данные новые, и не берёт разбор из кэша
    store.set_meta("shop_sampled", dict(meta, v=VERSION, reread=int(time.time())))
    store.commit()


def _read(db, urls, fetch=None):
    if fetch is None:
        from .fetcher import UA_PRESETS, Fetcher
        f = Fetcher(UA_PRESETS["chrome"], timeout=15, total_timeout=25)

        def fetch(u):
            r = f.fetch(u)
            return r.body if r.status == 200 else None
    from .parser import detect_encoding
    import time
    done = miss = 0
    for u in urls:
        try:
            body = fetch(u)
        except Exception:
            body = None
        if body:
            enc, _ = detect_encoding(body, "")
            db.execute("UPDATE pages SET shop=? WHERE url=?", (facts(body.decode(enc, "replace")), u))
            done += 1
            miss = 0
        else:
            miss += 1
            if miss >= STOP_AFTER:   # сайт перестал отвечать (закрыл доступ, упал): не ждать по 25 секунд на каждой
                return done, True
        time.sleep(0.15)
    return done, False


def pick(urls, n):
    """Выборка по разделам: из каждого раздела (первая часть пути) поровну, чтобы попали и товары, и каталог."""
    if len(urls) <= n:
        return urls
    groups = {}
    for u in urls:
        parts = urlsplit(u).path.strip("/").split("/")
        groups.setdefault((parts[0] if parts and parts[0] else "", min(len(parts), 3)), []).append(u)
    out, i = [], 0
    while len(out) < n:
        added = False
        for g in groups.values():
            if i < len(g) and len(out) < n:
                out.append(g[i])
                added = True
        if not added:
            break
        i += 1
    return out


CAT = "Что мешает покупать"
SEV_CLS = {"critical": "crit", "warning": "warn", "notice": "note"}


def html_block(issues, summary, h2="h2", h2_cls="sec", cls="card"):
    """Раздел отчёта «Что мешает покупать»: найденное по разделу со ссылками на проблемы ниже."""
    if not summary.get("has_shop") and not summary.get("buy_clicks") and not summary.get("consent_forms"):
        return ""
    from .fmt import esc, num
    items = [i for i in issues if i.category == CAT or i.key == "empty_category"]
    sm = summary.get("shop_sampled") or {}
    note = (f" Цены и кнопки прочитаны выборочно: {num(sm['pages'])} страниц из {num(sm['of'])}, из разных разделов."
            if sm.get("pages") else "")
    li = "".join(f'<li><a href="#{esc(i.key)}"><b class="{SEV_CLS[i.severity]}">{esc(i.title)}</b></a> - '
                 f'{esc(i.count_text)}</li>' for i in items)
    body = (f'<ul class="rg" style="margin:6px 0 0;padding-left:20px">{li}</ul>' if li else
            '<p class="rg" style="margin:6px 0 0"><b class="ok">Ничего, что мешает покупать, не нашлось.</b></p>')
    return (f'<{h2} class="{h2_cls}">{CAT}</{h2}><div class="{cls}"><p class="mut" style="margin:0">То, что посетитель '
            f'видит на странице перед покупкой или заявкой: цены, наличие, фото, характеристики, телефоны, мессенджеры, '
            f'формы и кнопки. Даже при хороших позициях такие мелочи забирают заказы.{note}</p>{body}</div>')
