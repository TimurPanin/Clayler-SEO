"""Запросы доменов из Букварикса (bukvarix.com, бесплатно): по каким запросам сайт и конкуренты видны в Яндексе.

Откуда: файл «Анализ домена» с сайта Букварикса (msk_site.ru.csv: «Ключевое слово», частотность «Весь мир»,
«!Частотность», «Позиция в выдаче Яндекса») или бесплатный API (ключ free, без регистрации):
api.bukvarix.com/v1/site/?q=домен&region=ufa&format=csv. Регион - город выдачи Яндекса (msk, ufa, rus…).

Позиции в базах Букварикса не свежие (города обновляются раз в несколько месяцев), поэтому это ориентир:
по каким запросам сайт вообще виден и каких запросов конкурентов у него нет. Настоящие места - в Вебмастере.

Что показывается (вкладка «Видимость» на странице «Семантика», page/sembx.js):
- запросы раскладываются по группам семантики так же, как во «Разложить новые» (assign.py);
- у группы: по каким запросам сайт уже виден и на каком месте, и какие запросы есть у конкурентов, а у сайта нет;
- мусор (чужой город, название конкурента, чужая фирма или адрес, «скачать», стоп-слова) - в «Отсеяно»,
  вопросы («что такое», «кто это») - в «Статьи для блога», как в обычном сборе.
Хранится по сайту в «решения семантики/<сайт> - букварикс.json», поэтому не теряется при новой проверке."""
import csv
import io
import os
import re
import time
import urllib.parse
import urllib.request

from . import BU_RX, JUNK_RX, MAX_INFO_WORDS, City, norm, tokens
from .stem import sound
from .words import canon_city
from . import decisions
from .. import jsonfile, sysproxy

API = "https://api.bukvarix.com/v1/site/"
MAX_ROWS = 20000   # на домен; у небольших сайтов запросов сотни
REGIONS = [("msk", "Москва"), ("spb", "Санкт-Петербург"), ("rus", "Россия"), ("nsk", "Новосибирск"),
           ("ekb", "Екатеринбург"), ("kzn", "Казань"), ("nnv", "Нижний Новгород"), ("kry", "Красноярск"),
           ("che", "Челябинск"), ("sam", "Самара"), ("ufa", "Уфа"), ("rnd", "Ростов-на-Дону"), ("krr", "Краснодар"),
           ("oms", "Омск"), ("vrn", "Воронеж"), ("prm", "Пермь"), ("vlg", "Волгоград"), ("sar", "Саратов"),
           ("tmn", "Тюмень"), ("tom", "Томск"), ("minsk", "Минск"), ("nursul", "Астана")]
REGION_NAME = dict(REGIONS)
# чужая фирма или адрес: «ооо газовик», «улица менделеева 137» - если в запросе
# нет названия этого сайта, это запрос про другую фирму с похожим названием
NAV_RX = re.compile(r"(?<![а-яa-z])(ооо|оао|зао|ип|улица|ул|проспект|пр-т|реквизиты|инн|вакансии|режим работы|"
                    r"часы работы)(?![а-яa-z])")
NOTE = ("Данные Букварикса: запросы, по которым сайт был в первой полусотне Яндекса, когда Букварикс обновлял базу "
        "(города обновляются раз в несколько месяцев). Места примерные, точные - в Яндекс Вебмастере.")


def region_of(city):
    """Город семантики → код региона Букварикса; не нашёлся - вся Россия."""
    c = (canon_city(city) or "").lower().replace("ё", "е")
    for code, name in REGIONS:
        if name.lower().replace("ё", "е") == c:
            return code
    return "rus"


def site(u):
    """«https://www.Site.ru/page» → «site.ru»."""
    u = str(u or "").strip().lower()
    u = re.sub(r"^[a-z]+://", "", u).split("/")[0].split(":")[0]
    return u[4:] if u.startswith("www.") else u


# ---------- чтение

