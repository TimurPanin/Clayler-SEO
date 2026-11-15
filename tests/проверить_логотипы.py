"""Автотест: бренды из блоков логотипов, свойства из адресов и общая таблица «Бренды и прочие»
(пример - lk-fabrika.ru: «Используем лучшую фурнитуру - бренды», логотипы «Бренд Blum», «Бренд Hettich»).
Без сети. Проверяется: блок логотипов по слову «Бренд» в alt и по заголовку над названиями; плитки материалов,
значки соцсетей, «Наши клиенты» и способы оплаты - не бренды; вид «комплектующие» в семантике (brands.build);
свойства из адресов (/material-mdf, /style-loft, /iz-ekokozhi) со словами из H1 и названием свойства со страницы;
раздел-адрес «gazovye-kotly» и товары с уникальными адресами - не свойства; таблица: лист ниши «Мебель», вид
«Комплектующие и материалы», новое, сайты, бренд с двух сайтов узнаётся в запросах третьего."""
import json
import os
import sys
import tempfile
import zlib

TMP = tempfile.mkdtemp(prefix="clayler-logos-")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
os.environ["CLAYLER_DICT_FILE"] = os.path.join(TMP, "словарь.json")
os.environ["CLAYLER_CATALOG_FILE"] = os.path.join(TMP, "бренды и прочие.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import brands as BR, logos, plan  # noqa: E402
from seocrawler.semantics.tree import _ro  # noqa: E402
from seocrawler import catalog  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


BRANDS = ["Blum", "Русский ламинат", "Egger", "Kronospan", "Boyard", "Hettich"]


def site(host, brands, extra_pages=()):
    """Сайт мебели: на главной блок логотипов брендов, плитки материалов, соцсети, клиенты; каталог со свойствами."""
    S = f"https://{host}"
    own = os.path.join(TMP, "reports", f"{host}_2026-10-11_10-00-00")
    os.makedirs(own)
    st = Store(os.path.join(own, "crawl.db"))
    st.set_meta("start", S + "/")
    text = ["Кухни и шкафы на заказ", "Материалы", "МДФ", "ЛДСП", "Массив дерева", "Стекло", "Пластик",
            "Материалы с которыми мы", "добиваемся максимального качества", "Используем лучшую фурнитуру - бренды",
            *brands, "Большой выбор материалов / Любое наполнение", "МДФ", "ЛДСП", "Массив дерева", "Стекло",
            "Пластик", "Стиль мебели", "Наши клиенты", "Сбербанк", "Газпром", "Яндекс", "Ростелеком",
            "Фабрика мебели на заказ по индивидуальным размерам в Москве. Делаем кухни, шкафы и гардеробные."]
    rows = [(S + "/", "Кухни и шкафы на заказ", "Мебель на заказ в Москве", text)]
    img = [(f"{S}/images/soc/{n}.svg", "") for n in ("telegram", "vk", "youtube", "whatsapp", "max")]
    img += [(f"{S}/cache/{i}.5483.png.webp", f"Бренд {b}") for i, b in enumerate(brands)]
    img += [(f"{S}/cache/{m}.57b4.jpg.webp", t) for m, t in (("mdf", "МДФ"), ("ldsp", "ЛДСП"),
                                                             ("massiv", "Массив дерева"), ("steklo", "Стекло"),
                                                             ("plastik", "Пластик"))]
    img += [(f"{S}/upload/clients/{n}.png", t) for n, t in (("sber", "Сбербанк"), ("gazprom", "Газпром"),
                                                            ("ya", "Яндекс"), ("rt", "Ростелеком"))]
    img += [(f"{S}/upload/pay/{n}.svg", n) for n in ("visa", "mastercard", "mir", "sbp")]
    # каталог: свойства в адресах
    MAT = [("mdf", "МДФ"), ("ldsp", "ЛДСП"), ("massiv", "массива"), ("shpon", "шпона"), ("steklo", "стекла")]
    STY = [("loft", "лофт"), ("klassika", "классика"), ("modern", "модерн"), ("provans", "прованс")]
    for cat, word in (("kuhni", "Кухни"), ("shkafy", "Шкафы"), ("prihozhie", "Прихожие")):
        for slug, ru in MAT:
            rows.append((f"{S}/katalog/{cat}/material-{slug}", f"{word} из {ru}", "", []))
        for slug, ru in STY:
            rows.append((f"{S}/katalog/{cat}/style-{slug}", f"{word} в стиле {ru}", "", []))
        for slug, ru in (("ekokozhi", "экокожи"), ("rogozhki", "рогожки"), ("velyura", "велюра"), ("kozhi", "кожи")):
            rows.append((f"{S}/katalog/{cat}/iz-{slug}", f"{word} из {ru}", "", []))
    # не свойства: разделы «Газовые котлы…» и товары с уникальными адресами
    for slug, ru in (("kotly", "котлы"), ("kolonki", "колонки"), ("gorelki", "горелки"), ("plity", "плиты")):
        for i in range(3):
            rows.append((f"{S}/gazovye-{slug}/item{i}", f"Газовые {ru} модель {i}", "", []))
    for i, (slug, ru) in enumerate((("zazhiganiya", "зажигания"), ("pitaniya", "питания"), ("datchika", "датчика"),
                                    ("nasosa", "насоса"), ("klapana", "клапана"))):
        rows.append((f"{S}/goods/kabel-{slug}", f"Кабель {ru}", "", []))
    rows += list(extra_pages)
    for u, h1, title, lines in rows:
        st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": title or h1,
                      "h1": h1, "word_count": 300,
                      "blocks": zlib.compress("\n".join(lines).encode("utf-8")) if lines else None})
    st.add_images([(S + "/", src, alt, 1, "", 0, 0) for src, alt in img])
    st.commit()
    st.db.close()
    return S, own


