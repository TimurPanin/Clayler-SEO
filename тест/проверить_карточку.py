"""Автотест: карточка сайта (seocrawler/site_card.py, план, раздел 6). Без сети.
- дата и время проверки «10.10.2026 в 10:05», здоровье, число проблем, сравнение с прошлой проверкой;
- «Что исправить первым»: критичные раньше важных, замечания и служебные проблемы не попадают;
- движок, хостинг, домен; бренды из названий товаров (меньше 30 товаров - блока нет);
- снимок главной с телефона - внутри файла; ссылки только на файлы, которые есть в папке;
- кнопка в окне: has_card в списке отчётов.
Запуск: py -3 тест/проверить_карточку.py"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="clayler-card-")
os.environ.update(CLAYLER_NO_USER_SETTINGS="1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.analyze import CRIT, WARN, NOTE  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402
from seocrawler.storage import Store  # noqa: E402
from seocrawler import site_card  # noqa: E402
from seocrawler.window import reports_list  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def make(folder, n):
    os.makedirs(os.path.join(folder, "мобильная"))
    st = Store(os.path.join(folder, "crawl.db"))
    st.set_meta("start", "https://optic.ru/")
    st.set_meta("finished_at", "2026-10-10 10:05:00")
    st.save_page({"url": "https://optic.ru/", "status": 200, "content_type": "text/html", "indexable": 1,
                  "title": "Оптика", "h1": "Оптика", "word_count": 300})
    brands = ["Ray-Ban", "Polaroid", "Vogue"]
    for i in range(n):
        nm = f"Оправа {brands[i % 3]} RB{1000 + i}"
        st.save_page({"url": f"https://optic.ru/p{i}/", "status": 200, "content_type": "text/html", "indexable": 1,
                      "title": nm, "h1": nm, "word_count": 100, "schema_types": "Product"})
    st.commit()
    st.db.close()
    with open(os.path.join(folder, "мобильная", "01.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0JPEGDATA")
    with open(os.path.join(folder, "отчёт.html"), "w", encoding="utf-8") as f:
        f.write("<html></html>")


def issue(key, sev, title, n, gain=0.0):
    return Issue(key, sev, "x", title, "Чем вредит.", f"Исправьте {title.lower()}. Подробно дальше.", ["Адрес"],
                 rows=[[f"https://optic.ru/{k}/"] for k in range(n)], gain=gain)


issues = [issue("title_dup", WARN, "Одинаковый title", 50, 3.0), issue("broken", CRIT, "Битые ссылки", 5, 1.5),
          issue("img_alt", NOTE, "Картинки без alt", 900), issue("program_fail", CRIT, "Служебная ошибка", 3)]
summary = {"health": 64, "pages": 1201, "crit": 1, "warn": 1, "note": 1, "queue_left": 0,
           "compare": {"old_finished": "2026-10-01 09:00:00", "fixed": 4, "added": 2},
           "works": [{"stage": "1. Срочно: мешает индексации", "hours": 2.0}, {"stage": "2. Важно: позиции", "hours": 1.5}]}
meta = {"start": "https://optic.ru/", "finished_at": "2026-10-10 10:05:00", "work_seconds": 3720,
        "mobile_view": {"width": 375, "pages": [{"url": "https://optic.ru/", "shot": "01.jpg", "load_s": 2.1}]},
        "site_tech": {"engines": [{"name": "1С-Битрикс", "version": ""}], "hosting": "Beget",
                      "domain": {"created": "2017-10-13", "expires": "2027-10-13", "registrar": "Beget"},
                      "cert": {"issuer": "Let's Encrypt", "expires": "2026-12-27"}}}

big = os.path.join(TMP, "optic.ru_2026-10-10_10-00-00")
make(big, 60)
doc = open(site_card.write(big, meta, issues, summary), encoding="utf-8").read()
check("Проверка 10.10.2026 в 10:05" in doc, "дата и время проверки")
check("64%" in doc and "обход 1 ч 2 мин" in doc and "1 201" in doc, "здоровье, время обхода, страниц с пробелом")
check("С проверки 01.10.2026 в 09:00: исправлено 4, новых 2" in doc, "сравнение с прошлой проверкой")
check(doc.find("Битые ссылки") < doc.find("Одинаковый title") and doc.find("Битые ссылки") > 0, "критичные раньше важных")
check("Картинки без alt" not in doc and "Служебная ошибка" not in doc, "замечания и служебные проблемы не в главных")
check("Исправьте битые ссылки." in doc, "что сделать")
check("+3,0% к здоровью" in doc, "прирост здоровья")
check("1С-Битрикс" in doc and "Beget" in doc and "оплачен до 13.10.2027" in doc and "до 27.12.2026" in doc,
      "движок, хостинг, домен, сертификат")
check("Бренды на сайте" in doc and "ray-ban" in doc and "<i>20</i>" in doc, "бренды из названий товаров")
check("data:image/jpeg;base64," in doc and "загрузка 2,1 с" in doc, "снимок главной внутри файла")
from urllib.parse import quote  # noqa: E402
check(f'href="{quote("отчёт.html")}"' in doc and f'href="{quote("аудит.pdf")}"' not in doc,
      "ссылки только на готовые файлы")
check("срочно 2 ч, важно 1,5 ч" in doc and "около 3,5 ч" in doc, "смета по этапам")
check("—" not in doc, "без длинного тире")

small = os.path.join(TMP, "small.ru_2026-10-10_10-00-00")
make(small, 10)
doc = open(site_card.write(small, {"start": "https://small.ru/", "finished_at": "2026-10-10 10:05:00"}, [], {"health": 100}),
           encoding="utf-8").read()
check("Бренды на сайте" not in doc, "мало товаров - бренды не разбираются")
check("Серьёзных проблем не найдено" in doc, "без проблем")
check("<h2>Сайт</h2>" not in doc and "data:image" not in doc, "нет данных - нет пустых блоков")

check(reports_list.FILES.get("has_card") == site_card.NAME, "кнопка «Карточка» в окне (has_card)")
item = reports_list.read_check(TMP, os.path.basename(big))
check(item and item.get("has_card"), "список отчётов видит карточку")
page = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seocrawler", "window", "page")
js = open(os.path.join(page, "app.js"), encoding="utf-8").read()
check('data-card="' in js and "function openCard" in js and "карточка.html" in js and "'#dark'" in js,
      "нажатие на строку сайта открывает карточку в окне")
check('id="cardDlg"' in open(os.path.join(page, "index.html"), encoding="utf-8").read(), "окно карточки в index.html")
check(":root.dark" in doc, "тёмная тема по #dark")

if fails:
    print("✗ карточка сайта:")
    for x in fails:
        print("  -", x)
    sys.exit(1)
print("✓ карточка сайта: дата проверки, здоровье, что исправить первым, движок, бренды, снимок главной, файлы")
