"""Городские версии сайта: поддомены (pervouralsk.site.ru) и разделы (site.ru/spb/).

Как находим (режим «Сайт с городами»):
1. Названия городов — из переключателя города на главной (блок, где у элементов в id/class/name есть city,
   gorod, region, town, или рядом «Выберите город»). Текущий город (отмеченный) — город основного сайта.
2. Адрес каждого города — сначала среди ссылок главной (поддомен или раздел, в котором угадывается название
   города латиницей), иначе угадываем поддомен: pervouralsk, nizhniy-tagil, ntagil, tagil… и проверяем, что он
   открывается и не перенаправляет на основной сайт. Так находятся и города, куда ведёт только JavaScript.
Город в тексте ищем по «основе» названия (без окончания): «Первоуральск» → «первоуральск», «Нижний Тагил» → «тагил»,
чтобы находились «в Первоуральске», «Нижнем Тагиле».
"""
import html as H
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

_TR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
       "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
       "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
       "э": "e", "ю": "yu", "я": "ya"}
# Как города часто сокращают в адресах
ABBR = {"москва": ["msk", "moscow"], "санкт-петербург": ["spb", "piter"], "екатеринбург": ["ekb", "ekt", "ekburg"],
        "новосибирск": ["nsk", "novosib"], "нижний новгород": ["nn", "nnov"], "ростов-на-дону": ["rnd", "rostov"],
        "челябинск": ["chel", "chelyabinsk"], "краснодар": ["krd"], "красноярск": ["krsk"], "казань": ["kzn"],
        "набережные челны": ["chelny", "nchelny"], "великий новгород": ["vnov", "novgorod"]}
_SELECTOR = re.compile(r"(?:(?:id|class|name|for|data-[a-z-]+)\s*=\s*[\"'][^\"']*(?:city|gorod|region|town)[^\"']*[\"']"
                       r"|data-(?:city|region|gorod|town)[a-z_-]*\s*=\s*[\"'][^\"']*[\"'])", re.I)
_CITY_WORD = re.compile(r"^[А-ЯЁ][а-яё]+(?:[ -](?:[А-ЯЁ]?[а-яё]+))*$")
_NOT_CITY = {"выберите", "город", "ваш", "другой", "все", "закрыть", "да", "нет", "выбрать", "найти", "регион",
             "россия", "поиск", "показать", "продолжить", "верно", "угадали"}


def translit(s):
    return "".join(_TR.get(c, c) for c in s.lower())


def stem(word):
    """Основа слова без окончания: «первоуральск», «тагил», «москв», «казан»."""
    w = word.lower()
    for end in ("ский", "ской", "ская", "ое", "ий", "ый", "ая", "а", "я", "ь", "е", "и", "о", "ы", "у", "ю"):
        if w.endswith(end) and len(w) - len(end) >= 4:
            return w[:-len(end)]
    return w


def city_stems(city):
    """Основы для поиска города в тексте. Для «Нижний Тагил» — только «тагил» (Нижний бывает и Новгород)."""
    words = re.split(r"[ -]+", city)
    main = [w for w in words if w.lower() not in ("на", "нижний", "великий", "новый", "старый", "верхний")] or words
    return [stem(w) for w in main if len(w) >= 3]


def mentions(text, city):
    t = (text or "").lower().replace("ё", "е")
    return any(s.replace("ё", "е") in t for s in city_stems(city))


def slug_variants(city):
    """Как город может выглядеть в адресе: pervouralsk, nizhniy-tagil, nizhniytagil, ntagil, tagil, спец. сокращения."""
    c = city.lower().replace("ё", "е")
    words = [w for w in re.split(r"[ -]+", c) if w]
    tw = [translit(w) for w in words]
    out = ["-".join(tw), "".join(tw)]
    alt = [w.replace("iy", "ij").replace("yy", "yj") for w in tw]
    out += ["-".join(alt), "".join(alt), "-".join(w.replace("iy", "ii") for w in tw)]
    if len(tw) > 1:
        out += ["".join(w[0] for w in tw[:-1]) + tw[-1], tw[-1]]
    out += ABBR.get(c, [])
    seen, res = set(), []
    for v in out:
        v = re.sub(r"[^a-z0-9-]", "", v)
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res


def city_names(html):
    """Названия городов из переключателя города на странице: [(город, отмечен ли)].
    Для каждого элемента с city/gorod/region/town в атрибутах берём первый текст после него (вариант переключателя);
    у <select> — все <option>."""
    names = []
    for m in re.finditer(r"<select[^>]*" + _SELECTOR.pattern + r"[^>]*>(.*?)</select>", html, re.I | re.S):
        for om in re.finditer(r"<option([^>]*)>([^<]{2,40})<", m.group(1)):
            names.append((" ".join(H.unescape(om.group(2)).split()), "selected" in om.group(1)))
    for m in _SELECTOR.finditer(html):
        t = re.search(r">\s*([^<>\s][^<>]{1,39}?)\s*<", html[m.end(): m.end() + 800])
        if t:
            txt = " ".join(H.unescape(t.group(1)).split())
            pre = html[m.start(): m.end() + t.start()]
            names.append((txt, bool(re.search(r"\bchecked\b|\bselected\b|is-active|_active\b|current", pre, re.I))))
    seen, out = {}, []
    for n, cur in names:
        if not (_CITY_WORD.match(n) and n.lower() not in _NOT_CITY and not any(w in _NOT_CITY for w in n.lower().split())):
            continue
        if n not in seen:
            seen[n] = len(out)
            out.append((n, cur))
        elif cur:
            out[seen[n]] = (n, True)
    if sum(1 for _, c in out if c) > 1:  # «отмечено» у нескольких — не понять, какой основной
        out = [(n, False) for n, _ in out]
    return out if len(out) >= 2 else []


