"""Автотест находок проверки кода «Семантики» 24.10.2026, без сети:
- «мск», «спб», «питер», «подмосковье» - это город сайта, а не «другой город» (City, city_by_name, site_city);
- город в подзаголовках ТЗ и адресе новой страницы - по основе слова, а не по первым буквам («перила» - не Пермь);
- путь страницы «/kotly/» из файла выгрузки не теряется;
- лимит Директа посреди пачки: загрузка частотности ждёт дня, а не встаёт с ошибкой; во «Спросе» недозагруженные
  фразы остаются в очереди, а не записываются нулём."""
import os
import shutil
import sqlite3
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-cities-")
os.environ["CLAYLER_ACCOUNTS_FILE"] = os.path.join(TMP, "доступы.json")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
# уведомления и «Журнал» - не в папку программы: поддельное «баллы кончились» попадало в колокольчик (25.10.2026)
os.environ.update(CLAYLER_JOURNAL_DIR=TMP, CLAYLER_NO_SOUND="1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import direct
from seocrawler.semantics import City, assign, bukvarix, demand, imports, plan, seeds, _drop_junk
from seocrawler.semantics.words import city_by_name

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# ---- город: другие имена того же города
c = City()
check(c.find("шкафы купе спб") == {"Санкт-Петербург"}, f"«спб» - Санкт-Петербург: {c.find('шкафы купе спб')}")
check(c.find("кухни питер") == {"Санкт-Петербург"}, "«питер» - Санкт-Петербург")
check(c.find("кухни мск") == {"Москва"} and c.find("кухни подмосковье") == {"Москва"}, "«мск», «подмосковье» - Москва")
check(city_by_name("СПб")[0] == "Санкт-Петербург" and city_by_name("Питер")[0] == "Санкт-Петербург",
      "город из окна «СПб» - Санкт-Петербург")
main = {"brand": [], "host": "mebel-spb.ru"}
Q = {q: {"src": {"подсказки Яндекса"}} for q in ("шкафы купе спб", "шкафы купе питер", "шкафы купе в санкт-петербурге",
                                                  "шкафы купе москва")}
dropped = dict((q, why) for q, why, _ in _drop_junk(Q, main, [], c, "Санкт-Петербург", {"шкаф", "куп"}))
check(set(Q) == {"шкафы купе спб", "шкафы купе питер", "шкафы купе в санкт-петербурге"},
      f"«спб» и «питер» не отсеяны как другой город: {dropped}")
check(dropped.get("шкафы купе москва", "").startswith("другой город"), "Москва для сайта из Петербурга - другой город")
check(bukvarix.drop_reason("шкафы купе спб", set(), set(), "СПб", c, set()) is None,
      "Видимость: старая семантика с городом «СПб» не отсеивает «спб»")
check(bukvarix.region_of("СПб") == "spb", "регион Букварикса для «СПб»")

db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE pages (title TEXT, status INT)")
db.executemany("INSERT INTO pages VALUES (?, 200)", [("Кухни в СПб",), ("Шкафы в СПб",), ("Двери в Санкт-Петербурге",)])
check((seeds.site_city(db) or ("",))[0] == "Санкт-Петербург", f"город сайта по «в СПб»: {seeds.site_city(db)}")

# ---- город в ТЗ и адресах: по основе слова
is_city, _ = plan._city_test("Пермь")
check(not is_city("перила") and is_city("перми"), "«перила» - не Пермь")
is_city, _ = plan._city_test("Санкт-Петербург")
check(not is_city("санузел") and is_city("спб") and is_city("петербурге"), "«санузел» - не Петербург, «спб» - он")
check(plan.slug("Москитные сетки в Москве", "Москва") == "moskitnye-setki", plan.slug("Москитные сетки в Москве", "Москва"))
check(plan.slug("Газовые котлы для дома в Уфе", "Уфа") == "gazovye-kotly-dlya-doma", "адрес без города")

# ---- путь страницы из файла выгрузки
rows, kind = imports.parse("вебмастер.csv", "Запрос;Показы;Клики;Позиция;URL\nгазовые котлы;100;5;7,5;/kotly/\n".encode())
imports.add_file("teplo.ru", "вебмастер.csv", "Запрос;Показы;Клики;Позиция;URL\nгазовые котлы;100;5;7,5;/kotly/\n".encode())
check(imports.rows("teplo.ru").get("газовые котлы", {}).get("page") == "https://teplo.ru/kotly/",
      f"путь «/kotly/» - адрес сайта: {imports.rows('teplo.ru')}")

# ---- пояснение раскладки: общее слово через синоним, а не «?»
res = assign.run([("Айфоны", ["айфон 15", "айфон купить", "айфон цена"])], [{"q": "iphone 15 про"}],
                 d=dict(assign.DI.load(), synonyms=["айфон = iphone"]))
check(res and res[0]["group"] == "Айфоны" and "?" not in res[0]["why"].split(", "), f"общие слова без «?»: {res}")

# ---- текст ссылок: город - не тема страницы, у любого города, а не только у Уфы и Москвы
from seocrawler.analyze.checks import inlink_anchors as IA
check(not IA._stems("Котлы в Казани") & IA._stems("Казань"), f"Казань в тексте ссылки: {IA._stems('Котлы в Казани')}")
check(not IA._stems("Котлы в Уфе") & IA._stems("Уфа") and IA._stems("Газовые котлы"), "Уфа и обычные слова")

# ---- семантика в отчёте: старая проверка берёт семантику своего времени, а не более новой проверки
from seocrawler.semantics import client
rep = os.path.join(TMP, "отчёты")
for n in ("site.ru_2026-09-01_10-00-00", "site.ru_2026-10-01_10-00-00", "site.ru_2026-10-20_10-00-00",
          "other.ru_2026-10-21_10-00-00"):
    os.makedirs(os.path.join(rep, n))
for n in ("site.ru_2026-09-01_10-00-00", "site.ru_2026-10-20_10-00-00", "other.ru_2026-10-21_10-00-00"):
    open(os.path.join(rep, n, "семантика.json"), "w").close()
got = os.path.basename(client.find(os.path.join(rep, "site.ru_2026-10-01_10-00-00")) or "")
check(got == "site.ru_2026-09-01_10-00-00", f"семантика своего времени: {got}")
os.remove(os.path.join(rep, "site.ru_2026-09-01_10-00-00", "семантика.json"))
got = os.path.basename(client.find(os.path.join(rep, "site.ru_2026-10-01_10-00-00")) or "")
check(got == "site.ru_2026-10-20_10-00-00", f"нет прошлой - самая новая того же сайта, не чужого: {got}")

# ---- «Спрос»: лимит Директа посреди пачки
orig = (direct.report_full, demand._wait_day)
calls = []


def fake_full(phrases, lr):
    calls.append(list(phrases))
    if len(phrases) > 1:
        raise direct.DirectError(5, "плохая фраза в пачке")
    if phrases[0] == "бакси":
        return {"бакси": {"shows": 70, "with": [], "also": []}}
    raise direct.DirectError(152, "баллы кончились")


waited = []


def fake_wait(soon):
    waited.append([x[0] for t in demand.QUEUE for x in t["items"]])
    for t in demand.QUEUE:
        t["items"] = []


direct.report_full, demand._wait_day = fake_full, fake_wait
demand.QUEUE[:] = [{"host": "teplo.ru", "kind": "brand", "label": "узнаваемость",
                    "items": [("бакси", 172), ("навьен", 172), ("вайлант", 172)], "total": 3}]
demand._loop()
br = (demand.load("teplo.ru").get("brand") or {}).get("172") or {}
check(br.get("бакси", {}).get("n") == 70, f"загруженная фраза сохранена: {br}")
check("навьен" not in br and "вайлант" not in br, f"недозагруженные фразы не записаны нулём: {br}")
check(waited and waited[0] == ["навьен", "вайлант"], f"недозагруженные фразы ждут следующего дня в очереди: {waited}")

# ---- загрузка частотности: лимит посреди пачки - ждать дня, а не ошибка
data = {"host": "teplo.ru", "city": "Уфа", "groups": [{"name": "Котлы", "q": [
    [q, "", "Общий", 10, 1, 0, 0, "", 0, "", 0, 0, 0, 0] for q in ("газовые котлы", "котлы бакси", "котлы навьен")]}]}
from seocrawler.semantics import export
saved = (export.load, direct.report, direct.fast_ok, direct.has_volume, direct._wait_day)


def fake_report(phrases, lr):
    if phrases == ['"газовые котлы"']:
        return {"газовые котлы": 500}
    raise direct.DirectError(152, "баллы кончились")


def no_volume(*a):
    raise direct.DirectError(-1, "нет связи")


export.load = lambda folder: data
direct.report_full, direct.report, direct.fast_ok, direct.has_volume = fake_full, fake_report, lambda: False, no_volume
direct._wait_day = lambda soon=False: False
direct.JOB.clear()
direct.JOB.update(state="running", folder="x", done=0, total=0)
direct._run(TMP)
phr = (direct.load("teplo.ru").get("172") or {}).get("phr") or {}
check(direct.JOB.get("state") != "error", f"лимит посреди пачки - не ошибка: {direct.JOB}")
check(phr.get("газовые котлы", [0])[0] == 500 and "котлы бакси" not in phr, f"загруженное сохранено, остальное ждёт: {phr}")
export.load, direct.report, direct.fast_ok, direct.has_volume, direct._wait_day = saved
direct.report_full, demand._wait_day = orig
shutil.rmtree(TMP, ignore_errors=True)

# город - не тип товара и не слово группы: любой город из общего списка, а не только вписанные в код города прошлых
# клиентов («уфа», «москва», «спб» в дереве сайта и решениях; 28.10.2026)
from seocrawler.semantics import tree as TR, decisions as DS, words as WD  # noqa: E402
for w in ("казань", "казани", "уфа", "москве", "спб", "питер", "петербурге", "краснодар"):
    check(w in TR.STOP and w in DS.WORD_STOP, f"город «{w}» - стоп-слово дерева сайта и решений")
check("газовые" not in WD.CITY_WORDS and "котлы" not in WD.CITY_WORDS, "обычные слова - не города")
for w in ("уральский", "грозный", "октябрьский", "нижний", "новый"):   # прилагательные из названий городов
    check(w not in WD.CITY_WORDS, f"«{w}» - не слово-город: «Уральский мотоцикл» не должен терять слово")
for w in ("новгород", "санкт-петербург", "петербург"):
    check(w in WD.CITY_WORDS, f"«{w}» - слово-город")

if fails:
    print("ГОРОДА И ЛИМИТЫ СЕМАНТИКИ: ОШИБКИ")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("Города, файлы и лимиты Директа в семантике: всё в порядке")
