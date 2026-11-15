"""Парсер HTML: SEO-элементы страницы и все ссылки. Только стандартная библиотека."""
import codecs
from collections import defaultdict
import hashlib
import json
import zlib
import re
from html.parser import HTMLParser

from .shop import BREAK as SHOP_BREAK, _Facts as _ShopFacts, facts as shop_facts, phone_norm as _norm_phone
from .calltrack import services as calltrack_services

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", re.I)
_WORD = re.compile(r"[\w\-]+", re.U)
# Контакты: телефон — только явный формат (+7/8, код в скобках или через пробел/дефис), чтобы не ловить артикулы и цены
_PHONE = re.compile(r"(?<![\d\w])(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?![\d])")
_STREET = re.compile(r"(?:ул\.|улица|проспект|пр-т|пр\.|бульвар|б-р|шоссе|тракт|пер\.|переулок)\s*"
                     r"[А-ЯЁ][А-Яа-яЁё\-\. ]{2,30},?\s*(?:д\.?\s*)?\d+[\/\dа-яА-Я]{0,5}")
# Счётчики посещаемости: Яндекс Метрика, Google Analytics, Google Tag Manager
_YM = [re.compile(r"\bym\(\s*(\d{5,})"), re.compile(r"yaCounter(\d{5,})"),
       re.compile(r"mc\.yandex\.(?:ru|com|by|kz)/watch/(\d{5,})")]
_YM_ANY = re.compile(r"mc\.yandex\.(?:ru|com|by|kz)/(?:metrika|watch)|metrika/tag\.js")
_GA = [re.compile(r"googletagmanager\.com/gtag/js\?id=((?:G|UA|AW)-[A-Z0-9\-]+)"),
       re.compile(r"gtag\(\s*['\"]config['\"]\s*,\s*['\"]((?:G|UA)-[A-Z0-9\-]+)")]
_GTM = re.compile(r"\b(GTM-[A-Z0-9]{4,10})\b")
_YM_NEED = ("ym(", "yaCounter", "mc.yandex.")   # без этих кусков шаблоны _YM и _GA найти ничего не могут
_GA_NEED = ("googletagmanager.com/gtag/js?id=", "gtag(")
_REQUISITES = re.compile(r"юр\.|юридическ|инн|огрн|кпп|р/с|реквизит|банк", re.I)
# Спрятанный блок (так прячут ссылки на чужие сайты при взломе): стиль самого тега, без CSS-файлов. Сдвиг за экран -
# от 1000 px (left:-9999px): конструкторы (Tilda) на узком экране ставят блокам left:-146px, и они видны
# (ложные «спрятанные ссылки» на hightime.agency)
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em|rem|%)?\s*(?:;|$|!)|"
                           r"(?:left|top|text-indent)\s*:\s*-\d{4,}|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$|!)|"
                           r"(?:height|width)\s*:\s*0(?:px)?\s*;[^\"]*overflow\s*:\s*hidden", re.I)
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# необязательные закрывающие теги: новый тег → (какой открытый закрыть, до какой границы искать)
_LIST, _TABLE = {"ul", "ol", "menu"}, {"table"}
_IMPLIED = {"li": [("li", _LIST)], "dt": [("dt", {"dl"}), ("dd", {"dl"})], "dd": [("dt", {"dl"}), ("dd", {"dl"})],
            "option": [("option", {"select", "datalist", "optgroup"})], "optgroup": [("optgroup", {"select"})],
            "tr": [("tr", _TABLE | {"tbody", "thead", "tfoot"})],
            "td": [("td", {"tr"} | _TABLE), ("th", {"tr"} | _TABLE)], "th": [("td", {"tr"} | _TABLE), ("th", {"tr"} | _TABLE)],
            "tbody": [("tbody", _TABLE), ("thead", _TABLE)], "tfoot": [("tbody", _TABLE), ("thead", _TABLE)]}
_CLOSES_P = {"address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset", "figcaption", "figure",
             "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
             "section", "table", "ul", "dd", "dt"}