def _cols(head):
    """Номера колонок по заголовку Букварикса или None, если это не Букварикс."""
    h = [str(c or "").strip().strip('"').lower() for c in head]
    q = next((i for i, c in enumerate(h) if c in ("ключевое слово", "фраза", "keyword")), None)
    pos = next((i for i, c in enumerate(h) if "позиция" in c), None)
    if q is None or pos is None or not any("частотность" in c for c in h):
        return None
    exact = next((i for i, c in enumerate(h) if c.startswith("!")), None)
    freq = next((i for i, c in enumerate(h) if "частотность" in c and i != exact), None)
    return {"q": q, "pos": pos, "freq": freq, "exact": exact}


def _text(raw):
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def detect(raw):
    """Это выгрузка «Анализ домена» Букварикса?"""
    line = _text(raw[:4000]).split("\n", 1)[0]
    return bool(_cols(next(csv.reader([line], delimiter=";" if ";" in line else "\t"), [])))


def parse_text(text):
    """Текст CSV/TSV Букварикса → [[запрос, частотность, «!частотность», место], …]."""
    lines = text.splitlines()
    if not lines:
        return []
    delim = ";" if lines[0].count(";") >= lines[0].count("\t") else "\t"
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    c = _cols(rows[0]) if rows else None
    if not c:
        raise ValueError("это не выгрузка «Анализ домена» Букварикса: нет колонок «Ключевое слово» и «Позиция»")

    def num(r, k):
        try:
            return int(float(str(r[c[k]]).replace(" ", "").replace(",", "."))) if c[k] is not None else 0
        except (ValueError, IndexError):
            return 0
    out = {}
    for r in rows[1:]:
        if len(r) <= c["q"]:
            continue
        q = norm(str(r[c["q"]]))
        if not q or len(q) > 120 or q in out:
            continue
        out[q] = [q, num(r, "freq"), num(r, "exact"), num(r, "pos")]
        if len(out) >= MAX_ROWS:
            break
    return list(out.values())


def from_name(name):
    """«msk_gasmasterservis.ru.csv» → («gasmasterservis.ru», «msk»); не похоже - (None, None)."""
    b = re.sub(r"\.(csv|tsv|txt)$", "", os.path.basename(name or "").lower())
    b = re.sub(r"\s*\(\d+\)$", "", b)   # «… (1).csv» - второй раз скачанный файл
    m = re.match(r"([a-z]+)_(.+)$", b)
    if m and m.group(1) in REGION_NAME and "." in m.group(2):
        return site(m.group(2)), m.group(1)
    return (site(b), None) if re.fullmatch(r"[a-z0-9а-я.\-]+\.[a-zа-я]{2,}", b) else (None, None)


def fetch(domain, region):
    """Запросы домена через бесплатный API Букварикса."""
    url = API + "?" + urllib.parse.urlencode({"q": domain, "api_key": "free", "format": "csv", "region": region,
                                              "num": MAX_ROWS})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Clayler SEO"})
    try:
        ctx = None
        try:
            import ssl
            import truststore
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            pass
        with sysproxy.urlopen(req, timeout=60, context=ctx) as r:
            text = _text(r.read(30_000_000))
    except urllib.error.HTTPError as e:
        raise RuntimeError({402: "Букварикс: бесплатный лимит на сегодня исчерпан, попробуйте завтра или скачайте "
                                 "файл на сайте bukvarix.com",
                            429: "Букварикс просит паузу: слишком много запросов подряд, подождите минуту"}.get(
                                e.code, f"Букварикс ответил ошибкой {e.code}")) from None
    except OSError as e:
        raise RuntimeError(f"Букварикс не ответил ({str(e)[:80]})") from None
    return parse_text(text)


# ---------- хранение: по своему сайту, внутри - домены (свой и конкуренты)

def _path(host):
    return decisions.site_file(host, " - букварикс")


def load(host):
    d = jsonfile.load(_path(host))
    d.setdefault("domains", {})
    return d


