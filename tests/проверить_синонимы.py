"""Автотест синонимов по нишам (semantics/synonyms.py): ниша определяется сама, синонимы - в одной группе (строки не
склеиваются), омонимы по нишам («батарея»), короткое слово рядом с числом, пары «похоже на синонимы», «да» и «нет»,
раскладка новых запросов со словарём ниши (assign.run)."""
import json
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-syn-")
os.environ["CLAYLER_DICT_FILE"] = os.path.join(TMP, "словарь.json")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари семантики.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.semantics import assign, dictionary as D, dicts as DI, synonyms as S

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def row(q, score=5):
    return [q, "", "Общий", score, 0, 0, 0, "", 0, "", 0, 0, 0, 0]


def heat():
    return {"host": "www.teplo-dom.ru", "groups": [
        {"name": "Бойлеры косвенного нагрева", "q": [row("бойлер косвенного нагрева", 20), row("бойлер косвенного нагрева купить"),
                                                     row("бойлер косвенного нагрева 100 литров")]},
        {"name": "Водонагреватели", "q": [row("водонагреватель косвенного нагрева", 8), row("водонагреватели электрические"),
                                          row("водонагреватель накопительный")]},
        {"name": "Циркуляционные насосы", "q": [row("циркуляционный насос для отопления", 15), row("насос циркуляционный grundfos")]},
        {"name": "Радиаторы", "q": [row("радиаторы отопления"), row("радиатор биметаллический")]},
        {"name": "Котлы", "q": [row("газовый котел"), row("котел отопления"), row("котлы газовые")]},
        {"name": "Насосы", "q": [row("циркуляционник для отопления", 3), row("насос для скважины")]},
        # «пароль» - чужая тема (ниша не та): одна строка в группе, не переезжает
        {"name": "Ремонт", "q": [row("ремонт котла уфа"), row("ремонт бойлера уфа"), row("наладка котла уфа"),
                                 row("ремонт котла цена"), row("наладка котла цена"), row("ремонт котла отзывы"),
                                 row("наладка котла отзывы"), row("ремонт котла на дому"), row("наладка котла на дому")]}]}


# ниша по запросам
d = heat()
check(S.detect(d)[0] == "heat", f"ниша котлов: {S.detect(d)}")
check(S.detect({"host": "x.ru", "groups": [{"name": "А", "q": [row("ремонт айфона"), row("замена экрана iphone"),
                                                                 row("ноутбук не включается")]}]})[0] == "tech", "ниша телефонов")

# синонимы - в одной группе, строки не склеиваются
S.apply(d)
names = {r[0]: g["name"] for g in d["groups"] for r in g["q"]}
check(names["водонагреватель косвенного нагрева"] == "Бойлеры косвенного нагрева",
      f"водонагреватель = бойлер - в одну группу: {names['водонагреватель косвенного нагрева']}")
check(names["циркуляционник для отопления"] == "Циркуляционные насосы",
      f"циркуляционник = циркуляционный насос (фраза в любой форме и порядке): {names['циркуляционник для отопления']}")
check(names["водонагреватели электрические"] == "Водонагреватели", "у остальных строк группа прежняя")
check(len(names) == sum(len(g["q"]) for g in heat()["groups"]), "строки не склеиваются и не теряются")
check(len(d["syn"]["moved"]) == 2 and d["syn"]["niche"] == "heat", f"что переехало: {d['syn']['moved']}")
check(S.apply(d)["syn"]["moved"] == d["syn"]["moved"], "повторно не применяется")

# омонимы по нишам и короткое слово рядом с числом
Wh = S.words(D.UNITS + D.node_lines("heat", "syn"))
Wt = S.words(D.UNITS + D.node_lines("tech", "syn"))
Wa = S.words(D.UNITS + D.node_lines("car", "syn"))
check(Wh.of("батарея отопления") == Wh.of("радиатор"), "у котлов батарея отопления = радиатор")
check(Wt.of("замена батареи айфон") == Wt.of("замена аккумулятора iphone"), "у телефонов батарея = аккумулятор, айфон = iphone")
check(Wh.of("батарея айфон") != Wh.of("аккумулятор айфон"), "у котлов батарея - не аккумулятор")
check(Wa.of("сто уфа") == Wa.of("автосервис уфа"), "у автосервиса сто = автосервис")
check(Wa.of("сто 100 рублей") != Wa.of("автосервис 100 рублей"), "короткое слово рядом с числом - не синоним")
check(Wh.of("сто уфа") != Wh.of("автосервис уфа"), "у котлов сто - не автосервис")

# раскладка новых запросов со словарём ниши
g2 = [("Бойлеры", ["бойлер косвенного нагрева", "бойлер 100 литров", "бойлер для котла"]),
      ("Расширительные баки", ["расширительный бак для отопления", "бак расширительный 8 литров"])]