# MinHash — «отпечаток» текста для поиска почти одинаковых страниц (как у Screaming Frog).
# 64 случайные хеш-функции вида (a*x + b) mod p; числа фиксированы, чтобы отпечатки были сравнимы между запусками.
_MH_P = 4294967311
_MH_N = 64
_MH_AB = [((i * 2654435761 + 97) % (_MH_P - 1) + 1, (i * 40503 + 7919) % _MH_P) for i in range(1, _MH_N + 1)]


def contacts(blocks, tel_phones):
    """Телефоны и адреса со страницы. Блоки с реквизитами (юр. адрес, ИНН, банк) пропускаем."""
    phones, addrs = set(p for p in tel_phones if p), set()
    for b in blocks:
        if _REQUISITES.search(b):
            continue
        for m in _PHONE.findall(b):
            p = _norm_phone(m)
            if p:
                phones.add(p)
        for m in _STREET.findall(b):
            addrs.add(" ".join(m.split()).rstrip(",."))
    return sorted(phones), sorted(addrs)


def minhash(words, k=5):
    """Отпечаток по пятёркам слов подряд. Меньше 50 слов — отпечаток не считаем (сравнивать нечего)."""
    if len(words) < 50:
        return ""
    shingles = {zlib.crc32(" ".join(words[i:i + k]).encode("utf-8")) for i in range(len(words) - k + 1)}
    sig = [min((a * x + b) % _MH_P for x in shingles) for a, b in _MH_AB]
    return ",".join(map(str, sig))


def detect_encoding(body: bytes, content_type_header: str):
    """Порядок как у браузера: BOM -> заголовок HTTP -> <meta charset> -> угадать."""
    if body.startswith(codecs.BOM_UTF8):
        return "utf-8-sig", "BOM"
    m = re.search(r"charset\s*=\s*[\"']?([\w\-]+)", content_type_header or "", re.I)
    header_cs = m.group(1).lower() if m else None
    mm = _META_CHARSET.search(body[:4096])
    meta_cs = mm.group(1).decode("ascii", "ignore").lower() if mm else None
    for cs, src in ((header_cs, "HTTP"), (meta_cs, "meta")):
        if cs:
            try:
                codecs.lookup(cs)
                return cs, src
            except LookupError:
                pass   # сайт назвал неизвестную кодировку: ниже угадываем сами, источник пишется в отчёт
    try:
        body.decode("utf-8")
        return "utf-8", "угадана"
    except UnicodeDecodeError:
        return "windows-1251", "угадана"


