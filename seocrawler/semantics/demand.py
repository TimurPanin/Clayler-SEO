"""Вкладка «Спрос» на странице «Семантика»: что ещё можно бесплатно узнать из Вордстата через API Директа (direct.py).

- Узнаваемость: сколько раз в месяц ищут сайт и конкурентов по названию (город семантики и вся Россия).
- Местный спрос: главные запросы в городе и по России; доля города заметно выше обычной для ниши - местный запрос
  (нужна страница под город), заметно ниже - ищут по всей стране.
- Своя сезонность: Вордстат через Директ даёт цифру только за последний месяц, поэтому раз в месяц программа
  запоминает точную частоту главных запросов (season_auto, пока окно открыто); через несколько месяцев - график.
- ВЧ/СЧ/НЧ относительно ниши: ВЧ - запросы, которые вместе дают первую половину спроса ниши, СЧ - до 80 %,
  НЧ - остальное (levels). Метка видна у числа в группе (direct.apply кладёт пороги в data["direct"]["levels"]).
- Что ещё искали (SearchedAlso): приходит в каждом отчёте загрузки частотности бесплатно (direct хранит "also"),
  для старых загрузок - дозагрузка по главным запросам. Новое раскладывается по группам (assign.run, как
  «Разложить новые»): дополнить группу, новые темы (идеи разделов), вопросы (идеи статей).
- Ёлочка: хвосты главных фраз ниши (SearchedWith, без кавычек), затем второй круг с минус-словами - самыми частыми
  словами найденных хвостов, чтобы Вордстат показал то, что пряталось за ними. Новые запросы - туда же.

Фразы для Вордстата тратят тот же суточный лимит (direct.DAY_LIMIT), что и загрузка точной частотности, поэтому
перед каждым действием окно показывает, сколько фраз уйдёт. Задания выполняются по очереди в одном потоке
(рядом с загрузкой частотности), по 10 фраз в отчёте; лимит кончился - ждут следующего дня (по Москве).
Итог - на сайт: «решения семантики/<сайт> - спрос.json», не теряется при новой проверке и новом сборе."""
import datetime
import os
import re
import sqlite3
import threading
import time

from .. import direct, jsonfile

_lock = threading.Lock()
QUEUE = []                 # задания по очереди: {host, kind, label, items: [(фраза, регион)], total}
RUN = {"state": "idle"}    # {state: idle|running|waiting|error, msg, label}
_thread = None
RF = 225                   # вся Россия
MAX_NAMES = 4              # названий на один сайт


# ---------- хранение

def _path(host):
    from . import decisions
    return decisions.site_file(host, " - спрос")


def load(host):
    return jsonfile.load(_path(host))


def _change(host, fn):
    from . import decisions
    with _lock:
        d = load(host)
        fn(d)
        decisions.save_site_file(host, " - спрос", d, indent=0)


def _day():
    return time.strftime("%d.%m.%Y")


def when(dates):
    """Даты загрузки («07.10.2026») → подпись у цифр: «17.10.2026» или «с 07.10.2026 по 17.10.2026». Пусто - не загружалось."""
    ds = sorted({d for d in dates if d and len(d) == 10}, key=lambda s: s[6:] + s[3:5] + s[:2])
    return "" if not ds else ds[0] if len(ds) == 1 else f"с {ds[0]} по {ds[-1]}"


# ---------- очередь заданий

def enqueue(host, kind, label, items):
    """Поставить задание в очередь. items - [(фраза для Вордстата, регион)]. Возвращает ошибку или ""."""
    global _thread
    if not direct._cfg().get("token"):
        return "Сначала вставьте ключ Директа: Подключения → Яндекс Директ."
    if not items:
        return "Всё уже загружено."
    with _lock:
        if any(t["host"] == host and t["kind"] == kind for t in QUEUE):
            return "Это уже в очереди."
        QUEUE.append({"host": host, "kind": kind, "label": label, "items": list(items), "total": len(items)})
        if not (_thread and _thread.is_alive()):
            _thread = threading.Thread(target=_loop, daemon=True)
            _thread.start()
    return ""


def cancel(host):
    with _lock:
        for t in QUEUE:
            if t["host"] == host:
                t["items"] = []   # текущий отчёт дойдёт, остальное - нет
    return ""


