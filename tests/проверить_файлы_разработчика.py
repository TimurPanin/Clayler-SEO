"""Автотест готовых файлов для разработчика (seocrawler/fix_files.py):
- robots.txt: открываются закрытые стили и скрипты (Allow длиннее запрета и только для .css/.js),
  постраничная навигация, из-за которой страницы видны только из sitemap, Clean-param для меток, адрес sitemap;
- sitemap.xml: только рабочие страницы, открытые для поиска, без дублей и чужих поддоменов;
- редиректы: 404 → тот же адрес без опечатки / переехавшая страница / раздел выше (не главная), цепочки — сразу
  на конечный адрес; правила Apache и nginx с экранированием;
- таблица title/description не стирает текущий текст.
Без сети и без настоящих проверок: выдуманная база."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import fix_files as F  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402
from seocrawler.robots import Robots  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


O = "https://site.ru"
ROBOTS = "User-agent: *\nDisallow: /bitrix/\nDisallow: *?\nDisallow: /*PAGEN*\n\nUser-agent: Yandex\nDisallow: /bitrix/\n"
tmp = tempfile.mkdtemp()
st = Store(os.path.join(tmp, "crawl.db"))
st.set_meta("start", O + "/")
st.set_meta("robots", {O: {"status": 200, "text": ROBOTS}})
pages = [  # адрес, код, индексируемость
    ("/", 200, "Индексируемая"), ("/catalog/", 200, "Индексируемая"), ("/catalog/sofas/", 200, "Индексируемая"),
    ("/catalog/sofas/old-sofa/", 404, "Код 404"), ("/catalog/beds", 200, "Индексируемая"),
    ("/catalog/beds/", 404, "Код 404"), ("/new/moved-item-long/", 200, "Индексируемая"),
    ("/old/moved-item-long/", 404, "Код 404"), ("/lonely-404", 404, "Код 404"),
    ("/closed/", 200, "noindex"), ("/canon/", 200, "Канонизирована"), ("/dup-a/", 200, "Индексируемая"),
    ("/dup-b/", 200, "Индексируемая"), ("/soft/", 200, "Индексируемая"), ("/a b/x (1)/", 404, "Код 404"),
    ("/chain/", 301, "Редирект"), ("/cases/ispring", 200, "Индексируемая"), ("/iSpring.es", 404, "Код 404"),
    ("/content-marketing", 200, "Индексируемая"), ("/content-marketing.", 404, "Код 404")]
for path, code, idx in pages:
    st.enqueue(O + path, 1, True, "page", None, "done")
    st.save_page({"url": O + path, "status": code, "indexability": idx, "indexable": int(idx == "Индексируемая")})
st.enqueue("https://sub.site.ru/", 1, True, "page", None, "done")
st.save_page({"url": "https://sub.site.ru/", "status": 200, "indexability": "Индексируемая", "indexable": 1})
st.add_param_links([(O + "/", O + "/catalog/?utm_source=x&page=2", O + "/catalog/", "utm_source,page")])
st.commit()


def issue(key, rows):
    return Issue(key, "warning", "", "", "", "", [], rows)


issues = [issue("js_blocked", [[O + "/", O + "/bitrix/templates/main/style.css?123\n" + O + "/bitrix/js/core.js"]]),
          issue("behind_blocked", [[O + "/p1", O + "/catalog/?PAGEN_1=2", "Disallow: /*PAGEN*"]]),
          issue("dup_content", [["2", O + "/dup-a/\n" + O + "/dup-b/"]]),
          issue("soft404", [[O + "/soft/", "", ""]]),
          issue("redirect_chains", [[O + "/chain/", 2, f"{O}/chain/\n→ {O}/mid/\n→ {O}/catalog/sofas/", 200]])]
summary = {"queue_left": 0, "meta_suggest": [
    {"url": O + "/catalog/", "title_now": "Каталог", "title": "Каталог мебели", "desc_now": "Старое", "desc": "",
     "h1_now": "Каталог", "h1": ""}]}

# robots.txt
text, changes = F.robots_fix(st, issues, O + "/", True)
for bot in ("googlebot", "yandex"):
    rb = Robots(text, bot)
    check(rb.allowed(O + "/bitrix/templates/main/style.css?123")[0], f"{bot}: стиль остался закрыт")
    check(rb.allowed(O + "/bitrix/js/core.js")[0], f"{bot}: скрипт остался закрыт")
    check(not rb.allowed(O + "/bitrix/admin/")[0], f"{bot}: открылось лишнее /bitrix/admin/")
check(Robots(text, "googlebot").allowed(O + "/catalog/?PAGEN_1=2")[0] is False, "навигацию закрывает ещё и *? - так и должно остаться")
check("# Disallow: /*PAGEN*" in text, "правило навигации не убрано")
check("Clean-param: utm_source" in text and "page" not in text.split("Clean-param:")[1], "Clean-param: " + text)
check(f"Sitemap: {O}/sitemap.xml" in text, "нет адреса sitemap")
check(len(changes) == 4, f"изменений {len(changes)}: {changes}")
# правило шире навигации (Disallow: /*? - и фильтры, и сортировки): не убираем, а «Allow: /*?PAGEN_1=»
wide = [issue("behind_blocked", [[O + "/p1", O + "/catalog/?PAGEN_1=2", "Disallow: /*?"],
                                 [O + "/p2", O + "/catalog/sofas/?PAGEN_1=3", "Disallow: /*?"]])]
text2, ch2 = F.robots_fix(st, wide, O + "/", True)
for bot in ("googlebot", "yandex"):
    rb = Robots(text2, bot)
    check(rb.allowed(O + "/catalog/?PAGEN_1=2")[0] and rb.allowed(O + "/catalog/sofas/?PAGEN_1=3")[0],
          f"{bot}: навигация не открылась узким Allow: {text2}")
    for u in (O + "/catalog/?sort=price", O + "/catalog/?set_filter=y&PAGEN_1=2",   # что было закрыто - закрыто
              O + "/search/?PAGEN_1=2", O + "/personal/orders/?PAGEN_1=3"):   # и навигация других разделов (04.11)
        check(rb.allowed(u)[0] == Robots(ROBOTS, bot).allowed(u)[0], f"{bot}: вместе с навигацией открылось {u}")
check("Allow: /catalog/*?PAGEN_1=" in text2 and "Allow: /*?PAGEN_1=" not in text2 and "# Disallow: /*?" not in text2,
      f"широкое правило убрано или Allow не по разделу: {text2}")
check(any("Allow: /catalog/*?PAGEN_1=" in c and "фильтры" in c and "до 2 стр." in c for c in ch2),
      f"нет пояснения про узкий Allow (и «до 2 стр.» - обе страницы за открытой навигацией): {ch2}")
# найден закрытый адрес, который такое правило тоже откроет (навигация + сортировка) - правило не вписываем
st.enqueue(O + "/catalog/?PAGEN_1=2&sort=price", 1, True, "page", "", "skipped", "Закрыт в robots.txt (Disallow: /*?)")
st.commit()
text3, ch3 = F.robots_fix(st, wide, O + "/", True)
check("PAGEN_1=" not in "".join(x for x in text3.splitlines() if x.startswith("Allow:")),
      f"правило открыло бы найденную сортировку: {text3}")
st.set_meta("robots", {O: {"status": 404, "text": ""}})
t404, ch404 = F.robots_fix(st, [], O + "/", True)
check(t404.startswith("User-agent: *\nDisallow:") and "Sitemap:" in t404, "robots.txt для сайта без него: " + t404)
st.set_meta("robots", {O: {"status": 500, "text": ""}})
check(F.robots_fix(st, [], O + "/", True) == ("", []), "robots.txt с ошибкой сервера - не трогаем")

# sitemap.xml
sm = F.sitemap_urls(st, issues, O + "/")
want = {O + p for p in ("/", "/catalog/", "/catalog/sofas/", "/catalog/beds", "/new/moved-item-long/", "/dup-a/",
                           "/cases/ispring", "/content-marketing")}
check(set(sm) == want, f"sitemap: лишнее {set(sm) - want}, нет {want - set(sm)}")

# редиректы
rd = {a: b for a, b, _ in F.redirects(st, issues, O + "/")}
check(rd.get(O + "/catalog/beds/") == O + "/catalog/beds", "404 со слешем → без слеша")
check(rd.get(O + "/old/moved-item-long/") == O + "/new/moved-item-long/", "переехавшая страница")
check(rd.get(O + "/catalog/sofas/old-sofa/") == O + "/catalog/sofas/", "404 → раздел выше")
check(O + "/lonely-404" not in rd, "404 без замены ушла на главную")
check(rd.get(O + "/chain/") == O + "/catalog/sofas/", "цепочка → конечный адрес")
rules = [(O + "/a%20b/x%20(1)/?q=1", O + "/catalog/", "тест")]
ap = F.apache_text(rules)
check('RewriteRule "^a b/x \\(1\\)/$"' in ap and 'RewriteCond %{QUERY_STRING} "^q=1$"' in ap and "QSD" in ap, ap)
check('"/a%20b/x%20(1)/?q=1" "https://site.ru/catalog/";' in F.nginx_text(rules), F.nginx_text(rules))
# адрес без параметров - по $uri (со ссылок с utm тоже срабатывает, метки переносятся), «проверьте» - выключено
ng = F.nginx_text([(O + "/content-marketing.", O + "/content-marketing", "тест")], [(O + "/iSpring.es", O + "/cases/ispring", "x")])
check("map $uri $seo_redirect" in ng and '"/content-marketing." "https://site.ru/content-marketing";' in ng
      and "$request_uri" not in ng and "$is_args$args" in ng and '# "/iSpring.es"' in ng, ng)
# у каждой внутренней 404 решение: замена по словам адреса («проверьте») или «уберите ссылки»
dd = {u: (c, w) for u, c, w, _ in F.dead_decisions(st, F.redirects(st, issues, O + "/"), O + "/")}
check(dd.get(O + "/iSpring.es", ("",))[0] == O + "/cases/ispring", f"404 /iSpring.es: {dd}")
check(dd.get(O + "/lonely-404", ("x", ""))[0] == "" and "уберите" in dd[O + "/lonely-404"][1], f"404 без замены: {dd}")
check(O + "/content-marketing." not in dd, "404 с редиректом попала и в «без решения»")

# таблица title / description
mr = F.meta_rows(summary)
check(mr == [[O + "/catalog/", "Каталог мебели", "Старое", "Каталог", "title", "", "Каталог", "Старое", "Каталог", ""]],
      f"title/description (неизменное - текущим текстом, импорт ничего не сотрёт): {mr}")
# дубли title: страница, у которой текст остаётся, и та, для которой не собрать текст, - в таблице с причиной
mm = F.meta_rows({"meta_suggest": [], "meta_manual": [
    {"url": O + "/a", "title_now": "Т", "desc_now": "Д", "h1_now": "", "keep": True, "look": ["такой же title у 2 стр."]},
    {"url": O + "/b", "title_now": "Т", "desc_now": "Д", "h1_now": "", "why": {"title": ["такой же"]},
     "look": ["напишите вручную"]}]})
check([r[4] for r in mm] == ["ничего (оставить)", "вручную: title"] and mm[0][1] == "Т", f"дубли в таблице: {mm}")
# один H1 с « | » в самом тексте - не два H1
one = F.meta_rows({"meta_suggest": [{"url": O + "/y", "title_now": "Y", "title": "Новый", "desc_now": "", "desc": "",
                                     "h1_now": "Ремонт iPhone | Сервис Москва", "h1": "", "h1_n": 1}]})[0]
check(one[3] == "Ремонт iPhone | Сервис Москва" and one[9] == "" and "H1" not in one[5], f"один H1 разрезан: {one}")
# несколько H1 - по колонкам, без « | »; самопроверка: «…», старый год, мусор в текущем H1
mr = F.meta_rows({"meta_suggest": [{"url": O + "/x", "title_now": "X", "title": "", "desc_now": "",
                                    "desc": "Задачи на 2022 год и дальше, и ещё…", "h1_now": "Кейс | +***% заявок",
                                    "h1": "", "look": ["title: обрезан по длине - фраза законченная?"]}]})[0]
check(mr[8:] == ["Кейс", "+***% заявок"] and " | " not in "".join(mr) and mr[3] == "", f"H1 склеены: {mr}")
for want in ("«…»", "2022", "«***»", "2 H1", "обрезан"):
    check(want in mr[5], f"самопроверка без «{want}»: {mr[5]}")

# обрезка title: не кончается предлогом, союзом и прилагательным без существительного (primerline.agency)
from seocrawler.analyze.checks.meta_text import _cut  # noqa: E402
for long, want in (("Кейс iSpring: стратегия продвижения сайта в Испании и Латинской Америке", "в Испании"),
                   ("Кейс Quartier Latin: Разработка структуры и дизайна для информационного сайта", "и дизайна")):
    got = _cut(long, len(long) - 9)
    check(got.endswith(want), f"обрезка «{long}» → «{got}»")
# существительное на -ой (доставкой, водой) - не прилагательное, не выкидывается
got = _cut("Диван угловой серый с доставкой по городу бесплатно", 36)
check(got.endswith("с доставкой"), f"обрезка съела существительное: «{got}»")
got = _cut("Комплексное SEO продвижение сайтов и интернет-магазинов", 30)
check(got.endswith("продвижение"), f"обрезка съела существительное на -ние: «{got}»")
# nginx: «/a%20b» и «/a b» - один ключ $uri, повтор ключа nginx не примет
ng = F.nginx_text([(O + "/a%20b", O + "/x", "1"), (O + "/a b", O + "/y", "2")])
check(ng.count('"/a b"') == 1, f"повтор ключа в map: {ng}")

# всё вместе
st.set_meta("robots", {O: {"status": 200, "text": ROBOTS}})
files = F.write(st, issues, summary, tmp)
names = set(os.listdir(F.folder(tmp)))
check({F.README, F.ROBOTS, F.SITEMAP, F.RD_APACHE, F.RD_NGINX, F.RD_TABLE, F.META_CSV} <= names, f"файлы: {names}")
check(".csv" not in F.html_block(files, client=True), "имя .csv в тексте для клиента")
st.db.close()

if fails:
    print("ОШИБКИ в файлах для разработчика:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("Файлы для разработчика: всё в порядке")