def put(host, domain, region, rows, src):
    d = load(host)
    d["domains"][site(domain)] = {"region": region, "at": time.strftime("%d.%m.%Y"), "src": src, "rows": rows}
    decisions.save_site_file(host, " - букварикс", d, separators=(",", ":"))
    return d


def remove(host, domain):
    d = load(host)
    d["domains"].pop(site(domain), None)
    jsonfile.save(_path(host), d, separators=(",", ":"))
    return d


def add_file(host, name, raw, domain=None, region=None):
    """Файл Букварикса → в хранилище сайта. Домен и регион - из имени файла (msk_site.ru.csv), если не указаны."""
    rows = parse_text(_text(raw))
    fd, fr = from_name(name)
    domain, region = site(domain) or fd or site(host), region or fr or "msk"
    put(host, domain, region, rows, f"файл «{os.path.basename(name)}»")
    who = "ваш сайт" if domain == site(host) else domain
    return {"name": name, "kind": "bukvarix", "n": len(rows), "domain": domain, "region": region,
            "label": f"Букварикс, {who}, Яндекс {REGION_NAME.get(region, region)} - смотрите вкладку «Видимость»"}


def listing(host):
    own = site(host)
    return [{"domain": k, "own": k == own, "region": v["region"], "region_name": REGION_NAME.get(v["region"], v["region"]),
             "at": v["at"], "src": v["src"], "n": len(v["rows"]),
             "top10": sum(1 for r in v["rows"] if 0 < r[3] <= 10)}
            for k, v in sorted(load(host)["domains"].items(), key=lambda kv: (kv[0] != own, kv[0]))]


# ---------- разбор: по группам семантики

def _brand(domain):
    """Название из домена - звучанием латиницей: «gasmasterservis». Части через дефис («termo-ufa») не берутся:
    это обычные слова («термо»), запросы с ними - не про конкурента."""
    label = domain.split(".")[0].replace("-", "")
    return {sound(label)} if len(label) > 3 else set()


def _has(toks, names):
    """Есть ли в запросе название: по звучанию с допуском («газмастерсервис» ~ «gasmasterservis», «вигаз» ~ «vigas»)."""
    from difflib import SequenceMatcher
    for t in toks:
        if len(t) < 4:
            continue
        st = sound(t)
        for n in names:
            if st == n or len(n) >= 6 and SequenceMatcher(None, st, n).ratio() >= 0.85:
                return True
    return False


def drop_reason(q, own, rivals, city, cities, stop):
    toks = tokens(q)
    mine = _has(toks, own)
    if stop and (sw := set(toks) & stop):
        return "стоп-слово: " + ", ".join(sorted(sw))
    if len(toks) > MAX_INFO_WORDS:   # запросы настоящие (не подсказки), поэтому длиннее, чем при сборе
        return "слишком длинная фраза - не запрос"
    m = JUNK_RX.search(q) or BU_RX.search(q)
    if m:
        return "мусор: " + m.group(0).strip()
    if cs := cities.find(q) - {canon_city(city)}:   # в старой семантике город мог быть записан «СПб»
        return "другой город: " + ", ".join(sorted(cs))
    if not mine and _has(toks, rivals):
        return "название конкурента"
    if NAV_RX.search(q) and not mine:
        return "чужая фирма или адрес"
    return None


