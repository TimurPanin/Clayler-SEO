"""Словарь (страница «Словарь» в меню слева): синонимы, омонимы, бренды, единицы и цифры, опечатки и раскладка,
мусорные слова - по темам.

Темы - дерево не глубже трёх уровней: «Общий» → ниша («Котлы, отопление, водоснабжение») → подтема («Котлы»).
Правила темы действуют и во всех темах под ней: пара из «Общего» - везде, из ниши - в её подтемах, а из подтемы
«Котлы» в соседней «Водонагреватели» уже нет. Поэтому в «Общий» - только то, что верно в любой нише. Одно слово
может быть в нескольких темах.

Сайт привязан к теме: сама по запросам семантики (detect - ниша) или выбранная человеком (подтема тоже).
Виды (KINDS): синонимы, единицы и цифры, опечатки и раскладка - работают одинаково, как синонимы (одна группа,
одинаковая раскладка, synonyms.py); омонимы - слова с разным смыслом («сто = автосервис | 100»): программа не
предлагает их в паре без проверки; бренды - как на вкладке «Бренды» Семантики (brands.py); мусорные слова - запросы
с ними уходят в «Отсеяно» при сборе.

Где лежит: «решения семантики/словарь.json» (темы, привязка сайтов, правила, откуда и когда добавлены, отклонённые
пары). «Общий» для синонимов, брендов и мусорных слов - прежние файлы (словари семантики.json, стоп-слова.json),
чтобы не было двух словарей. Правила, которые программа знает сама (BUILTIN), видны с пометкой «в программе»;
когда тему правят, её список сохраняется целиком."""
import json
import os
import functools
import re
import threading
import time

from .. import jsonfile, paths
from . import _canon, keys, norm, tokens
from . import dicts as DI
from .decisions import site_key

# папка в «data», без CLAYLER_DECISIONS_DIR: у словаря своя подмена - CLAYLER_DICT_FILE
DIR = paths.data("решения семантики")
FILE = os.environ.get("CLAYLER_DICT_FILE") or os.path.join(DIR, "словарь.json")
ROOT = "common"
DEPTH = 3
NICHE_MIN = 0.06     # столько запросов со словами ниши - ниша определена
KINDS = [("syn", "Синонимы"), ("unit", "Единицы и цифры"), ("typo", "Опечатки и раскладка"), ("homonym", "Омонимы"),
         ("brand", "Бренды"), ("junk", "Мусорные слова")]
KIND = dict(KINDS)
SYN_KINDS = ("syn", "unit", "typo")   # работают как синонимы
HINT = {
    "syn": "Слова и фразы через «=», первое - главное: «водонагреватель = бойлер». Формы слова и порядок слов подходят "
           "сами. Синонимы держатся в одной группе и на одной странице, но остаются отдельными строками.",
    "unit": "Единицы и числа: «м2 = кв м = квадратных метров», «2 = два». Работают как синонимы.",
    "typo": "Как пишут с ошибкой или в другой раскладке: «котел = rjntk = кател». Первое - правильное. Работают как синонимы.",
    "homonym": "Слово с разным смыслом: «сто = автосервис | 100». Такое слово программа не предлагает в паре без "
               "пометки «проверьте», а заменяет его только в теме, где у него один смысл.",
    "brand": "Бренд и как его ещё пишут: «Samsung = самсунг, самсунк». По звучанию (Baxi = бакси) программа узнаёт "
             "сама, сюда - то, что звучит иначе. Видно на вкладке «Бренды» Семантики.",
    "junk": "Одно слово в строке: запросы с ним уходят в «Отсеяно» при сборе семантики сайтов этой темы. "
            "«Общий» - это стоп-слова со страницы «Семантика».",
}

# ---------- что программа знает сама

UNITS = """м2 = кв м = кв метров = квм = квадратных метров = квадратов
квт = киловатт
мм = миллиметр
см = сантиметр
1 = один = одного = одному
2 = два = две = 2мя
3 = три = тремя = 3мя
4 = четыре = 4мя
100 = ста""".split("\n")

HOMONYMS = """сто = автосервис | 100
батарея = радиатор отопления | аккумулятор
ключ = гаечный | от замка | родник
кран = водопроводный | подъемный
мак = macbook | цветок
лед = led | замерзшая вода
ми = xiaomi | нота
бойлер = водонагреватель | котел (в некоторых регионах)
колонка = газовая колонка | акустическая колонка
замок = дверной | крепость
коса = инструмент | прическа""".split("\n")

