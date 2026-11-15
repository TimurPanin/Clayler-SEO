"""Автотест: короткие пункты меню и запросы «про другое» в семантике (15.10.2026, по ревизии lk-fabrika.ru).
Без сети: маленькая выдуманная проверка мебельного сайта, подсказки - заранее в кеше. Проверяется:
- пункт меню без слова темы берётся по H1 своей страницы («Детские» → «Детская мебель на заказ», «Кухни» → «Распил
  кухонь»), если H1 про другое - имя прежнее («Термостат» под H1 «Системы безопасности котла»), а если нет темы -
  к запросу добавляется слово темы сайта («Библиотека» → «библиотека мебель»);
- служебные ссылки (политика, рассрочка, оплата, отзывы, фото) и заготовки шаблона «{$...}» - не разделы;
- запрос со словом, которого нет ни на одной странице сайтов, уходит в «Отсеяно» («слов нет на сайтах»), а со словом
  из текста страниц - остаётся («шкафы на заказ из дерева»);
- длинный запрос с «заказ» и своим городом не выбрасывается; группа из одного названия страницы без подсказок - не
  группа; «в стиле современный» → «в современном стиле»; «шкаф-купе купить» - не повтор слова.
Запуск: py -3 тест/проверить_темы_семантики.py (и из проверить_всё.py)."""
import json
import os
import sys
import tempfile
import time
import zlib

TMP = tempfile.mkdtemp(prefix="clayler-topics-")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")
os.environ["CLAYLER_DICTS_FILE"] = os.path.join(TMP, "словари.json")
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.storage import Store  # noqa: E402
from seocrawler.semantics import build, seeds as S  # noqa: E402
from seocrawler.semantics.words import SERVICE_NAMES  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


# 1. имена разделов и запросы по ним (без базы)
secs = [{"name": "Детские", "url": "/d/", "h1": "Детская мебель на заказ", "parent": None},
        {"name": "Без декора", "url": "/b/", "h1": "Корпусная мебель с", "parent": None},
        {"name": "Кухни", "url": "/k/", "h1": "Распил кухонь", "parent": None},
        {"name": "Библиотеки", "url": "/l/", "h1": "Библиотека", "parent": None},
        {"name": "Шкафы-купе на заказ", "url": "/s/", "h1": "Шкафы-купе на заказ", "parent": None},
        {"name": "С зеркалом", "url": "/s/z/", "h1": "Шкаф-купе из зеркала", "parent": "Шкафы-купе на заказ"},
        {"name": "Настенные", "url": "/n/", "h1": "", "parent": "Газовые котлы"},
        {"name": "Мебель из МДФ", "url": "/m/", "h1": "Мебель из МДФ", "parent": None},
        {"name": "Белая мебель", "url": "/w/", "h1": "Белая мебель", "parent": None}]
S._with_topic(secs, ["мебель на заказ"])
by = {s["url"]: s for s in secs}
check(by["/d/"]["name"] == "Детская мебель на заказ", f"«Детские» по H1: {by['/d/']['name']}")
check(by["/b/"]["name"] == "Без декора" and S.query_form(by["/b/"]) == "без декора мебель",
      f"«Без декора»: H1 не про то же - имя прежнее, к запросу слово темы: {S.query_form(by['/b/'])}")
gen = [{"name": "Термостат", "url": "/t/", "h1": "Системы безопасности котла", "parent": None}]
S._with_topic(gen, [])
check(gen[0]["name"] == "Термостат", f"H1 общего раздела не заменяет пункт меню: {gen[0]['name']}")
check(by["/k/"]["name"] == "Распил кухонь", f"«Кухни» по H1 услуги: {by['/k/']['name']}")
check(S.query_form(by["/l/"]) == "библиотека мебель", f"«Библиотека» со словом темы: {S.query_form(by['/l/'])}")
check(by["/s/z/"]["name"] == "Шкаф-купе из зеркала", f"«С зеркалом» по H1: {by['/s/z/']['name']}")
check(S.query_form(by["/n/"]) == "настенные газовые котлы", f"«Настенные» с родителем: {S.query_form(by['/n/'])}")
check(S.query_form(by["/m/"]) == "мебель из мдф", f"раздел с темой не трогается: {S.query_form(by['/m/'])}")
check(S.query_form({"name": "Шкаф-купе", "parent": "Шкафы-купе на заказ"}) == "шкаф-купе",
      f"без повтора слова родителя: {S.query_form({'name': 'Шкаф-купе', 'parent': 'Шкафы-купе на заказ'})}")