class _Extractor(HTMLParser):
    SKIP_TEXT = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles, self.descriptions, self.h1, self.canonicals = [], [], [], []
        self.h2_count = 0
        self.robots, self.refresh = [], ""
        self.links = []      # dict(href, anchor, nofollow, kind, alt)
        self.images = []     # dict(src, alt, has_size, loading, in_picture, srcset)
        self.resources = []  # dict(src, type): стили, скрипты, фреймы
        self._picture = 0
        self.hreflang = []   # (lang, href)
        self.alt_media = []  # (media, href) — <link rel=alternate media=...>: ссылка на мобильную версию (m.сайт)
        self.base = None
        self.lang = ""
        self.text_parts = []
        self.content_parts = []  # текст без <nav> и <footer> — для поиска почти дублей
        self._navfoot = 0
        self._skip = 0
        self._in_noscript = 0
        self._in_title = False
        self._title_buf = []
        self._hstack = None  # ("h1", buf)
        self._a = None       # текущая ссылка
        self._open = []      # открытые теги [тег, спрятан ли стилем] - ссылки внутри спрятанного помечаются hidden
        self._hid = False
        self._nhid = 0       # сколько из _open спрятаны: _hid без перебора всего стека на каждом теге
        # мобильная версия, соцсети, микроразметка
        self.viewport = None           # None — тега нет
        self.keywords = None
        self.og = {}                   # og:title, og:image...
        self.schema_types = []         # типы Schema.org (JSON-LD и microdata)
        self.schema_errors = 0         # JSON-LD, который не разбирается
        self._ld = None                # текст текущего <script type=application/ld+json>
        self.ld_items = []             # разобранные объекты JSON-LD с их полями — для проверки полноты разметки
        self.md_props = []             # itemprop, встреченные на странице (microdata)
        self.md_avail = []             # microdata: значения availability
        self.md_text = {}              # microdata: первое название и бренд товара (itemprop name, brand) - текстом
        self._mdcap = None             # [свойство, тег, вложенность, текст] - собирается текст свойства
        # microdata по объектам (itemscope): [{types, props, avail, parent, end}] и стек открытых (номера) - у каждого
        # товара свои свойства, вложенный Offer - к своему товару (_md_scope, schema_info)
        self.md_scopes = []
        self._mds = []
        self.md_itemref = False   # на странице есть itemref - разбор по объектам не годится (schema_info)
        self.light = False        # облегчённый разбор (parse_html light): объекты microdata не нужны
        # структура HTML
        self.tag_counts = {"html": 0, "head": 0, "body": 0}
        self.ids = {}
        self._head_phase = True        # ещё в <head> (до </head>, <body> или первого «чужого» тега)
        self.head_break = ""           # тег, который по правилам HTML закрыл <head> раньше времени
        self.after_break = []          # что из важного оказалось после такого тега
        self._head_closed = False
        self.blocks = []               # текст страницы по блокам: из них потом вычитается шаблон сайта
        self.phones = set()            # телефоны из ссылок tel:
        self._blk = []
    HEAD_OK = {"html", "head", "title", "meta", "link", "script", "style", "base", "noscript", "template"}
    # теги, на которых кончается один блок текста и начинается другой (и внутри заголовка - пробел между словами)
    BLOCK = SHOP_BREAK

    def _flush(self):
        if self._blk:
            t = " ".join(" ".join(self._blk).split())
            if t:
                self.blocks.append(t)
            self._blk = []

    def _late(self, what):
        if self.head_break and what not in self.after_break:
            self.after_break.append(what)

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag not in _VOID:
            self._implied_close(tag)
            hidden = bool(a.get("style") and _HIDDEN_STYLE.search(a["style"]))
            self._open.append([tag, hidden])
            if hidden:   # счётчик вместо any() по всему стеку: на кривом HTML с тысячами незакрытых тегов разбор
                self._nhid += 1   # был квадратичным
                self._hid = True
        if tag in self.BLOCK:
            self._flush()
            if self._hstack:   # «сайтов<br>в США» - «сайтов в», не «сайтовв» (hightime.agency)
                self._hstack[1].append(" ")
        if tag in self.tag_counts:
            self.tag_counts[tag] += 1
        if a.get("id"):
            self.ids[a["id"]] = self.ids.get(a["id"], 0) + 1
        if a.get("itemtype"):
            for t in a["itemtype"].split():
                self.schema_types.append(t.rstrip("/").rsplit("/", 1)[-1])
        if a.get("itemprop"):
            for t in a["itemprop"].split():
                self.md_props.append(t)
                if t == "availability":
                    self.md_avail.append(a.get("href") or a.get("content") or "")
                elif (t in ("name", "brand") and t not in self.md_text and self._mdcap is None
                      and set(self.schema_types) & _PRODUCT):   # после начала товара: не название магазина в шапке
                    if a.get("content"):
                        self.md_text[t] = a["content"].strip()[:150]
                    elif tag not in ("meta", "link", "img", "br", "input"):
                        self._mdcap = [t, tag, 0, []]
        if not self.light and (a.get("itemprop") or "itemscope" in a or "itemref" in a):
            self._md_scope(tag, a)
        if self._mdcap is not None and tag == self._mdcap[1]:
            self._mdcap[2] += 1
        if self._head_phase and not self._in_noscript:
            if tag == "body":
                self._head_phase = False
            elif tag not in self.HEAD_OK:
                # браузер и поисковик считают, что здесь начался <body>: всё, что ниже, уже не в <head>
                self._head_phase = False
                if self.tag_counts["head"] and not self._head_closed:
                    self.head_break = tag
        if tag == "script" and "ld+json" in (a.get("type") or "").lower():
            self._ld = []
        if tag in self.SKIP_TEXT:
            self._skip += 1
        if tag == "noscript":
            self._in_noscript += 1
        if tag in ("nav", "footer"):
            self._navfoot += 1
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"].strip()
        elif tag == "title" and not self._skip:
            self._in_title, self._title_buf = True, []
            self._late("title")
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if name == "description":
                self.descriptions.append(a.get("content", "").strip())
                self._late("description")
            elif name in ("robots", "googlebot", "yandex"):
                self.robots.append((name, a.get("content", "").lower()))
                self._late("meta robots")
            elif name == "viewport" and self.viewport is None:
                self.viewport = a.get("content", "").strip()
            elif name == "keywords" and self.keywords is None:
                self.keywords = a.get("content", "").strip()
            if prop.startswith("og:") and prop not in self.og:
                self.og[prop] = a.get("content", "").strip()
            if (a.get("http-equiv") or "").lower() == "refresh":
                self.refresh = a.get("content", "")
        elif tag == "picture":
            self._picture += 1
        elif tag == "source" and self._picture:
            self._srcset(a.get("srcset") or a.get("data-srcset"))
        elif tag == "script" and a.get("src"):
            self.resources.append({"src": a["src"].strip(), "type": "js"})
        elif tag == "iframe" and a.get("src") and not self._in_noscript:
            self.resources.append({"src": a["src"].strip(), "type": "iframe"})
        elif tag == "link":
            rel = (a.get("rel") or "").lower().split()
            if "stylesheet" in rel and a.get("href"):
                self.resources.append({"src": a["href"].strip(), "type": "css"})
            if "canonical" in rel and a.get("href"):
                self.canonicals.append(a["href"].strip())
                self._late("canonical")
            if "alternate" in rel and a.get("hreflang"):
                self.hreflang.append((a["hreflang"], a.get("href", "").strip()))
                self._late("hreflang")
            if "alternate" in rel and a.get("media") and a.get("href"):
                self.alt_media.append((a["media"], a["href"].strip()))
        elif tag in ("h1", "h2"):
            if tag == "h2":
                self.h2_count += 1
            self._hstack = (tag, [])
        elif tag == "a" and a.get("href", "").lower().startswith("tel:"):
            self.phones.add(_norm_phone(a["href"][4:]))
            self._a = {"href": a["href"].strip(), "anchor": [], "nofollow": False, "kind": "a", "alt": ""}
        elif tag == "a" and "href" in a:
            rel = (a.get("rel") or "").lower()
            self._a = {"href": a["href"].strip(), "anchor": [], "nofollow": "nofollow" in rel,
                       "kind": "a", "alt": "", "hidden": bool(self._hid)}
        elif tag == "img" and not self._in_noscript:  # пиксели счётчиков в <noscript> — не картинки
            src = a.get("src") or ""
            lazy = (a.get("loading") or "").lower() == "lazy"
            if not src or src.startswith("data:"):  # «ленивые» картинки: настоящий адрес в data-src
                real = a.get("data-src") or a.get("data-lazy-src") or a.get("data-original")
                if real:
                    src, lazy = real, True
            self._srcset(a.get("srcset") or a.get("data-srcset"))
            if src and not src.startswith("data:"):
                self.images.append({"src": src.strip(), "alt": a.get("alt"),  # None — атрибута alt нет вовсе
                                    "has_size": bool(a.get("width") and a.get("height")),
                                    "loading": "lazy" if lazy else (a.get("loading") or "").lower(),
                                    "in_picture": self._picture > 0,
                                    "srcset": bool(a.get("srcset") or a.get("data-srcset"))})
            if self._a is not None and a.get("alt"):
                self._a["anchor"].append(a["alt"])
                self._a["alt"] = a["alt"]

    def _srcset(self, value):
        """srcset="a.jpg 1x, a@2x.jpg 2x" — все варианты картинки проверяем, что они открываются."""
        for part in (value or "").split(","):
            u = part.strip().split(" ")[0] if part.strip() else ""
            if u and not u.startswith("data:"):
                self.resources.append({"src": u, "type": "srcset"})

    def _md_scope(self, tag, a):
        """Свойство itemprop - тому объекту (itemscope), внутри которого стоит; новый itemscope - объект, вложенный
        в текущий. Раньше свойства всей страницы складывались в один товар: на странице с несколькими товарами
        название одного и цена другого давали «разметка заполнена» (НА ПОТОМ)."""
        cur = self._mds[-1] if self._mds else None
        props = a.get("itemprop", "").split()
        if cur is not None and props:
            sc = self.md_scopes[cur]
            sc["props"].update(props)
            if "availability" in props and not sc["avail"]:
                sc["avail"] = a.get("href") or a.get("content") or ""
        if "itemref" in a:
            self.md_itemref = True   # свойства берутся по id из другого места страницы - объекты не разобрать
        if "itemscope" in a and tag not in _VOID:   # у элемента со своим itemprop свойство - родителю, сам он - новый объект
            types = {t.rstrip("/").rsplit("/", 1)[-1] for t in (a.get("itemtype") or "").split()}
            # via - каким свойством объект привязан к родителю: hasVariant (вариант товара) или isRelatedTo (похожий)
            self.md_scopes.append({"types": types, "props": set(), "avail": "", "parent": cur, "end": len(self._open),
                                   "via": set(props)})
            self._mds.append(len(self.md_scopes) - 1)

    def _close_to(self, tag, stop=()):
        """Закрыть открытый тег tag и всё, что открыто внутри него (незакрытые <span>, <li>). Тега нет или раньше
        встретился тег из stop (граница списка, таблицы) - ничего не закрываем."""
        for i in range(len(self._open) - 1, -1, -1):
            t = self._open[i][0]
            if t == tag:
                self._nhid -= sum(1 for _, h in self._open[i:] if h)
                del self._open[i:]
                self._hid = self._nhid > 0
                while self._mds and self.md_scopes[self._mds[-1]]["end"] > len(self._open):
                    self._mds.pop()   # элемент объекта microdata закрылся - объект кончился
                return
            if t in stop:
                return

    def _implied_close(self, tag):
        # теги, у которых закрывающий можно не писать: <li> закрывает прежний <li>, блок - открытый <p> и т. д.
        # Без этого незакрытый спрятанный <li style="display:none"> делал «спрятанными» все ссылки ниже
        for old, stop in _IMPLIED.get(tag, ()):
            self._close_to(old, stop)
        if tag in _CLOSES_P and self._open and self._open[-1][0] == "p":
            self._close_to("p")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self._flush()
            if self._hstack:
                self._hstack[1].append(" ")
        self._close_to(tag)
        if self._mdcap is not None and tag == self._mdcap[1]:
            self._mdcap[2] -= 1
            if self._mdcap[2] <= 0:
                t = " ".join(" ".join(self._mdcap[3]).split())[:150]
                if t:
                    self.md_text.setdefault(self._mdcap[0], t)
                self._mdcap = None
        if tag == "head":
            self._head_closed = True
            self._head_phase = False
        if tag == "script" and self._ld is not None:
            self._parse_ld("".join(self._ld))
            self._ld = None
        if tag == "picture" and self._picture:
            self._picture -= 1
        if tag in ("nav", "footer") and self._navfoot:
            self._navfoot -= 1
        if tag in self.SKIP_TEXT and self._skip:
            self._skip -= 1
        if tag == "noscript" and self._in_noscript:
            self._in_noscript -= 1
        if tag == "title" and self._in_title:
            self.titles.append(" ".join("".join(self._title_buf).split()))
            self._in_title = False
        elif self._hstack and tag == self._hstack[0]:
            text = " ".join("".join(self._hstack[1]).split())
            if tag == "h1":
                self.h1.append(text)
            self._hstack = None
        elif tag == "a" and self._a is not None:
            self._a["anchor"] = " ".join(" ".join(self._a["anchor"]).split())
            self.links.append(self._a)
            self._a = None

    def _parse_ld(self, raw):
        raw = raw.strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except ValueError:
            self.schema_errors += 1
            return

        def walk(x, depth=0):
            if depth > 3:
                return
            if isinstance(x, list):
                for y in x:
                    walk(y, depth)
            elif isinstance(x, dict):
                t = x.get("@type")
                types = [tt.rsplit("/", 1)[-1] for tt in (t if isinstance(t, list) else [t]) if isinstance(tt, str) and tt]
                self.schema_types.extend(types)
                if types:
                    self.ld_items.append((types, x))
                if "@graph" in x:
                    walk(x["@graph"], depth + 1)
        walk(data)

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._skip:
            return
        if self._mdcap is not None:
            self._mdcap[3].append(data)
        if self._hstack:
            self._hstack[1].append(data)
        if self._a is not None:
            self._a["anchor"].append(data)
        self.text_parts.append(data)
        self._blk.append(data)
        if not self._navfoot:
            self.content_parts.append(data)


