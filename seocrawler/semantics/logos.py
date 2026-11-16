"""Бренды из блоков логотипов и свойства товаров из адресов сайта (пример -
fabrika-primer.ru: «Используем лучшую фурнитуру - бренды» и сетка логотипов Blum, Egger, Hettich, Boyard…; адреса
/katalog/izdelie-shkaf/vid-uglovoj, /material-mdf, /style-loft). Без нейросети и без списков брендов: только
устройство страницы.

Блок логотипов - подряд от RUN_MIN картинок из одной папки с короткими подписями (alt без слова «Бренд»,
«Логотип», иначе имя файла: blum.png). Брендами он считается, если есть хотя бы один признак:
- у всех подписей общее слово «Бренд», «Логотип», «Партнёр», «Производитель» («Бренд Blum»);
- над этими же названиями в тексте страницы - заголовок со словами бренд, партнёр, производитель, поставщик,
  комплектующие, фурнитура;
- папка или имена файлов со словами brand, logo, partner и названия в основном латиницей;
- со страницы есть ссылки на сайты с теми же названиями (blum.com у логотипа Blum).
Не бренды - клиенты, отзывы, сертификаты, награды, СМИ, способы оплаты и доставки, банки (слова в заголовке,
подписи или папке). Список названий в тексте под таким заголовком без картинок - тоже бренды, если больше половины
названий латиницей.

Свойства из адресов: часть адреса «приставка-значение» (izdelie-shkaf, material-mdf, style-loft) с одной приставкой
у RUN_MIN и больше значений, и значение есть словами в H1 этих страниц («Кухни из МДФ»). Название свойства - слово
сайта с тем же звучанием, что приставка («Материалы» = material), иначе приставка русскими буквами."""
import re
import sqlite3
import zlib
from urllib.parse import unquote, urlsplit

from .stem import sound

RUN_MIN = 4          # от стольких логотипов подряд - блок
SAMPLE = 60          # страниц на просмотр: главная, «О компании», «Бренды», страницы первого уровня
HEAD_UP = 3          # заголовок блока - не дальше стольких строк над первым названием
TRIGGER = re.compile(r"бренд|brand|партн[её]р|partner|производител|поставщик|vendor|manufactur", re.I)
PARTS = re.compile(r"комплектующ|фурнитур|материал|используем|работаем с|плит", re.I)
FOR_HEAD = re.compile(r"ремонт|обслужива|сервис|запчаст|чиним|для ", re.I)   # «Мы ремонтируем бренды» - марки
EXCL = re.compile(r"клиент|client|отзыв|review|сертифик|certif|диплом|наград|award|лиценз|license|\bсми\b|press|"
                  r"пресс|соцсет|social|оплат|payment|\bpay|card|доставк|delivery|банк|bank|рассрочк|кредит|"
                  r"мессенджер|messenger|магазин[аы]? приложений|app ?store|google ?play|дилер|dealer|установочн|"
                  r"сервисн\w* центр|филиал|офис", re.I)
PREFIX = re.compile(r"^(?:бренд|brand|логотип|logo|лого|партн[её]р|partner|производитель|поставщик|фабрика)"
                    r"(?![а-яa-z])[\s:.\-–]*", re.I)
PATH_HINT = re.compile(r"brand|logos/|partner|proizvod|postavsh|vendor|manufact", re.I)
# имя файла: служебные слова картинки - убрать («uppercut-red» → «uppercut»), значки и соцсети - не логотип бренда
FILE_MOD = {"white", "black", "light", "dark", "color", "colour", "red", "green", "blue", "grey", "gray", "round",
            "new", "full", "min", "small", "big", "mini", "main", "desktop", "mobile", "retina", "preview", "thumb",
            "img", "image", "pic", "sq", "square", "rgb", "svg", "png", "w", "b"}
FILE_BAD = re.compile(r"(?i)\b(?:icon|ico|flag|map|pin|bg|banner|slide|slider|arrow|footer|header|separator|"
                      r"telegram|whatsapp|viber|vk|vkontakte|youtube|facebook|instagram|twitter|tiktok|dzen|zen|ok|"
                      r"rutube|appstore|googleplay|appgallery|max|paysystem|phone|mail|del)\b")
ALL_RX = re.compile(r"(?i)^(?:все|all|показать|ещё|еще|more|другие|смотреть)(?![а-яa-z])")
PAGE_HINT = re.compile(r"about|o-kompanii|o-nas|kompaniya|company|brand|brend|partner|proizvod|postavsh|materia|"
                       r"furnitur|komplekt", re.I)