for n in ("Политикой конфиденциальности", "Рассрочка и кредит", "Онлайн-оплата", "Живые отзывы", "Фото",
          "Информация об онлайн-оплате"):
    check(SERVICE_NAMES.match(n), f"служебная ссылка - не раздел: {n}")
check(S.clean_name("Мебель в стиле современный") == "Мебель в современном стиле", "падеж: «в стиле современный»")
check(S.clean_name("Кухни в стиле классический") == "Кухни в классическом стиле", "падеж: «в стиле классический»")
check(S.clean_name("Мебель в стиле лофт") == "Мебель в стиле лофт", "«в стиле лофт» не трогается")
from seocrawler.semantics import _canon, core, repeated_word, tokens  # noqa: E402
check([_canon(k) for k in core("шкафы-купе на заказ")] == ["шкаф", "куп"] == [_canon(k) for k in core("шкафы купе")],
      f"«шкафы-купе» - не уточнение «купить», «на заказ» - уточнение: {[_canon(k) for k in core('шкафы-купе на заказ')]}")
check(len(core("интернет-магазин котлов")) == 1, "«интернет-магазин» - уточнение")
check(not repeated_word(tokens("шкаф-купе купить в москве")), "«шкаф-купе купить» - не повтор слова")
check(repeated_word(tokens("тепловентиляторы тепловентиляторы")), "настоящий повтор слова ловится")
# 16.10.2026 (exist.ru, talisman): форум, справка, филиалы, преподаватели, приложение, ссылки-фразы - не разделы
for n in ("Форум", "Форум по Toyota Camry VIII", "Филиалы", "Карьера", "Мобильное приложение «»", "Документация",
          "Пресс-релизы", "Выбрать другой офис", "Вам помочь?", "chat"):
    check(SERVICE_NAMES.match(n), f"служебная ссылка - не раздел: {n}")
for u in ("https://x.ru/Forum/105489", "https://x.ru/Hint/Feedback/", "https://x.ru/vacancies/", "https://x.ru/teachers/",
          "https://x.ru/filialy/", "https://x.ru/Stat/Default2.aspx", "https://x.ru/career/info/"):
    check(S.NOT_SECTION_URL.search(u), f"служебный адрес - не раздел: {u}")
check(not S.NOT_SECTION_URL.search("https://x.ru/kotly/stalnye/"), "обычный раздел принят за служебный адрес")
for n in ("Шкафы-купе на заказ", "Газовые котлы", "Детская мебель"):
    check(not SERVICE_NAMES.match(n), f"обычный раздел принят за служебный: {n}")

# 2. сбор по выдуманной проверке
B = "https://mebel.ru"
F = os.path.join(TMP, "mebel.ru_2026-10-15_10-00-00")
os.makedirs(F)
st = Store(os.path.join(F, "crawl.db"))
st.set_meta("start", B + "/")
st.set_meta("finished_at", "2026-10-15 10:05:00")
MENU = [(B + "/detskie/", "Детские", "Детская мебель на заказ"), (B + "/shkafy/", "Шкафы", "Шкафы на заказ"),
        (B + "/policy.html", "Политикой конфиденциальности", "Политика конфиденциальности"),
        (B + "/rassrochka/", "Рассрочка и кредит", "Рассрочка и кредит"),
        (B + "/x/", "Мебель с {$dveri_t} без декора", "Мебель с {$dveri_t} без декора"),
        (B + "/kuhni/kantri-kuhnya.html", "Кантри-кухня в сливочно-кремовом", "Кантри-кухня в сливочно-кремовом"),
        (B + "/shkafy/bez-dekora/", "Шкаф", "Шкаф с")]   # H1 оборван: шаблон не подставил значение - не раздел
TEXT = "Шкафы на заказ из массива дерева и ЛДСП. Детская мебель по индивидуальным размерам."
# на сайте должно быть много текста: на маленьком сайте запросы «про другое» только помечаются (BIG_VOCAB)
ABC = "бвгдклмнпрст"
FILLER = " ".join(a + v + b + "а" + c + "ик" for v in "оу" for a in ABC for b in ABC for c in ABC)
pages = [B + "/"] + [f"{B}/p{i}/" for i in range(6)] + [u for u, _a, _h in MENU]
for u in pages:
    h1 = next((h for x, _a, h in MENU if x == u), "Мебель на заказ в Уфе")
    st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": h1 + " в Уфе",
                  "h1": h1, "word_count": 300, "blocks": zlib.compress((TEXT + " " + FILLER).encode("utf-8"), 6)})
