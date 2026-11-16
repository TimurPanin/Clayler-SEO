"""Точная частотность Вордстата через API Яндекс Директа (v4 Live: CreateNewWordstatReport и соседние методы).

Как подключить: на oauth.yandex.ru своё приложение с доступом к API Директа (заявка на доступ одобрена Директом),
его ClientID вписывается в «Подключения» → «Яндекс Директ». Кнопка «Получить ключ» открывает страницу Яндекса,
человек нажимает «Разрешить» и копирует показанный ключ в программу. Ключ хранится в «доступы.json»
зашифрованным (как ключи Вебмастера, accounts.seal), в git не попадает.

Частотность: фраза в кавычках («"газовый котел"» - эта фраза и её словоформы, без хвостов), регион - город
семантики (Уфа - 172). Один отчёт - до 10 фраз; отчёт создаётся, программа ждёт, забирает и сразу удаляет его
(на сервере Директа не больше 5 отчётов). В сутки не больше DAY_LIMIT фраз; когда лимит или баллы кончились,
загрузка ждёт следующего дня (по Москве, как у Директа) и продолжает сама, пока окно программы открыто (и после перезапуска окна).
С 10.10.2026 сначала - прогноз бюджета (CreateNewForecast, shows_fast): фраза в кавычках даёт то же число, что
отчёт Вордстата, по 100 фраз за раз, баллы не тратит и в суточный лимит не входит. Не ответил - в этот день
загрузка идёт отчётами Вордстата, как раньше. Пустышки (без кавычек) и «что ещё искали» - по-прежнему отчётами.
Итог - на сайт в папке «решения семантики» («<сайт> - частотность директ.json»), поэтому не теряется при новой
проверке и новом сборе. При чтении семантики (export.load → apply) частотность ставится в колонку «Спрос».
"""
import datetime
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import accounts, jsonfile, sysproxy

_T = os.environ.get("CLAYLER_DIRECT_TEST")   # в тестах - поддельный сервер Директа
API = (_T or "https://api.direct.yandex.ru") + "/live/v4/json/"
API5 = (_T or "https://api.direct.yandex.com") + "/json/v5/"
OAUTH = "https://oauth.yandex.ru/authorize"
DAY_LIMIT = 1000     # фраз в сутки (ограничение Директа на отчёты Вордстата)
BATCH = 10           # фраз в одном отчёте
MAX_WORDS = 7        # длиннее Директ не принимает
PAUSE = 2            # секунд между отчётами
WAIT = 180           # секунд ждать готовности одного отчёта
# проверка ключа - одна нейтральная фраза, не про чей-то сайт (было «газовый котел» с первого клиента)
CHECK_PHRASE = "погода"
# ошибки Директа, после которых ждём следующего дня: нет баллов, лимит вызовов или фраз в сутки
DAY_ERRORS = {152, 56, 57}
_lock = threading.Lock()
JOB = {"state": "idle"}   # одна загрузка за раз: {state, host, folder, region, total, done, msg, until}
_thread = None


class DirectError(RuntimeError):
    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


# ---------- ключ и приложение ----------

def _cfg():
    return accounts._get("direct")


MSK = datetime.timezone(datetime.timedelta(hours=3))   # сутки лимитов Директа - по Москве


def _today():
    return datetime.datetime.now(MSK).date().isoformat()


def used_today():
    c = _cfg()
    return int(c.get("used") or 0) if c.get("day") == _today() else 0


def _count(n):
    with _lock:
        _put(day=_today(), used=used_today() + n)


def _put(**kw):
    accounts._put("direct", **kw)


def status():
    c = _cfg()
    return {"client_id": c.get("client_id", ""), "has_token": bool(c.get("token")), "login": c.get("login", ""),
            "since": c.get("since", ""), "check": c.get("check", ""), "check_ok": bool(c.get("check_ok")),
            "units": c.get("units"), "used": used_today(), "limit": DAY_LIMIT,
            "auth_url": auth_url() if c.get("client_id") else ""}


def auth_url():
    return OAUTH + "?" + urllib.parse.urlencode({"response_type": "token", "client_id": _cfg().get("client_id", ""),
                                                 "force_confirm": "yes"})


def save(client_id=None, token=None, login=None):
    """ClientID приложения Директа, ключ (пустой - оставить прежний) и логин Директа (для остатка баллов)."""
    client_id = (client_id or "").strip()
    token = re.sub(r"\s+", "", token or "")
    if token.startswith("http"):   # вставили адрес из браузера целиком: ключ после access_token=
        token = (re.search(r"access_token=([^&#]+)", token) or [None, ""])[1]
    if not client_id:
        return "Вставьте ClientID приложения Директа."
    if token and not re.fullmatch(r"[A-Za-z0-9_\-.]{20,}", token):
        return "Это не похоже на ключ: скопируйте его целиком со страницы Яндекса."
    fields = {"client_id": client_id, "login": (login or "").strip() or None}
    if token:
        fields.update(token=accounts.seal(token), since=time.strftime("%d.%m.%Y %H:%M"), check=None, check_ok=None)
    _put(**fields)
    return ""