def counters(html_text):
    """Счётчики на странице: {"ym": [номера Метрики], "ga": [...], "gtm": [...]}. JSON-строка; "{}" — счётчиков нет."""
    out = {}
    # шаблон ищем, только если на странице есть его обязательный кусок: поиск подстроки во много раз быстрее
    # шаблона по всей странице (33 мс на страницу товара thehome.ru в 570 КБ, а счётчиков там нет)
    has = lambda s: s in html_text   # noqa: E731
    ym = sorted({m for rx, s in zip(_YM, _YM_NEED) if has(s) for m in rx.findall(html_text)})
    if ym or ((has("mc.yandex.") or has("metrika/tag.js")) and _YM_ANY.search(html_text)):
        out["ym"] = ym or ["?"]
    ga = sorted({m for rx, s in zip(_GA, _GA_NEED) if has(s) for m in rx.findall(html_text)})
    if ga:
        out["ga"] = ga
    gtm = sorted(set(_GTM.findall(html_text))) if has("GTM-") else []
    if gtm:
        out["gtm"] = gtm
    return json.dumps(out)


_PRODUCT = {"Product", "IndividualProduct", "ProductModel", "ProductGroup", "Car", "Vehicle"}
_ORG = {"Organization", "LocalBusiness", "Store", "HomeAndConstructionBusiness", "HVACBusiness", "AutoPartsStore",
        "HardwareStore", "ProfessionalService", "EducationalOrganization", "LanguageSchool", "Corporation"}