# ниши: (код, название, слова ниши для определения, {вид: строки})
NICHES = [
    ("heat", "Котлы, отопление, водоснабжение",
     "котел котлы бойлер водонагреватель радиатор отопление отопления колонка дымоход теплый насос газовый "
     "конвектор теплоноситель расширительный",
     {"syn": """водонагреватель = бойлер
циркуляционник = циркуляционный насос
экспанзомат = расширительный бак
радиатор = батарея = батарея отопления
грязевик = фильтр грубой очистки
термоголовка = термостатическая головка
тэн = тен = нагревательный элемент
гвс = горячее водоснабжение
коаксиальный дымоход = коаксиальная труба
газовая колонка = проточный газовый водонагреватель"""}),
    ("tech", "Телефоны, ноутбуки, ремонт техники",
     "телефон смартфон айфон iphone ноутбук планшет ipad macbook макбук экран дисплей samsung xiaomi компьютер "
     "аккумулятор зарядка",
     {"syn": """iphone = айфон = айфоны = телефон айфон = смартфон айфон = смартфон iphone = телефон apple = смартфон apple = apple iphone = сотовый айфон = сотовый iphone = мобильный айфон = телефон эпл = смартфон эпл
ipad = айпад = планшет айпад = планшет ipad = планшет apple = планшет эпл = apple планшет
macbook = макбук = mac = ноутбук apple = apple ноутбук = ноутбук эпл = apple макбук = apple macbook = ноутбук макбук = ноутбук macbook
apple = эпл = эппл = аппле
mediapad = медиапад = медиа пад
watch = вотч
led = лед
oled = олед
amoled = амолед
miniled = минилед
incell = in cell = инсел
ии = ai
crm = црм = crm система = црм программа
safari = сафари
itunes = айтюнс
icloud = айклауд
windows = виндовс = винда = винды
imei = имей = имеи
sim = сим
face = фейс = фэйс
айди = id = идентификатор
se = се
xr = хр
про = pro
макс = max = мах
мини = mini
модель = model
регион = region
аккумулятор = акб = аккум = акум = батарея = батарейка = аккумуляторная батарея
телефон = смартфон = сотовый = мобильный = мобильник = сотовый телефон = мобильный телефон
планшет = tablet = таблет
компьютер = комп = пк = персональный компьютер
ноутбук = ноут = лаптоп
экран = дисплей = матрица = дисплейный модуль = тачскрин = сенсор
стекло = стекло дисплея = стекло экрана = стеклышко = glass
разъем = гнездо
хард = жесткий диск = hard
пароль = пин код
ремонт = починка = починить = отремонтировать = ремонтировать = восстановление = восстановить = remont = сломался = сломалась = поломался
замена = заменить = поменять = смена = установка нового
разблокировать = разблокировка = разлочить = разлочка
задняя крышка = заднее стекло = задняя панель
зарядка = зарядное
перезагрузка = перезагрузить = ресет = рестарт
глючит = лагает
разряжается = разряжаться
поврежденный = с дефектом
мастер = техник
поддержка = помощь = support
срочно = быстро = экспресс""",
      "brand": """Asus = асус
HP = хп, hewlett packard
Honor = хонор
Acer = асер, акер
Nitro = нитро
Dexp = дексп
Lenovo = леново
Irbis = ирбис
Xiaomi = сяоми, ксяоми, сиаоми, ксиаоми, сиоми, ксиоми, хаоми, mi, ми
Huawei = хуавей
Sony = сони
HTC = нтс, хтс
Google = гугл
Pixel = пиксель, пиксел
Redmi = редми, рэдми
Prestigio = престижио
Digma = дигма
Samsung = самсунг
eMachines = емашинес"""}),
    ("car", "Автосервис и автозапчасти",
     "автосервис авто автомобиль машина шиномонтаж двигатель кузов акпп тормозной подвеска грм автомобиля "
     "запчасти уаз лада ваз газель камаз приора гранта нива бензонасос рено логан тойота киа хендай форд шкода",
     {"syn": """автосервис = сто = техцентр = автотехцентр = автомастерская
авто = автомобиль = машина
шиномонтаж = шиномонтажка
акпп = автоматическая коробка = коробка автомат
мкпп = механическая коробка
двс = двигатель
бензонасос = топливный насос
вин = vin
развал = развал схождение
покраска = окраска""",
      "brand": """УАЗ = uaz
Лада = lada, ваз, vaz, гранта, приора, калина, нива, веста, ларгус, granta, priora, vesta
Камаз = kamaz
Газель = gazelle
Scania = скания
Renault = рено
Toyota = тойота
Kia = киа
Hyundai = хендай, хундай
Ford = форд
Skoda = шкода
Volkswagen = фольксваген
Nissan = ниссан
Chevrolet = шевроле"""}),
    ("locks", "Вскрытие замков",
     "вскрытие замок замков замка дверь двери сейф ключ",
     {"syn": """вскрытие = вскрыть = аварийное вскрытие = взлом
замок = личинка"""}),
    ("loans", "Займы и кредиты",
     "займ займы кредит микрозайм залог залога заем",
     {"syn": """займ = заем = микрозайм = микрокредит = мини кредит = микро кредит
беззалоговый = без залога
залоговый = под залог
наличными = наличкой = наличка
получить = взять = оформить"""}),
    ("money", "Скупка, валюта, деньги",
     "скупка валюта валюты доллар доллары купюра банкнота монета продать",
     {"syn": """деньги = купюра = банкнота
доллар = доллары = купюра доллар = валюта доллар
скупка = продать = сдать = прием = приемка
рбк = rbk"""}),
    ("house", "Строительство домов",
     "строительство дом дома коттедж газобетон брус фундамент проект этажный каркасный",
     {"syn": """дом = частный дом = коттедж
строительство = постройка = построить = стройка = строить
газобетон = газоблок
терраса = веранда
проект = план = планировка = план проект
одноэтажный = 1 этажный = 1 этаж = в один этаж
двухэтажный = 2 этажный = 2х этажный = 2 этажа = в два этажа
для постоянного проживания = для пмж = для круглогодичного проживания
деревянный = из дерева
коттеджный = коттеджные
спальня = спальная
гостиная = зал"""}),
    ("furniture", "Мебель",
     "мебель шкаф диван кровать кухня комод стол стул тумба прихожая гарнитур",
     {"syn": """кухня = кухонный гарнитур
тумба = тумбочка
матрас = матрац
на заказ = под заказ = по индивидуальным размерам
гостиная = зал
спальня = спальный гарнитур"""}),
    ("school", "Обучение и курсы",
     "курс курсы обучение школа урок уроки репетитор английский занятия преподаватель",
     {"syn": """курсы = обучение = обучение на курсах
онлайн = дистанционно = дистанционный = удаленно
репетитор = частный преподаватель
английский = english = англ"""}),
    ("dental", "Стоматология и медицина",
     "стоматология стоматолог зуб зубы зубов имплант имплантация брекеты клиника врач лечение",
     {"syn": """стоматолог = зубной врач = дантист
стоматология = стоматологическая клиника = зубная клиника
брекеты = брекет система"""}),
    ("realty", "Недвижимость",
     "квартира квартиры новостройка ипотека недвижимость комнатная жк застройщик",
     {"syn": """однокомнатная = 1 комнатная = однушка
двухкомнатная = 2 комнатная = двушка
трехкомнатная = 3 комнатная = трешка
новостройка = новый дом
вторичка = вторичное жилье"""}),
]
NICHE = {n[0]: n for n in NICHES}
BUILTIN = {ROOT: {"unit": UNITS, "homonym": HOMONYMS}}
for _id, _name, _marks, _kinds in NICHES:
    BUILTIN[_id] = {k: v.split("\n") for k, v in _kinds.items()}