S, OWN = site("mebel-one.ru", BRANDS)
b = logos.blocks(_ro(OWN), "mebel-one.ru")
names = [x[0] for x in b]
check(names == BRANDS, f"бренды из блока логотипов: {names}")
check(all(x[3] == "parts" for x in b) and "фурнитуру" in b[0][2], f"вид «комплектующие» по заголовку: {b[:2]}")
check(not {"МДФ", "ЛДСП", "Сбербанк", "Telegram", "Visa", "Mastercard"} & set(names), "лишнее в брендах")

# 2. без слова «Бренд» в alt - по заголовку над названиями; список текстом без картинок
blk = ["Мы ремонтируем бренды", "Bosch", "Siemens", "Electrolux", "Candy", "Ariston", "Наши мастера приедут сегодня."]
S2, OWN2 = site("mebel-two.ru", ["Blum", "Egger", "Hettich", "Kronospan"],
                [("https://mebel-two.ru/remont", "Ремонт техники", "", blk)])
b2 = {x[0]: x for x in logos.blocks(_ro(OWN2), "mebel-two.ru")}
check({"Bosch", "Siemens", "Electrolux", "Candy", "Ariston"} <= set(b2) and b2["Bosch"][3] == "for",
      f"список брендов текстом, «ремонтируем» - марки: {sorted(b2)}")

# 3. свойства из адресов
rows = _ro(OWN).execute("SELECT url, h1, title FROM pages WHERE status=200").fetchall()
fs = dict(logos.facets(rows, "mebel-one.ru", ["Материалы", "Стиль", "мебели"]))
check(set(fs) == {"Материалы", "Стиль", "Из чего"}, f"свойства: {sorted(fs)}")
check([v[0] for v in fs.get("Материалы", [])][:2] == ["МДФ", "ЛДСП"] and fs.get("Материалы", [[0, 0]])[0][1] == 3,
      f"значения материала: {fs.get('Материалы')}")
check({v[0] for v in fs.get("Стиль", [])} == {"лофт", "классика", "модерн", "прованс"}, f"стиль: {fs.get('Стиль')}")
check(logos.detranslit("pomeshenie") == "помешение" and logos._same("prixozhaya", "прихожая"), "транслит")

# 4. семантика: вид «комплектующие», бренд не ищут - всё равно в списке
def q(text, score=5):
    return [text, "", "Общий", score, 1, 1, 0, "", 0, "", 0, 0, 0, 0]