def _has(x, *keys):
    for k in keys:
        v = x.get(k) if isinstance(x, dict) else None
        if v not in (None, "", [], {}):
            return True
    return False


def _offers(x):
    o = x.get("offers") if isinstance(x, dict) else None
    if isinstance(o, list):
        o = o[0] if o else None
    return o if isinstance(o, dict) else {}


def _last(v):
    v = str(v or "")
    return v.rstrip("/").rsplit("/", 1)[-1] if v else ""


def _texts(p, name, brand):
    """Название и бренд товара текстом (для брендов в семантике, когда H1 пустой): p["title"], p["brand"]."""
    if isinstance(brand, list):
        brand = brand[0] if brand else ""
    if isinstance(brand, dict):
        brand = brand.get("name") or ""
    for k, v in (("title", name), ("brand", brand)):
        v = " ".join(str(v or "").split())[:150] if isinstance(v, (str, int, float)) else ""
        if v:
            p[k] = v


def _md_product(md, av):
    """Сведения о товаре из набора свойств microdata md и значения availability av."""
    return {"src": "microdata", "name": "name" in md, "image": "image" in md,
            "price": bool({"price", "lowPrice"} & md), "currency": "priceCurrency" in md,
            "availability": _last(av) or ("?" if "availability" in md else ""),
            "rating": bool({"aggregateRating", "ratingValue"} & md),
            "offers": "offers" in md or "price" in md}