# ---------- хранение

_LOCK = threading.RLock()   # окно отвечает в нескольких потоках: правки словаря - по одной, чтобы не терять нажатия


def _locked(fn):
    @functools.wraps(fn)
    def run(*a, **k):
        with _LOCK:
            return fn(*a, **k)
    return run


def _load():
    if os.environ.get("CLAYLER_NO_USER_SETTINGS") and not os.environ.get("CLAYLER_DICT_FILE"):
        return _empty()       # автотесты: только то, что в программе
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    e = _empty()
    for k in e:
        if isinstance(d.get(k), dict):
            e[k] = d[k]
    return e


def _empty():
    return {"nodes": {}, "rules": {}, "meta": {}, "no": {}, "sites": {}, "done": {}}


def _save(st):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    jsonfile.save(FILE, st, indent=1)


def lkey(line):
    """Строка без регистра, «ё» и лишних пробелов - чтобы узнавать её в метках и списке отклонённых."""
    return re.sub(r"\s+", " ", str(line).lower().replace("ё", "е")).strip()


def pair_key(a, b):
    return "|".join(sorted((norm(a), norm(b))))


def parts(line):
    return [norm(p) for p in re.split(r"[=,|]", str(line)) if norm(p)]


def tidy(ps):
    """Строка синонимов: первым - одно слово, если оно есть (фраза не может быть главной у слова)."""
    ps = list(dict.fromkeys(p for p in ps if p))
    if ps and " " in ps[0]:
        one = next((p for p in ps if " " not in p), None)
        if one:
            ps.remove(one)
            ps.insert(0, one)
    return " = ".join(ps)