def forget():
    _put(token=None, since=None, check=None, check_ok=None, units=None)
    return ""


def _token():
    c = _cfg()
    if not c.get("token"):
        raise DirectError(0, "Ключ Директа не вставлен (Подключения → Яндекс Директ).")
    return accounts.unseal(c["token"])


def call(method, param=None):
    """Один вызов API Директа v4 Live. Ошибку Директа - DirectError с кодом и понятным текстом."""
    body = {"method": method, "token": _token(), "locale": "ru"}
    if param is not None:
        body["param"] = param
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with sysproxy.urlopen(req, timeout=60) as r:
            ans = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise DirectError(e.code, f"Директ ответил {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
    except (urllib.error.URLError, OSError) as e:
        raise DirectError(-1, f"нет связи с Директом: {e}")
    if "error_code" in ans:
        code = int(ans.get("error_code") or 0)
        text = " ".join(x for x in (ans.get("error_str"), ans.get("error_detail")) if x).strip()
        raise DirectError(code, f"Директ: {text or 'ошибка'} (код {code})")
    return ans.get("data")


def call5(service, method, params):
    """Один вызов API Директа v5 (ключ - в заголовке). Ошибку - DirectError."""
    h = {"Authorization": "Bearer " + _token(), "Accept-Language": "ru", "Content-Type": "application/json; charset=utf-8"}
    if _cfg().get("login"):
        h["Client-Login"] = _cfg()["login"]
    req = urllib.request.Request(API5 + service, headers=h,
                                 data=json.dumps({"method": method, "params": params}, ensure_ascii=False).encode("utf-8"))
    try:
        with sysproxy.urlopen(req, timeout=120) as r:
            ans = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise DirectError(e.code, f"Директ ответил {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
    except (urllib.error.URLError, OSError) as e:
        raise DirectError(-1, f"нет связи с Директом: {e}")
    if "error" in ans:
        er = ans["error"] or {}
        code = int(er.get("error_code") or 0)
        text = " ".join(x for x in (er.get("error_string"), er.get("error_detail")) if x).strip()
        raise DirectError(code, f"Директ: {text or 'ошибка'} (код {code})")
    return ans.get("result") or {}


def units():
    """Остаток баллов API (если вписан логин Директа), иначе None."""
    login = _cfg().get("login")
    if not login:
        return None
    try:
        d = call("GetClientsUnits", [login])
        n = int(d[0]["UnitsRest"]) if d else None
    except (DirectError, LookupError, TypeError, ValueError):
        return None
    _put(units=n)
    return n


# ---------- отчёт Вордстата ----------

def phrase(q):
    """Запрос → фраза для Вордстата в кавычках; не подходит (длинная, без букв) - ""."""
    s = re.sub(r"[^a-zа-яё0-9 \-]", " ", (q or "").lower().replace("ё", "е"))
    s = re.sub(r"\s+-|-\s+", " ", s)
    words = s.split()
    if not words or len(words) > MAX_WORDS or not re.search(r"[a-zа-я]", s):
        return ""
    return '"' + " ".join(words) + '"'


def _clean(p):
    return re.sub(r"[\"!+\[\]]", "", p or "").strip().lower().replace("ё", "е")


def _drop_old_reports(mine):
    """На сервере не больше 5 отчётов: удаляем наши прошлые (оставшиеся после сбоя)."""
    try:
        lst = call("GetWordstatReportList") or []
    except DirectError:
        return
    for r in lst:
        if r.get("ReportID") in mine:
            try:
                call("DeleteWordstatReport", r["ReportID"])
            except DirectError:
                pass
    _put(ids=None)


def report(phrases, lr):
    """Фразы (уже в кавычках) → {фраза без кавычек: показов в месяц}. Отчёт создаётся, ждётся и удаляется."""
    out = {_clean(p): 0 for p in phrases}   # фразы без показов Директ может не вернуть
    for want, x in report_full(phrases, lr).items():
        out[want] = x["shows"]
    return out


def report_full(phrases, lr):
    """Фразы → {фраза без кавычек: {"shows": показов в месяц, "with": [[хвост, показов], …] (что искали вместе с фразой,
    до 200 штук), "also": [[запрос, показов], …] (что ещё искали люди, искавшие эту фразу)}}."""
    mine = _cfg().get("ids") or []
    try:
        rid = call("CreateNewWordstatReport", {"Phrases": phrases, "GeoID": [int(lr)]})
    except DirectError as e:
        if e.code != 31 or not mine:   # 31 - на сервере уже 5 отчётов
            raise
        _drop_old_reports(mine)
        rid = call("CreateNewWordstatReport", {"Phrases": phrases, "GeoID": [int(lr)]})
    _put(ids=list(set(_cfg().get("ids") or []) | {rid}))
    _count(len(phrases))
    try:
        t0 = time.time()
        while True:
            time.sleep(2 if time.time() - t0 < 20 else 5)
            st = next((r.get("StatusReport") for r in call("GetWordstatReportList") or [] if r.get("ReportID") == rid), None)
            if st == "Done":
                break
            if st == "Failed" or st is None:
                raise DirectError(-2, "Директ не смог составить отчёт Вордстата")
            if time.time() - t0 > WAIT:
                raise DirectError(-2, "Директ долго не готовит отчёт Вордстата")
        out = {}
        for item, sent in zip(call("GetWordstatReport", rid) or [], phrases):
            want = _clean(item.get("Phrase") or sent)
            sw = item.get("SearchedWith") or []
            hit = next((x for x in sw if _clean(x.get("Phrase")) == want), sw[0] if sw else None)
            out[want] = {"shows": int((hit or {}).get("Shows") or 0),
                         "with": [[_clean(x.get("Phrase")), int(x.get("Shows") or 0)] for x in sw],
                         "also": [[_clean(x.get("Phrase")), int(x.get("Shows") or 0)]
                                  for x in item.get("SearchedAlso") or []]}
        return out
    finally:
        try:
            call("DeleteWordstatReport", rid)
            _put(ids=[i for i in _cfg().get("ids") or [] if i != rid] or None)
        except DirectError:
            pass


# ---------- прогноз бюджета: цена клика в рекламе (CreateNewForecast, баллы не тратит - проверено) ----------

FC_BATCH = 100   # фраз в одном прогнозе (ограничение Директа)
FC_MAX = 300     # фраз за одно нажатие «Посчитать стоимость в рекламе»


SIEVE = 10000   # фраз в одном вызове hasSearchVolume (ограничение Директа)


def _words(p):
    return len(re.split(r"[\s\-]+", _clean(p)))   # Директ v5 считает слова через дефис отдельно


def has_volume(phrases, lr):
    """Фразы в кавычках → {фраза без кавычек: есть ли показы в месяц} (KeywordsResearch.hasSearchVolume, Директ v5).
    Проверено на 995 фразах gasmasterservis.ru (Уфа): все 508 «нет» - точно 0, из «да» только 3 оказались 0.
    Стоит 1 балл за вызов, лимит Вордстата (DAY_LIMIT) не трогает. Длиннее 7 слов (через дефис тоже) не спрашиваются."""
    out = {}
    ok = [p for p in phrases if _words(p) <= MAX_WORDS]
    for i in range(0, len(ok), SIEVE):
        res = call5("keywordsresearch", "hasSearchVolume",
                    {"SelectionCriteria": {"Keywords": ok[i:i + SIEVE], "RegionIds": [int(lr)]},
                     "FieldNames": ["Keyword", "AllDevices"]})
        for x in res.get("HasSearchVolumeResults") or []:
            if x.get("AllDevices") in ("YES", "NO"):
                out[_clean(x.get("Keyword"))] = x["AllDevices"] == "YES"
    return out


def _sieve(data, left):
    """Перед загрузкой: фразы без показов (по флагу Директа) сразу получают 0 и не тратят суточный лимит.
    Флаг запоминается («nv»), чтобы не спрашивать снова. Не получилось - грузим как раньше. Возвращает сколько отсеяно."""
    lr, region = region_of(data.get("city"))
    nv = (load(data["host"]).get(str(lr)) or {}).get("nv") or {}
    ask = [p for p in left if p and _clean(p) not in nv]
    if not ask:
        return 0
    try:
        got = has_volume(ask, lr)
    except DirectError as e:
        JOB["sieve"] = str(e)
        return 0
    _store(data["host"], lr, region, {p: int(v) for p, v in got.items()}, kind="nv")
    zero = {p: 0 for p, v in got.items() if not v}
    if zero:
        _store(data["host"], lr, region, zero)
    return len(zero)


def _rf_flags(host, lr, region, phrases):
    """Кандидаты в пустышки: ищут ли фразу по всей России (флаг Директа, 1 балл, суточный лимит Вордстата не
    тратит). В городе 0, а по России ищут - это не пустышка, а «в этом городе почти не ищут» («rf»)."""
    try:
        got = has_volume([phrase(p) for p in phrases if phrase(p)], 225)   # в кавычках: без них почти всегда «да»
    except DirectError:
        return
    if got:
        _store(host, lr, region, {p: int(v) for p, v in got.items()}, kind="rf")


def ad_phrase(q):
    """Запрос → фраза для прогноза рекламы: как в объявлении, без кавычек (с хвостами)."""
    return phrase(q).strip('"')


def forecast(phrases, lr):
    """Фразы (ad_phrase) → {фраза: [цена клика при показе наверху поиска (вход в блок), кликов наверху в месяц,
    показов в месяц]}. Прогноз создаётся, ждётся и удаляется (на сервере держится не больше 5 прогнозов)."""
    mine = _cfg().get("fc_ids") or []
    param = {"Phrases": phrases, "GeoID": [int(lr)], "Currency": "RUB"}
    try:
        fid = call("CreateNewForecast", param)
    except DirectError as e:
        if e.code != 31 or not mine:
            raise
        for i in mine:   # прошлые наши прогнозы, оставшиеся после сбоя
            try:
                call("DeleteForecastReport", i)
            except DirectError:
                pass
        _put(fc_ids=None)
        fid = call("CreateNewForecast", param)
    _put(fc_ids=list(set(_cfg().get("fc_ids") or []) | {fid}))
    try:
        t0 = time.time()
        while True:
            time.sleep(2 if time.time() - t0 < 20 else 5)
            st = next((r.get("StatusForecast") for r in call("GetForecastList") or [] if r.get("ForecastID") == fid), None)
            if st == "Done":
                break
            if st == "Failed" or st is None:
                raise DirectError(-2, "Директ не смог составить прогноз")
            if time.time() - t0 > WAIT:
                raise DirectError(-2, "Директ долго не готовит прогноз")
        out = {}
        for item in (call("GetForecast", fid) or {}).get("Phrases") or []:
            p = _clean(item.get("Phrase"))
            out[p] = [round(float(item.get("PremiumMin") or 0), 2), int(item.get("PremiumClicks") or 0),
                      int(item.get("Shows") or 0)]
        return out
    finally:
        try:
            call("DeleteForecastReport", fid)
            _put(fc_ids=[i for i in _cfg().get("fc_ids") or [] if i != fid] or None)
        except DirectError:
            pass


def shows_fast(phrases, lr):
    """Частота фраз в кавычках через прогноз бюджета, по 100 за раз: {фраза без кавычек: показов в месяц}.
    Проверено на gasmasterservis (Уфа): 100 фраз из 100 - ровно те же числа, что отчёт Вордстата
    (без кавычек прогноз даёт широкие показы, в среднем в 16 раз больше). Баллы не тратятся (32 000 до и после),
    в суточный лимит отчётов Вордстата (DAY_LIMIT) не входит. «Что ещё искали» прогноз не даёт."""
    out = {_clean(p): 0 for p in phrases}
    for q, v in forecast(['"' + _clean(p) + '"' for p in phrases], lr).items():
        out[q] = v[2]
    return out


def fast_ok():
    """Частота через прогноз сегодня не ломалась (иначе - отчёты Вордстата, как раньше)."""
    return _cfg().get("fast_off") != _today()


def ads(host, city, queries):
    """Цена клика в рекламе для запросов сайта (самые важные первыми), ещё не посчитанных: до FC_MAX за раз.
    Возвращает (сколько посчитано, ошибка)."""
    if not _cfg().get("token"):
        return 0, "Сначала вставьте ключ Директа: Подключения → Яндекс Директ."
    lr, region = region_of(city)
    have = (load(host).get(str(lr)) or {}).get("fc") or {}
    todo = []
    for q in queries:
        p = ad_phrase(q)
        if p and p not in have and p not in todo:
            todo.append(p)
    todo = todo[:FC_MAX]
    n = 0
    for i in range(0, len(todo), FC_BATCH):
        part = todo[i:i + FC_BATCH]
        try:
            got = forecast(part, lr)
        except DirectError as e:
            return n, str(e)
        got.update({p: [0, 0, 0] for p in part if p not in got})   # без цены - чтобы не спрашивать снова
        _store(host, lr, region, got, kind="fc")
        n += len(part)
    return n, ""


def check():
    """Маленькая проверка: одна фраза по всей России. Возвращает (текст, ошибка)."""
    try:
        n = report([phrase(CHECK_PHRASE)], 225)[CHECK_PHRASE]
    except DirectError as e:
        msg = str(e)
        if e.code == 58:
            msg += ". Похоже, заявка на доступ к API ещё не одобрена или ClientID не того приложения."
        elif e.code == 53:
            msg += ". Ключ не подходит: получите новый кнопкой «Получить ключ»."
        _put(check="Не работает: " + msg, check_ok=False)
        return "", msg
    u = units()
    from .fmt import num
    text = (f"Работает. Проверочный запрос «{CHECK_PHRASE}» - {num(n)} показов в месяц по России"
            + (f", баллов осталось {num(u)}" if u is not None else "") + f" ({time.strftime('%d.%m.%Y %H:%M')}).")
    _put(check=text, check_ok=True)
    return text, ""


# ---------- частотность для семантики сайта ----------

def _path(host):
    from .semantics import decisions
    return decisions.site_file(host, " - частотность директ")


def load(host):
    return jsonfile.load(_path(host))


def _store(host, lr, region, got, kind="phr"):
    """kind: «phr» - частота фразы в кавычках, «broad» - без кавычек, с хвостами (проверка пустышек), «nv» - флаг
    «есть показы» (отсев), «also» - что ещё искали ([[запрос, показов], …])."""
    from .semantics import decisions
    with _lock:
        d = load(host)
        e = d.setdefault(str(lr), {"region": region, "phr": {}})
        day = time.strftime("%d.%m.%Y")
        for q, n in got.items():
            e.setdefault(kind, {})[q] = [n, day]
        decisions.save_site_file(host, " - частотность директ", d, indent=0)


def region_of(city):
    """Город семантики → (код региона Яндекса, название). Нет города - вся Россия."""
    from .semantics.words import city_by_name
    c = city_by_name(city) if city else None
    return (c[2], c[0]) if c and c[2] else (225, "Россия")


def apply(data):
    """Семантика (семантика.json) → частотность из Директа в колонке «Спрос» (r[11]) и data["direct"]."""
    if not data or not data.get("groups") or not data.get("host"):
        return data
    lr, region = region_of(data.get("city"))
    phr = (load(data["host"]).get(str(lr)) or {}).get("phr") or {}
    if not phr:
        return data
    n, fs = 0, {}
    for g in data["groups"]:
        for r in g.get("q") or []:
            p = _clean(phrase(r[0]))
            x = phr.get(p)
            for f in (r[14] if len(r) > 14 and isinstance(r[14], list) else []):   # другие формы запроса:
                y = phr.get(_clean(phrase(f)))                                       # частота - наибольшая
                if y is not None and (x is None or y[0] > x[0]):
                    x = y
            if x is not None and len(r) > 11:
                r[11] = x[0]
                n += 1
                if not r[7]:
                    fs[frozenset(p.split())] = x[0]   # «котлы газовые» = «газовые котлы» - один раз
    from .semantics.demand import levels, when   # ВЧ/СЧ/НЧ относительно самой ниши
    data["direct"] = {"n": n, "region": region, "at": max((v[1] for v in phr.values()), key=lambda s: s[6:] + s[3:5] + s[:2]),
                      "dates": when(v[1] for v in phr.values()),   # подпись у цифр: «с 07.10.2026 по 17.10.2026»
                      "levels": levels(list(fs.values()))}
    return data


def todo(data):
    """Фразы семантики по важности, ещё без частотности из Директа: по уровням масок (главная и меню, потом разделы,
    потом подразделы и карточки, masks.py), внутри уровня - сначала главные запросы каждой группы.
    Фраза спрашивается один раз, даже если она есть в группе раздела и подраздела."""
    lr, _ = region_of(data.get("city"))
    have = set((load(data["host"]).get(str(lr)) or {}).get("phr") or {})
    out, seen = [], set()
    for lv in sorted({g.get("lv") or 9 for g in data["groups"]}):
        from .semantics import repeated_word, tokens, norm
        lists = [[r[0] for r in sorted(g.get("q") or [], key=lambda r: -(r[3] or 0))
                  if not r[7] and not repeated_word(tokens(norm(r[0])))]
                 for g in data["groups"] if (g.get("lv") or 9) == lv]
        for i in range(max((len(x) for x in lists), default=0)):
            for x in lists:
                if i < len(x):
                    p = phrase(x[i])
                    if p and _clean(p) not in have and p not in seen:
                        seen.add(p)
                        out.append(p)
    return out


def _wait_day(soon=False):
    """Ждать нового дня (soon - Яндекс ещё не обновил лимит после полуночи: попробовать через час)."""
    t = datetime.datetime.now(MSK)
    nxt = (t + datetime.timedelta(hours=1)) if soon else         datetime.datetime.combine(t.date() + datetime.timedelta(days=1), datetime.time(0, 10), MSK)
    until = nxt.astimezone().strftime("%d.%m в %H:%M")   # по часам этого компьютера
    JOB.update(state="waiting", until=until,
               msg=(f"Яндекс ещё не обновил лимит на новый день, попробую {until}." if soon
                    else f"Лимит Яндекса на сегодня исчерпан, продолжу {until}."))
    while datetime.datetime.now(MSK) < nxt and JOB.get("state") == "waiting":
        time.sleep(30)
    return JOB.get("state") == "waiting"


def _run(folder):
    from .semantics import export
    try:
        while True:
            data = export.load(folder)
            if not data:
                JOB.update(state="error", msg="Семантика для этой проверки не собрана.")
                return
            lr, region = region_of(data.get("city"))
            left = todo(data)
            if _sieve(data, left):   # фразы без показов - сразу 0, лимит на них не тратится
                left = todo(data)
            e = load(data["host"]).get(str(lr)) or {}
            old = [p for p, v in (e.get("broad") or {}).items() if v[0] <= EMPTY_BROAD and p not in (e.get("rf") or {})]
            if old and int(lr) != 225:   # пустышки, проверенные до флага «по России»
                _rf_flags(data["host"], lr, region, old)
            JOB.update(host=data["host"], region=region, total=JOB.get("done", 0) + len(left))
            if not left and _empty_candidates(data):   # всё в кавычках есть - проверить пустышки
                left = [None]
            if not left:
                JOB.update(state="done", msg=f"Частотность загружена для всех фраз ({JOB.get('done', 0)} за этот раз).")
                _event("ok", f"Частотность загружена: {data['host']}", folder)
                _put(job=None)
                nxt = _next_folder()
                if not nxt:
                    return
                # «Загрузить частотность» для нескольких сайтов: следующий сайт - в тот же поток и тот же лимит
                folder = os.path.join(_reports(), nxt)
                JOB.clear()
                JOB.update(state="running", folder=nxt, done=0, total=0, msg="")
                _put(job=nxt)
                continue
            JOB.update(state="running", msg="", detail="")
            if left != [None] and fast_ok():   # сначала быстро: прогноз Директа, по 100 фраз, без суточного лимита
                JOB["fast"] = True
                broke = False
                for i in range(0, len(left), FC_BATCH):
                    if JOB.get("state") != "running":
                        return
                    part = [p for p in left[i:i + FC_BATCH] if p]
                    try:
                        got = shows_fast(part, lr)
                    except DirectError as e:   # дальше отчётами, прогноз - снова завтра
                        _put(fast_off=_today())
                        JOB.update(fast=False, detail=f"Прогноз Директа не ответил ({e}), гружу отчётами Вордстата.")
                        broke = True
                        break
                    _store(data["host"], lr, region, got, "phr")
                    JOB["done"] = JOB.get("done", 0) + len(got)
                    time.sleep(PAUSE)
                if not broke:
                    continue   # всё по прогнозу: заново посчитать, что осталось (и проверить пустышки)
                left = todo(data)
            stop_day = soon = False
            for n, i in enumerate(range(0, len(left), BATCH)):
                if JOB.get("state") != "running":
                    return
                room = DAY_LIMIT - used_today()
                if room <= 0:
                    stop_day = True
                    break
                kind = "phr"
                cand = _empty_candidates(data) if n % 10 == 9 or left == [None] else []
                if cand:   # раз в 10 отчётов - кандидаты в пустышки без кавычек (с хвостами)
                    part, kind = [c for c in cand[:min(BATCH, room)]], "broad"
                else:
                    part = [p for p in left[i:i + min(BATCH, room)] if p]   # остаток дня меньше 10 - отчёт поменьше
                if not part:
                    continue
                also = {}
                try:
                    full = report_full(part, lr)
                    got = {_clean(p): 0 for p in part}
                    for q, x in full.items():
                        got[q] = x["shows"]
                        if kind == "phr" and x["shows"] and x["also"]:   # «что ещё искали» - для вкладки «Спрос», бесплатно
                            also[q] = x["also"][:ALSO_KEEP]
                except DirectError as e:
                    if e.code in DAY_ERRORS:
                        JOB["detail"] = str(e)   # как ответил Яндекс - в подсказке
                        # день только начался, а лимит «исчерпан»: у Яндекса сутки ещё старые
                        soon = used_today() <= len(part)
                        if not soon:
                            _put(day=_today(), used=DAY_LIMIT)   # Яндекс считает строже: на сегодня всё
                        stop_day = True
                        break
                    if e.code > 0:   # мешает одна фраза - по одной, плохую пропускаем (и единственную тоже)
                        got = {}
                        for p in part:
                            try:
                                got.update(report([p], lr))
                            except DirectError as e1:
                                if e1.code <= 0:
                                    raise
                                if e1.code in DAY_ERRORS:
                                    # лимит кончился посреди пачки: загруженное сохранить и ждать дня, как выше. Раньше
                                    # ошибка уходила наружу, и загрузка вставала с ошибкой вместо ожидания
                                    JOB["detail"] = str(e1)
                                    soon = used_today() <= len(part)
                                    if not soon:
                                        _put(day=_today(), used=DAY_LIMIT)
                                    stop_day = True
                                    break
                                got[_clean(p)] = 0
                            time.sleep(PAUSE)
                    else:
                        raise
                _store(data["host"], lr, region, got, kind)
                if kind == "broad" and int(lr) != 225:
                    _rf_flags(data["host"], lr, region, part)
                if also:
                    _store(data["host"], lr, region, also, "also")
                if kind == "phr":
                    JOB["done"] = JOB.get("done", 0) + len(got)
                if stop_day:
                    break
                time.sleep(PAUSE)
            if stop_day and not _wait_day(soon):
                return
    except DirectError as e:
        JOB.update(state="error", msg=str(e))
        _event("err", str(e), folder)
    except Exception as e:   # noqa: BLE001 - показать в окне, а не уронить поток
        JOB.update(state="error", msg=f"Ошибка: {e}"[:300])
        _event("err", str(e), folder)


def _event(kind, text, folder):
    """Плашка в окне программы и запись в «Журнал» (window/events.py)."""
    try:
        from urllib.parse import quote
        from .window import events
        name = os.path.basename(folder or "")
        host = name.split("_")[0]
        if kind == "ok":
            events.push("ok", text, link="/semantics?f=" + quote(name), site=host)
        else:
            events.error(text, host, "Частотность из Директа")
    except Exception:   # noqa: BLE001 - уведомление не главное
        pass


def _next_folder():
    """Следующий сайт из «Загрузить частотность» для выбранных («next» в настройках Директа)."""
    with _lock:
        rest = [f for f in _cfg().get("next") or [] if os.path.isfile(os.path.join(_reports(), f, "семантика.json"))]
        nxt = rest.pop(0) if rest else ""
        _put(next=rest)
    return nxt


def start_many(folders):
    """Частотность для нескольких сайтов по очереди: сейчас идёт загрузка - сайты встают за ней.
    Лимит Директа 1 000 фраз в сутки: кончился - загрузка ждёт новых суток по Москве и продолжает сама."""
    folders = list(dict.fromkeys(os.path.basename(f) for f in folders if f))
    if not folders:
        return "Не выбрано ни одного сайта с семантикой."
    if not _cfg().get("token"):
        return "Сначала вставьте ключ Директа: Подключения → Яндекс Директ."
    busy = _thread and _thread.is_alive() and JOB.get("state") in ("running", "waiting")
    with _lock:
        have = list(_cfg().get("next") or [])
        cur = JOB.get("folder") if busy else ""
        _put(next=have + [f for f in folders if f not in have and f != cur])
    if busy:
        return ""
    return start(_next_folder())


def queued():
    return list(_cfg().get("next") or [])


def start(folder):
    """Начать (или продолжить) загрузку частотности для семантики проверки. Возвращает ошибку или ""."""
    global _thread
    if not _cfg().get("token"):
        return "Сначала вставьте ключ Директа: Подключения → Яндекс Директ."
    if _thread and _thread.is_alive():
        if JOB.get("state") not in ("running", "waiting"):
            return "Загрузка останавливается, нажмите ещё раз через несколько секунд."
        if JOB.get("folder") == folder:
            return ""
        return "Уже идёт загрузка частотности для другого сайта. Остановите её."
    JOB.clear()
    JOB.update(state="running", folder=folder, done=0, total=0, msg="")
    _put(job=folder)
    _thread = threading.Thread(target=_run, args=(os.path.join(_reports(), folder),), daemon=True)
    _thread.start()
    return ""


def stop():
    if JOB.get("state") in ("running", "waiting"):
        JOB.update(state="stopped", msg="Остановлено. Уже загруженное сохранено, «Загрузить» продолжит.")
    _put(job=None, next=[])   # и сайты, которые ждали за этим («для выбранных» в «Отчётах»)
    return ""


ALSO_KEEP = 10     # «что ещё искали» на фразу (SearchedAlso), хранится для вкладки «Спрос»
EMPTY_MAX = 5      # пустышка: в кавычках не больше стольких показов в месяц
EMPTY_BROAD = 30   # ... и с хвостами (без кавычек) тоже не больше - иначе фразу ищут, но длиннее
EMPTY_CHECK = 40   # сколько кандидатов в пустышки на сайт проверять без кавычек (это тоже фразы из суточного лимита)
BIG_MIN = 30       # неожиданно крупный: точно не меньше стольких


def _pool(data):
    """Запросы семантики: {фраза: (запрос, группа, оценка по подсказкам, место в подсказках Яндекса)}, группы,
    уровень спроса по подсказкам. Оценка — без очков за подсказки Google: они по всей России, а частота из
    Вордстата — по городу семантики. Иначе фраза, которую часто набирают в Google по стране, в Уфе выглядела
    «пустышкой» (по подсказкам спрос высокий, в Вордстате 0)."""
    from .semantics import repeated_word, tokens, norm
    rows, groups = {}, []
    for g in data["groups"]:
        ps = []
        for r in g.get("q") or []:
            p = _clean(phrase(r[0]))
            if r[7] or not p or repeated_word(tokens(norm(r[0]))):   # «тепловентиляторы тепловентиляторы» - дубль
                continue
            ps.append(p)
            y, gp = (r[4] or 0, r[5] or 0) if len(r) > 5 else (1, 0)
            google = max(1, 11 - gp) if gp else 0
            rows.setdefault(p, (r[0], g["name"], max(0, (r[3] or 0) - google), y))
        if ps:
            groups.append((g["name"], ps))
    sc = sorted((x[2] for x in rows.values()), reverse=True)
    hi, mid = (sc[len(sc) // 3], sc[len(sc) * 2 // 3]) if sc else (0, 0)
    # как полоски «Спроса» в окне; без подсказок Яндекса в регионе (оценка 0) - всегда низкий
    return rows, groups, lambda s: 1 if not s else 3 if s >= hi else 2 if s >= mid else 1


def _empty_candidates(data):
    """Кандидаты в пустышки (по подсказкам высокий спрос, в кавычках почти 0), ещё не проверенные без кавычек.
    В кавычках длинную фразу почти не ищут дословно - поэтому настоящая пустышка, только если и с хвостами мало."""
    lr, _ = region_of(data.get("city"))
    e = load(data["host"]).get(str(lr)) or {}
    phr, broad = e.get("phr") or {}, e.get("broad") or {}
    rows, _, level = _pool(data)
    cand = sorted((p for p in phr if p in rows and phr[p][0] <= EMPTY_MAX and level(rows[p][2]) == 3
                   and rows[p][3]),   # пустышка - только если её подсказывает Яндекс в этом же регионе
                  key=lambda p: -rows[p][2])[:EMPTY_CHECK]
    return [p for p in cand if p not in broad]


def progress(data):
    """Как идёт загрузка для семантики: всего и готово, дней осталось, последние фразы (было по подсказкам -
    стало точно), группы (сколько запросов уже с точной частотой) по спросу, пустышки (проверенные без кавычек) и
    неожиданно крупные запросы (не из одного слова: одно слово - часто омоним, «север» - не бренд)."""
    lr, region = region_of(data.get("city"))
    e = load(data["host"]).get(str(lr)) or {}
    phr, broad = e.get("phr") or {}, e.get("broad") or {}
    rows, glist, level = _pool(data)
    groups = []
    for name, ps in glist:
        done = [p for p in ps if p in phr]
        # запрос из одного слова в группе с названием из нескольких слов - не в сумму: «консультация» (3 028 - про
        # врачей и юристов) делала «Консультацию по стратегии роста» второй по спросу (primerline.agency).
        # Группа из одного слова («Кухни») своё слово считает
        multi = len(name.split()) > 1
        freq = sum(phr[p][0] for p in done if not (multi and len(rows[p][0].split()) == 1))
        groups.append({"name": name, "n": len(ps), "done": len(done), "freq": freq})
    groups.sort(key=lambda g: (-g["freq"], -g["done"], g["name"]))
    got = [(p, rows[p], phr[p][0]) for p in phr if p in rows]
    nv = e.get("nv") or {}
    sieved = {p for p, _, _ in got if p in nv and not nv[p][0]}   # ноль по флагу Директа, без отчёта Вордстата

    def item(p, x, f):
        return {"q": x[0], "group": x[1], "level": level(x[2]), "freq": f,
                "broad": broad[p][0] if p in broad else None}
    total, done = len(rows), len(got)
    rf = e.get("rf") or {}
    low = [x for x in got if level(x[1][2]) == 3 and x[1][3] and x[2] <= EMPTY_MAX and x[0] in broad
           and broad[x[0]][0] <= EMPTY_BROAD]
    empty = [x for x in low if not (rf.get(x[0]) or [0])[0]]   # по России ищут - не пустышка, а мало в городе
    return {"total": total, "done": done, "region": region, "sieved": len(sieved),
            "days": 0 if fast_ok() else -(-(total - done) // DAY_LIMIT), "fast": fast_ok(),
            "feed": [item(*x) for x in [x for x in got if x[0] not in sieved][-12:][::-1]],
            "groups": groups,
            "empty": [item(*x) for x in sorted(empty, key=lambda x: -x[1][2])[:10]],
            "city_small": [item(*x) for x in low if (rf.get(x[0]) or [0])[0]][:10],
            "empty_wait": len(_empty_candidates(data)),
            "big": [item(*x) for x in sorted((x for x in got if level(x[1][2]) <= 2 and x[2] >= BIG_MIN
                                              and len(x[0].split()) >= 2), key=lambda x: -x[2])[:10]]}


def job(folder=None):
    out = dict(JOB, used=used_today(), limit=DAY_LIMIT, has_token=bool(_cfg().get("token")), next=queued())
    if folder and JOB.get("folder") != folder:
        out.update(state="idle", msg="", done=0, total=0)
    return out


def _reports():
    from .window import REPORTS
    return REPORTS


def resume():
    """После перезапуска окна: продолжить загрузку, которая не закончилась."""
    folder = _cfg().get("job")
    if folder and os.path.isdir(os.path.join(_reports(), folder)) and _cfg().get("token"):
        start(folder)
    elif _cfg().get("next") and _cfg().get("token"):   # «для выбранных»: окно закрыли между сайтами
        nxt = _next_folder()
        if nxt:
            start(nxt)
