"""Автотест: перенос строки (<br>) и блоки внутри текста дают пробел, как в браузере (без сети).
На hightime.agency H1 «SEO-продвижение сайтов<br>в США» записывался «сайтовв США», «Семантика» брала из него
склеенные слова. Проверяет seocrawler/parser.py (H1, H2) и seocrawler/shop.py (кнопки «Купить», крошки, H1 товара):
<br>, <div>, <p> внутри - пробел; <span>, <b>, <a> - нет («<span>Ко</span><span>тлы</span>» - одно слово).
Запуск: py -3 tests/проверить_перенос_строки.py (и из проверить_всё.py)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler.parser import parse_html  # noqa: E402
from seocrawler import shop  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def h1(body):
    return parse_html(f"<html><head><title>t</title></head><body>{body}</body></html>".encode(), "text/html; charset=utf-8")["h1"]


check(h1("<h1>SEO-продвижение сайтов<br>в США</h1>") == ["SEO-продвижение сайтов в США"], "br в H1")
check(h1("<h1>каталогов и агрегаторов<br/>на нескольких языках</h1>") == ["каталогов и агрегаторов на нескольких языках"],
      "br/ в H1")
check(h1("<h1>Результаты работы HighTime.agency<br>\n</h1>") == ["Результаты работы HighTime.agency"], "br в конце H1")
check(h1("<h1><div>Газовые котлы</div><div>в Уфе</div></h1>") == ["Газовые котлы в Уфе"], "div внутри H1")
check(h1("<h1><p>Котлы</p>Baxi</h1>") == ["Котлы Baxi"], "p внутри H1")
check(h1("<h1><span>Ко</span><span>тлы</span> <b>Baxi</b></h1>") == ["Котлы Baxi"], "span без пробела - одно слово")
check(h1("<h1>Купить <a href='/x'>котёл</a>!</h1>") == ["Купить котёл!"], "ссылка внутри H1")

f = json.loads(shop.facts("<html><body><h1>Котёл Baxi</h1><p>12 000 руб.</p>"
                          "<button>Купить<br>в 1 клик</button><a href='/cart'><span>В кор</span><span>зину</span></a>"
                          "</body></html>") or "{}")
check(f.get("buy") == 2 and f.get("one_click") == 1, f"кнопки с br и span: {f}")
f = json.loads(shop.facts("<html><body><div class='breadcrumbs'><a href='/'>Главная</a> / "
                          "<a href='/k/'>Газовые<br>котлы</a></div><h1>Котёл</h1></body></html>") or "{}")
check("Газовые котлы" in (f.get("crumbs") or []), f"br в хлебных крошках: {f.get('crumbs')}")
# первый H1 - логотип картинкой (пустой), настоящий ниже: «Что мешает покупать» берёт настоящий
f = json.loads(shop.facts("<html><body><h1><img src='/logo.png' alt='logo'></h1><div>меню</div>"
                          "<h1>Котёл<br>Navien Deluxe</h1></body></html>") or "{}")
check(f.get("h1") == "Котёл Navien Deluxe", f"пустой первый H1: {f.get('h1')}")

if fails:
    print("✗ перенос строки:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ перенос строки: <br> и блоки в H1, кнопках и крошках - пробел, <span> - нет")