for src in pages:
    st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a, _h in MENU])
st.commit()
st.db.close()
SUG = {"детская мебель на заказ": ["детская мебель на заказ", "детская мебель на заказ уфа"],
       "шкафы на заказ": ["шкафы на заказ", "шкафы на заказ из дерева", "шкафы на заказ майнкрафт",
                          "шкафы на заказ из массива дерева в уфе недорого от производителя"],
       "мебель на заказ": ["мебель на заказ", "мебель на заказ уфа", "мебель на заказ кантри",
                           "мебель на заказ под ключ", "мебель на заказ синоним"]}
now = time.time()
cache = {f"{e}|{r}|{ph}": {"s": lst, "t": now} for ph, lst in SUG.items() for e, r in (("yandex", "172"), ("google", "ru"))}
with open(os.path.join(F, ".семантика_подсказки.json"), "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)
sem = build(F, log=lambda *a: None, offline=True, region="Уфа")
qs = set(sem["queries"])
dropped = {q: why for q, why, _src in sem["dropped"]}
check("детская мебель на заказ уфа" in qs, f"«Детские» собраны по H1: {sorted(qs)}")
check("шкафы на заказ из дерева" in qs, "слово из текста страниц - запрос остаётся")
check(dropped.get("шкафы на заказ майнкрафт", "").startswith("слов нет на сайтах"),
      f"слова нет на сайтах - в отсеянное: {dropped.get('шкафы на заказ майнкрафт')}")
check("шкафы на заказ из массива дерева в уфе недорого от производителя" in qs,
      f"длинный запрос с «заказ» и своим городом - не выброшен: {dropped.get('шкафы на заказ из массива дерева в уфе недорого от производителя')}")
check(dropped.get("кантри-кухня в сливочно-кремовом", "").startswith("нет спроса"),
      f"группа из одного названия страницы - не группа: {dropped.get('кантри-кухня в сливочно-кремовом')}")
check(not any(s_["url"].endswith("/bez-dekora/") for s_ in S.load(F)["sections"]), "страница с H1 «Шкаф с» - не раздел")
check(sem.get("dropped") and any(w == "майнкрафт" for q, why, _s in sem["dropped"] for w in [why.split(": ", 1)[-1]]),
      "в отсеянном видно, какого слова нет на сайтах")
# «Это про нас»: слово запомнено для сайта - при следующем сборе запрос с ним остаётся
from seocrawler.semantics import masks as MK  # noqa: E402
check(MK.set_ok("mebel.ru", add=["Майнкрафт"]) == ["майнкрафт"], "«Это про нас» запоминается")
sem2 = build(F, log=lambda *a: None, offline=True, region="Уфа")
check("шкафы на заказ майнкрафт" in set(sem2["queries"]), "после «Это про нас» запрос со словом не отсеивается")
# и пометки «возможно, про другое» у него нет: иначе он лежал в «Без группы» (hightime.agency 29.10.2026, «топ»)
check(not sem2["queries"]["шкафы на заказ майнкрафт"]["check"], f"«про нас» с пометкой: {sem2['queries']['шкафы на заказ майнкрафт']['check']}")
# тема + одно слово без своей группы - в группу главной, а не в «Без группы» (hightime.agency 28.10.2026:
# «продвижение сайтов услуги», «… агентство» лежали в «Без группы»)
home_g = next((g for g in sem2["groups"] if g["name"].lower() == "мебель на заказ"), {})
# «под ключ» - коммерческое уточнение, не «про другое»; «синоним» - словарный запрос, мусор для любого сайта
check("мебель на заказ под ключ" in home_g.get("queries", []), f"«под ключ» не в группе главной: {home_g.get('queries')}")
check(any(q == "мебель на заказ синоним" and why.startswith("мусор") for q, why, _s in sem2["dropped"]),
      f"«синоним» не отсеян: {[x for x in sem2['dropped'] if 'синоним' in x[0]]}")
check("мебель на заказ кантри" in home_g.get("queries", []),
      f"тема + слово - в группу главной: {[(g['name'], g['queries']) for g in sem2['groups']]}")
MK.set_ok("mebel.ru", remove=["майнкрафт"])
# пункт меню (маска уровня 1), по которому ищут только его название: группа остаётся, но не «Продвигать эту
# страницу», а «Спроса не видно» (hightime.agency 28.10.2026: 8 таких пунктов звались «продвигать»)
MK.propose(F, log=lambda *a: None)
MK.update("mebel.ru", confirmed=True)
sem3 = build(F, log=lambda *a: None, offline=True, region="Уфа")
kk = next((g for g in sem3["groups"] if g["name"].startswith("Кантри-кухня")), None)
check(kk and kk.get("todo", "").startswith("Спроса не видно"), f"пункт меню без спроса: {kk and kk.get('todo')}")
# приоритет страницы: 4 - это «Без группы» (export.PRIO_KIND), пункт пропал бы из дерева и проверки страниц
check(kk and kk.get("prio") == 1, f"пункт без спроса - не страница: приоритет {kk and kk.get('prio')}")
check(all(not g.get("todo", "").startswith("Спроса не видно") for g in sem3["groups"] if len(g["queries"]) > 1),
      "«Спроса не видно» у группы с запросами")
names = {g["name"] for g in sem["groups"]}
check(not any("онфиденц" in n or "ассрочк" in n or "{" in n for n in names), f"служебные и шаблонные группы: {names}")

# 3. «плоский» сайт агентства (hightime.agency 28.10.2026): все страницы в корне, у многих длинный H1 - корень
# считался папкой товаров, меню уходило в карточки, а разделами становились кнопки, кейсы и словарь терминов
A = "https://brand.agency"
F2 = os.path.join(TMP, "brand.agency_2026-10-28_10-00-00")
os.makedirs(F2)
st = Store(os.path.join(F2, "crawl.db"))
st.set_meta("start", A + "/")
MENU2 = [(A + "/strategy", "SEO-стратегия", "Стратегия SEO-продвижения: план роста на основе рынка и конкурентов"),
         (A + "/seo-germany", "Германия", "SEO-продвижение сайтов в Германии, Австрии, Швейцарии и других странах"),
         (A + "/cases", "Кейсы", "Результаты системной работы на проектах клиентов и партнёров"),
         (A + "/glossary", "SEO Глоссарий", "Словарь SEO-терминов от агентства и его специалистов"),
         (A + "/jobs", "Карьера", "Отправить резюме"),
         (A + "/tender", "Пригласить в тендер", "Пригласить нас в тендер"),
         (A + "/team", "Подробнее о команде", "Команда агентства и наши специалисты по продвижению")]
SIDE = [(A + "/cases/travelline", "Россия, СНГ, мир", 30), (A + "/glossary/ymyl", "YMYL", 10),
        (A + "/cases/ispring", "Читать кейс", 8)]
long_h1 = "Статья о продвижении сайтов за рубежом для компаний номер {}"
pages2 = [A + "/"] + [f"{A}/p{i}" for i in range(40)] + [u for u, _a, _h in MENU2] + [u for u, _a, _n in SIDE]
for u in pages2:
    h1 = ("Brand.agency — рост заявок для ИТ-компаний" if u == A + "/" else
          next((h for x, _a, h in MENU2 if x == u), long_h1.format(len(u))))
    st.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1, "title": h1, "h1": h1,
                  "word_count": 300})
