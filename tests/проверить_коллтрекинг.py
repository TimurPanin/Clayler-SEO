"""Автотест коллтрекинга (seocrawler/calltrack.py): номер в HTML от сервера и после JavaScript разный -
находка «номер подменяется» с обоими номерами и сервисом по адресу скрипта; разные подменные номера на страницах
не дают «разные телефоны»; одинаковый номер - не подмена. Без сети. Запуск: py -3 tests/проверить_коллтрекинг.py."""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import calltrack as CT  # noqa: E402
from seocrawler.parser import parse_html  # noqa: E402
from seocrawler.analyze.checks import local_seo  # noqa: E402

fails = []
RAW = ('<html><body><header><a href="tel:+74951234567">+7 (495) 123-45-67</a></header>'
       '<script src="https://mod.calltouch.ru/init.js?id=1"></script></body></html>')


def page(js_phone):
    return ('<html><body><header><a href="tel:+7495%s">+7 (495) %s-%s-%s</a></header></body></html>'
            % (js_phone, js_phone[:3], js_phone[3:5], js_phone[5:])).encode()


raw = parse_html(RAW.encode(), "text/html; charset=utf-8")
if raw["calltrack"] != ["Calltouch"]:
    fails.append(f"сервис по скрипту не узнан: {raw['calltrack']}")
pages = []
for n, ph in enumerate(("7654321", "7000001")):   # каждому «посетителю» свой номер
    js = parse_html(page(ph), "text/html; charset=utf-8")
    ct = CT.compare(raw["contacts"], js["contacts"], raw["calltrack"])
    pages.append({"url": f"https://s.ru/{n}", "contacts": js["contacts"], "calltrack": ct, "indexable": 1})
same = CT.compare(raw["contacts"], raw["contacts"], [])
if same is not None:
    fails.append(f"одинаковый номер считается подменой: {same}")

got = {}
ctx = SimpleNamespace(add=lambda key, *a, **k: got.__setitem__(key, a), indexable=pages, html_ok=pages)
local_seo.run(ctx)
if "calltracking" not in got:
    fails.append(f"нет находки «номер подменяется»: {list(got)}")
else:
    rows = got["calltracking"][6]
    if len(rows) != 2 or "74951234567" not in rows[0][1] or "74957654321" not in rows[0][2] or rows[0][3] != "Calltouch":
        fails.append(f"в строке нет обоих номеров или сервиса: {rows}")
if "contacts_mix" in got:
    fails.append("подменные номера дали «На разных страницах разные телефоны»")

# сервис не узнан - «сервис не определён»
plain = parse_html(RAW.replace("mod.calltouch.ru", "cdn.example.ru").encode(), "text/html; charset=utf-8")
ct = CT.compare(plain["contacts"], parse_html(page("7654321"), "text/html")["contacts"], plain["calltrack"])
got.clear()
local_seo.run(SimpleNamespace(add=lambda key, *a, **k: got.__setitem__(key, a), indexable=[],
                              html_ok=[{"url": "https://s.ru/", "calltrack": ct}]))
if "calltracking" not in got or got["calltracking"][6][0][3] != "сервис не определён":
    fails.append(f"без сервиса: {got.get('calltracking')}")

# ссылка или слово «Calltouch» в тексте - не подключённый скрипт; номер дорисовал скрипт без номера в HTML - не подмена
if CT.services('<a href="https://calltouch.ru">Calltouch</a> про roistat.com'):
    fails.append("ссылка на сервис в тексте принята за скрипт коллтрекинга")
if json.loads(CT.compare('{"phones": []}', '{"phones": ["+79991234567"]}', ["Roistat"]) or "{}").get("swap"):
    fails.append("номер, которого нет в HTML от сервера, принят за подмену")
# сведения о коллтрекинге не меняют вывод пункта аудита («Ошибок нет» остаётся)
from seocrawler import audit  # noqa: E402
from seocrawler.analyze.common import Issue  # noqa: E402
pt = [p for p in audit.audit_data([Issue("calltracking", "notice", "", "", "", "", [], [["x"]])], {"has_v6": 1})[0]
      if p["num"] == 19]
if pt and pt[0]["verdict"] != "Ошибок нет":
    fails.append(f"коллтрекинг поменял вывод аудита: {pt[0]['verdict']}")

print("\n".join(fails) if fails else "Коллтрекинг: всё в порядке")
sys.exit(1 if fails else 0)
