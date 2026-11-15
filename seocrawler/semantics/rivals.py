"""Конкуренты для семантики, когда пользователь их не выбрал: программа ищет главные разделы сайта в обычной выдаче
(DuckDuckGo, без ключей) и берёт сайты, которые встречаются чаще всего. Агрегаторы, СМИ, справочники и рейтинги
(«топ-10 школ») пропускаются. У найденных сайтов разделы берутся из меню главной страницы (и одной страницы
каталога, если она есть) — без полной проверки, за пару запросов на сайт. Их разделы становятся семенами
семантики, и появляются группы, которых на вашем сайте нет (красные на карте спроса).
Ответы выдачи и меню запоминаются в папке проверки на 30 дней."""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from urllib.parse import urlsplit

from .suggest import UA
from .. import jsonfile, sysproxy
from .words import SERVICE_NAMES

CACHE_NAME = ".семантика_конкуренты.json"
CACHE_DAYS = 30
SEARCH = "https://html.duckduckgo.com/html/?q={q}&kl=ru-ru"
MAX_QUERIES = 10      # столько главных разделов ищем в выдаче
MAX_RIVALS = 3
MIN_HITS = 2          # сайт встретился хотя бы по двум запросам
MAX_SECTIONS = 80
PAUSE = 1.2

# не конкуренты: поисковики, площадки, справочники, СМИ, соцсети, отзывы, вакансии
NOT_RIVAL = re.compile(
    r"(^|\.)(yandex|ya|google|bing|duckduckgo|wikipedia|wiki|youtube|youtu|vk|ok|mail|rambler|dzen|zen|t|telegram|"
    r"instagram|facebook|twitter|x|tiktok|pinterest|avito|ozon|wildberries|wb|aliexpress|market|megamarket|sbermegamarket|"
    r"lamoda|dns-shop|citilink|mvideo|eldorado|leroymerlin|petrovich|vseinstrumenti|2gis|zoon|yell|flamp|otzovik|"
    r"irecommend|otzyvru|pikabu|habr|vc|rbc|ria|tass|lenta|gazeta|kp|aif|mk|iz|kommersant|vedomosti|banki|sravni|"
    r"hh|superjob|rabota|zarplata|profi|youdo|uslugio|tripadvisor|booking|ostrovok|tutu|drom|auto|cian|domclick|"
    r"pulscen|tiu|satom|blizko|all-companies|list-org|rusprofile|checko|spark-interfax|kursly|schoolrate|"
    r"markakachestva|study|tutortop|skillbox-reviews|reviewdetector|startpack|apteka|uteka|eapteka|"
    r"gosuslugi|nalog|consultant|garant|stackoverflow|reddit|quora|livejournal|blogspot|wordpress|tildacdn)\.[a-z]+$")
LISTICLE = re.compile(r"(top|luchsh|rejting|reyting|rating|obzor|review|otzyv|sravn|kak-vybrat|article|blog|news|novost|"
                      r"stati|statya|journal|zhurnal|/a/|/post)", re.I)
NOT_SECTION_URL = re.compile(r"/(blog|news|novosti|stati|articles?|o-kompanii|company|about|kontakty|contacts?|"
                             r"politika|privacy|reviews|otzyvy|login|auth|cart|basket|korzina|search|poisk|personal|"
                             r"lk|account|vakansii|jobs?)\b", re.I)
# пункты меню, которые не раздел: новости, вакансии, акции, «перейти», «подробнее»
MENU_NOISE = re.compile(r"(?<![а-яёa-z])(наш[аие]? |новост|вакансии|работа у нас|карьера|предложени|акци|скидк|горящ|ссылк|перейти|подробн|"
                        r"смотреть|читать|сми|видео|фото|отзыв|блог|статьи|мероприят|события|день открытых|дни открытых|"
                        r"контакт|о нас|о компании|о школе|партн[её]р|франшиз|документ|лицензи|реквизит|оплат|доставк|"
                        r"войти|вход|регистрац|личный кабинет|корзин|поиск|вопрос|faq|помощь|англ\.|eng$|rus$)", re.I)