res = {r["q"]: r["group"] for r in assign.run(g2, [{"q": "водонагреватель для котла"}, {"q": "экспанзомат 8 литров"}], data=heat())}
check(res.get("водонагреватель для котла") == "Бойлеры", f"раскладка: водонагреватель → бойлеры: {res}")
check(res.get("экспанзомат 8 литров") == "Расширительные баки", f"раскладка: экспанзомат → баки: {res}")

# пары «похоже на синонимы», «да» и «нет»
d = heat()
pairs = {(p["a"], p["b"]) for p in S.suggest(d)}
check(("наладка", "ремонт") not in pairs and ("ремонт", "наладка") not in pairs,
      f"без доказательства (одно место в запросе) пара не предлагается: {pairs}")
tc = {"host": "teplo-dom.ru", "groups": [{"name": "Термопары", "q": [row(q) for q in (
    "термопара ха купить", "термопара ха цена", "термопара хромель алюмель купить", "термопара хромель алюмель цена",
    "ру уфа купить", "рено уфа купить", "ру уфа цена", "рено уфа цена")]}]}
pairs = {(p["a"], p["b"], p["why"]) for p in S.suggest(tc)}
check(("ха", "хромель алюмель", "сокращение") in pairs, f"сокращение с одинаковым хвостом: {pairs}")
check(not any(p[0] == "ру" for p in pairs), "сокращение с городом в полном названии - не пара")
D.confirm(d, "ремонт", "наладка")
lines = D.node_lines("heat", "syn")
check(any("ремонт" in l and "наладка" in l for l in lines), f"«да» - в словаре ниши: {lines[-2:]}")
check(not any({p["a"], p["b"]} == {"ремонт", "наладка"} for p in S.suggest(heat())), "подтверждённая пара больше не предлагается")
D.reject(d, "радиатор", "батарея")
lines = D.node_lines("heat", "syn")
check(not any("радиатор" in l and "батарея =" in l.replace("батарея отопления", "") for l in lines) and
      any(l.startswith("радиатор = батарея отопления") for l in lines), f"«нет» убирает пару из словаря: {lines}")
with open(os.environ["CLAYLER_DICT_FILE"], encoding="utf-8") as f:
    st = json.load(f)
check("батарея|радиатор" in st["no"]["heat"], "«нет» запомнено")
check(D.meta(st, "heat", "syn", next(l for l in lines if "наладка" in l))["src"] == "пара с сайта teplo-dom.ru", "откуда пара")
D.set_site("teplo-dom.ru", "tech")
check(S.niche_of(heat()) == ("tech", True), "ниша, выбранная вручную (без www)")
D.set_site("teplo-dom.ru", "car")
check(S.niche_of(heat()) == ("car", True), "другая ниша вручную")
D.set_site("teplo-dom.ru", None)
check(S.niche_of(heat()) == ("heat", False), "снова сама по запросам")
check(S.tidy(["циркуляционный насос", "циркуляционник"]) == "циркуляционник = циркуляционный насос", "первым - одно слово")
v = S.view(S.apply(heat()))
check(v["niche"] == "heat" and v["lines"] and v["moved"], "вид для окна")

# ---------- «Словарь»: дерево тем, наследование, виды, в файл и из файла
boil = D.add_node("Котлы", "heat")
water = D.add_node("Водонагреватели", "heat")
try:
    D.add_node("Глубже", boil)
    check(False, "глубже трёх уровней нельзя")
except ValueError:
    pass
D.add("common", "syn", "дешевый = бюджетный")
D.add(boil, "syn", "котел = котлоагрегат")
D.add(boil, "junk", "майнкрафт")
D.add("heat", "brand", "Navien = навиен")
D.set_site("teplo-dom.ru", boil)
ls = D.lines(heat())
check("котел = котлоагрегат" in ls and any("водонагреватель = бойлер" in x for x in ls) and "дешевый = бюджетный" in ls,
      "подтема видит свои, ниши и «Общего»")