# ---------- дерево тем

def nodes(st=None):
    """{код: {name, parent, builtin}}: «Общий», ниши программы и темы человека."""
    st = st or _load()
    out = {ROOT: {"name": "Общий", "parent": None, "builtin": True}}
    for nid, name, *_ in NICHES:
        out[nid] = {"name": name, "parent": ROOT, "builtin": True}
    for nid, n in st["nodes"].items():
        if nid not in out and isinstance(n, dict):
            out[nid] = {"name": str(n.get("name") or nid), "parent": n.get("parent") or ROOT, "builtin": False}
    # тема, у которой пропал родитель (удалили), - под «Общий»
    for nid, n in out.items():
        if nid != ROOT and n["parent"] not in out:
            n["parent"] = ROOT
    return out


def chain(nid, N=None):
    """«Общий» → … → эта тема."""
    N = N or nodes()
    out, seen = [], set()
    while nid and nid in N and nid not in seen:
        seen.add(nid)
        out.insert(0, nid)
        nid = N[nid]["parent"]
    if not out or out[0] != ROOT:
        out.insert(0, ROOT)
    return out


def depth(nid, N=None):
    return len(chain(nid, N))


def path(nid, N=None):
    N = N or nodes()
    return " → ".join(N[x]["name"] for x in chain(nid, N) if x in N)


# ---------- правила темы

def _special(nid, kind):
    """«Общий» для синонимов, брендов и мусорных слов - прежние файлы (вкладка «Разложить новые», стоп-слова)."""
    if nid != ROOT:
        return None
    if kind == "syn":
        return DI.load()["synonyms"]
    if kind == "brand":
        return DI.load()["brands"]
    if kind == "junk":
        from .words import load_stop
        return load_stop()
    return None


def _write_special(nid, kind, lines):
    if kind in ("syn", "brand"):
        DI.save({"syn": "synonyms", "brand": "brands"}[kind], lines)
    else:
        from .words import save_stop
        save_stop(lines)


def node_lines(nid, kind, st=None):
    """Строки темы этого вида (со строками «# …» - выключенными)."""
    sp = _special(nid, kind)
    if sp is not None:
        return list(sp)
    st = st or _load()
    own = (st["rules"].get(nid) or {}).get(kind)
    if isinstance(own, list):
        return list(own)
    return list((BUILTIN.get(nid) or {}).get(kind) or [])


def _set_lines(st, nid, kind, lines):
    lines = [re.sub(r"\s+", " ", str(s)).strip() for s in lines]
    lines = list(dict.fromkeys(s for s in lines if s))[:DI.MAX_LINES]
    if _special(nid, kind) is not None:
        _write_special(nid, kind, lines)
    else:
        st["rules"].setdefault(nid, {})[kind] = lines


def _mark(st, nid, kind, line, src):
    st["meta"][f"{nid}|{kind}|{lkey(line)}"] = {"src": src, "at": time.strftime("%d.%m.%Y")}


def meta(st, nid, kind, line):
    m = st["meta"].get(f"{nid}|{kind}|{lkey(line)}")
    if m:
        return m
    builtin = {lkey(x) for x in (BUILTIN.get(nid) or {}).get(kind) or []}
    if nid == ROOT and kind == "syn":
        builtin |= {lkey(x) for x in DI.SYNONYMS}
    if nid == ROOT and kind == "brand":
        builtin |= {lkey(x) for x in DI.BRANDS}
    return {"src": "в программе" if lkey(line) in builtin else "вручную", "at": ""}


def active(lines):
    return [s for s in lines if s.strip() and not s.lstrip().startswith("#")]


# ---------- тема сайта

def _marks(nid):
    return {_canon(keys(t)) for t in NICHE[nid][2].split()}


