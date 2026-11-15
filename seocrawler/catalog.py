"""«Бренды и прочие»: одна общая таблица по всем проверенным сайтам - бренды
(марки, производители, комплектующие и материалы, модели) и свойства товаров (материал, стиль, вид изделия…), по
нишам: лист «Мебель», лист «Автосервис и автозапчасти»… Внутри листа - столбец «Вид» (группа): «Марки»,
«Производители», «Комплектующие и материалы», «Модели», «Материал», «Стиль»…

Пополняется сама: после каждой проверки сайта (бренды и свойства с сайта) и после каждой сборки семантики (там же
бренды из запросов). Новая ниша - новый лист, новый вид - новая группа в листе. У каждой строки: на каких сайтах
встречалось, когда добавлено, «новое» - добавлено последним обновлением.

Где лежит: «решения семантики/бренды и прочие.json» (данные) и «Бренды и прочие.xlsx» в папке «data» (его
можно загрузить в Google Таблицы: Файл → Импортировать). Бренды той же ниши, которые нашлись на 2 и больше сайтах,
семантика следующего сайта узнаёт в запросах сама (brands.build → known_brands).

Тестовые сайты (127.0.0.1, localhost) и запуск с CLAYLER_NO_USER_SETTINGS (автотесты) таблицу не трогают, если не
задан CLAYLER_CATALOG_FILE."""
import json
import os
import re
import time
from urllib.parse import urlsplit

from . import jsonfile, paths, sysproxy

NAME = "Бренды и прочие"
NO_NICHE = "Без ниши"
KNOWN_MIN = 2         # бренд ниши с стольких сайтов семантика узнаёт в запросах сама
GROUPS = {"for": "Марки: товары и услуги для них", "maker": "Производители", "parts": "Комплектующие и материалы",
          "": "Бренды", "model": "Модели"}
ORDER = [GROUPS[k] for k in ("for", "model", "maker", "parts", "")]
BRAND_GROUPS = [GROUPS[k] for k in ("for", "maker", "parts", "")]     # бренд - в одной из них, по этому порядку
QUERIES_MIN = 3       # бренд только из запросов (не с сайта) - в таблицу, если в стольких запросах


def _paths():
    f = os.environ.get("CLAYLER_CATALOG_FILE")
    if f:
        return f, os.path.splitext(f)[0] + ".xlsx"
    if os.environ.get("CLAYLER_NO_USER_SETTINGS"):
        return None, None
    return paths.data("решения семантики", NAME.lower() + ".json"), paths.data(NAME + ".xlsx")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("v") == 2:
            return d
    except (OSError, ValueError):
        pass
    return {"v": 2, "sites": {}, "items": {}, "last": {}}


def _host(s):
    return (urlsplit(s if "//" in (s or "") else "//" + (s or "")).hostname or "").removeprefix("www.")


def _local(host):
    return not host or host in ("localhost", "127.0.0.1", "::1") or host.endswith((".localhost", ".test"))


NICHE_SHARE = 0.2     # ниша по запросам или заголовкам сайта: столько строк со словами ниши и вдвое больше второй


def niche(data=None, folder=None, host=""):
    """Название ниши сайта (верхний уровень темы «Словаря»): выбранная человеком тема сайта; раздел марок машин
    (/auto/…, /cars/…) - «Автосервис и автозапчасти»; по запросам семантики; по title и H1 страниц. Слова ниши
    должны быть у NICHE_SHARE строк и вдвое чаще, чем у следующей ниши, - иначе «Без ниши» (барбершоп с одним
    «кредитом» в заголовках - не «Займы»)."""
    from .semantics import dictionary as DC
    try:
        N = DC.nodes()
        host = host or _host((data or {}).get("site") or "")
        own = DC._load()["sites"].get(DC.site_key(host))
        nid = own if own in N else ""
        if not nid and folder and "car" in N and _car_marks(folder, host):
            nid = "car"
        if not nid and data:
            nid = _detect([r[0] for g in data.get("groups") or [] for r in g.get("q") or []])
        if not nid and folder:
            nid = _detect(_titles(folder))
        ch = [x for x in DC.chain(nid, N) if x != DC.ROOT and x in N] if nid else []
        return N[ch[0]]["name"] if ch else NO_NICHE
    except Exception:
        return NO_NICHE


