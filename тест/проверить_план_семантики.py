"""Автотест «Запрос → страница» и ТЗ копирайтеру (semantics/plan.py): что с каждой группой (подходит, доработать,
создать), адрес новой страницы (латиницей, без города, внутри родительского раздела, с той же косой чертой в конце,
без повторов), объём текста по страницам конкурентов из их проверки и подзаголовки H2 без почти одинаковых.
Без сети: маленькая выдуманная семантика и выдуманная база конкурента во временной папке."""
import copy
import json
import os
import sqlite3
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-plan-")
os.environ["CLAYLER_DECISIONS_DIR"] = os.path.join(TMP, "решения")   # настоящие решения не трогаем
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.semantics import client, plan  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def q(text, score=10, intent="Покупка"):
    return [text, "", intent, score, 1, 1, 0, "", 0]


REP = os.path.join(TMP, "отчёты")
MINE = os.path.join(REP, "test.ru_2026-10-04_10-00-00")
os.makedirs(MINE)
for name in ("rival.ru_2026-09-01_10-00-00", "rival.ru_2026-10-01_10-00-00"):   # взять надо более новую
    os.makedirs(os.path.join(REP, name))
    db = sqlite3.connect(os.path.join(REP, name, "crawl.db"))
    db.execute("CREATE TABLE pages (url TEXT PRIMARY KEY, word_count INTEGER, content_words INTEGER)")
    new = name.startswith("rival.ru_2026-10")
    db.execute("INSERT INTO pages VALUES (?, ?, ?)", ("https://rival.ru/kotly/", 3000, 800 if new else 5))
    db.execute("INSERT INTO pages VALUES (?, ?, ?)", ("https://rival.ru/pusto/", 20, 20))
    db.commit()
    db.close()

S = "https://test.ru"
DATA = {"site": S + "/", "host": "test.ru", "city": "Уфа", "groups": [
    {"name": "Газовые котлы", "kind": "page", "page": S + "/katalog/kotly/", "todo": "Продвигать эту страницу",
     "rivals": ["https://rival.ru/kotly/"], "ptype": "page",
     "a": {"main": "газовые котлы", "problems": [], "words": "навьен, двухконтурные"},
     "f": [{"name": "Газовые котлы навьен"}], "faq": ["как выбрать газовый котел"],
     "q": [q("газовые котлы", 50), q("газовые котлы навьен", 30), q("газовые котлы двухконтурные уфа", 20),
           q("газовые котлы цены", 15), q("как установить газовый котел", 9, "Информация"),
           q("как правильно установить газовый котел", 8, "Информация"), q("как выбрать газовый котел", 7, "Информация")]},
    {"name": "Настенные газовые котлы", "kind": "create", "page": "", "near": S + "/katalog/kotly/",
     "todo": "Создать подраздел в «Газовые котлы»", "rivals": ["https://rival.ru/pusto/"], "ptype": "page",
     "a": {"main": "настенные газовые котлы", "problems": [], "new": True, "h1": "Настенные газовые котлы",
           "title": "Настенные газовые котлы в Уфе — купить, цены"},
     "q": [q("настенные газовые котлы", 20), q("настенные газовые котлы в уфе", 10)]},
    {"name": "Котлы в Уфе", "kind": "create", "page": "", "near": "", "todo": "Создать раздел", "rivals": [],
     "ptype": "article", "a": {"h1": "Котлы в Уфе", "new": True, "problems": []}, "q": [q("котлы уфа")]},
    {"name": "Котлы в Уфе", "kind": "absent", "page": "", "near": "", "todo": "решить", "rivals": [], "q": [q("котлы уфе")]},
    {"name": "Ремонт", "kind": "page", "page": S + "/remont/", "todo": "", "rivals": [], "a": {"problems": ["В H1 нет"]},
     "q": [q("ремонт котлов")]},
    {"name": "Разное", "kind": "manual", "page": "", "todo": "", "rivals": [], "q": [q("что-то")]},
]}

check(plan.slug("Газовые котлы для дома в Уфе", "Уфа") == "gazovye-kotly-dlya-doma", plan.slug("Газовые котлы для дома в Уфе", "Уфа"))
check(plan.slug("Щётки и ёршики", None) == "schetki-ershiki", plan.slug("Щётки и ёршики", None))

# настоящие запросы (Вебмастер и Search Console): показы, место, какую страницу показывает Google, переходы
DATA["groups"][0]["q"] += [["газовые котлы купить", "", "Покупка", 5, 1, 1, 900, "", 12.0, S + "/old-kotly/", 30],
                           ["газовый котел", "", "Покупка", 5, 1, 1, 100, "", 22.0, S + "/old-kotly/", 2]]