IMG_EXT = re.compile(r"(?:\.(?:png|jpe?g|svg|webp|gif|avif|bmp))+$", re.I)


def _short(s):
    """Похоже на название: 1-3 слова, до 30 букв, есть буква, без точки в конце."""
    s = (s or "").strip()
    return (0 < len(s) <= 30 and len(s.split()) <= 3 and re.search(r"[A-Za-zА-Яа-яЁё]", s)
            and not re.search(r"[.!?:;]$|\d{4,}", s))


def _lat(s):
    return bool(re.match(r"[A-Za-z]", s or ""))


def _file_name(src):
    """Название из имени файла: «blum.png», «logo-hettich.svg» → «blum», «hettich»; номера и хеши - нет."""
    f = IMG_EXT.sub("", unquote(urlsplit(src).path).rsplit("/", 1)[-1])
    f = re.sub(r"(?i)(?:^|[-_.])(?:logo|logotip|brand|partner)(?=$|[-_.])", "", f)
    f = re.sub(r"[-_.]?\d+(?:x\d+)?$", "", f).strip("-_. ")
    if not re.fullmatch(r"[A-Za-z][A-Za-z_-]{2,20}", f):
        return ""
    ws = [w for w in re.split(r"[-_]+", f) if w]
    if FILE_BAD.search(" ".join(ws)):
        return ""
    ws = [w for w in ws if w.lower() not in FILE_MOD]
    return " ".join(ws) if ws and len(" ".join(ws)) >= 3 else ""


def _img_name(src, alt):
    """(название, слово перед названием) по картинке: «Бренд Blum» → («Blum», «бренд»)."""
    a = re.sub(r"\s+", " ", alt or "").strip(" -–—|:.«»\"")
    pre = ""
    m = PREFIX.match(a)
    if m:
        pre = m.group(0).strip(" :.-–").lower()
        a = a[m.end():].strip(" -–—|:.«»\"")
    a = re.sub(r"(?i)\s+(?:логотип|logo)$", "", a)
    return (a if _short(a) else "") or _file_name(src), pre


def _key(src, pre):
    """Картинки одного блока: та же папка, то же расширение, то же слово перед названием."""
    p = urlsplit(src).path
    folder, _, f = p.rpartition("/")
    m = IMG_EXT.search(f)
    return folder, (m.group(0).lower() if m else ""), pre


def _lines(blob):
    try:
        return [x.strip() for x in zlib.decompress(blob).decode("utf-8").split("\n")] if blob else []
    except (zlib.error, UnicodeDecodeError):
        return []


def _head(lines, names):
    """Заголовок над этими названиями в тексте страницы ("" - названий подряд в тексте нет)."""
    low = [x.lower() for x in lines]
    want = [n.lower() for n in names]
    for i, x in enumerate(low):
        if x in want:
            run = 0
            for y in low[i:i + len(want) + 2]:
                run += y in want
            if run >= max(2, 0.6 * len(want)):
                return " · ".join(x for x in lines[max(0, i - HEAD_UP):i] if len(x.split()) <= 10)
    return ""


def _sample(db, host):
    """Страницы для поиска блоков логотипов: главная, «О компании», «Бренды», «Материалы» и первый уровень."""
    rows = db.execute("SELECT url FROM pages WHERE status=200 AND (content_type LIKE '%html%' OR content_type IS NULL)"
                      ).fetchall()
    own = [u for (u,) in rows if (urlsplit(u).hostname or "").removeprefix("www.") == host]
    path = lambda u: urlsplit(u).path.strip("/")  # noqa: E731
    home = [u for u in own if not path(u) and not urlsplit(u).query]
    hint = sorted((u for u in own if PAGE_HINT.search(path(u)) and path(u).count("/") <= 1), key=len)[:20]
    top = sorted((u for u in own if path(u) and "/" not in path(u) and not urlsplit(u).query), key=len)
    return list(dict.fromkeys(home + hint + top))[:SAMPLE]


def _ext_hosts(db, page):
    """Сайты, на которые ссылается страница: {звучание имени сайта} (blum.com → blum)."""
    out = set()
    try:
        r = db.execute("SELECT id FROM strs WHERE s=?", (page,)).fetchone()
        rows = db.execute("SELECT s.s FROM link_rows l JOIN strs s ON s.id=l.dst WHERE l.src=? AND l.internal=0",
                          (r[0],)).fetchall() if r else []
    except sqlite3.Error:
        try:
            rows = db.execute("SELECT dst FROM links WHERE src=? AND internal=0", (page,)).fetchall()
        except sqlite3.Error:
            rows = []
    for (d,) in rows:
        h = (urlsplit(d or "").hostname or "").removeprefix("www.").split(".")
        if len(h) >= 2:
            out.add(sound(h[-2].replace("-", "")))
    return out