for i, src in enumerate(pages2):
    st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a, _h in MENU2])
    st.add_links([(src, dst, dst, a, 0, "a", 1) for dst, a, n in SIDE if i < n])
st.commit()
st.db.close()
m2 = S.load(F2, cards=50)
secs2 = {s_["url"]: s_["name"] for s_ in m2["sections"]}
check(A + "/strategy" in secs2, f"пункт меню в плоском сайте - раздел, а не карточка: {secs2}")
check(secs2.get(A + "/seo-germany") == "SEO-продвижение сайтов в Германии",
      f"«Германия» - по началу длинного H1: {secs2.get(A + '/seo-germany')}")
for u in ("/cases", "/glossary", "/jobs", "/tender", "/team", "/cases/travelline", "/glossary/ymyl", "/cases/ispring"):
    check(A + u not in secs2, f"не раздел: {u} ({secs2.get(A + u)})")
cards2 = {c["url"] for c in m2.get("cards") or []}
check(not cards2 & ({A + "/", A + "/jobs", A + "/tender"} | set(secs2)), f"главная, вакансии и разделы - не карточки: {cards2}")
check(S.clean_name("Brand.agency — рост заявок для ИТ-компаний", ["brand"]) == "рост заявок для ИТ-компаний",
      "первая часть H1 - только название компании: имя по следующей части, а не «agency»")
check(S.clean_name("Разбор проекта от экспертов Brand.agency", ["brand"]) == "Разбор проекта от экспертов",
      "без хвоста «.agency» после названия компании")