def build(data, host, d=None):
    """Семантика (с решениями) + данные Букварикса → вид для вкладки «Видимость»."""
    from . import assign as A
    from .words import load_stop
    from . import labels as L
    d = d or load(host)
    own = site(host)
    doms = d["domains"]
    if not doms:
        return {"domains": [], "groups": [], "regions": REGIONS, "region": region_of(data.get("city")), "note": NOTE,
                "quick": quick(data, [], host, d)}
    own_b = _brand(own)
    riv_b = set()
    for k in list(doms) + list(data.get("competitors") or []):
        if site(k) != own:
            riv_b |= _brand(site(k))
    riv_b -= own_b
    pool = {}   # запрос → {mine: место, rivals: {домен: место}, freq, exact}
    for dom, v in doms.items():
        for q, fr, ex, pos in v["rows"]:
            p = pool.setdefault(q, {"mine": 0, "rivals": {}, "freq": 0, "exact": 0})
            p["freq"], p["exact"] = max(p["freq"], fr), max(p["exact"], ex)
            if dom == own:
                p["mine"] = pos or 99
            else:
                p["rivals"][dom] = pos or 99
    from . import dictionary
    cities, stop = City(), set(load_stop()) | set(dictionary.junk_for(host, [r[0] for g in data.get("groups") or [] for r in g.get("q") or []]))
    dropped, keep = [], []
    for q, p in pool.items():
        why = drop_reason(q, own_b, riv_b, data.get("city"), cities, stop)
        if why:
            dropped.append({"q": q, "why": why, "mine": p["mine"], "rivals": p["rivals"], "freq": p["freq"]})
        else:
            keep.append({"q": q, "freq": p["exact"] or p["freq"]})
    # места по Вебмастеру из семантики - рядом, чтобы было видно, насколько данные Букварикса устарели
    wm, gmeta = {}, {}
    for i, g in enumerate(data.get("groups") or []):
        gmeta[g["name"]] = (i, g)
        for r in g.get("q") or []:
            if len(r) > 12 and r[12]:
                wm[r[0]] = r[12]
    groups = A.groups_from_semantics(data)
    placed = A.run(groups, keep, data=data) if groups else [dict(k, group=A.NONE, how="", topic="") for k in keep]
    out = {}
    for r in placed:
        p = pool[r["q"]]
        g = out.setdefault(r["group"], {"name": r["group"], "mine": [], "miss": [], "both": 0})
        row = {"q": r["q"], "freq": p["freq"], "exact": p["exact"], "mine": p["mine"], "rivals": p["rivals"],
               "wm": wm.get(r["q"], 0), "how": r.get("how") or "", "topic": r.get("topic") or ""}
        if p["mine"]:
            g["mine"].append(row)
            g["both"] += bool(p["rivals"])
        else:
            g["miss"].append(row)
    special = {A.ARTICLES: 1, A.GALLERY: 2, A.NONE: 3}
    res = []
    for name, g in out.items():
        i, sg = gmeta.get(name, (None, {}))
        g["mine"].sort(key=lambda r: (r["mine"], -r["freq"]))
        g["miss"].sort(key=lambda r: (-len(r["rivals"]), -r["freq"]))
        res.append(dict(g, idx=i, page=sg.get("page") or "", kind=sg.get("kind") or "", special=name in special,
                        top10=sum(1 for r in g["mine"] if r["mine"] <= 10),
                        demand=sum(r["exact"] or r["freq"] for r in g["miss"])))
    res.sort(key=lambda g: (special.get(g["name"], 0), -g["demand"], -len(g["mine"])))
    lst = listing(host)
    mine_all = [q for q, p in pool.items() if p["mine"]]
    return {"domains": lst, "groups": res, "dropped": sorted(dropped, key=lambda r: (r["why"], -r["freq"])),
            "regions": REGIONS, "region": region_of(data.get("city")), "note": NOTE, "own": own,
            "competitors": [site(c) for c in data.get("competitors") or []],
            "kinds": {k: v[0] for k, v in L.KIND.items()},
            "total": {"mine": len(mine_all), "top10": sum(1 for q in mine_all if pool[q]["mine"] <= 10),
                      "miss": sum(len(g["miss"]) for g in res if not g["special"]),
                      "rivals": len([x for x in lst if not x["own"]]), "dropped": len(dropped),
                      "articles": sum(len(g["mine"]) + len(g["miss"]) for g in res if g["name"] == A.ARTICLES)},
            "names": {"articles": A.ARTICLES, "gallery": A.GALLERY, "none": A.NONE}, "quick": quick(data, res, host, d)}