def detect_queries(qs):
    """Ниша по списку запросов: (код, доля) или ("", доля)."""
    if not qs:
        return "", 0
    cks = [{_canon(keys(t)) for t in tokens(norm(q))} for q in qs]
    best = ("", 0.0)
    for nid, *_ in NICHES:
        m = _marks(nid)
        share = sum(1 for c in cks if c & m) / len(cks)
        if share > best[1]:
            best = (nid, share)
    return best if best[1] >= NICHE_MIN else ("", best[1])


def detect(data):
    return detect_queries([r[0] for g in data.get("groups") or [] for r in g.get("q") or []])


def site_node(data, st=None):
    """(тема сайта, выбрана ли человеком). "" - только «Общий»."""
    st = st or _load()
    N = nodes(st)
    own = st["sites"].get(site_key(data.get("host")))
    if own is not None and (own == "" or own in N):
        return own, True
    return detect(data)[0], False


def lines(data, kinds=SYN_KINDS, st=None, root=True):
    """Действующие строки этих видов для сайта: «Общий» → ниша → подтема (без выключенных «#»)."""
    st = st or _load()
    nid, _ = site_node(data, st)
    out = []
    for x in chain(nid or ROOT, nodes(st)):
        if x == ROOT and not root:
            continue
        for k in kinds:
            out += active(node_lines(x, k, st))
    return out


def junk_for(host, queries=(), st=None):
    """Мусорные слова темы сайта, кроме «Общего» (он - стоп-слова, их читают и так)."""
    st = st or _load()
    if not any(active(node_lines(x, "junk", st)) for x in nodes(st) if x != ROOT):
        return []
    data = {"host": host, "groups": [{"q": [[q] for q in queries]}]}
    return [norm(s) for s in lines(data, ("junk",), st, root=False) if norm(s)]


def homonyms(st=None):
    """Слова-омонимы «Общего»: {слово: «автосервис | 100»}."""
    out = {}
    for s in active(node_lines(ROOT, "homonym", st)):
        w, _, rest = s.partition("=")
        if norm(w):
            out[norm(w)] = rest.strip()
    return out


# ---------- изменения

@_locked
def add(nid, kind, line, src="вручную", st=None):
    """Добавить строку в тему. Синонимы с общим словом - в ту же строку («бойлер = водонагреватель» + «бойлер = накопитель»)."""
    save = st is None
    st = st or _load()
    if nid not in nodes(st):
        raise ValueError("Нет такой темы. Обновите страницу.")
    cur = node_lines(nid, kind, st)
    if kind in SYN_KINDS:
        ps = parts(line)
        if len(ps) < 2:
            raise ValueError("Нужно два слова или фразы через «=»: «водонагреватель = бойлер».")
        for i, s in enumerate(cur):
            if s.lstrip().startswith("#"):
                continue
            old = parts(s)
            if set(old) & set(ps):
                cur[i] = tidy(old + ps)
                line = cur[i]
                break
        else:
            line = tidy(ps)
            cur.append(line)
    else:
        line = re.sub(r"\s+", " ", str(line)).strip()
        if not line:
            raise ValueError("Пустая строка.")
        if lkey(line) in {lkey(s) for s in cur}:
            return st
        cur.append(line)
    _set_lines(st, nid, kind, cur)
    _mark(st, nid, kind, line, src)
    if save:
        _save(st)
    return st


@_locked
def remove(nid, kind, line, st=None):
    save = st is None
    st = st or _load()
    cur = node_lines(nid, kind, st)
    _set_lines(st, nid, kind, [s for s in cur if lkey(s) != lkey(line)])
    st["meta"].pop(f"{nid}|{kind}|{lkey(line)}", None)
    if save:
        _save(st)
    return st


@_locked
def edit(nid, kind, old, new):
    st = _load()
    cur = node_lines(nid, kind, st)
    new = re.sub(r"\s+", " ", str(new)).strip()
    if kind in SYN_KINDS and len(parts(new)) < 2:
        raise ValueError("Нужно два слова или фразы через «=».")
    if kind in SYN_KINDS:
        new = tidy(parts(new))
    if lkey(old) not in {lkey(s) for s in cur}:
        raise ValueError("Этой строки уже нет. Обновите страницу.")
    _set_lines(st, nid, kind, [new if lkey(s) == lkey(old) else s for s in cur])
    m = st["meta"].pop(f"{nid}|{kind}|{lkey(old)}", None) or {"src": "вручную"}
    st["meta"][f"{nid}|{kind}|{lkey(new)}"] = dict(m, at=time.strftime("%d.%m.%Y"))
    _save(st)