def blocks(db, host):
    """Бренды из блоков логотипов и списков под заголовком «Бренды»: [(название, адрес страницы, заголовок,
    вид)], вид - "parts" (комплектующие и материалы: «Используем фурнитуру брендов»), "for" (марки, для которых
    услуги или товары: «Ремонтируем бренды») или "". Одно название - один раз (первая страница)."""
    if db is None:
        return []
    try:
        pages = _sample(db, host)
        if not pages:
            return []
        marks = ",".join("?" * len(pages))
        imgs = {}
        for p, src, alt in db.execute(f"SELECT page, src, alt FROM images WHERE page IN ({marks}) ORDER BY rowid",
                                      pages):
            imgs.setdefault(p, []).append((src or "", alt))
        texts = dict(db.execute(f"SELECT url, blocks FROM pages WHERE url IN ({marks})", pages).fetchall())
    except sqlite3.Error:
        return []
    found = {}

    def put(name, page, head, parts):
        k = name.lower()
        if k not in found:
            found[k] = (_case(name), page, head, "parts" if PARTS.search(parts) else "for" if FOR_HEAD.search(parts)
                        else "")
    for page in pages:
        lines = _lines(texts.get(page))
        runs, cur = [], []
        for src, alt in imgs.get(page, []):
            name, pre = _img_name(src, alt)
            k = _key(src, pre)
            if cur and (cur[-1][2] != k or not name):
                runs.append(cur)
                cur = []
            if name:
                cur.append((name, src, k))
        runs.append(cur)
        ext = None
        for run in runs:
            names = list(dict.fromkeys(n for n, _s, _k in run))
            if len(names) < RUN_MIN:
                continue
            folder, _ext, pre = run[0][2]
            head = _head(lines, names)
            if EXCL.search(head) or EXCL.search(pre) or EXCL.search(folder):
                continue
            if pre and TRIGGER.search(pre):    # «Бренд Blum», «Бренд Русский ламинат» - все названия
                for n in names:
                    put(n, page, head, head + " " + pre)
                continue
            names = _clean(names)
            if len(names) < RUN_MIN:
                continue
            lat = sum(map(_lat, names)) / len(names)
            # заголовок - ближайшая строка над названиями («Кофе по стране» под «Кофе по бренду» - не бренды),
            # и в списке больше половины латиницей, как у брендов
            ok = bool(head and TRIGGER.search(head.split(" · ")[-1])) and lat >= 0.5
            if not ok and lat >= 0.7 and PATH_HINT.search(folder + " " + " ".join(s for _n, s, _k in run)):
                ok = True
            if not ok:
                ext = _ext_hosts(db, page) if ext is None else ext
                ok = sum(1 for n in names if sound(n.replace(" ", "")) in ext) >= max(2, len(names) // 3)
            if ok:
                for n in names:
                    put(n, page, head, head)
        # список названий текстом под заголовком «Бренды» (без картинок)
        i = 0
        while i < len(lines):
            h = lines[i]
            if len(h.split()) <= 10 and TRIGGER.search(h) and not EXCL.search(h):
                items = []
                for y in lines[i + 1:i + 41]:
                    if not _short(y):
                        break
                    items.append(y)
                names = _clean(list(dict.fromkeys(items)))
                if len(names) >= RUN_MIN and sum(map(_lat, names)) > 0.5 * len(names):
                    for n in names:
                        put(n, page, h, h)
                    i += len(items)
            i += 1
    return list(found.values())


def _clean(names):
    """Названия блока без лишнего: значки и соцсети; в списке латиницей - русские фразы («Ремонт телефонов»,
    «Популярные линейки»). Одно слово почти во всех названиях («Коллекторы FAR», «Фитинги FAR») - это товары
    бренда, а не бренды: пусто."""
    names = [n for n in names if not FILE_BAD.search(n) and not ALL_RX.match(n)
             and not all(w in FILE_MOD for w in n.lower().split())]
    if not names:
        return []
    if sum(map(_lat, names)) > 0.5 * len(names):     # в списке латиницей русское - пункт меню («Каталог», «Назад»)
        names = [n for n in names if _lat(n)]
    cnt = {}
    for n in names:
        for w in set(re.findall(r"[a-zа-яё0-9]{2,}", n.lower())):
            cnt[w] = cnt.get(w, 0) + 1
    if len(names) >= RUN_MIN and any(c >= 0.6 * len(names) for c in cnt.values()):
        return []
    return names


def _case(name):
    """«ROYAL THERMO» → «Royal Thermo», «BAXI» → «Baxi»; короткое «TIM», «HEC» - как есть."""
    if name.isupper() and len(name.replace(" ", "")) > 3:
        return " ".join(w.capitalize() for w in name.split())
    return name


# ---------- свойства из адресов: /material-mdf, /style-loft

FACET = re.compile(r"^([a-z]{2,15})[-_]([a-z0-9][a-z0-9_-]{0,40})$")
FACET_SKIP = {"page", "sort", "order", "limit", "view", "brand", "brend", "filter", "tag", "tags", "id", "price",
              "utm", "amp", "lang", "city", "region", "color", "size", "p", "s", "n", "is", "apply", "set", "show",
              "kupit", "buy", "zakaz", "cena", "tsena"}
FACET_MAX = 80       # свойство с большим числом значений - не свойство (врачи, товары, адреса)
# предлог вместо названия свойства: /iz-ekokozhi/, /dlya-spalni/
PREP = {"iz": "Из чего", "dlya": "Для чего", "dlja": "Для чего", "bez": "Без чего", "pod": "Под что", "na": "На чём",
        "so": "С чем", "ot": "От чего", "po": "По чему", "v": "В чём"}
DETR = [("shch", "щ"), ("sch", "щ"), ("ija", "ия"), ("iya", "ия"), ("yo", "ё"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
        ("yu", "ю"), ("ya", "я"), ("iy", "ий"), ("yy", "ый"), ("yi", "ый"), ("ij", "ий"), ("oj", "ой"), ("ej", "ей"),
        ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"), ("i", "и"), ("j", "й"),
        ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"),
        ("u", "у"), ("f", "ф"), ("h", "х"), ("x", "х"), ("c", "ц"), ("y", "ы"), ("w", "в"), ("q", "к")]


def detranslit(s):
    out, i = "", 0
    while i < len(s):
        for a, b in DETR:
            if s.startswith(a, i):
                out += b
                i += len(a)
                break
        else:
            out += s[i]
            i += 1
    return out


def _snd(w):
    """Звучания: обычное и с «x» как «х» (prixozhaya = прихожая)."""
    out = {sound(w)}
    if "x" in w:
        out.add(sound(w.replace("x", "h")))
    return out


def _same(a, b):
    """Слово адреса и слово текста - одно слово (с другим окончанием: massiv = массива, style = стиль)."""
    for x in _snd(a):
        y = sound(b)
        if x == y:
            return True
        n = min(len(x), len(y))
        if n >= 4 and abs(len(x) - len(y)) <= 2:
            k = 0
            while k < n and x[k] == y[k]:
                k += 1
            if k >= max(4, max(len(x), len(y)) - 2):
                return True
    return False


def _phrase(slug, texts, vocab=None):
    """Как значение адреса написано в текстах: «mdf» → «МДФ», «na-vsyu-stenu» → «на всю стену»."""
    parts = [p for p in re.split(r"[-_]+", slug) if p]
    if not parts or len(parts) > 4:
        return ""
    seen = {}
    for t in texts:
        ws = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", t or "")
        for i in range(len(ws) - len(parts) + 1):
            if all(_same(p, w) for p, w in zip(parts, ws[i:])):
                f = " ".join(ws[i:i + len(parts)])
                seen[f] = seen.get(f, 0) + 1
    if not seen:
        return ""
    # то же слово в меню и заголовках сайта - в начальной форме: «массива» → «Массив», «спальню» → «спальня»
    if vocab:
        got = []
        for pt in parts:
            w = vocab.get(sound(pt)) or (vocab.get(sound(pt.replace("x", "h"))) if "x" in pt else None)
            if not w:
                break
            got.append(w)
        if len(got) == len(parts):
            f = " ".join(got)
            return f if f.isupper() and len(f) > 1 else f.lower()
    caps = [f for f in seen if f.isupper() and len(f) > 1]
    if caps:
        return max(caps, key=lambda f: seen[f])
    best = min(seen, key=lambda f: (len(f), -seen[f]))
    return best.lower() if not best.isupper() else best


def facets(rows, host, words=()):
    """Свойства из адресов: [(свойство, [(значение, страниц, пример адреса)])]. rows - [(адрес, H1, title)],
    words - слова сайта (заголовки, меню) для названия свойства и начальной формы значений."""
    vocab = {}
    for w in words:
        if len(w) >= 3:
            vocab.setdefault(sound(w.lower()), w if w.isupper() else w.lower())
    seg = {}
    for u, h1, title in rows:
        sp = urlsplit(u)
        if (sp.hostname or "").removeprefix("www.") != host or sp.query or IMG_EXT.search(sp.path) or \
                re.search(r"\.(?:pdf|docx?|xlsx?|zip|rar|mp4|css|js)$", sp.path, re.I):
            continue
        for part in sp.path.lower().split("/"):
            m = FACET.match(part)
            if m and m.group(1) not in FACET_SKIP and not re.fullmatch(r"[\d_-]+", m.group(2)):
                seg.setdefault(m.group(1), {}).setdefault(m.group(2), []).append((u, h1 or title or ""))
    out = []
    for pre, vals in sorted(seg.items(), key=lambda x: -len(x[1])):
        if len(vals) < RUN_MIN or len(vals) > FACET_MAX:
            continue
        # значение повторяется в разных адресах (material-mdf у шкафов, кухонь, прихожих), а не один товар
        # («kabel-zazhiganiya-123»); приставка - не начало H1 («gazovye-kotly» = «Газовые котлы» - это раздел)
        if sum(1 for us in vals.values() if len(us) >= 2) < 0.5 * len(vals):
            continue
        heads = [t for us in vals.values() for _u, t in us[:5]]
        starts = sum(1 for t in heads if (re.findall(r"[A-Za-zА-Яа-яЁё]+", t) or [""])[0] and
                     _same(pre, re.findall(r"[A-Za-zА-Яа-яЁё]+", t)[0].lower()))
        if starts >= 0.3 * len(heads):
            continue
        # приставка - часть названия, а не свойство: «Кровать дуб сонома» (dub-sonoma), «Кухня Барбара люкс»;
        # у свойства перед словом предлог или его нет вовсе: «Кухни из МДФ», «Шкаф в стиле лофт»
        glued = seen_ = 0
        for val, us in vals.items():
            first = re.split(r"[-_]+", val)[0]
            for _u, t in us[:3]:
                ws = [w.lower() for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", t)]
                for i in range(len(ws) - 1):
                    if _same(pre, ws[i]) and _same(first, ws[i + 1]):
                        seen_ += 1
                        glued += not (i and ws[i - 1] in ("в", "из", "для", "на", "с", "со", "по", "под", "от"))
                        break
        if pre not in PREP and seen_ and glued >= 0.5 * seen_:
            continue
        name = _facet_name(pre, words)
        if not name:
            continue
        named = []
        for val, us in vals.items():
            nm = _phrase(val, [t for _u, t in us[:40]], vocab)
            if nm and len(us) >= 2 and len(nm) >= 2:
                named.append((nm, len(us), us[0][0]))
        if len(named) < RUN_MIN or len(named) < 0.5 * len(vals):
            continue
        out.append((name, sorted(named, key=lambda x: -x[1])))
    return out


def _facet_name(pre, words):
    if pre in PREP:
        return PREP[pre]
    hits = {}
    for w in words:
        if len(w) >= 3 and re.fullmatch(r"[А-Яа-яЁё]+", w) and _same(pre, w.lower()):
            hits[w.lower()] = hits.get(w.lower(), 0) + 1
    if detranslit(pre) in hits:      # izdelie = «изделие», а не «изделий»
        return detranslit(pre)[:1].upper() + detranslit(pre)[1:]
    if hits:
        w = min(hits, key=lambda x: (-hits[x] // 3, len(x)))
        return w[:1].upper() + w[1:]
    return ""     # слова свойства на сайте нет: «tiggo-7-pro», «ethiopia-sidamo» - это серии и сорта, а не свойства


def site_words(db, pages):
    """Слова главной и меню (текст страниц) для названий свойств."""
    out = []
    try:
        marks = ",".join("?" * len(pages))
        for (b,) in db.execute(f"SELECT blocks FROM pages WHERE url IN ({marks})", pages):
            for line in _lines(b):
                if len(line.split()) <= 4:
                    out += re.findall(r"[А-Яа-яЁё]+", line)
    except sqlite3.Error:
        pass
    return out