def visibility(data, host):
    """Видимость своего сайта в Яндексе по группам для «Запрос → страница»: {idx группы: [запросов, в десятке]},
    откуда и от какого числа. None - свой сайт в Букварикс не загружен: тогда «не виден» сказать нельзя."""
    d = load(host)
    v = d["domains"].get(site(host))
    if not v:
        return None
    import copy
    b = build(copy.deepcopy(data), host, d)   # build не должен менять семантику, которая уходит в окно
    return {"at": v["at"], "region": REGION_NAME.get(v["region"], v["region"]), "src": v["src"],
            "groups": {g["idx"]: [len(g["mine"]), g["top10"]] for g in b["groups"] if g["idx"] is not None and g["mine"]}}


# ---------- быстрые победы: запросы на 4-15 местах, страница уже есть

# Примерная доля кликов по месту в выдаче (средняя кликабельность обычной выдачи по открытым исследованиям,
# у каждого запроса своя): оценка, а не обещание
CTR = {1: .28, 2: .15, 3: .10, 4: .07, 5: .055, 6: .045, 7: .035, 8: .03, 9: .025, 10: .02}
QUICK_FROM, QUICK_TO, QUICK_TARGET = 4, 15, 3
QUICK_MIN = 10   # показов в месяц: меньше - не «хороший спрос»
QUICK_NOTE = ("Оценка: частота запроса в месяц, умноженная на разницу средней кликабельности 3-го места и "
              "нынешнего места (у 3-го места примерно 10 % кликов, у 4-го 7 %, у 10-го 2 %, ниже десятки около 1 %). "
              "У каждого запроса своя кликабельность (реклама, карты, колдунщики), поэтому числа примерные.")


def ctr(pos):
    p = int(round(pos))
    return CTR.get(p) or (.01 if p <= 15 else .005 if p <= 20 else 0)