@_locked
def move(nid, kind, line, to):
    st = _load()
    if to not in nodes(st):
        raise ValueError("Нет такой темы.")
    m = st["meta"].get(f"{nid}|{kind}|{lkey(line)}") or meta(st, nid, kind, line)
    remove(nid, kind, line, st)
    add(to, kind, line, m.get("src") or "вручную", st)
    _save(st)


@_locked
def reset(nid, kind):
    st = _load()
    if _special(nid, kind) is not None:
        if kind == "junk":
            raise ValueError("У мусорных слов «Общего» нет списка из программы.")
        DI.reset({"syn": "synonyms", "brand": "brands"}[kind])
    else:
        (st["rules"].get(nid) or {}).pop(kind, None)
    _save(st)


@_locked
def confirm(data, a, b, nid=None, src=None):
    """«Да, это одно» для пары с сайта: в тему сайта (или выбранную)."""
    st = _load()
    host = site_key(data.get("host"))
    cur, own = site_node(data, st)
    if nid is None:
        nid = cur or ROOT
    add(nid, "syn", f"{a} = {b}", src or f"пара с сайта {host}", st)
    for x in st["no"].values():
        if pair_key(a, b) in x:
            x.remove(pair_key(a, b))
    N = nodes(st)
    # пара ушла в тему ниже темы сайта («Общий» → «Чай и кофе»): сайт и есть этой темы, иначе её правила к нему не
    # применятся и пара осталась бы в списке
    if not own and nid != (cur or ROOT) and (cur or ROOT) in chain(nid, N):
        st["sites"][host] = nid
    # тема сайта другая: у этого сайта пару больше не предлагать
    if pair_key(a, b) not in st["done"].setdefault(host, []):
        st["done"][host].append(pair_key(a, b))
    _save(st)


@_locked
def reject(data, a, b):
    """«Нет»: в теме сайта больше не предлагать; если пара была в словаре темы - убрать её оттуда."""
    st = _load()
    nid = site_node(data, st)[0] or ROOT
    st["no"].setdefault(nid, [])
    if pair_key(a, b) not in st["no"][nid]:
        st["no"][nid].append(pair_key(a, b))
    a, b = norm(a), norm(b)
    for x in chain(nid, nodes(st)):
        cur = node_lines(x, "syn", st)
        out = []
        for s in cur:
            ps = parts(s)
            if a in ps and b in ps and not s.lstrip().startswith("#"):
                ps.remove(b if ps[0] != b else a)
                if len(ps) < 2:
                    continue
                s = tidy(ps)
            out.append(s)
        if out != cur:
            _set_lines(st, x, "syn", out)
    _save(st)


def niche_for(qs, site=None, N=None):
    """Тема для пары по её примерам: ниша, если примеры явно из неё (vin и вин - «запчасти по vin коду автомобиля»
    на сайте котлов - автосервис), иначе тема сайта."""
    nid, share = detect_queries(qs)
    if nid and share >= 0.5 and nid not in chain(site or ROOT, N):
        return nid
    return site or ROOT


def all_lines(st=None, kinds=SYN_KINDS):
    """Строки этих видов (по умолчанию синонимы, единицы и опечатки) всех тем."""
    st = st or _load()
    return [line for nid in nodes(st) for k in kinds for line in active(node_lines(nid, k, st))]


def rejected(data, st=None):
    """Отклонённые пары в теме сайта и выше."""
    st = st or _load()
    nid = site_node(data, st)[0] or ROOT
    return {k for x in chain(nid, nodes(st)) for k in st["no"].get(x) or []} | set(st["done"].get(site_key(data.get("host"))) or [])


@_locked
def set_site(host, nid):
    """Тема сайта: код темы, "" - только «Общий», None - сама по запросам."""
    st = _load()
    if nid is None:
        st["sites"].pop(site_key(host), None)
    else:
        if nid and nid not in nodes(st):
            raise ValueError("Нет такой темы.")
        st["sites"][site_key(host)] = "" if nid == ROOT else nid
    _save(st)


