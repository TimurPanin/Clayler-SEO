"""Автотест: адрес с параметром без «=» остаётся как на сайте (без сети).
Сверка с Screaming Frog на lancentre.ru: «core.js?1750233058498479» программа записывала как «core.js?1750233058498479=»,
то есть открывала и показывала в отчёте другой адрес. Проверяет seocrawler/urls.normalize и strip_params:
- параметр без «=» остаётся без «=», пустой «a=» остаётся с «=», «?=123» не меняется;
- порядок параметров по-прежнему сортируется, русские буквы кодируются, трекинговые параметры убираются.
Запуск: py -3 tests/проверить_адреса_как_на_сайте.py (и из проверить_всё.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler.fmt import pretty_url  # noqa: E402
from seocrawler.report import _link  # noqa: E402
from seocrawler.urls import normalize, strip_params  # noqa: E402

fails = []


def check(got, want, what):
    if got != want:
        fails.append(f"{what}: {got!r}, ждали {want!r}")


check(normalize("https://a.ru/core.js?1750233058498479"), "https://a.ru/core.js?1750233058498479", "параметр без «=»")
check(normalize("https://a.ru/s.js?=17501"), "https://a.ru/s.js?=17501", "«?=число»")
check(normalize("https://a.ru/?b=2&a=&c"), "https://a.ru/?a=&b=2&c", "пустое значение и параметр без «=»")
check(normalize("https://a.ru/c/?q=Ippon&s=Найти"), "https://a.ru/c/?q=Ippon&s=%D0%9D%D0%B0%D0%B9%D1%82%D0%B8",
      "русские буквы")
check(normalize("https://a.ru/?a=1&a=2"), "https://a.ru/?a=1&a=2", "повтор параметра")
check(strip_params("https://a.ru/?utm_source=y&v&x=1"), ("https://a.ru/?v&x=1", ["utm_source"]), "трекинговый параметр")

# показ адреса в отчёте - как в браузере (vsekuhni.ru: /image/catalog/%D0%91%D0%BB%D0%BE%D0%B3/...)
IMG = "https://a.ru/image/catalog/%D0%91%D0%BB%D0%BE%D0%B3/%D1%82%D0%B0%D0%BD%D0%B4%D0%B5%D0%BC2.jpg"
check(pretty_url(IMG), "https://a.ru/image/catalog/Блог/тандем2.jpg", "показ: русские буквы")
check(pretty_url("https://xn--80aswg.xn--p1ai/?q=%D0%BA%D0%BE%D1%82%20%D0%B3%D0%B0%D0%B7&a=%2F"),
      "https://сайт.рф/?q=кот%20газ&a=%2F", "показ: домен .рф, пробел и %2F остаются")
check(pretty_url("https://a.ru/x%C2%A0y%FF"), "https://a.ru/x%C2%A0y%FF", "показ: невидимый пробел и не UTF-8 - как есть")
check(pretty_url("https://a.ru/?"), "https://a.ru/?", "показ: пустой «?» не пропадает")
check(_link(IMG), f'<a href="{IMG}" target="_blank" rel="noopener">https://a.ru/image/catalog/Блог/тандем2.jpg</a>',
      "ссылка в отчёте: ведёт на прежний адрес, текст - как в браузере")

if fails:
    print("✗ адреса как на сайте:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ адреса как на сайте: параметр без «=» не превращается в «параметр=», в отчёте русские буквы вместо %D0%91…")