D.set_site("teplo-dom.ru", water)
ls = D.lines(heat())
check("котел = котлоагрегат" not in ls and any("водонагреватель = бойлер" in x for x in ls), "соседняя подтема не видит чужие")
check(D.junk_for("teplo-dom.ru") == [], "мусорные слова соседней подтемы не действуют")
D.set_site("teplo-dom.ru", boil)
check(D.junk_for("teplo-dom.ru") == ["майнкрафт"], f"мусорные слова темы: {D.junk_for('teplo-dom.ru')}")
check(D.lines(heat(), ("brand",), root=False) == ["Navien = навиен"], "бренды ниши")
check("дешевый = бюджетный" in DI.load()["synonyms"], "«Общий» - прежний словарь синонимов")
D.add(boil, "syn", "котел = котлы отопления")
check(sum(1 for x in D.node_lines(boil, "syn") if "котел" in x) == 1, "общее слово - в ту же строку")
D.edit(boil, "syn", D.node_lines(boil, "syn")[0], "котел = котлоагрегат = теплогенератор")
check(D.node_lines(boil, "syn") == ["котел = котлоагрегат = теплогенератор"], f"правка: {D.node_lines(boil, 'syn')}")
D.move(boil, "syn", "котел = котлоагрегат = теплогенератор", "heat")
check(not D.node_lines(boil, "syn") and "котел = котлоагрегат = теплогенератор" in D.node_lines("heat", "syn"), "перенос в другую тему")
D.rename_node(water, "Бойлеры")
check(D.nodes()[water]["name"] == "Бойлеры", "переименование")
x = D.export()
D.delete_node(boil)
check(boil not in D.nodes() and "майнкрафт" in D.node_lines("heat", "junk") and D.site_node(heat())[0] == "heat",
      "удаление темы: правила и сайт - к родителю")
D.remove("heat", "junk", "майнкрафт")
n = D.import_(x)
check(n >= 1 and any(m["name"] == "Котлы" for m in D.nodes().values()), f"из файла: тема и строки вернулись ({n})")
check(D.import_(x) == 0, "второй раз из файла - без повторов")
try:
    D.import_({"a": 1})
    check(False, "чужой файл не загружается")
except ValueError:
    pass
site = {"idx": {}, "qs": []}
for i, q in enumerate(["бойлер косвенного нагрева", "бойлер 100", "водонагреватель"]):
    for t in D.tokens(D.norm(q)):
        site["idx"].setdefault(D._canon(D.keys(t)), set()).add(i)
check(D._hits("водонагреватель = бойлер", "syn", site) == 2, "сработало: в двух запросах другое написание")
v = D.view()
check(v["nodes"][0]["id"] == "common" and "heat" in v["rules"] and any(k["id"] == "homonym" for k in v["kinds"]), "вид страницы")
check("сто" in D.homonyms(), "омонимы из программы")

# пара в тему ниже темы сайта (кофе: сайт - «Общий», пара - в свою нишу «Чай и кофе»): сайт переходит в эту тему,
# пара больше не предлагается; тема пары по её примерам
def cafe():
    return {"host": "cafe.ru", "groups": [{"name": "Кофе", "q": [row("кофе illy молотый"), row("кофе илли молотый"),
                                                                 row("кофе illy в зернах"), row("кофе илли в зернах")]}]}
check(D.site_node(cafe()) == ("", False), "кофейня - без ниши")
check(any({p["a"], p["b"]} == {"illy", "илли"} for p in S.suggest(cafe())), "пара illy = илли нашлась")
tea = D.add_node("Чай и кофе", "common")
D.confirm(cafe(), "illy", "илли", tea)
check(D.site_node(cafe()) == (tea, True), f"сайт перешёл в тему пары: {D.site_node(cafe())}")
check(not any({p["a"], p["b"]} == {"illy", "илли"} for p in S.suggest(cafe())), "подтверждённая пара в другой теме больше не предлагается")
check(D.niche_for(["запчасти по vin коду автомобиля", "запчасти по вин коду автомобиля"], "heat") == "car", "пара про машины - в автосервис")
check(D.niche_for(["бойлер косвенного нагрева"], "heat") == "heat", "пара про котлы - в тему сайта")

# параллельные нажатия «Нет» (окно отвечает в нескольких потоках): ни ошибки, ни потерянного ответа
import threading
from seocrawler import jsonfile
errs = []
def no_pair(i):
    try:
        D.reject(cafe(), f"слово{i}", f"другое{i}")
    except Exception as e:
        errs.append(repr(e))
ths = [threading.Thread(target=no_pair, args=(i,)) for i in range(20)]
[t.start() for t in ths]
[t.join() for t in ths]
with open(os.environ["CLAYLER_DICT_FILE"], encoding="utf-8") as f:
    st = json.load(f)
got = {k for v in st["no"].values() for k in v}
check(not errs and all(D.pair_key(f"слово{i}", f"другое{i}") in got for i in range(20)), f"параллельные «Нет»: {errs[:2]}, {len(got)}")
p = os.path.join(TMP, "x.json")
ths = [threading.Thread(target=lambda i=i: jsonfile.save(p, {"i": i}) or None) for i in range(30)]
try:
    [t.start() for t in ths]
    [t.join() for t in ths]
    check(json.load(open(p, encoding="utf-8"))["i"] in range(30), "jsonfile: параллельная запись")
except Exception as e:
    check(False, f"jsonfile: {e}")
check(not [x for x in os.listdir(TMP) if x.endswith(".tmp")], "временные файлы не остаются")

shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("СИНОНИМЫ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Синонимы по нишам: всё в порядке")