CATALOG_ANCHOR = re.compile(r"^(каталог|весь каталог|все товары|продукция|услуги|все услуги|направления|курсы|"
                            r"программы|все курсы|товары)$", re.I)


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"})
    with sysproxy.urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000)
        enc = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(enc, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _host(u):
    h = (urlsplit(u).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


class Cache:
    def __init__(self, folder):
        self.path = os.path.join(folder, CACHE_NAME)
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}
        old = time.time() - CACHE_DAYS * 86400
        self.data = {k: v for k, v in self.data.items() if v.get("t", 0) > old}

    def get(self, key):
        v = self.data.get(key)
        return v["v"] if v else None

    def put(self, key, value):
        self.data[key] = {"t": time.time(), "v": value}
        try:
            jsonfile.save(self.path, self.data)
        except OSError:
            pass


def search(q, cache):
    """Адреса из выдачи DuckDuckGo по порядку (до 30)."""
    key = "s:" + q
    hit = cache.get(key)
    if hit is not None:
        return hit
    page = _get(SEARCH.format(q=urllib.parse.quote(q)))
    urls = []
    for m in re.finditer(r"uddg=([^&\"']+)", page):
        u = urllib.parse.unquote(m.group(1))
        if u.startswith("http") and u not in urls:
            urls.append(u)
    urls = [u for u in urls if "duckduckgo.com" not in u][:30]
    cache.put(key, urls)
    time.sleep(PAUSE)
    return urls


def find(own_host, phrases, city_word, folder, log=print):
    """[(host, сколько запросов, пример адреса)] — самые частые сайты в выдаче по главным разделам."""
    cache = Cache(folder)
    hits, ranks, sample, listicle = defaultdict(set), defaultdict(list), {}, defaultdict(int)
    done = 0
    for ph in phrases[:MAX_QUERIES]:
        q = f"{ph} {city_word}".strip()
        try:
            urls = search(q, cache)
        except Exception as e:
            log(f"  выдача не ответила на «{q}»: {str(e)[:80]}")
            continue
        done += 1
        for i, u in enumerate(urls):
            h = _host(u)
            if not h or h == own_host or h.endswith("." + own_host) or NOT_RIVAL.search(h):
                continue
            if LISTICLE.search(urlsplit(u).path):
                listicle[h] += 1
            hits[h].add(ph)
            ranks[h].append(i)
            sample.setdefault(h, u)
    out = []
    for h, qs in hits.items():
        if len(qs) < MIN_HITS or listicle[h] > len(ranks[h]) / 2:  # в выдаче в основном статьи и рейтинги
            continue
        out.append((h, len(qs), sum(ranks[h]) / len(ranks[h]), sample[h]))
    out.sort(key=lambda x: (-x[1], x[2]))
    return [(h, n, u) for h, n, _r, u in out[:MAX_RIVALS]], done


def _links(page, base):
    for m in re.finditer(r"<a\b[^>]*?href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", page, re.S | re.I):
        href, text = m.group(1), m.group(2)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"\s+", " ", text).strip()
        yield urllib.parse.urljoin(base, html.unescape(href)), text


def ascii_name(host):
    try:
        return host.encode("idna").decode()
    except UnicodeError:
        return host


def sections(host, folder, log=print):
    """Разделы сайта по меню главной (и одной страницы каталога): в том же виде, что seeds.load()."""
    cache = Cache(folder)
    key = "m:" + host
    hit = cache.get(key)
    if hit is None:
        hit = []
        for scheme in ("https", "http"):
            try:
                try:
                    ascii_host = host.encode("idna").decode()  # сайт.рф → xn--…
                except UnicodeError:
                    ascii_host = host
                base = f"{scheme}://{ascii_host}/"
                page = _get(base)
                hit = [[u, t] for u, t in _links(page, base)]
                cat = next((u for u, t in hit if CATALOG_ANCHOR.match(t) and _host(u) == ascii_host), None)
                if cat:
                    time.sleep(PAUSE)
                    try:
                        hit += [[u, t] for u, t in _links(_get(cat), cat)]
                    except Exception:
                        pass
                break
            except Exception as e:
                log(f"  {host}: главная не открылась ({str(e)[:60]})")
        cache.put(key, hit)
    count, name = defaultdict(int), {}
    for u, t in hit:
        sp = urlsplit(u)
        if _host(u) not in (host, ascii_name(host)) or sp.query or sp.path in ("", "/") or NOT_SECTION_URL.search(sp.path):
            continue
        if not t or len(t) > 60 or re.search(r"\d", t) or not 1 <= len(t.split()) <= 6 or SERVICE_NAMES.match(t)                 or MENU_NOISE.search(t) or t.endswith("!"):
            continue
        if len([x for x in sp.path.split("/") if x]) > 3:
            continue
        clean = sp._replace(fragment="").geturl()
        count[clean] += 1
        name.setdefault(clean, t)
    secs = [{"name": name[u], "url": u, "links": n, "h1": "", "parent": None} for u, n in count.items()]
    secs.sort(key=lambda s: (-s["links"], len(s["url"])))
    by_name = {}
    for s in secs:
        by_name.setdefault(s["name"].lower(), s)
    secs = list(by_name.values())[:MAX_SECTIONS]
    urls = sorted(secs, key=lambda s: -len(s["url"]))
    for s in secs:
        s["parent"] = next((p["name"] for p in urls if p is not s and s["url"].startswith(p["url"])
                            and len(p["url"]) < len(s["url"])), None)
    return {"site": f"https://{host}/", "host": host, "city": None, "brand": [host.split(".")[0]],
            "sections": secs, "folder": None, "light": True}