groups = [{"name": "Кухни на заказ", "kind": "page", "page": S + "/", "todo": "Продвигать эту страницу", "score": 90,
           "rivals": [], "a": {"problems": []},
           "q": [q("кухни на заказ"), q("кухня с фурнитурой blum"), q("кухня egger"), q("шкаф купе на заказ"),
                 q("кухня из мдф на заказ"), q("кухня с фурнитурой hettich")]}]
data = plan.enrich({"site": S + "/", "host": "mebel-one.ru", "groups": groups, "made": "11.10.2026 10:00",
                    "city": "Москва", "competitors": [], "total": 6, "dropped": {}}, OWN)
r = BR.build(data, OWN)
by = {x["name"]: x for x in r["brands"]}
check(set(BRANDS) <= set(by) and all(by[n]["kind"] == "parts" for n in BRANDS), f"семантика: {r['kinds']} {sorted(by)}")
check(by.get("Blum", {}).get("n") == 1 and by.get("Hettich", {}).get("n") == 1 and by.get("Boyard", {}).get("st") == "decide"
      and by.get("Blum", {}).get("logo") == S + "/", f"Blum ищут, Boyard - решить: {by.get('Blum')} {by.get('Boyard')}")
v = BR.view(r)
check(v["kinds"]["parts"] == 6 and "Комплектующие" in v["kind_names"]["parts"], f"окно: {v['kinds']}")

# 5. общая таблица «Бренды и прочие»
xl = catalog.update(OWN, data, r)
st = json.load(open(os.environ["CLAYLER_CATALOG_FILE"], encoding="utf-8"))
items = list(st["items"].values())
check(xl and os.path.isfile(xl), "Excel таблицы не записан")
check(st["sites"]["mebel-one.ru"]["niche"] == "Мебель", f"ниша: {st['sites']}")
check({i["name"] for i in items if i["group"] == "Комплектующие и материалы"} == set(BRANDS), "комплектующие в таблице")
check({i["group"] for i in items} >= {"Комплектующие и материалы", "Материалы", "Стиль", "Из чего"},
      f"группы: {sorted({i['group'] for i in items})}")
catalog.update(OWN2)       # второй сайт - без семантики, только с сайта
st = json.load(open(os.environ["CLAYLER_CATALOG_FILE"], encoding="utf-8"))
blum = next(i for i in st["items"].values() if i["name"] == "Blum")
check(set(blum["sites"]) == {"mebel-one.ru", "mebel-two.ru"} and st["last"]["site"] == "mebel-two.ru", f"Blum: {blum}")
check(st["last"]["new"] >= 5 and all(i["run"] != st["last"]["run"] for i in st["items"].values() if i["name"] == "Blum"),
      f"новое - только с последнего обновления: {st['last']}")
from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(xl)
check(wb.sheetnames[:2] == ["Сводка", "Мебель"], f"листы: {wb.sheetnames}")
ws = wb["Мебель"]
hdr = [c.value for c in ws[1]]
row = next(r_ for r_ in ws.iter_rows(min_row=2, values_only=True) if r_[1] == "Bosch")
check(hdr[:4] == ["Вид", "Название", "Марка или бренд", "Сайтов"] and row[0] == catalog.GROUPS["for"] and row[4] == "да" and len(hdr) == 5,
      f"Excel: {hdr} {row}")
# бренд с двух сайтов той же ниши семантика третьего узнаёт в запросах
S3, OWN3 = site("mebel-three.ru", ["Aristo", "Integra", "Miragle", "Lamarty"])
d3 = plan.enrich({"site": S3 + "/", "host": "mebel-three.ru", "groups": [dict(groups[0], page=S3 + "/")],
                  "made": "11.10.2026 10:00", "city": "Москва", "competitors": [], "total": 6, "dropped": {}}, OWN3)
kb = dict(catalog.known_brands(d3))
check(kb.get("Blum") == "parts" and "Hettich" in kb and "Boyard" not in kb, f"бренды ниши с других сайтов: {kb}")
r3 = {x["name"]: x for x in BR.build(d3, OWN3)["brands"]}
check(r3.get("Blum", {}).get("n") == 1 and r3["Blum"]["kind"] == "parts" and "Boyard" not in r3,
      f"Blum узнан в запросах, Boyard не ищут - не в списке: {sorted(r3)}")