@_locked
def add_node(name, parent):
    st = _load()
    N = nodes(st)
    name = re.sub(r"\s+", " ", str(name)).strip()[:60]
    if not name:
        raise ValueError("Напишите название темы.")
    if parent not in N:
        raise ValueError("Нет такой темы.")
    if depth(parent, N) >= DEPTH:
        raise ValueError("Глубже трёх уровней нельзя: «Общий» → ниша → подтема.")
    if any(n["name"].lower() == name.lower() and n["parent"] == parent for n in N.values()):
        raise ValueError("Такая тема уже есть.")
    nid = "u" + str(int(time.time() * 1000))[-9:]
    st["nodes"][nid] = {"name": name, "parent": parent}
    _save(st)
    return nid


@_locked
def rename_node(nid, name):
    st = _load()
    if nid not in st["nodes"]:
        raise ValueError("Переименовать можно только свою тему.")
    name = re.sub(r"\s+", " ", str(name)).strip()[:60]
    if not name:
        raise ValueError("Напишите название темы.")
    st["nodes"][nid]["name"] = name
    _save(st)


@_locked
def delete_node(nid):
    """Удалить свою тему: её правила переходят в родительскую тему, подтемы и сайты - тоже к родителю."""
    st = _load()
    if nid not in st["nodes"]:
        raise ValueError("Удалить можно только свою тему.")
    N = nodes(st)
    parent = N[nid]["parent"] or ROOT
    for kind in KIND:
        for s in active(node_lines(nid, kind, st)):
            m = st["meta"].get(f"{nid}|{kind}|{lkey(s)}") or {}
            add(parent, kind, s, m.get("src") or "вручную", st)
    st["rules"].pop(nid, None)
    for k in [k for k in st["meta"] if k.startswith(nid + "|")]:
        st["meta"].pop(k)
    for x in st["nodes"].values():
        if x.get("parent") == nid:
            x["parent"] = parent
    for h, x in list(st["sites"].items()):
        if x == nid:
            st["sites"][h] = parent if parent != ROOT else ""
    st["no"].setdefault(parent, []).extend(st["no"].pop(nid, []))
    st["nodes"].pop(nid)
    _save(st)


# ---------- в файл и из файла

def export():
    """Весь словарь одним файлом: темы, правила со своими метками, привязка сайтов, отклонённые пары."""
    st = _load()
    N = nodes(st)
    rules = {nid: {k: node_lines(nid, k, st) for k in KIND} for nid in N}
    return {"clayler": "словарь", "version": 1, "saved": time.strftime("%d.%m.%Y %H:%M"),
            "nodes": {nid: {"name": n["name"], "parent": n["parent"]} for nid, n in N.items() if not n["builtin"]},
            "rules": rules, "meta": st["meta"], "no": st["no"], "sites": st["sites"]}


@_locked
def import_(d):
    """Добавить словарь из файла к своему: новые темы и строки добавляются, свои не пропадают.
    Возвращает, сколько строк добавлено."""
    if not isinstance(d, dict) or d.get("clayler") != "словарь":
        raise ValueError("Это не файл словаря Clayler SEO.")
    st = _load()
    N = nodes(st)
    ids = {}
    for nid, n in (d.get("nodes") or {}).items():   # свои темы из файла: по названию и родителю
        if not isinstance(n, dict):
            continue
        parent = n.get("parent") or ROOT
        parent = ids.get(parent, parent if parent in N else ROOT)
        same = next((x for x, m in nodes(st).items() if m["name"].lower() == str(n.get("name") or "").lower()
                     and m["parent"] == parent), None)
        if same:
            ids[nid] = same
        elif depth(parent, nodes(st)) < DEPTH:
            new = "u" + str(abs(hash((nid, n.get("name")))) % 10 ** 9)
            st["nodes"][new] = {"name": str(n.get("name") or "Тема")[:60], "parent": parent}
            ids[nid] = new
    added = 0
    for nid, kinds in (d.get("rules") or {}).items():
        to = ids.get(nid, nid if nid in nodes(st) else None)
        if not to or not isinstance(kinds, dict):
            continue
        for kind, ls in kinds.items():
            if kind not in KIND or not isinstance(ls, list):
                continue
            have = {lkey(s) for s in node_lines(to, kind, st)}
            for s in ls:
                if isinstance(s, str) and s.strip() and lkey(s) not in have:
                    m = (d.get("meta") or {}).get(f"{nid}|{kind}|{lkey(s)}") or {}
                    try:
                        add(to, kind, s, m.get("src") or "из файла", st)
                    except ValueError:
                        continue
                    added += 1
    for nid, ks in (d.get("no") or {}).items():
        to = ids.get(nid, nid if nid in nodes(st) else None)
        if to and isinstance(ks, list):
            st["no"][to] = sorted(set(st["no"].get(to) or []) | {str(k) for k in ks})
    for h, nid in (d.get("sites") or {}).items():
        if h not in st["sites"]:
            to = ids.get(nid, nid if nid in nodes(st) or nid == "" else None)
            if to is not None:
                st["sites"][h] = to
    _save(st)
    return added