def _detect(lines):
    from .semantics import dictionary as DC
    from .semantics import _canon, keys, norm, tokens
    if not lines:
        return ""
    cks = [{_canon(keys(t)) for t in tokens(norm(q))} for q in lines]
    sh = sorted(((sum(1 for c in cks if c & DC._marks(nid)) / len(cks), nid) for nid, *_ in DC.NICHES), reverse=True)
    best, second = sh[0], (sh[1] if len(sh) > 1 else (0, ""))
    return best[1] if best[0] >= NICHE_SHARE and best[0] >= 2 * second[0] else ""


def _car_marks(folder, host):
    """На сайте раздел марок машин: от 8 марок «для них» в папке /auto/, /cars/ (brands._hubs)."""
    from .semantics import brands as BR
    pages, _f, _m = BR._site_cached(folder, host)
    return sum(1 for _n, u, k, _x in pages if k == "for" and BR.FOR_PATH.search(urlsplit(u).path)) >= BR.HUB_MIN


def _titles(folder):
    import sqlite3
    try:
        db = sqlite3.connect("file:" + os.path.join(folder, "crawl.db") + "?mode=ro", uri=True)
        rows = db.execute("SELECT COALESCE(h1, title) FROM pages WHERE status=200 AND COALESCE(h1, title) != '' "
                          "LIMIT 5000").fetchall()
        db.close()
        return [r[0] for r in rows]
    except Exception:
        return []


# кириллица, похожая на латиницу: «Coffeespaсe» с русской «с» → латинская
LOOK = str.maketrans("аАвВеЕкКмМнНоОрРсСтТуУхХ", "aABBeEkKmMHHoOpPcCTTyYxX")


def _fix(name):
    """Название без лишних пробелов; слово латиницей с русскими буквами внутри - латиницей."""
    out = []
    for w in re.sub(r"\s+", " ", name or "").strip().split(" "):
        lat = len(re.findall(r"[A-Za-z]", w))
        if lat and lat >= len(re.findall(r"[А-Яа-яЁё]", w)):
            w = w.translate(LOOK)
        out.append(w)
    return " ".join(out)


def _junk(name):
    """Не название: код модели или адреса («Air35fv1», «Blum2», «Germaniya1475504921»), одни цифры, длинная фраза."""
    return (not name or len(name) < 2 or len(name) > 40 or len(name.split()) > 4 or re.fullmatch(r"[\d\W_]+", name)
            or re.search(r"[A-Za-zА-Яа-я]\d|\d{5,}", name.replace(" ", "")) is not None and not re.fullmatch(
                r"[A-Za-zА-Яа-я]{1,4}[- ]?\d{1,3}", name))


def _norm(name):
    """Одно написание: без регистра, пробелов, дефисов и апострофов; латиница - по звучанию (Buggati = Bugatti)."""
    from .semantics.stem import sound
    t = re.sub(r"[\s\-'’`.]+", "", name.lower().replace("ё", "е"))
    return sound(t) if re.fullmatch(r"[a-z0-9&+]+", t) else t


def _key(nm, g, n, p=""):
    return "|".join((nm, "бренд" if g in BRAND_GROUPS else g, _norm(p) if p else "", _norm(n)))