def _wait_day(soon):
    t = datetime.datetime.now(direct.MSK)
    nxt = (t + datetime.timedelta(hours=1)) if soon else \
        datetime.datetime.combine(t.date() + datetime.timedelta(days=1), datetime.time(0, 10), direct.MSK)
    until = nxt.astimezone().strftime("%d.%m в %H:%M")
    RUN.update(state="waiting", msg=f"Лимит Яндекса на сегодня исчерпан, продолжу {until}.")
    while datetime.datetime.now(direct.MSK) < nxt and any(t["items"] for t in QUEUE):
        time.sleep(30)


def _loop():
    while True:
        with _lock:
            while QUEUE and not QUEUE[0]["items"]:
                QUEUE.pop(0)
            if not QUEUE:
                RUN.update(state="idle", msg="", label="")
                return
            t = QUEUE[0]
        lr = t["items"][0][1]
        room = direct.DAY_LIMIT - direct.used_today()
        if room <= 0:
            _wait_day(False)
            continue
        part = [x for x in t["items"] if x[1] == lr][:min(direct.BATCH, room)]
        RUN.update(state="running", label=t["label"], msg="", done=t["total"] - len(t["items"]), total=t["total"])
        day_err = None
        try:
            got = direct.report_full([p for p, _ in part], lr)
        except direct.DirectError as e:
            if e.code in direct.DAY_ERRORS:
                soon = direct.used_today() <= len(part)
                if not soon:
                    direct._put(day=direct._today(), used=direct.DAY_LIMIT)
                _wait_day(soon)
                continue
            if len(part) > 1 and e.code > 0:   # мешает одна фраза - по одной
                got, tried = {}, []
                for x in part:
                    try:
                        got.update(direct.report_full([x[0]], lr))
                    except direct.DirectError as e1:
                        if e1.code <= 0 or e1.code in direct.DAY_ERRORS:
                            # лимит или связь: остальные фразы остаются в очереди. Раньше они снимались с очереди
                            # и записывались нулём показов, как будто их не ищут (24.10.2026)
                            day_err = e1.code in direct.DAY_ERRORS
                            break
                    tried.append(x)   # загружена или плохая фраза (пропустить)
                part = tried
            elif e.code > 0:
                got = {}   # плохая фраза: пропустить
            else:
                RUN.update(state="error", msg=str(e))
                with _lock:
                    if QUEUE and QUEUE[0] is t:
                        QUEUE.pop(0)
                continue
        with _lock:
            done = {p for p, _ in part}
            t["items"] = [x for x in t["items"] if not (x[1] == lr and x[0] in done)]
        try:
            more = HANDLERS[t["kind"]](t["host"], lr, got, [p for p, _ in part]) or []
        except Exception as e:   # noqa: BLE001 - показать в окне, а не уронить поток
            RUN.update(state="error", msg=f"Ошибка: {e}"[:300])
            more = []
        if more:
            with _lock:
                t["items"].extend(more)
                t["total"] += len(more)
        if day_err:   # лимит кончился посреди пачки - ждать, как при лимите на всю пачку
            soon = direct.used_today() <= len(part) + 1
            if not soon:
                direct._put(day=direct._today(), used=direct.DAY_LIMIT)
            _wait_day(soon)
            continue
        time.sleep(direct.PAUSE)


def run_state(host):
    with _lock:
        mine = [t for t in QUEUE if t["host"] == host]
        out = {"state": RUN.get("state", "idle"), "msg": RUN.get("msg", ""),
               "queue": [{"kind": t["kind"], "label": t["label"], "left": len(t["items"]), "total": t["total"]} for t in mine],
               "other": len(QUEUE) - len(mine)}
    if RUN.get("state") == "error" and not mine:
        out["state"] = "error"
    return out


# ---------- 4. узнаваемость: название сайта и конкурентов