DATA["groups"][4]["q"] += [["ремонт котлов уфа", "", "Услуга", 5, 1, 1, 50, "", 8.0, S + "/remont", 1]]
RAW = copy.deepcopy(DATA)
out = plan.enrich(DATA, MINE)
G = out["groups"]
st = [g["land"]["st"] for g in G]
check(st == ["ok", "create", "create", "absent", "fix", "manual"], f"что с группами: {st}")
check(G[0]["land"]["url"] == S + "/katalog/kotly/" and not G[0]["land"]["new"], f"своя страница: {G[0]['land']}")
check(G[1]["land"]["url"] == S + "/katalog/kotly/nastennye-gazovye-kotly/", f"подраздел: {G[1]['land']['url']}")
check(G[1]["land"]["title"] == "Настенные газовые котлы в Уфе - купить, цены", f"title без длинного тире: {G[1]['land']['title']}")
check(G[2]["land"]["url"] == S + "/kotly/", f"раздел от корня, без города: {G[2]['land']['url']}")
check(G[3]["land"]["url"] == S + "/kotly-2/", f"второй такой же адрес: {G[3]['land']['url']}")
check("tz" not in G[5], "у «Разобрать» не должно быть ТЗ")
v = G[0]["tz"]["volume"]
check(v["rivals"] == [800] and v["min"] == 650 and v["max"] == 950, f"объём по конкуренту (новая проверка): {v}")
check(G[1]["tz"]["volume"]["rivals"] == [] and G[1]["tz"]["volume"]["min"] == 300, f"почти пустая страница конкурента - не ориентир: {G[1]['tz']['volume']}")
check(G[2]["tz"]["volume"]["min"] == 1000, f"статья без конкурентов: {G[2]['tz']['volume']}")
h2 = G[0]["tz"]["h2"]
check("Газовые котлы навьен" in h2 and "Газовые котлы: цены" in h2 and "Вопросы и ответы" in h2, f"подзаголовки: {h2}")
check(sum(h.startswith("Как") and "установ" in h for h in h2) == 1, f"почти одинаковые вопросы: {h2}")
check(not any("уфа" in h.lower() for h in h2), f"город в подзаголовке: {h2}")
check(len(h2) <= plan.H2_MAX, f"подзаголовков много: {h2}")

R0, R4 = G[0].get("real"), G[4].get("real")
check(R0 and R0["shows"] == 1000 and R0["clicks"] == 32 and R0["pos"] == 13.0 and R0["n"] == 2, f"показы группы: {R0}")
check(R0 and R0["other"] and R0["other"]["url"] == S + "/old-kotly/", f"Google показывает другую страницу: {R0}")
check(R4 and R4["other"] is None, f"та же страница без косой черты - не «другая»: {R4}")
check("real" not in G[1], "у группы без показов не должно быть настоящих запросов")
gaps = out["rival_gaps"]
check(len(gaps) == 1 and gaps[0]["host"] == "rival.ru" and gaps[0]["have"] == 1 and [m["name"] for m in gaps[0]["missing"]] == ["Настенные газовые котлы"],
      f"темы конкурента, которых нет у вас: {gaps}")

plan.enrich({"site": S, "groups": []}, MINE)     # пустая семантика не падает
plan.enrich(dict(DATA, groups=[dict(G[0], rivals=["https://none.ru/x"])]), "")   # без папки и без конкурентов

# семантика в отчёте для клиента: собрана по прошлой проверке того же сайта - берётся она
OLD = os.path.join(REP, "test.ru_2026-09-20_10-00-00")
os.makedirs(OLD)
RAW["groups"][1]["name"] = 'ЖК "Котлы"'
with open(os.path.join(OLD, "семантика.json"), "w", encoding="utf-8") as f:
    json.dump(dict(RAW, made="20.09.2026 10:00"), f, ensure_ascii=False)
check(client.find(MINE) == OLD, f"не нашлась семантика прошлой проверки: {client.find(MINE)}")
sm = client.summary(MINE)
check(sm and sm["cnt"] == {"ok": 1, "create": 2, "absent": 1, "fix": 1} and sm["groups"] == 6, f"итог семантики: {sm and sm['cnt']}")
html = client.html_block(sm, h2="h2", h2_cls="sec", cls="card") + client.html_block(sm, for_audit=True)
check("Семантика: по каким запросам" in html and "/katalog/kotly/" in html and "Создать 2 страницы" in html, "раздел для клиента")
check("—" not in html and "программ" not in html.lower() and "«Котлы»" in html and '"Котлы"' not in html,
      "в разделе для клиента длинное тире, «программа» или прямые кавычки")
check("Поиск показывает не ту страницу" in html and "/old-kotly/" in html and "Темы конкурентов, которых нет у вас: 1" in html
      and "1 000 показов" in html, "в разделе для клиента нет настоящих запросов или тем конкурентов")