def _items(folder, host, brands=None):
    """Что нашлось у сайта: [(вид, название, к чему относится)]."""
    from .semantics import brands as BR
    out = []
    if brands is not None:
        for b in brands.get("brands") or []:
            from_site = b.get("page") or b.get("logo") or b.get("filters") or b.get("user")
            if b.get("exact") is False and not b.get("user") and (b.get("n") or 0) < QUERIES_MIN:
                continue    # название придумано из адреса («~Bianca 2») и почти не ищут
            if not from_site and not b.get("kind") and (b.get("n") or 0) < QUERIES_MIN:
                continue
            out.append((GROUPS.get(b.get("kind") or "", GROUPS[""]), b["name"], ""))
            for m, _n in b.get("models") or []:
                out.append((GROUPS["model"], m, b["name"]))
    if folder and os.path.isfile(os.path.join(folder, "crawl.db")):
        pages, filters, models = BR._site_cached(folder, host)
        extra = BR.site_extra(folder, host)
        if brands is None:     # без семантики - только то, что на сайте; придуманные из адреса («~») - нет
            for name, _u, kind, _f in pages:
                if not name.startswith("~"):
                    out.append((GROUPS.get(kind, GROUPS[""]), name, ""))
            for name, *_r in filters:
                if not name.startswith("~"):
                    out.append((GROUPS["maker"], name, ""))
            for name, _u, _h, hint in extra["logos"]:
                out.append((GROUPS.get(hint, GROUPS[""]), name, ""))
        for b, m in models:
            out.append((GROUPS["model"], m, b))
        for facet, vals in extra["facets"]:
            for v, _n, _u in vals:
                out.append((facet, v, ""))
    seen, res = set(), []
    for g, n, p in out:
        n, p = _fix(n), _fix(p)
        if (re.search(r"\d{5,}", n) or not n) if g == GROUPS["model"] else _junk(n):
            continue
        k = _key("", g, n, p)
        if k not in seen:
            seen.add(k)
            res.append((g, n, p))
    return res