# ---------- сколько раз сработало: в скольких запросах семантик сайтов есть другое написание

_QCACHE = {}


def _site_queries(path):
    """Запросы семантики сайта (с другими формами) → {основа слова: множество номеров запросов}."""
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    c = _QCACHE.get(path)
    if c and c[0] == mt:
        return c[1]
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    qs = [r[0] for g in d.get("groups") or [] for r in g.get("q") or []]
    idx = {}
    for i, q in enumerate(qs):
        for t in tokens(norm(q)):
            idx.setdefault(_canon(keys(t)), set()).add(i)
    res = {"host": d.get("host") or "", "qs": qs, "idx": idx}
    _QCACHE[path] = (mt, res)
    return res


def _hits(line, kind, site):
    """В скольких запросах сайта есть не главное написание из строки."""
    if kind == "homonym":
        ws = [line.partition("=")[0]]
    elif kind == "brand":
        name, _, rest = line.partition("=")
        ws = [name] + [x for x in re.split(r"[,=]", rest)]
    elif kind == "junk":
        ws = [line]
    else:
        ws = parts(line)[1:]
    found = set()
    for w in ws:
        cs = [_canon(keys(t)) for t in tokens(norm(w))]
        if not cs:
            continue
        s = set(site["idx"].get(cs[0], set()))
        for c in cs[1:]:
            s &= site["idx"].get(c, set())
        found |= s
    return len(found)


def sites_with_semantics():
    """Последняя семантика каждого сайта: [(папка, хост, путь к семантика.json)]."""
    from ..window import REPORTS
    out = {}
    try:
        names = sorted(os.listdir(REPORTS))
    except OSError:
        return []
    for name in names:
        p = os.path.join(REPORTS, name, "семантика.json")
        if os.path.isfile(p):
            host = site_key(name.split("_")[0])
            out[host] = (name, host, p)     # папки по дате: последняя - свежая
    return list(out.values())


def view():
    """Всё для страницы «Словарь»: темы со счётчиками, правила с метками и срабатываниями, сайты и их темы."""
    st = _load()
    N = nodes(st)
    sites = []
    for folder, host, p in sites_with_semantics():
        s = _site_queries(p)
        if not s or not s["qs"]:
            continue
        own = st["sites"].get(host)
        auto = detect_queries(s["qs"])[0]
        nid = own if own is not None and (own == "" or own in N) else auto
        sites.append({"folder": folder, "host": host, "node": nid or ROOT, "own": own is not None, "auto": auto,
                      "queries": len(s["qs"]), "_s": s})
    under = {nid: [x for x in sites if nid in chain(x["node"], N)] for nid in N}
    rules = {}
    for nid in N:
        for kind in KIND:
            rows = []
            for line in node_lines(nid, kind, st):
                m = meta(st, nid, kind, line)
                off = line.lstrip().startswith("#")
                hits = 0 if off else sum(_hits(line, kind, x["_s"]) for x in under[nid])
                rows.append({"t": line, "src": m.get("src") or "", "at": m.get("at") or "", "hits": hits, "off": off})
            if rows:
                rules.setdefault(nid, {})[kind] = rows
    from . import synonyms as SY
    from ..window import REPORTS
    known = SY.words(all_lines(st)) if sites else None
    for x in sites:
        x.pop("_s")
        try:   # пары, найденные при сборе семантики: сколько ждут ответа (None - ещё не искали)
            p = SY.cached_pairs(os.path.join(REPORTS, x["folder"]), x["host"], x["node"], st, known)
            x["pairs"] = None if p is None else len(p)
        except Exception:
            x["pairs"] = None
    return {"nodes": [{"id": nid, "name": n["name"], "parent": n["parent"], "builtin": n["builtin"],
                       "depth": depth(nid, N), "edited": sorted((st["rules"].get(nid) or {}).keys())}
                      for nid, n in N.items()],
            "kinds": [{"id": k, "name": v, "hint": HINT[k]} for k, v in KINDS], "rules": rules, "sites": sites,
            "no": {k: len(v) for k, v in st["no"].items()}, "depth": DEPTH}