_LAT = [("shch", "щ"), ("sch", "ск"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ya", "я"),
        ("yu", "ю"), ("yo", "ё"), ("ph", "ф"), ("oo", "у"), ("ee", "и"), ("ck", "к"), ("ce", "се"), ("ci", "си"),
        ("cy", "си"), ("x", "кс"), ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"),
        ("h", "х"), ("i", "и"), ("j", "дж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
        ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("w", "в"), ("y", "и"), ("z", "з")]


def cyr(word):
    """Латиница → кириллица на слух («gigas» → «гигас»). Догадка: человек поправит написание в окне."""
    s, out = re.sub(r"ce$", "s", word.lower()), ""   # «service» → «сервис»
    while s:
        for a, b in _LAT:
            if s.startswith(a):
                out, s = out + b, s[len(a):]
                break
        else:
            out, s = out + s[0], s[1:]
    return out


def _label(host):
    return host.split(".")[-2] if "." in host else host


def guess_names(host, folder=None):
    """Названия сайта для Вордстата: из хвоста заголовков страниц («… | ГазПрофСервис»), латиницей - из домена,
    и тот же домен кириллицей. Части через дефис («termo-ufa») - обычные слова, без дефиса они ничего не значат."""
    names = []
    if folder and os.path.exists(os.path.join(folder, "crawl.db")):
        try:
            from .seeds import _brand_words
            db = sqlite3.connect(os.path.join(folder, "crawl.db"))
            try:
                names += [w for w in _brand_words(db, host)[:-1] if len(w.split()) <= 2]
            finally:
                db.close()
        except sqlite3.Error:
            pass
    lab = _label(host)
    if "-" not in lab:
        names.append(lab)
        from .bukvarix import sound
        from difflib import SequenceMatcher
        ru = cyr(lab)   # русское название из заголовков уже есть («газпрофсервис») - догадка на слух не нужна
        if not any(re.search("[а-я]", n) and SequenceMatcher(None, sound(n.lower()), sound(ru)).ratio() >= 0.75 for n in names):
            names.append(ru)
    out = []
    for n in names:
        n = direct.ad_phrase(n)
        if n and len(n) > 2 and n not in out:
            out.append(n)
    return out[:MAX_NAMES]


def _sites(data, host):
    from . import bukvarix
    out = [host] + [bukvarix.site(c) for c in data.get("competitors") or []]
    try:
        out += [x["domain"] for x in bukvarix.listing(host)]
    except Exception:   # noqa: BLE001 - Букварикс не загружался
        pass
    seen = []
    for h in out:
        if h and h not in seen:
            seen.append(h)
    return seen[:8]


def names_of(data, host, folder=None):
    """{сайт: [названия]}: вписанные человеком, иначе догадка."""
    saved = load(host).get("names") or {}
    return {h: saved[h] if h in saved else guess_names(h, folder if h == host else None) for h in _sites(data, host)}


def set_names(host, site, names):
    clean = []
    for n in re.split(r"[,\n;]", names or ""):
        n = direct.ad_phrase(n)
        if n and n not in clean:
            clean.append(n)
    _change(host, lambda d: d.setdefault("names", {}).__setitem__(site, clean[:MAX_NAMES]))
    return ""


def _regions(data):
    lr, region = direct.region_of(data.get("city"))
    return [(lr, region)] + ([(RF, "Россия")] if lr != RF else [])


def brand_items(data, host, folder=None):
    """Что спросить: каждое название (без кавычек - со всеми хвостами) по городу и по России. Вордстат даёт цифру за
    последний месяц, поэтому загруженное в этом месяце не спрашивается снова."""
    have = load(host).get("brand") or {}
    month = _day()[3:]
    items = []
    for names in names_of(data, host, folder).values():
        for n in names:
            for lr, _ in _regions(data):
                if ((have.get(str(lr)) or {}).get(n) or {}).get("at", "")[3:] != month and (n, lr) not in items:
                    items.append((n, lr))
    return items


def _on_brand(host, lr, got, sent):
    def fn(d):
        b = d.setdefault("brand", {}).setdefault(str(lr), {})
        for p in sent:
            x = got.get(direct._clean(p)) or {"shows": 0, "with": []}
            b[direct._clean(p)] = {"n": x["shows"], "with": [w for w in x["with"] if w[0] != direct._clean(p)][:8],
                                   "at": _day()}
    _change(host, fn)


def brand_view(data, host, folder=None):
    d = load(host).get("brand") or {}
    regs = _regions(data)
    sites = []
    for h, names in names_of(data, host, folder).items():
        rows = []
        for n in names:
            r = {"name": n}
            for lr, _ in regs:
                x = (d.get(str(lr)) or {}).get(n)
                r["rf" if lr == RF else "city"] = x["n"] if x else None
                if x and lr == regs[0][0]:
                    r["with"], r["at"] = x["with"], x["at"]
            rows.append(r)
        total = {k: sum(r.get(k) or 0 for r in rows) if any(r.get(k) is not None for r in rows) else None
                 for k in ("city", "rf")}
        sites.append({"host": h, "own": h == host, "names": names, "rows": rows, **total})
    at = when(x.get("at") for v in d.values() if isinstance(v, dict) for x in v.values() if isinstance(x, dict))
    return {"sites": sites, "cost": len(brand_items(data, host, folder)), "city": regs[0][1] if regs[0][0] != RF else "",
            "at": at}


# ---------- 5. местный спрос: город / Россия для главных запросов

LOCAL_TOP = 30   # запросов с самым большим спросом в городе


def _exact(data):
    """Точная частота в городе семантики (загрузка частотности): [(фраза, запрос, группа, показов)] по убыванию."""
    lr, _ = direct.region_of(data.get("city"))
    phr = (direct.load(data["host"]).get(str(lr)) or {}).get("phr") or {}
    rows, _, _ = direct._pool(data)
    return sorted(((p, rows[p][0], rows[p][1], phr[p][0]) for p in phr if p in rows and phr[p][0] > 0),
                  key=lambda x: -x[3])


def _local_rows(data):
    """Запросы с самым большим спросом в городе, без названия города («сантехника уфа» ищут почти только в Уфе)."""
    from . import City
    cities = City()
    out, seen = [], set()
    for x in _exact(data):
        key = frozenset(x[0].split())   # в кавычках порядок слов не важен: «котлы газовые» = «газовые котлы»
        if key not in seen and not cities.find(x[1]):
            seen.add(key)
            out.append(x)
    return out[:LOCAL_TOP]


def local_items(data, host):
    lr, _ = direct.region_of(data.get("city"))
    if lr == RF:
        return []
    have = load(host).get("rf") or {}
    return [('"' + p + '"', RF) for p, _, _, _ in _local_rows(data) if p not in have]


def _on_rf(host, lr, got, sent):
    def fn(d):
        r = d.setdefault("rf", {})
        for p in sent:
            c = direct._clean(p)
            r[c] = [(got.get(c) or {}).get("shows", 0), _day()]
    _change(host, fn)


def local_view(data, host):
    lr, region = direct.region_of(data.get("city"))
    if lr == RF:
        return {"city": "", "rows": [], "cost": 0}
    rf = load(host).get("rf") or {}
    rows, dates = [], []
    for p, q, g, n in _local_rows(data):
        x = rf.get(p)
        if x:
            dates.append(x[1])
        rows.append({"q": q, "group": g, "city": n, "rf": x[0] if x else None,
                     "share": round(n / x[0] * 100, 2) if x and x[0] else None})
    sh = sorted(r["share"] for r in rows if r["share"])
    med = sh[len(sh) // 2] if len(sh) >= 3 else None
    for r in rows:   # заметно выше обычной для ниши доли - местный запрос, ниже - ищут по всей стране
        r["kind"] = "" if not (med and r["share"]) else "local" if r["share"] >= med * 2 else "wide" if r["share"] <= med / 2 else ""
    from .words import city_by_name
    c = city_by_name(region)
    return {"city": region, "in": c[1] if c else region, "rows": rows, "median": med, "cost": len(local_items(data, host)),
            "at": when(dates), "city_at": (data.get("direct") or {}).get("dates") or ""}


# ---------- 3. своя сезонность: раз в месяц запоминать точную частоту главных запросов

SEASON_TOP = 30       # запросов, за которыми следим
SEASON_CHECK = 6 * 3600   # как часто окно проверяет, не пора ли записать новый месяц


def _month(day=None):
    d = day or _day()   # «07.10.2026» → «2026-10»
    return d[6:10] + "-" + d[3:5]


def season_start(data, host):
    """Начать следить: главные запросы (по точной частоте в городе), цифра этого месяца - из загрузки частотности,
    если она загружена в этом месяце (бесплатно)."""
    lr, region = direct.region_of(data.get("city"))
    seen, top = set(), []
    for p, _, _, _ in _exact(data):
        k = frozenset(p.split())
        if k not in seen:
            seen.add(k)
            top.append(p)
    top = top[:SEASON_TOP]
    if not top:
        return "Сначала загрузите точную частотность: следить можно за запросами, у которых она есть."
    phr = (direct.load(host).get(str(lr)) or {}).get("phr") or {}

    def fn(d):
        se = d.setdefault("season", {"host": host, "lr": lr, "region": region, "q": {}})
        for p in top:
            m = se["q"].setdefault(p, {})
            if p in phr:
                m.setdefault(_month(phr[p][1]), phr[p][0])
    _change(host, fn)
    return ""


def season_items(host):
    se = load(host).get("season") or {}
    month = _month()
    return [('"' + p + '"', se["lr"]) for p, m in (se.get("q") or {}).items() if month not in m]


def _on_season(host, lr, got, sent):
    def fn(d):
        q = d["season"]["q"]
        for p in sent:
            c = direct._clean(p)
            q.setdefault(c, {})[_month()] = (got.get(c) or {}).get("shows", 0)
    _change(host, fn)


def season_tick():
    """Раз в месяц по каждому сайту, за которым следим, - цифры нового месяца (ставится в очередь сама)."""
    from . import decisions
    if not direct._cfg().get("token"):
        return
    try:
        names = [n for n in os.listdir(decisions.DIR) if n.endswith(" - спрос.json")]
    except OSError:
        return
    for n in names:
        try:
            import json
            with open(os.path.join(decisions.DIR, n), encoding="utf-8") as f:
                se = json.load(f).get("season") or {}
        except (OSError, ValueError):
            continue
        if se.get("host") and season_items(se["host"]):
            enqueue(se["host"], "season", "сезонность, новый месяц", season_items(se["host"]))


def season_auto():
    """При запуске окна и потом раз в несколько часов."""
    def loop():
        while True:
            try:
                season_tick()
            except Exception:   # noqa: BLE001 - фоновая проверка не должна ронять окно
                pass
            time.sleep(SEASON_CHECK)
    threading.Thread(target=loop, daemon=True).start()


def season_view(host):
    se = load(host).get("season") or {}
    q = se.get("q") or {}
    months = sorted({m for v in q.values() for m in v})
    rows = sorted(({"q": p, "m": [v.get(m) for m in months]} for p, v in q.items()),
                  key=lambda r: -max([x or 0 for x in r["m"]] or [0]))
    total = [sum(r["m"][i] or 0 for r in rows) for i in range(len(months))]
    return {"on": bool(q), "months": months, "rows": rows, "total": total, "region": se.get("region", ""),
            "cost": len(season_items(host)) if q else None}


def season_cost(data):
    """Сколько фраз уйдёт на «Начать запоминать»: у чего нет частоты, загруженной в этом месяце."""
    lr, _ = direct.region_of(data.get("city"))
    phr = (direct.load(data["host"]).get(str(lr)) or {}).get("phr") or {}
    seen, n = set(), 0
    for p, _, _, _ in _exact(data):
        k = frozenset(p.split())
        if k in seen:
            continue
        seen.add(k)
        if len(seen) > SEASON_TOP:
            break
        n += _month(phr[p][1]) != _month()
    return n


# ---------- 6. ВЧ/СЧ/НЧ относительно самой ниши (по точной частоте, бесплатно)

HEAD, BODY = 0.5, 0.8   # ВЧ - запросы, дающие первую половину всего спроса ниши; СЧ - до 80 %; НЧ - остальное


def levels(freqs):
    """Точные частоты запросов ниши → пороги {"hi": от скольких ВЧ, "mid": от скольких СЧ, …} или None.
    Не по общим таблицам («ВЧ - от 10 000»): в нише с 300 запросами в месяц таких нет вовсе, а в Москве - всё ВЧ."""
    fs = sorted((f for f in freqs if f > 0), reverse=True)
    total = sum(fs)
    if len(fs) < 10 or not total:
        return None
    acc, hi, mid = 0, None, None
    for f in fs:
        acc += f
        if hi is None and acc >= total * HEAD:
            hi = f
        if mid is None and acc >= total * BODY:
            mid = f
            break
    mid = min(mid, hi - 1) if hi > 1 else mid   # у СЧ порог ниже, чем у ВЧ
    out = {"hi": hi, "mid": max(mid, 1), "total": total}
    out.update(n_hi=sum(1 for f in fs if f >= out["hi"]), n_mid=sum(1 for f in fs if out["mid"] <= f < out["hi"]),
               n_lo=sum(1 for f in fs if f < out["mid"]), n_zero=sum(1 for f in freqs if not f))
    return out


def levels_view(data):
    rows = list({frozenset(x[0].split()): x for x in reversed(_exact(data))}.values())[::-1]   # без повторов порядка слов
    lv = levels([x[3] for x in rows] + [0] * _zero_count(data))
    if not lv:
        return None
    seen, top = set(), []
    for p, q, g, n in rows:
        k = frozenset(p.split())
        if n >= lv["hi"] and k not in seen:
            seen.add(k)
            top.append({"q": q, "group": g, "n": n})
    return dict(lv, top=top[:15], at=(data.get("direct") or {}).get("dates") or "")


def _zero_count(data):
    lr, _ = direct.region_of(data.get("city"))
    phr = (direct.load(data["host"]).get(str(lr)) or {}).get("phr") or {}
    rows, _, _ = direct._pool(data)
    return sum(1 for p in phr if p in rows and not phr[p][0])


# ---------- новые запросы (что ещё искали, ёлочка) → по группам семантики, как «Разложить новые»

def sort_new(data, found):
    """found: {запрос: показов} → {"add": дополнить группу, "topics": новые темы, "articles": вопросы, "dropped": n}.
    Уже собранные запросы (в любом порядке слов), чужие города, мусор и стоп-слова не берутся."""
    from . import assign, City
    from .bukvarix import drop_reason
    from .words import load_stop
    have = {frozenset(direct._clean(direct.phrase(r[0])).split()) for g in data.get("groups") or [] for r in g.get("q") or []}
    from . import dictionary
    cities, stop = City(), set(load_stop()) | set(dictionary.junk_for(data.get("host"), [r[0] for g in data.get("groups") or [] for r in g.get("q") or []]))
    new, dropped = [], 0
    for q, n in sorted(found.items(), key=lambda x: -x[1]):
        if not q or frozenset(q.split()) in have:
            continue
        if drop_reason(q, set(), set(), data.get("city"), cities, stop):
            dropped += 1
            continue
        new.append({"q": q, "freq": n})
    out = {"add": [], "topics": [], "articles": [], "dropped": dropped}
    for r in assign.run(assign.groups_from_semantics(data), new, data=data):
        x = {"q": r["q"], "n": r["freq"] or 0, "group": r["group"], "near": r.get("alt") or r.get("topic") or ""}
        if r["how"] == "уже в группе":
            continue
        out["articles" if r["group"] == assign.ARTICLES else "topics" if r["group"] in (assign.NONE, assign.GALLERY)
            else "add"].append(x)
    return out


# ---------- 2. что ещё искали (SearchedAlso): соседние темы, идеи разделов и статей

ALSO_TOP = 40   # главных запросов, для которых дозагрузить «что ещё искали» (новая загрузка частотности хранит сама)


def _also(data):
    lr, _ = direct.region_of(data.get("city"))
    return (direct.load(data["host"]).get(str(lr)) or {}).get("also") or {}


def also_items(data, host):
    lr, _ = direct.region_of(data.get("city"))
    have, seen, out = _also(data), set(), []
    for p, _, _, _ in _exact(data):
        k = frozenset(p.split())
        if k in seen:
            continue
        seen.add(k)
        if len(seen) > ALSO_TOP:
            break
        if p not in have:
            out.append(('"' + p + '"', lr))
    return out


def _on_also(host, lr, got, sent):
    region = (direct.load(host).get(str(lr)) or {}).get("region", "")
    also = {direct._clean(p): (got.get(direct._clean(p)) or {}).get("also", [])[:direct.ALSO_KEEP] for p in sent}
    direct._store(host, lr, region, also, "also")
    # частота - только по фразам, на которые Директ ответил: плохая фраза не затирает загруженную раньше частоту нулём
    direct._store(host, lr, region, {p: got[p]["shows"] for p in also if p in got}, "phr")


def also_view(data, host):
    found = {}
    for lst, _ in _also(data).values():   # хранится как [[[запрос, показов], …], дата]
        for q, n in lst:
            found[q] = max(found.get(q, 0), n)
    v = sort_new(data, found)
    return dict(v, n=len(_also(data)), cost=len(also_items(data, host)), at=when(x[1] for x in _also(data).values()))


# ---------- 1. ёлочка: хвосты главных фраз (SearchedWith), потом ещё раз - с минус-словами

TREE_ROOTS = 15   # главных фраз ниши за одно нажатие (каждая - 2 фразы лимита: хвосты и хвосты без найденного)
TREE_MINUS = 6    # минус-слов во втором круге: самые частые слова из найденных хвостов


def _roots(data, host):
    done = (load(host).get("tree") or {})
    seen, out = set(), []
    for p, _, _, _ in _exact(data):
        k = frozenset(p.split())
        if k not in seen and p not in done:
            seen.add(k)
            out.append(p)
    return out[:TREE_ROOTS]


def tree_items(data, host):
    lr, _ = direct.region_of(data.get("city"))
    return [(r, lr) for r in _roots(data, host)]


def minus_words(root, tails):
    """Слова, которые чаще всего добавляют к фразе (по числу показов): «газовый котел» → «купить», «цена», «бакси»."""
    rw = set(root.split())
    w = {}
    for q, n in tails:
        for t in set(q.split()) - rw:
            if len(t) > 2 and re.fullmatch(r"[a-zа-я0-9\-]+", t):
                w[t] = w.get(t, 0) + n
    return [t for t, _ in sorted(w.items(), key=lambda x: -x[1])[:TREE_MINUS]]


def _on_tree(host, lr, got, sent):
    more = []

    def fn(d):
        tr = d.setdefault("tree", {})
        for p in sent:
            c = direct._clean(p)
            root = c.split(" -")[0].strip()
            x = got.get(c) or next((v for k, v in got.items() if k.split(" -")[0].strip() == root), None) or {"with": []}
            tails = [w for w in x["with"] if w[0] != root]
            e = tr.setdefault(root, {"at": _day()})
            if " -" in c:
                e["r2"], e["minus"] = tails, [m.lstrip("-") for m in c.split()[len(root.split()):]]
            else:
                e["r1"] = tails
                minus = minus_words(root, tails)
                if minus and len(tails) >= 20:   # хвостов мало - Вордстат и так показал все, второй круг не нужен
                    more.append((root + " " + " ".join("-" + m for m in minus), lr))
    _change(host, fn)
    return more


def tree_view(data, host):
    tr = load(host).get("tree") or {}
    found = {}
    for e in tr.values():
        for q, n in (e.get("r1") or []) + (e.get("r2") or []):
            found[q] = max(found.get(q, 0), n)
    v = sort_new(data, found)
    return dict(v, roots=[{"q": k, "r1": len(e.get("r1") or []), "r2": len(e.get("r2") or []), "minus": e.get("minus") or []}
                          for k, e in tr.items()], cost=len(tree_items(data, host)) * 2, found=len(found),
                at=when(e.get("at") for e in tr.values()))


HANDLERS = {"brand": _on_brand, "rf": _on_rf, "season": _on_season, "also": _on_also, "tree": _on_tree}


# ---------- для окна

def build(data, host, folder=None):
    return {"has_token": bool(direct._cfg().get("token")), "used": direct.used_today(), "limit": direct.DAY_LIMIT,
            "load": direct.job(os.path.basename(folder or "")).get("state"),
            "run": run_state(host), "brand": brand_view(data, host, folder), "local": local_view(data, host),
            "season": dict(season_view(host), start=season_cost(data)), "levels": levels_view(data), "also": also_view(data, host),
            "tree": tree_view(data, host), "region": direct.region_of(data.get("city"))[1]}


def start(data, host, kind, folder=None):
    if kind == "brand":
        return enqueue(host, "brand", "узнаваемость", brand_items(data, host, folder))
    if kind == "rf":
        return enqueue(host, "rf", "местный спрос", local_items(data, host))
    if kind == "season":
        err = season_start(data, host)
        if err:
            return err
        items = season_items(host)
        return enqueue(host, "season", "сезонность", items) if items else ""
    if kind == "also":
        return enqueue(host, "also", "что ещё искали", also_items(data, host))
    if kind == "tree":
        return enqueue(host, "tree", "ёлочка", tree_items(data, host))
    return "Неизвестное действие."