def update(folder, data=None, brands=None, host="", send=True):
    """Дописать в общую таблицу всё, что нашлось у сайта; вернуть путь к Excel или ""."""
    path, xlsx = _paths()
    host = host or _host((data or {}).get("site") or (data or {}).get("host") or "") or \
        os.path.basename(folder or "").split("_")[0].removeprefix("www.")
    if not path or _local(host):
        return ""
    items = _items(folder, host, brands)
    if not items:
        return ""
    nm = niche(data, folder, host)
    st = _load(path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    day = now[:10]
    # что сайт показывал раньше и больше не показывает - убрать сайт у строки (строка без сайтов - уходит)
    for k, it in list(st["items"].items()):
        if host in it["sites"]:
            del it["sites"][host]
            if not it["sites"]:
                del st["items"][k]
    # то же свойство под другим словом на другом сайте («Стиль» и «Стиле») - в одну группу
    from .semantics.logos import _same
    have = list(dict.fromkeys(it["group"] for it in st["items"].values() if it["niche"] == nm))

    def worse(g):     # «Стиле», «Материалы» хуже, чем «Стиль», «Материал»
        return bool(re.search(r"[еийыуюая]$", g.lower())), len(g)

    def same_group(g):
        h = next((h for h in have if h == g or (" " not in g + h and _same(g.lower(), h.lower()))), None)
        if h is None or h == g:
            return g
        if worse(g) >= worse(h):
            return h
        for k, it in list(st["items"].items()):     # новое слово лучше - переименовать группу
            if it["niche"] == nm and it["group"] == h:
                it["group"] = g
                del st["items"][k]
                k2 = _key(nm, g, it["name"], it["parent"])
                if k2 in st["items"]:
                    st["items"][k2]["sites"].update(it["sites"])
                else:
                    st["items"][k2] = it
        have[have.index(h)] = g
        return g
    items = [(same_group(g), n, p) for g, n, p in items]
    new, run = 0, st.get("run", 0) + 1
    st["run"] = run
    for g, n, p in items:
        k = _key(nm, g, n, p)
        it = st["items"].get(k)
        if it is not None and g in BRAND_GROUPS and BRAND_GROUPS.index(g) < BRAND_GROUPS.index(it["group"]):
            it["group"] = g     # тот же бренд на другом сайте - марка или производитель, а не «Бренды»
        if it is None:
            it = st["items"][k] = {"niche": nm, "group": g, "name": n, "parent": p, "sites": {}, "added": now,
                                   "added_site": host, "run": run}
            new += 1
        it["sites"][host] = day
    st["sites"][host] = {"niche": nm, "at": now, "folder": os.path.basename(folder or "")}
    st["last"] = {"at": now, "site": host, "new": new, "run": run}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    jsonfile.save(path, st)
    try:
        write_xlsx(st, xlsx)
    except PermissionError:
        print(f"Не удалось обновить «{os.path.basename(xlsx)}» - наверное, он открыт. Закройте его: таблица "
              "обновится после следующей проверки или семантики.")
        return ""
    except ImportError:
        return ""
    if send:
        err = push(st)
        if err:
            print("Google-таблица не обновлена:", err)
    return xlsx


def known_brands(data):
    """Бренды ниши сайта с других сайтов (от KNOWN_MIN): [(название, вид)] - чтобы узнать их в запросах."""
    path, _x = _paths()
    if not path or not data or not os.path.isfile(path):
        return []
    host = _host(data.get("site") or data.get("host") or "")
    nm = niche(data)
    if nm == NO_NICHE:
        return []
    kind = {v: k for k, v in GROUPS.items() if k != "model"}
    out = []
    for it in _load(path)["items"].values():
        if (it["niche"] == nm and it["group"] in kind and not it["parent"]
                and len(set(it["sites"]) - {host}) >= KNOWN_MIN):
            out.append((it["name"], kind[it["group"]]))
    return out


def _sheet_name(s, used):
    s = re.sub(r"[\[\]:*?/\\]", " ", s).strip() or NO_NICHE
    while len(s) > 31 and "," in s:     # «Телефоны, ноутбуки, ремонт техники» → «Телефоны, ноутбуки»
        s = s.rsplit(",", 1)[0].strip()
    s = s[:31]
    base, i = s, 2
    while s.lower() in used:
        s = f"{base[:28]} {i}"
        i += 1
    used.add(s.lower())
    return s


# сайты и время добавления в таблицу не выводятся: ею пользуются несколько человек, это шум;
# в данных они есть - «Сайтов» и «Новое» считаются по ним
COLS = ["Вид", "Название", "Марка или бренд", "Сайтов", "Новое"]
WIDTHS = (30, 32, 22, 9, 8)


def tables(st):
    """Листы таблицы: [(имя, строки, номер строки заголовка, номера новых строк)] - для Excel и Google."""
    last = st.get("last") or {}
    by = {}
    for it in st["items"].values():
        by.setdefault(it["niche"], []).append(it)
    summary = [[NAME], [f"Бренды и свойства товаров со всех проверенных сайтов, по нишам. Последнее обновление: "
                        f"{_date(last.get('at', ''))}, сайт {last.get('site', '')}, добавлено {last.get('new', 0)}. "
                        "Жёлтым - новое с последнего обновления."], [],
               ["Ниша", "Сайтов", "Всего строк", "Новых", "Виды"]]
    out, used = [], {"сводка"}
    for nm in sorted(by, key=lambda x: (x == NO_NICHE, -len(by[x]), x)):
        rows = by[nm]
        groups = {}
        for it in rows:
            groups[it["group"]] = groups.get(it["group"], 0) + 1
        sites = {h for it in rows for h in it["sites"]}
        new = sum(1 for it in rows if it.get("run") == last.get("run"))
        summary.append([nm, len(sites), len(rows), new, ", ".join(f"{g} {n}" for g, n in _gsort(groups.items()))])
        order = {g: i for i, (g, _n) in enumerate(_gsort(groups.items()))}
        lines, fresh = [list(COLS)], []
        for it in sorted(rows, key=lambda x: (order[x["group"]], x["parent"].lower(), -len(x["sites"]),
                                              x["name"].lower())):
            is_new = it.get("run") == last.get("run")
            lines.append([it["group"], it["name"], it["parent"], len(it["sites"]), "да" if is_new else ""])
            if is_new:
                fresh.append(len(lines))
        out.append((_sheet_name(nm, used), lines, 1, fresh))
    return [("Сводка", summary, 4, [])] + out


def write_xlsx(st, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    bold, head_fill = Font(bold=True), PatternFill("solid", fgColor="E8EEF7")
    new_fill = PatternFill("solid", fgColor="FFF4C2")
    wrap = Alignment(wrap_text=True, vertical="top")
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows, head, fresh in tables(st):
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
        for c in ws[head]:
            c.font, c.fill, c.alignment = bold, head_fill, wrap
        if name == "Сводка":
            ws["A1"].font = Font(bold=True, size=14)
            for w, col in zip((34, 10, 12, 10, 90), "ABCDE"):
                ws.column_dimensions[col].width = w
            ws.auto_filter.ref = f"A{head}:E{len(rows)}"
            continue
        for i, w in enumerate(WIDTHS, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}1"
        for r in fresh:
            for c in ws[r]:
                c.fill = new_fill
    wb.save(path)


# ---------- запись прямо в Google Таблицу (бесплатно): скрипт таблицы (Apps Script) принимает данные от программы

GOOGLE_RX = re.compile(r"^https://script\.google\.com/(?:a/[^/]+/)?macros/s/[\w-]+/exec$")
SCRIPT = """// Clayler SEO: программа присылает сюда таблицу «Бренды и прочие» после каждой проверки и семантики.
var KEY = "{key}";

function doPost(e) {
  var d = JSON.parse(e.postData.contents);
  if (d.key !== KEY) return answer({ok: false, error: "Не тот ключ: скопируйте скрипт из программы заново"});
  var ss = SpreadsheetApp.getActiveSpreadsheet(), keep = {};
  d.sheets.forEach(function (s, i) {
    keep[s.name] = true;
    var sh = ss.getSheetByName(s.name) || ss.insertSheet(s.name, i);
    sh.clear();
    var w = 1;
    s.rows.forEach(function (r) { w = Math.max(w, r.length); });
    var rows = s.rows.map(function (r) { r = r.slice(); while (r.length < w) r.push(""); return r; });
    if (!rows.length) return;
    var rg = sh.getRange(1, 1, rows.length, w);
    rg.setValues(rows);
    var bg = rows.map(function () { return new Array(w).fill(null); });
    (s.fresh || []).forEach(function (n) { bg[n - 1] = new Array(w).fill("#fff4c2"); });
    bg[s.head - 1] = new Array(w).fill("#e8eef7");
    rg.setBackgrounds(bg);
    sh.getRange(s.head, 1, 1, w).setFontWeight("bold");
    sh.setFrozenRows(s.head);
  });
  var mine = PropertiesService.getDocumentProperties(), was = JSON.parse(mine.getProperty("sheets") || "[]");
  ss.getSheets().forEach(function (sh) {   // пустой «Лист1» и листы ниш, которых больше нет
    var n = sh.getName();
    if (!keep[n] && ss.getSheets().length > 1 && (sh.getLastRow() === 0 || was.indexOf(n) >= 0)) ss.deleteSheet(sh);
  });
  mine.setProperty("sheets", JSON.stringify(Object.keys(keep)));
  return answer({ok: true, url: ss.getUrl()});
}

function answer(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
"""


def _gpath():
    path, _x = _paths()
    return os.path.join(os.path.dirname(path), "google таблица.json") if path else None


def google():
    """{"url": адрес скрипта, "key": ключ, "sheet": адрес таблицы, "at": когда отправлено, "error": ...}."""
    p = _gpath()
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return {}


def _gsave(g):
    p = _gpath()
    if p:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        jsonfile.save(p, g)


def script():
    """Текст скрипта для таблицы со своим ключом (ключ создаётся один раз)."""
    import secrets
    g = google()
    if not g.get("key"):
        g["key"] = secrets.token_hex(16)
        _gsave(g)
    return SCRIPT.replace("{key}", g["key"])


def google_connect(url):
    """Запомнить адрес скрипта и сразу отправить таблицу. Возвращает текст ошибки или ""."""
    url = (url or "").strip()
    if not GOOGLE_RX.match(url):
        return ("Нужен адрес веб-приложения из окна «Новое развертывание»: он начинается с "
                "https://script.google.com/macros/s/ и заканчивается на /exec.")
    script()
    g = google()
    g["url"] = url
    _gsave(g)
    return push()


def google_off():
    g = google()
    for k in ("url", "sheet", "at", "error"):
        g.pop(k, None)
    _gsave(g)


def push(st=None):
    """Отправить всю таблицу в Google. Возвращает текст ошибки или "" (не подключено - тоже "")."""
    import urllib.request
    g = google()
    if not g.get("url"):
        return ""
    if st is None:
        path, _x = _paths()
        st = _load(path)
    body = json.dumps({"key": g.get("key"), "sheets": [{"name": n, "rows": r, "head": h, "fresh": f}
                                                        for n, r, h, f in tables(st)]},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(g["url"], data=body, headers={"Content-Type": "application/json"})
    try:
        import ssl
        try:
            import truststore
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            ctx = ssl.create_default_context()
        with sysproxy.urlopen(req, timeout=180, context=ctx) as r:
            text = r.read().decode("utf-8", "replace")
        try:
            ans = json.loads(text)
        except ValueError:
            ans = {"ok": False, "error": "Google ответил не так: проверьте, что при развертывании выбран тип "
                                         "«Веб-приложение» и «У кого есть доступ» - «Все»."}
    except Exception as e:
        ans = {"ok": False, "error": "Не получилось отправить в Google: " + str(e)[:150]}
    g = google()
    if ans.get("ok"):
        g.update(sheet=ans.get("url") or g.get("sheet", ""), at=time.strftime("%Y-%m-%d %H:%M:%S"), error="")
    else:
        g["error"] = ans.get("error") or "ошибка"
    _gsave(g)
    return "" if ans.get("ok") else g["error"]


def _date(s):
    """«2026-10-11 14:09:42» → «11.10.2026 14:09»."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)", s or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)} {m.group(4)}" if m else s


def _gsort(pairs):
    """Сначала бренды (марки, модели, производители, комплектующие), потом свойства по числу строк."""
    return sorted(pairs, key=lambda x: (ORDER.index(x[0]) if x[0] in ORDER else len(ORDER), -x[1], x[0]))


def rebuild_all(reports=None):
    """Собрать таблицу заново по последней проверке каждого сайта (с семантикой, если она собрана)."""
    from .semantics import export as SX, decisions as D, plan
    if reports is None:
        from .window import REPORTS as reports
    path, _x = _paths()
    if path and os.path.isfile(path):
        os.remove(path)
    latest = {}
    for name in sorted(os.listdir(reports)):
        full = os.path.join(reports, name)
        if "_20" in name and os.path.isfile(os.path.join(full, "crawl.db")):
            latest[name.split("_")[0].removeprefix("www.")] = full
    out = ""
    for host, full in latest.items():
        try:
            raw = SX.load(full) if os.path.isfile(os.path.join(full, "семантика.json")) else None
            if raw:
                from .semantics import brands as BR
                data = plan.enrich(D.apply(raw, full), full)
                out = update(full, data, BR.build(data, full), send=False) or out
            else:
                out = update(full, host=host, send=False) or out
            print(f"{host}: готово")
        except Exception as e:
            print(f"{host}: не получилось - {str(e)[:120]}")
    err = push()
    if err:
        print("Google-таблица не обновлена:", err)
    return out


if __name__ == "__main__":
    print(rebuild_all())