def quick(data, groups, host, d=None):
    """Быстрые победы: запросы, где сайт на 4-15 месте (Вебмастер свежее, иначе Букварикс), у группы уже есть
    страница, спрос не меньше QUICK_MIN. Частота - по городу семантики из Директа (точная) или из файла
    частотности; нет - «!частотность» Букварикса по России, пересчитанная на город по запросам, где известны обе
    (или как есть, с пометкой). gain - сколько посетителей в месяц сайт недополучает против 3-го места.
    ads - сколько стоили бы в рекламе Яндекса посетители, которых сайт уже получает из поиска (места 1-15):
    посетители × цена клика наверху поиска из прогноза Директа (direct.ads, кнопка «Посчитать стоимость в рекламе»)."""
    from .. import direct
    lr, region = direct.region_of(data.get("city"))
    e = direct.load(host).get(str(lr)) or {}
    city_f = {k: v[0] for k, v in (e.get("phr") or {}).items()}
    fc = {k: v[0] for k, v in (e.get("fc") or {}).items()}
    fc_at = max((v[1] for v in (e.get("fc") or {}).values()), key=lambda s: s[6:] + s[3:5] + s[:2], default="")
    sem = {}   # запрос → (частота из семантики, группа)
    for i, g in enumerate(data.get("groups") or []):
        for r in g.get("q") or []:
            sem[r[0]] = (r[11] if len(r) > 11 else 0, i)
    cand = {}   # запрос → (группа, название, страница, место, откуда место, !частотность, можно в быстрые победы)
    for g in groups:
        for r in g["mine"]:
            cand[r["q"]] = (g["idx"], g["name"], g["page"], r["wm"] or r["mine"], "Вебмастер" if r["wm"] else "Букварикс",
                            r["exact"], bool(g["page"]) and not g["special"])
    for g in data.get("groups") or []:   # места по Вебмастеру из семантики - и без Букварикса
        for r in g.get("q") or []:
            if r[0] not in cand and len(r) > 12 and r[12]:
                cand[r[0]] = (sem[r[0]][1], g["name"], g.get("page") or "", r[12], "Вебмастер", 0, bool(g.get("page")))

    def city(q):
        x = city_f.get(direct._clean(direct.phrase(q)))
        return x if x is not None else (sem.get(q) or (0,))[0] or None
    exact = {q: e for v in (d or load(host))["domains"].values() for q, _f, e, _p in v["rows"] if e >= 10}
    pairs = sorted(c / e for q, e in exact.items() if (c := city(q)))
    ratio = pairs[len(pairs) // 2] if len(pairs) >= 5 and lr != 225 else None
    rows, seen = [], []
    for q, (idx, name, page, pos, psrc, exact, ok) in cand.items():
        if not 1 <= pos <= QUICK_TO:
            continue
        f, fsrc = city(q), "city"
        if f is None and exact:
            f, fsrc = (max(1, round(exact * ratio)), "calc") if ratio else (exact, "ru")
        price = fc.get(direct.ad_phrase(q))
        r = {"q": q, "group": name, "idx": idx, "page": page, "pos": pos, "psrc": psrc, "freq": f or 0, "fsrc": fsrc,
             "now": round((f or 0) * ctr(pos)), "cpc": price[0] if price else None}
        seen.append(r)
        if not ok or pos < QUICK_FROM or not f or f < QUICK_MIN:
            continue
        r["gain"] = round(f * (ctr(QUICK_TARGET) - ctr(pos)))
        if r["gain"] >= 1:
            rows.append(r)
    for r in seen:
        r["money"] = round(r["now"] * r["cpc"]) if r["cpc"] else None
        if "gain" in r:
            r["gmoney"] = round(r["gain"] * r["cpc"]) if r["cpc"] else None
    rows.sort(key=lambda r: -r["gain"])
    by = {}
    for r in rows:
        g = by.setdefault(r["group"], {"name": r["group"], "idx": r["idx"], "page": r["page"], "rows": [], "gain": 0,
                                       "gmoney": 0})
        g["rows"].append(r)
        g["gain"] += r["gain"]
        g["gmoney"] += r["gmoney"] or 0
    seen.sort(key=lambda r: (-(r["money"] or 0), -r["now"]))
    priced = [r for r in seen if r["money"]]
    want = [r["q"] for r in sorted(seen, key=lambda r: -r["now"]) if r["cpc"] is None and r["now"] >= 1]
    return {"rows": rows, "groups": sorted(by.values(), key=lambda g: -g["gain"]), "gain": sum(r["gain"] for r in rows),
            "gmoney": sum(r["gmoney"] or 0 for r in rows),
            "region": region, "ratio": ratio, "ru": sum(1 for r in rows if r["fsrc"] == "ru"),
            "calc": sum(1 for r in rows if r["fsrc"] == "calc"), "note": QUICK_NOTE,
            "ads": {"rows": priced, "money": sum(r["money"] for r in priced), "visitors": sum(r["now"] for r in priced),
                    "ru": sum(1 for r in priced if r["fsrc"] == "ru"), "at": fc_at, "left": len(want),
                    "want": want, "note": ADS_NOTE}}


ADS_NOTE = ("Сколько стоили бы в рекламе Яндекса посетители, которых сайт уже получает из поиска: посетители в месяц "
            "(частота × средняя кликабельность места) × цена клика при показе рекламы наверху поиска по прогнозу "
            "Яндекс Директа на месяц (нижняя цена входа в блок). Это оценка: показывает, сколько денег экономит "
            "сайту бесплатный трафик из поиска.")


FSRC = {"city": "по городу", "calc": "по городу, пересчитано из частоты по России", "ru": "по всей России"}


def quick_xlsx(q):
    """Быстрые победы (quick()) → строки листа «Быстрые победы» и пояснение под ним."""
    from ..fmt import num
    rows = [[r["group"], r["page"], r["q"], r["pos"], r["psrc"], r["freq"], FSRC[r["fsrc"]], r["now"], r["gain"],
             r.get("gmoney")] for g in q["groups"] for r in g["rows"]]
    note = [f"Запросы, где сайт на 4-15 месте, страница уже есть и запрос ищут не меньше {QUICK_MIN} раз в месяц. "
            f"Всего недополучаете примерно {num(q['gain'])} посетителей в месяц против 3-го места.", q["note"]]
    if q["calc"]:
        note.append(f"Частота «по городу, пересчитано»: точной частоты по городу нет, частота Букварикса по России "
                    f"умножена на долю города (примерно {str(round(q['ratio'] * 100, 1)).replace('.', ',')} %).")
    if q["ru"] and q["region"] != "Россия":
        note.append("Частота «по всей России»: для одного города посетителей будет меньше.")
    if q["gmoney"]:
        note.append(f"«В рекламе стоили бы» - столько в месяц пришлось бы платить Яндекс Директу за этих недополученных "
                    f"посетителей (всего примерно {num(q['gmoney'])} ₽).")
    return rows, note


def ads_xlsx(q):
    """Стоимость в рекламе (quick()["ads"]) → строки листа «Стоимость в рекламе» и пояснение."""
    from ..fmt import num
    a = q["ads"]
    rows = [[r["q"], r["group"], r["pos"], r["freq"], FSRC[r["fsrc"]], r["now"], r["cpc"], r["money"]] for r in a["rows"]]
    note = [f"Всего: примерно {num(a['money'])} ₽ в месяц стоили бы в рекламе {num(a['visitors'])} посетителей, "
            f"которых сайт уже получает из поиска.", a["note"]]
    if a["at"]:
        note.append(f"Цены клика - прогноз Яндекс Директа от {a['at']}.")
    if a["ru"]:
        note.append("Частота «по всей России»: для одного города сумма будет меньше.")
    return rows, note


def xlsx_rows(v):
    """Вид build() → (строки листа «Видимость» по группам, строки «Видимость - запросы», пояснение)."""
    pos = lambda p: p if p and p < 99 else ("есть" if p else "")   # noqa: E731
    riv = lambda r: ", ".join(f"{h} - {p}" if p < 99 else h for h, p in r["rivals"].items())   # noqa: E731
    kinds = v.get("kinds") or {}
    g_rows, q_rows = [], []
    for g in v["groups"]:
        g_rows.append([g["name"], kinds.get(g["kind"], ""), g["page"], len(g["mine"]), g["top10"], len(g["miss"]),
                       g["demand"], ", ".join(r["q"] for r in g["miss"][:8])])
        for r in g["mine"] + g["miss"]:
            q_rows.append([r["q"], g["name"], "виден" if r["mine"] else "нет, есть у конкурентов", pos(r["mine"]),
                           r["wm"] or "", riv(r), r["exact"], r["freq"]])
    for r in v.get("dropped") or []:
        q_rows.append([r["q"], "Отсеяно: " + r["why"], "виден" if r["mine"] else "нет", pos(r["mine"]), "", riv(r),
                       None, r["freq"]])
    from ..fmt import num
    from .labels import plural
    t = v["total"]
    note = [NOTE,
            "Загружено: " + "; ".join(f"{d['domain']}{' (ваш сайт)' if d['own'] else ''} - {num(d['n'])} "
                                      f"{plural(d['n'], 'query')}, Яндекс {d['region_name']}, {d['at']}" for d in v["domains"]),
            f"Ваш сайт виден по запросам: {num(t['mine'])}, в первой десятке - {num(t['top10'])}. Запросов конкурентов, "
            f"которых нет у вас: {num(t['miss'])}. Отсеяно (чужие города, фирмы, мусор): {num(t['dropped'])}.",
            "«!Частотность» - сколько раз в месяц ищут именно эту фразу по всей стране (данные Букварикса)."]
    return g_rows, q_rows, note