# пункт меню не про тему сайта (тема - из длинного title главной): «США и Европа» собирали «последние новости»,
# «Тарифы» - «тарифы теле2» (hightime.agency 28.10.2026). H1 со словом темы - имя; без него - имя прежнее
check(S._topic_head("Продвижение IT-компаний и SaaS-продуктов в России и за рубежом") ==
      "Продвижение IT-компаний и SaaS-продуктов", f"тема из длинного title: {S._topic_head('Продвижение IT-компаний и SaaS-продуктов в России и за рубежом')}")
secs3 = [{"name": "США и Европа", "url": "/u", "h1": "SEO-продвижение сайтов в США, Европе и мире", "parent": None},
         {"name": "Технический аудит", "url": "/a", "h1": "Технический SEO-аудит сайта для международных проектов",
          "parent": None},
         {"name": "SEO-оптимизация сайта", "url": "/o", "h1": "Разовая SEO-оптимизация сайтов IT-компаний", "parent": None},
         {"name": "E-Commerce", "url": "/e", "h1": "SEO-продвижение eCommerce-проектов: магазины и экспортёры",
          "parent": None}]
S._with_topic(secs3, [], (), "продвижение it-компаний и saas-продуктов")
check([x["name"] for x in secs3] == ["SEO-продвижение сайтов в США", "Технический аудит", "SEO-оптимизация сайта",
                                     "SEO-продвижение eCommerce-проектов"], f"пункты не про тему: {[x['name'] for x in secs3]}")
check(not any(x.get("need") for x in secs3), "тема из длинного title дописана к запросам")
# тема главной из пунктов меню, когда в заголовках главной её нет: два слова, общие хотя бы для трёх пунктов
# (hightime.agency 28.10.2026: «продвижение сайтов» лежало в «Без группы»); меньше трёх - темы нет
menu = [{"name": n} for n in ("SEO-продвижение сайтов в Германии", "SEO-продвижение сайтов во Франции",
                              "SEO-продвижение сайтов в США", "Технический аудит", "Контент-маркетинг")]
check(S._menu_topic(menu) == ["продвижение сайтов"], f"тема из меню: {S._menu_topic(menu)}")
check(S._menu_topic(menu[2:]) == [], f"два пункта - не тема: {S._menu_topic(menu[2:])}")
from seocrawler.semantics.words import INTENT  # noqa: E402
check(next((n for n, rx in INTENT if rx.search("купить книги по программированию")), "") == "Покупка",
      "«купить книги» - покупка, «книга» - не информационное слово (книжный магазин)")
for q in ("консультация синоним", "технический аудит простыми словами"):
    check(next((n for n, rx in INTENT if rx.search(q)), "") == "Информация", f"информационный запрос: {q}")
# «сео» = «seo»: короткое русское слово сравнивается с латиницей по звучанию, группа одна (hightime.agency 29.10.2026)
from seocrawler.semantics import _canon, core as _core, keys as _keys  # noqa: E402
check(_keys("сео") & _keys("seo"), f"«сео» не узнаёт «seo»: {_keys('сео')}")
check([_canon(k) for k in _core("сео продвижение")] == [_canon(k) for k in _core("seo продвижение")],
      "«сео продвижение» и «seo продвижение» - разные группы")
# уточнение запроса - от его новой группы, а не от «Без группы»: иначе «продвижение» - уточнение группы «Seo
# продвижение сайтов», и в дереве у каждой новой группы фильтр-двойник (hightime.agency 29.10.2026)
import seocrawler.semantics as SM  # noqa: E402
Qx = {"seo продвижение сайтов под ключ": {"extra": "seo продвижение сайтов под ключ"},
      "seo продвижение сайтов цена": {"extra": "seo продвижение сайтов цена"}}
SM._reextra(Qx, list(Qx), SM.core("seo продвижение сайтов", set()), set())
check(all("продвижение" not in v["extra"] and "seo" not in v["extra"] for v in Qx.values()),
      f"уточнение от новой группы: {[v['extra'] for v in Qx.values()]}")
for n in ("Тарифы", "Цены", "Стоимость"):
    check(SERVICE_NAMES.match(n), f"страница цен - не раздел: {n}")
for n in ("Пригласить в тендер", "Читать кейс", "Смотреть кейс", "Отправить резюме", "SEO Глоссарий",
          "Подробнее о команде"):
    check(SERVICE_NAMES.match(n), f"кнопка или словарь - не раздел: {n}")

if fails:
    print("✗ темы семантики:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ темы семантики: короткие пункты меню по H1 и со словом темы, служебные ссылки не разделы, "
      "запросы со словами не с сайтов - в отсеянное")