# вложенный товар, привязанный этими свойствами, - другой товар («похожие», «аксессуары»): его цена и валюта не
# про основной. Остальные вложенные товары (hasVariant - варианты ProductGroup, model) - часть основного
_MD_OTHER = {"isRelatedTo", "isSimilarTo", "isAccessoryOrSparePartFor", "isConsumableFor"}
_MD_OFFER = {"Offer", "AggregateOffer"}


def _md_products(ex):
    """[(свойства, availability)] каждого товара microdata, который не внутри другого товара: со свойствами вложенных
    объектов (Offer, AggregateRating, варианты hasVariant), кроме вложенных «похожих» товаров (_MD_OTHER), и с
    предложением вокруг товара (Offer → itemOffered → Product). Ревью кода: без вариантов и предложения
    вокруг правильная разметка давала ложное «Товар размечен без цены»."""
    from collections import deque
    scopes = ex.md_scopes
    kids = defaultdict(list)
    for i, sc in enumerate(scopes):
        if sc["parent"] is not None:
            kids[sc["parent"]].append(i)

    def in_product(i):
        p = scopes[i]["parent"]
        while p is not None:
            if scopes[p]["types"] & _PRODUCT:
                return True
            p = scopes[p]["parent"]
        return False
    out = []
    for i, sc in enumerate(scopes):
        if not sc["types"] & _PRODUCT or in_product(i):
            continue
        props, av, todo = set(sc["props"]), sc["avail"], deque(kids[i])
        while todo:
            k = todo.popleft()
            if scopes[k]["types"] & _PRODUCT and scopes[k]["via"] & _MD_OTHER:
                continue
            props |= scopes[k]["props"]
            av = av or scopes[k]["avail"]
            todo.extend(kids[k])
        p = sc["parent"]
        while p is not None and scopes[p]["types"] & _MD_OFFER:   # <div itemscope Offer>… itemOffered → Product
            props |= scopes[p]["props"] | {"offers"}
            av = av or scopes[p]["avail"]
            p = scopes[p]["parent"]
        out.append((props, av))
    return out


