"""Автотест советов под движок сайта и срока домена (23.10.2026, разбор пакета hightime.agency):
- cms_help: движок узнаётся по названию из site_tech; Тильде не советуется «заменить robots.txt» и плагины WordPress,
  WordPress - плагины, неизвестный движок - общий совет; ссылки только на справку движка;
- «Прочитайте сначала» файлов для разработчика - под движок;
- совет про уменьшенные картинки (проблема 4xx) - плагин Regenerate Thumbnails только у WordPress;
- домен: меньше DOMAIN_CRIT_DAYS дней до конца оплаты - критично, меньше DOMAIN_WARN_DAYS - предупреждение.
Без сети: выдуманные данные. Запуск: py -3 тест/проверить_советы_движка.py (и из проверить_всё.py)."""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import cms_help, fix_files as F, settings as S  # noqa: E402
from seocrawler.analyze.checks import not_found_cert  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


check(cms_help.detect([{"name": "Tilda"}]) == "tilda", "Тильда не узнаётся")
check(cms_help.detect([{"name": "1С-Битрикс"}]) == "bitrix", "Битрикс не узнаётся")
check(cms_help.detect([{"name": "WordPress"}, {"name": "Yoast SEO (SEO-плагин WordPress)"}]) == "wordpress", "WordPress")
check(cms_help.detect([{"name": None}, {"name": "Самописный"}]) == "", "неизвестный движок")
t = cms_help.how("tilda", "robots")
check("нельзя" in t and "help-ru.tilda.cc" in t, f"Тильда robots: {t}")
check("Regenerate" not in cms_help.how("tilda", "thumbs") and "Regenerate" in cms_help.how("wordpress", "thumbs"),
      "совет про уменьшенные картинки не по движку")
check(cms_help.how("", "redirects") == cms_help.GENERIC["redirects"], "общий совет без движка")
for key, (_rx, _name, tips, links) in cms_help.ENGINES.items():
    check(set(tips) <= set(cms_help.TOPICS) and set(links) <= set(tips), f"{key}: темы или ссылки без совета")
    check(all(u.startswith("https://") for u in links.values()), f"{key}: ссылка не https")

# «Прочитайте сначала» и «Как применить» - под движок
tmp = tempfile.mkdtemp()
st = Store(os.path.join(tmp, "crawl.db"))
st.set_meta("start", "https://site.ru/")
st.set_meta("site_tech", {"engines": [{"name": "Tilda"}]})
st.set_meta("robots", {"https://site.ru": {"status": 200, "text": "User-agent: *\nDisallow:\n"}})
st.enqueue("https://site.ru/", 0, True, "page", None, "done")
st.save_page({"url": "https://site.ru/", "status": 200, "indexability": "Индексируемая", "indexable": 1})
st.commit()
files = F.write(st, [], {"queue_left": 0, "meta_suggest": [{"url": "https://site.ru/", "title_now": "А", "title": "Б",
                                                             "desc_now": "", "desc": "", "h1_now": "", "h1": ""}]}, tmp)
readme = open(os.path.join(F.folder(tmp), F.README), encoding="utf-8-sig").read()
check("Тильда (определён при проверке)" in readme and "Настройки страницы → SEO" in readme
      and "плагин" not in readme.lower(), f"«Прочитайте сначала» не под Тильду:\n{readme[:1500]}")

class Ctx:
    def __init__(self, store):
        self.store, self.issues, self.home_copies = store, {}, set()

    def add(self, key, sev, *a, **k):
        self.issues[key] = (sev, a)


# домен: 3 дня - критично, 45 - предупреждение, 200 - ничего
for days, want in ((3, "critical"), ((S.DOMAIN_CRIT_DAYS + S.DOMAIN_WARN_DAYS) // 2, "warning"), (200, None)):
    st.set_meta("site_tech", {"engines": [{"name": "Tilda"}], "domain": {
        "domain": "site.ru", "registrar": "Регистратор", "expires": (dt.date.today() + dt.timedelta(days)).isoformat()}})
    c = Ctx(st)
    not_found_cert.run(c)
    got = c.issues.get("domain_expiry", (None,))[0]
    check(got == want, f"домен через {days} дн.: {got}, а нужно {want}")
st.db.close()

# в «Пороги и проверки» у новой проверки есть название; в блоке «Безопасность» - строка срока домена
from seocrawler.window import settings_ui  # noqa: E402
check(settings_ui.TITLES.get("domain_expiry"), "у domain_expiry нет названия в «Пороги и проверки»")
from seocrawler import security  # noqa: E402
check(any("домена" in r[1] for r in security.summary_rows({"error": "нет"}, [])), "нет строки срока домена в безопасности")
# устаревший год: план «на 2022 год» - да, «работаем с 2012 года» - нет; услуги по адресу /uslugi/ - не магазин
from seocrawler.analyze.checks.meta_text import SERVICE_URL, STALE_YEAR, STORE  # noqa: E402
check(STALE_YEAR.findall("задачи на 2022 год. Работаем с 2012 года") == ["2022"], "устаревший год")
check(SERVICE_URL.search("/uslugi/kontekst/") and not STORE.search("Купить тариф"), "услуги считаются магазином")
look = F._look({"desc": "Работаем с 2012 года. Задачи на 2022 год.", "title": ""})
check("2022" in look and "2012" not in look, f"пометка про год: {look}")

if fails:
    print("✗ советы под движок и срок домена:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ советы под движок и срок домена: Тильда без «замените robots.txt» и плагинов, WordPress с плагинами, "
      "общий совет без движка, домен за месяц - критично")