check(len(client.docx_paras(sm, lambda r, *a, **k: r, lambda t, **k: t)) >= 5, "раздел в Word")
check(client.summary(os.path.join(REP, "other.ru_2026-10-04_10-00-00")) is None, "чужой сайт без семантики")

# почему эта страница (29.10.2026): ручной выбор, главная, маска меню, уточнение без своей страницы
S = "https://site.ru/"
W = plan.why_page
check(W({"page": S, "todo": "Продвигать эту страницу", "lv": 1}, S) == "Главная: общие запросы темы сайта", "почему: главная")
check(W({"page": S + "a/", "todo": "Продвигать эту страницу (выбрана вручную)", "lv": 1}, S) == "Выбрана вами вручную",
      "почему: вручную")
check(W({"page": S + "a/", "todo": "Продвигать эту страницу", "lv": 1, "kind": "page"}, S) == "Пункт меню: группа собрана по его маске",
      f"почему: меню - {W({'page': S + 'a/', 'lv': 1}, S)}")
check(W({"page": "", "todo": "Создать подраздел в «Котлы»", "kind": "create"}, S).startswith("Уточнение группы «Котлы»"),
      "почему: подраздел без страницы")
# спрос группы: запрос из одного слова не входит, если в названии группы больше слова (как плашки частотности)
dd = {"site": S, "groups": [{"name": "Консультация по стратегии", "kind": "page", "page": S + "c/", "todo": "",
      "q": [["консультация", "", "", 1, 0, 0, 0, "", 0, "", 0, 3000], ["консультация по стратегии", "", "", 1, 0, 0, 0, "", 0, "", 0, 5]]},
      {"name": "Кухни", "kind": "page", "page": S + "k/", "todo": "", "q": [["кухни", "", "", 1, 0, 0, 0, "", 0, "", 0, 700]]}]}
plan.enrich(dd, "")
check([g.get("freq") for g in dd["groups"]] == [5, 700], f"спрос группы: {[g.get('freq') for g in dd['groups']]}")

# слова вопроса - не тема страницы: «Технический аудит: такое. Цены…» (hightime.agency 29.10.2026)
from seocrawler.semantics import pages as PG, keys as _keys  # noqa: E402
Qh = {q: {"check": "", "extra": x, "score": 5} for q, x in (
    ("что такое технический аудит", "что такое"), ("технический аудит это", "это"),
    ("технический аудит что это такое", "что это такое"), ("технический аудит сайта онлайн", "онлайн"),
    ("технический аудит онлайн бесплатно", "онлайн"))}
hot = [w for w, _k, _n in PG._hot_words({"queries": list(Qh)}, Qh, _keys, set())]
check("такое" not in hot and "это" not in hot and "онлайн" in hot, f"слова для описания: {hot}")
check(PG.SIGNUP_RX.search("записаться на курсы") and not PG.SIGNUP_RX.search("технический аудит заказать"),
      "«запись» - только когда ищут «записаться»")

# H1 и title новой страницы - из естественного запроса людей, имена собственные с большой (29.10.2026)
Qn = {q: {"check": "", "intent": "Общий", "score": sc} for q, sc in (
    ("продвижение сайтов топ", 10), ("продвижение сайтов в топ", 8), ("продвижение в яндексе", 3), ("что такое топ", 30))}
check(PG.nice_name({"name": "Продвижение сайтов топ", "queries": list(Qn)}, Qn) == "Продвижение сайтов в топ",
      f"H1 новой страницы: {PG.nice_name({'name': 'x', 'queries': list(Qn)}, Qn)}")
check(PG.proper("seo продвижение в яндексе в уфе", {"уфе"}) == "SEO продвижение в Яндексе в Уфе",
      f"большие буквы: {PG.proper('seo продвижение в яндексе в уфе', {'уфе'})}")
check(PG._brand_spelling("hightime", {"u": ("u", "Агентство HighTime", "HighTime.agency")}) == "HighTime",
      "название компании - как на сайте")
from seocrawler.semantics import brands as BR  # noqa: E402
check({"seo", "serm", "programmatic", "ppc"} <= BR.LAT_STOP, "отраслевые сокращения - не бренды")

# подзаголовки H2 - с большими буквами, как H1 новой страницы (29.10.2026)
check(plan._cap("seo продвижение сайтов: цены") == "SEO продвижение сайтов: цены" and
      plan._cap("продвижение сайтов топ яндекса") == "Продвижение сайтов топ Яндекса", "H2 с большими буквами")

if fails:
    print("✗ запрос → страница и ТЗ:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ запрос → страница и ТЗ: что с группой, адрес новой страницы, объём по конкурентам, подзаголовки, раздел для клиента")