def schema_info(ex):
    """Что заполнено в микроразметке — то, без чего Яндекс и Google не покажут цену, наличие, звёзды и крошки.
    JSON: {"product": {"src": "json-ld"/"microdata", "name", "image", "price", "currency", "availability", "rating",
    "offers"}, "crumbs": пунктов в хлебных крошках, "org": {"name", "address", "phone"}, "faq": вопросов}."""
    info = {}
    for types, x in ex.ld_items:
        ts = set(types)
        if ts & _PRODUCT and "product" not in info:
            o = _offers(x)
            info["product"] = {"src": "json-ld", "name": _has(x, "name"), "image": _has(x, "image"),
                               "price": _has(o, "price", "lowPrice"), "currency": _has(o, "priceCurrency"),
                               "availability": _last(o.get("availability")), "rating": _has(x, "aggregateRating"),
                               "offers": bool(o)}
            _texts(info["product"], x.get("name"), x.get("brand") or x.get("manufacturer"))
        if "BreadcrumbList" in ts:
            items = x.get("itemListElement")
            info["crumbs"] = max(info.get("crumbs", 0), len(items) if isinstance(items, list) else 0)
        if ts & _ORG and "org" not in info:
            info["org"] = {"name": _has(x, "name"), "address": _has(x, "address"), "phone": _has(x, "telephone")}
        if "FAQPage" in ts:
            q = x.get("mainEntity")
            info["faq"] = len(q) if isinstance(q, list) else (1 if q else 0)
    md = set(ex.md_props)
    if set(ex.schema_types) & _PRODUCT and "product" not in info:
        prods = [] if ex.md_itemref else _md_products(ex)
        if len(prods) == 1:   # один товар - по объекту: его свойства, без «похожих товаров» внутри карточки
            info["product"] = _md_product(*prods[0])
        else:
            # несколько товаров (каталог или «похожие» рядом с карточкой - какой основной, по разметке не понять),
            # itemref или itemtype без itemscope - как раньше, по всей странице: так отчёт не строже, чем было, и
            # ложного «без цены» нет
            info["product"] = _md_product(md, ex.md_avail[0] if ex.md_avail else "")
            if len(prods) > 1:
                info["product"]["count"] = len(prods)
        _texts(info["product"], ex.md_text.get("name"), ex.md_text.get("brand"))
    if "BreadcrumbList" in ex.schema_types and "crumbs" not in info:
        info["crumbs"] = ex.md_props.count("itemListElement")
    return json.dumps(info, ensure_ascii=False)