# 6. Google-таблица: адрес проверяется, таблица уходит POST-ом, ответ после перенаправления (как у Apps Script)
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
got = {}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        got.update(json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")))
        self.send_response(302)
        self.send_header("Location", "/echo")
        self.end_headers()

    def do_GET(self):
        ok = got.get("key") == catalog.google().get("key")
        b = json.dumps({"ok": ok, "url": "https://docs.google.com/spreadsheets/d/x/edit"} if ok else
                       {"ok": False, "error": "Не тот ключ"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
check(catalog.google_connect("https://example.com/x") != "", "чужой адрес принят как адрес скрипта")
check("var KEY" in catalog.script() and catalog.google().get("key") in catalog.script(), "ключ в скрипте")
g = catalog.google()
g["url"] = f"http://127.0.0.1:{srv.server_address[1]}/exec"
catalog._gsave(g)
err = catalog.push()
names = [x["name"] for x in got.get("sheets") or []]
check(err == "" and names[:2] == ["Сводка", "Мебель"] and catalog.google().get("sheet", "").startswith("https://docs"),
      f"отправка в Google: {err} {names}")
meb = next((x for x in got.get("sheets") or [] if x["name"] == "Мебель"), {})
check(meb.get("head") == 1 and meb["rows"][0][0] == "Вид" and meb.get("fresh"), "лист для Google: заголовок и новое")
srv.shutdown()
# сам скрипт таблицы: запускается в node с подменой SpreadsheetApp и пишет листы
import shutil  # noqa: E402
import subprocess  # noqa: E402
if shutil.which("node"):
    stub = """var log = [], sheets = {"Лист1": {rows: 0}};
function Sheet(n) { this.n = n; }
Sheet.prototype = {clear: function () {}, getRange: function () { var s = this; return {setValues: function (v) { sheets[s.n].rows = v.length; return this; },
  setBackgrounds: function () { return this; }, setFontWeight: function () { return this; }}; },
  setFrozenRows: function () {}, getName: function () { return this.n; }, getLastRow: function () { return sheets[this.n].rows; }};
var SpreadsheetApp = {getActiveSpreadsheet: function () { return {
  getSheetByName: function (n) { return sheets[n] ? new Sheet(n) : null; },
  insertSheet: function (n) { sheets[n] = {rows: 0}; return new Sheet(n); },
  getSheets: function () { return Object.keys(sheets).map(function (n) { return new Sheet(n); }); },
  deleteSheet: function (s) { delete sheets[s.n]; }, getUrl: function () { return "u"; }}; }};
var props = {}, PropertiesService = {getDocumentProperties: function () { return {getProperty: function (k) { return props[k]; }, setProperty: function (k, v) { props[k] = v; }}; }};
var ContentService = {MimeType: {JSON: 1}, createTextOutput: function (t) { return {setMimeType: function () { return t; }}; }};
"""
    body = json.dumps({"key": catalog.google()["key"], "sheets": [{"name": n, "rows": r, "head": h, "fresh": f}
                       for n, r, h, f in catalog.tables(json.load(open(os.environ["CLAYLER_CATALOG_FILE"],
                                                                        encoding="utf-8")))]}, ensure_ascii=False)
    js = stub + catalog.script() + "\nconsole.log(doPost({postData: {contents: " + json.dumps(body) + \
        "}}) + ' ' + Object.keys(sheets).join('|'));\n"
    jp = os.path.join(TMP, "script.js")
    open(jp, "w", encoding="utf-8").write(js)
    res = subprocess.run(["node", jp], capture_output=True, text=True, encoding="utf-8")
    check('"ok":true' in res.stdout and "Мебель" in res.stdout and "Лист1" not in res.stdout,
          f"скрипт таблицы: {res.stdout[-300:]} {res.stderr[-300:]}")

# тестовые сайты и автотесты без CLAYLER_CATALOG_FILE таблицу не трогают
check(catalog._local("127.0.0.1") and catalog.update(OWN, host="127.0.0.1") == "", "тестовый сайт попал в таблицу")

if fails:
    print("ЛОГОТИПЫ И ТАБЛИЦА: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Логотипы и «Бренды и прочие»: всё в порядке")