def match_link(city, links, root):
    """Адрес города среди ссылок: поддомен или раздел, где есть название латиницей. Возвращает адрес или None."""
    vs = slug_variants(city)
    for u in links:
        p = urlsplit(u)
        h = (p.hostname or "").lower()
        if h.endswith("." + root) and h != "www." + root:
            label = h[: -len(root) - 1]
            if label in vs:
                return f"{p.scheme}://{h}/"
        elif h in (root, "www." + root):
            seg = p.path.strip("/").split("/")[0].lower()
            if seg and seg in vs:
                return f"{p.scheme}://{h}/{seg}/"
    return None


def guess_subdomain(city, root, scheme, fetch):
    """Угадать поддомен города. fetch(url) → (код, конечный адрес). Возвращает адрес или None."""
    hosts = [f"{v}.{root}" for v in slug_variants(city)]
    port = 443 if scheme == "https" else 80

    def resolves(host):
        try:
            socket.getaddrinfo(host, port)
            return True
        except OSError:
            return False
    # все варианты разом: несуществующий поддомен DNS иногда отвергает только через 10-11 с (так у пользователя),
    # по очереди это минута на город
    with ThreadPoolExecutor(max_workers=len(hosts) or 1) as pool:
        ok = list(pool.map(resolves, hosts))
    for host, good in zip(hosts, ok):
        if not good:
            continue
        try:
            code, final = fetch(f"{scheme}://{host}/")
        except Exception:
            continue
        fh = (urlsplit(final or "").hostname or "").lower()
        if code == 200 and fh == host:
            return f"{scheme}://{host}/"
    return None


MAX_MISSES = 12   # первые столько городов подряд не нашлись (ни ссылки, ни поддомена) - городских версий нет
MAX_SECONDS = 180  # угадывать поддомены не дольше: дальше - только по ссылкам главной


def discover(start_url, html, links, fetch, log=print, stop=None, progress=None):
    """Городские версии сайта. Возвращает [{"city", "url", "how", "main"}] или [].
    stop() - нажата «Остановить» (поиск прерывается сразу), progress(сделано, всего) - для окна.
    Поддомены угадываются запросами, это долго: если первые MAX_MISSES городов не нашлись ни ссылкой, ни
    поддоменом, дальше не ищем (klimat-primer.ru: переключатель со всеми регионами России, час перебора впустую)."""
    names = city_names(html)
    if not names:
        log("   Переключатель города на главной не найден - сайт проверяется как обычно.")
        return []
    sp = urlsplit(start_url)
    root = (sp.hostname or "").lower()
    root = root[4:] if root.startswith("www.") else root
    out = []
    main_city = next((n for n, cur in names if cur), None)
    # сервер отвечает на любой поддомен (wildcard) — угадывать нельзя: «найдётся» любой город
    wildcard = guess_subdomain("Zzqx Nosuchcity", root, sp.scheme, fetch) is not None
    t0, late = time.time(), False
    misses = 0
    for n, (city, cur) in enumerate(names, 1):
        if stop and stop():
            log("   Поиск городов прерван: нажата «Остановить».")
            return []
        if progress:
            progress(n, len(names))
        if city == main_city:
            out.append({"city": city, "url": f"{sp.scheme}://{sp.hostname}/", "how": "основной сайт", "main": True})
            continue
        u = match_link(city, links, root)
        how = "ссылка на сайте"
        if not u and not late and time.time() - t0 > MAX_SECONDS:
            late = True
            log(f"   Угадываю поддомены городов уже {MAX_SECONDS // 60} мин - дальше ищу только по ссылкам главной.")
        if not u:
            u = None if (wildcard or late) else guess_subdomain(city, root, sp.scheme, fetch)
            how = "адрес угадан: ссылки нет (переключатель на JavaScript)"
        if u:
            out.append({"city": city, "url": u, "how": how, "main": False})
            misses = 0
        else:
            log(f"   Город «{city}»: не нашёл его адрес - ни ссылки, ни поддомена.")
            misses += 1
            if misses >= MAX_MISSES and not any(not r["main"] for r in out):
                log(f"   Первые {MAX_MISSES} городов из {len(names)} не нашлись - городских версий, похоже, нет, "
                    "дальше не ищу. Сайт проверяется как обычно.")
                return []
    if not main_city:  # отмеченный город не определился — основной сайт отдельной строкой
        out.insert(0, {"city": "", "url": f"{sp.scheme}://{sp.hostname}/", "how": "основной сайт", "main": True})
    found = [r for r in out if not r["main"]]
    log(f"   Городов в переключателе: {len(names)}; адреса найдены: "
        + (", ".join(f"{r['city']} - {r['url']}" for r in found) or "нет") + ".")
    return out if found else []


def region_of(url, regions):
    """К какому городу относится адрес: самый длинный подходящий адрес города. Возвращает запись или None."""
    best = None
    h = (urlsplit(url).hostname or "").lower()
    for r in regions:
        ru = urlsplit(r["url"])
        rh = (ru.hostname or "").lower()
        same = h == rh or (h.startswith("www.") and h[4:] == rh) or (rh.startswith("www.") and rh[4:] == h)
        if not same or not urlsplit(url).path.startswith(ru.path or "/"):
            continue
        if not best or len(ru.path) > len(urlsplit(best["url"]).path):
            best = r
    return best
