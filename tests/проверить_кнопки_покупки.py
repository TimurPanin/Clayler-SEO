"""Автотест: программа нажимает «Купить в один клик», «В корзину», «Заказать звонок» в браузере
(seocrawler/buy_clicks.py) и видит: ничего не происходит, общая форма без товара, форма спрашивает выбранный город.
Формы при этом не отправляются - сайт считает, сколько раз ему что-то отправили (должно быть 0).
Нужен playwright с Chromium (как для снимков телефона); без него тест пропускается.
Запуск: py -3 tests/проверить_кнопки_покупки.py"""
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seocrawler import buy_clicks, shop  # noqa: E402
from seocrawler.mobile_view import available  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

POSTS = []
HEAD = ('<header style="position:relative"><span>Ваш город: Уфа</span> '
        '<button type="button" onclick="document.getElementById(\'cb\').style.display=\'block\'">Заказать звонок</button>'
        ' <span class="cart">Корзина: <b id="cnt">0</b></span></header>')
MODAL = ('<div id="{id}" style="display:none;position:fixed;left:30%;top:20%;width:400px;height:300px;background:#fff;'
         'border:1px solid #000;z-index:99"><p>{text}</p><form action="/order" method="post">{fields}'
         '<input name="phone" placeholder="Телефон"><button type="submit">Отправить</button></form></div>')


def page(name, body):
    return (f'<!doctype html><html><head><meta charset="utf-8"></head><body>{HEAD}<h1>{name}</h1>'
            f'<div class="price">45 000 ₽</div>{body}'
            + MODAL.format(id="cb", text="Мы перезвоним", fields='<input name="name"><input name="city" placeholder="Город">')
            + '</body></html>')


PAGES = {
    # «В корзину» ничего не делает; «Купить в 1 клик» - общая форма «Оставьте телефон» без товара
    "/kotel-navien/": page("Котёл газовый Navien Deluxe", '<button type="button">В корзину</button> '
                           '<button type="button" onclick="document.getElementById(\'oc\').style.display=\'block\'">'
                           'Купить в 1 клик</button>'
                           + MODAL.format(id="oc", text="Оставьте телефон, мы перезвоним", fields="")),
    # всё правильно: корзина обновляется, форма с товаром; а «Заказать звонок» сам отправляет форму - не должен
    "/kotel-baxi/": page("Котёл газовый Baxi Eco", '<button type="button" onclick="document.getElementById(\'cnt\')'
                         '.textContent=\'1\'">В корзину</button> <button type="button" onclick="document.getElementById('
                         '\'oc\').style.display=\'block\';document.forms[1].submit()">Купить в 1 клик</button>'
                         + MODAL.format(id="oc", text="Котёл газовый Baxi Eco - 45 000 ₽", fields="")),
}


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        b = PAGES.get(self.path, "<h1>Нет</h1>").encode()
        self.send_response(200 if self.path in PAGES else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        POSTS.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


def main():
    if not available():
        print("• кнопки покупки: playwright не установлен - тест пропущен")
        return
    fails = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    tmp = tempfile.mkdtemp(prefix="clayler-clicks-")
    st = Store(os.path.join(tmp, "crawl.db"))
    st.set_meta("start", base + "/")
    for path, html in PAGES.items():
        st.enqueue(base + path, 1, True, "page", base + "/", "done")
        st.save_page({"url": base + path, "status": 200, "shop": shop.facts(html)})
    st.commit()
    todo = buy_clicks.pick(st)
    if sorted(u for _, u in todo) != sorted(base + p for p in PAGES):
        fails.append(f"какие страницы нажимать: {todo}")
    res = buy_clicks.ensure(st, tmp, log=lambda *a: None)
    srv.shutdown()
    got = {(i["url"].replace(base, ""), i["kind"]): i for i in (res or {}).get("items", [])}
    want = {("/kotel-navien/", "cart"): "нажали, а на экране ничего не изменилось",
            ("/kotel-navien/", "one_click"): "форма «купить в один клик» не показывает, какой товар заказывают",
            ("/kotel-navien/", "callback"): "форма спрашивает город, хотя в шапке уже выбран город Уфа",
            ("/kotel-baxi/", "cart"): "", ("/kotel-baxi/", "one_click"): ""}
    for k, v in want.items():
        if k not in got:
            fails.append(f"{k}: кнопку не нажали")
        elif got[k]["problem"] != v:
            fails.append(f"{k}: «{got[k]['what']}» / «{got[k]['problem']}» (ждали «{v}»)")
        elif not os.path.exists(os.path.join(tmp, buy_clicks.DIR, got[k]["file"])):
            fails.append(f"{k}: нет снимка")
    if POSTS:
        fails.append(f"формы отправились: {POSTS}")
    if "Кнопки покупки и заявки на снимках" not in buy_clicks.html_block(res):
        fails.append("нет раздела со снимками")
    if fails:
        print("✗ кнопки покупки:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ кнопки покупки: ничего не происходит, форма без товара, город заново - найдены, формы не отправлены")


if __name__ == "__main__":
    main()