class _Both(HTMLParser):
    """Одно чтение страницы для двух разборов (_Extractor и «Что мешает покупать»): теги и текст режутся один раз и
    отдаются обоим. Раньше каждый резал страницу сам - на странице товара thehome.ru в 570 КБ это ~60 мс лишнего
    на каждое чтение. Разбор, упавший с ошибкой, дальше ничего не получает - как раньше, когда его
    feed прерывался исключением, а второй читал страницу до конца."""

    NAMES = ("handle_starttag", "handle_startendtag", "handle_endtag", "handle_data")

    def __init__(self, *targets):
        super().__init__(convert_charrefs=True)
        self.targets = list(targets)
        self.failed = []   # «Facts: KeyError: 'x'» - какой разбор упал (parse_html → parse_errors)
        self._bind()

    def _bind(self):
        # методы целей заранее: событий на большой странице десятки тысяч
        self.fns = [[getattr(t, n) for t in self.targets] for n in self.NAMES]

    def _send(self, k, args):
        fns, i = self.fns[k], 0
        while i < len(fns):
            try:
                fns[i](*args)
                i += 1
            except Exception as e:   # упавший разбор больше ничего не получает, остальным - то же событие
                self.failed.append(f"{type(self.targets[i]).__name__.strip('_')}: {type(e).__name__}: {e}"[:200])
                del self.targets[i]
                self._bind()
                fns = self.fns[k]

    def handle_starttag(self, tag, attrs):
        self._send(0, (tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self._send(1, (tag, attrs))

    def handle_endtag(self, tag):
        self._send(2, (tag,))

    def handle_data(self, data):
        self._send(3, (data,))


def parse_html(body: bytes, content_type_header: str = "", light=False):
    """light - исходный HTML, когда страница успешно открылась в браузере с JavaScript и осталась на своём адресе:
    страницей тогда считается версия после скриптов (crawler/page.compare_js), а от исходной нужно только то, с чем
    её сравнивают (title, H1, canonical, robots, ссылки, текст, телефоны, ошибки в <head>). Цены и наличие,
    счётчики, разметка, блоки текста и отпечаток для неё не считаются (~110 мс на страницу товара)."""
    enc, enc_src = detect_encoding(body, content_type_header)
    text = body.decode(enc, errors="replace")
    ex = _Extractor()
    ex.light = light   # облегчённый разбор - без объектов microdata (schema_info для него не считается)
    sh = None if light else _ShopFacts()
    both = _Both(ex, sh) if sh else _Both(ex)
    try:
        both.feed(text)
        both.close()
    except Exception as e:   # страница разобрана до места сбоя; сбой - в parse_errors (crawler/page.handle → сбои.txt)
        both.failed.append(f"HTMLParser: {type(e).__name__}: {e}"[:200])
    ex._flush()
    if ex._a is not None:  # незакрытая ссылка
        ex._a["anchor"] = " ".join(" ".join(ex._a["anchor"]).split())
        ex.links.append(ex._a)
    visible = " ".join(" ".join(ex.text_parts).split())
    words = _WORD.findall(visible)
    refresh_url = ""
    if ex.refresh:
        m = re.search(r"url\s*=\s*['\"]?([^'\";]+)", ex.refresh, re.I)
        if m:
            refresh_url = m.group(1).strip()
    return {
        "encoding": enc, "encoding_source": enc_src,
        "bad_chars": text.count("�"),
        "titles": ex.titles, "descriptions": ex.descriptions, "h1": ex.h1,
        "h2_count": ex.h2_count, "canonicals": ex.canonicals, "robots": ex.robots,
        "refresh": ex.refresh, "refresh_url": refresh_url,
        "links": ex.links, "images": ex.images, "resources": ex.resources, "hreflang": ex.hreflang,
        "alt_media": ex.alt_media,
        "base": ex.base, "lang": ex.lang,
        "word_count": len(words),
        "content_words": len(_WORD.findall(" ".join(ex.content_parts))),
        "viewport": ex.viewport, "keywords": ex.keywords, "og": ex.og,
        "schema_types": sorted(set(ex.schema_types)), "schema_errors": ex.schema_errors,
        "schema_info": None if light else schema_info(ex),
        "counters": "{}" if light else counters(text),
        "calltrack": calltrack_services(text),
        "shop": "" if light else shop_facts(text, sh),
        "html_counts": ex.tag_counts,
        "dup_ids": sorted(k for k, v in ex.ids.items() if v > 1),
        "head_break": ex.head_break, "after_break": ex.after_break,
        "contacts": json.dumps(dict(zip(("phones", "addresses"), contacts(ex.blocks, ex.phones))), ensure_ascii=False),
        "blocks": None if light else zlib.compress("\n".join(ex.blocks).encode("utf-8"), 6),
        "text_sample": visible[:400],
        "text": visible,
        "minhash": "" if light else minhash(_WORD.findall(" ".join(ex.content_parts).lower())),
        "content_hash": hashlib.md5(visible.lower().encode("utf-8")).hexdigest() if visible else "",
        "parse_errors": both.failed,
    }
