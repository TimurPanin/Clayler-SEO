"""Тестовый сайт для проверок, которые не срабатывали ни на одном другом тестовом сайте:
title и description (нет, длинный, короткий), несколько H1, все проверки canonical, язык страницы, адреса с
заглавными и русскими буквами, несуществующая страница отдаёт 200, страница, где сервер молчит, десятки
вариантов адреса с параметрами, ссылка из меню на закрытую страницу, разные телефоны на страницах, лишний тег
в <head>, разметка товара не полностью и без хлебных крошек, роботу и браузеру разное, несколько счётчиков Метрики.
Запуск: python tests/checksite.py 8769, затем: python crawl.py http://127.0.0.1:8769/"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8769
B = f"http://127.0.0.1:{PORT}"
TEXT = " ".join(["Текст страницы тестового сайта про проверки, которые раньше молчали."] * 30)
DESC = "Описание страницы для теста, достаточно длинное, чтобы не считаться коротким, но и не длинным."
NAV = ('<a href="/">Главная</a> <a href="/p/">Товары</a> <a href="/closed">Закрытая</a> <a href="/t-missing">a</a> '
       '<a href="/t-long">b</a> <a href="/d-missing">c</a> <a href="/d-long">d</a> <a href="/d-short">e</a> '
       '<a href="/h1-multi">f</a> <a href="/c-bad">g</a> <a href="/c-chain">h</a> <a href="/c-multi">i</a> '
       '<a href="/list/">j</a> <a href="/list/?page=2">k</a> <a href="/Upper-Case">l</a> '
       '<a href="/%D0%BA%D0%BE%D0%BD%D1%82%D0%B0%D0%BA%D1%82%D1%8B">m</a> <a href="/nolang">n</a> '
       '<a href="/head-div">o</a> <a href="/hang">p</a> <a href="/phone2">q</a> <a href="/heavy">r</a> '
       '<a href="/under_score">s</a> <a href="/contact">t</a> '
       f'<a href="http://localhost:{PORT}/forbidden">чужой сайт</a> '
       '<a href="/tmpl">Мебель с {$dveri_t} без декора</a> ')
REQ = threading.local()   # роботу одно, браузеру на компьютере другое (title с пометкой)
# шаблон тяжелее 1 МБ (скрипт на каждой странице), страница тяжелее 3 МБ (большая картинка), маленькая og:image
APP_JS = b"//" + b"x" * (1200 * 1024)
BIG_JPG = b"\xff\xd8\xff" + b"0" * (3500 * 1024)
OG_PNG = (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + (100).to_bytes(4, "big") + (100).to_bytes(4, "big")
          + b"\x08\x02\x00\x00\x00" + b"\x00" * 4 + b"0" * 200)
YM = '<script>ym(11111111, "init", {});</script>'


def page(title, body="", head="", desc=DESC, h1=None, lang=True):
    t = f"<title>{title}{' (браузер)' if REQ.browser else ''}</title>" if title is not None else ""
    d = f'<meta name="description" content="{desc}">' if desc is not None else ""
    head += '<script src="/app.js"></script>'
    h = h1 if h1 is not None else f"<h1>{title or 'Страница'}</h1>"
    return (f'<!doctype html><html{" lang=\"ru\"" if lang else ""}><head><meta charset="utf-8">{t}{d}{head}</head>'
            f'<body>{h}{NAV}{body}<p>{TEXT}</p> <a href="tel:+73472000000">+7 (347) 200-00-00</a>{YM}</body></html>')


def product(n):
    ld = {"@context": "https://schema.org", "@type": "Product", "name": f"Товар номер {n} в Уфе",
          "offers": {"@type": "Offer", "price": "1000"}}   # нет валюты, наличия и картинки - «не полностью»
    return f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body="", ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p, path = self.path, self.path.split("?")[0]
        REQ.browser = "Windows NT" in (self.headers.get("User-Agent") or "")
        if p == "/robots.txt":
            return self.send(200, "User-agent: *\nAllow: /\n")
        if p == "/sitemap.xml":   # страницы, на которые на сайте нет ссылок (для проверки на подставных данных)
            x = "".join(f"<url><loc>{B}{u}</loc></url>" for u in ("/", "/orphan", "/sec/"))
            return self.send(200, f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{x}</urlset>',
                             "application/xml")
        if path == "/orphan":
            return self.send(200, page("Страница без ссылок на сайте, есть только в sitemap"))
        if path == "/sec/":
            return self.send(200, page("Раздел, на который не ведёт ни одна ссылка", '<a href="/sec/a">Страница раздела</a>'))
        if path == "/sec/a":
            return self.send(200, page("Страница раздела, на который не ведёт ни одна ссылка", '<a href="/sec/">Раздел</a>'))
        if path == "/":
            shop = " ".join(f'<a href="/shop/?f={i}">Фильтр {i}</a>' for i in range(25))
            return self.send(200, page("Главная тестового сайта для молчащих проверок", shop))
        if path == "/p/":
            items = " ".join(f'<a href="/p/{i}">Товар {i}</a>' for i in range(25))
            return self.send(200, page("Каталог товаров тестового сайта проверок", items))
        if path.startswith("/p/"):
            n = path.split("/")[2]
            # город в title у товаров (у остальных страниц его нет - «Title без города»); у товара 3 пустые
            # характеристики; у товаров 1 и 2 другой счётчик Метрики
            html = page(f"Товар номер {n} в Уфе", '<span class="price">1000 ₽</span><p>Характеристики не указаны</p>' if n == "3" else "", head=product(n))
            return self.send(200, html.replace("ym(11111111", "ym(22222222") if n in ("1", "2") else html)
        if path == "/contact":   # согласие на обработку данных - нажатием кнопки, без галочки
            return self.send(200, page("Контакты и форма заявки тестового сайта",
                                       '<form action="/send" method="post"><input name="name" placeholder="Имя">'
                                       '<input name="phone" type="tel" placeholder="Телефон"><button>Отправить</button>'
                                       '<p>Нажимая кнопку, вы соглашаетесь на обработку персональных данных и с '
                                       '<a href="/privacy">политикой конфиденциальности</a>.</p></form>'))
        if path == "/privacy":
            return self.send(200, page("Политика конфиденциальности тестового сайта", "Политика обработки персональных данных."))
        if path == "/forbidden":   # «чужой сайт» (localhost) не пускает робота
            return self.send(403, page("Доступ запрещён"))
        if path == "/shop/":
            return self.send(200, page("Магазин с фильтрами тестового сайта проверок"))
        if path == "/closed":
            return self.send(200, page("Закрытая от поиска страница из меню", head='<meta name="robots" content="noindex">'))
        if path == "/t-missing":
            return self.send(200, page(None, h1="<h1>Страница без title</h1>"))
        if path == "/t-long":
            return self.send(200, page("Очень длинный заголовок страницы тестового сайта, который точно не поместится в выдаче"))
        if path == "/d-missing":
            return self.send(200, page("Страница без описания тестового сайта", desc=None))
        if path == "/d-long":
            return self.send(200, page("Страница с длинным описанием тестового сайта", desc=DESC * 3))
        if path == "/d-short":
            return self.send(200, page("Страница с коротким описанием тестового сайта", desc="Коротко."))
        if path == "/h1-multi":
            return self.send(200, page("Страница с двумя заголовками H1 тестового сайта", h1="<h1>Первый</h1><h1>Второй</h1>"))
        if path == "/c-bad":
            return self.send(200, page("Canonical на неработающую страницу тестового сайта",
                                       head=f'<link rel="canonical" href="{B}/gone">'))
        if path == "/c-chain":
            return self.send(200, page("Canonical на закрытую страницу тестового сайта",
                                       head=f'<link rel="canonical" href="{B}/closed">'))
        if path == "/c-multi":
            return self.send(200, page("Два canonical на одной странице тестового сайта",
                                       head=f'<link rel="canonical" href="{B}/c-multi"><link rel="canonical" href="{B}/">'))
        if path == "/list/":   # вторая страница списка с canonical на первую
            if "page=" in p:
                return self.send(200, page("Список статей тестового сайта, вторая страница",
                                           head=f'<link rel="canonical" href="{B}/list/">'))
            return self.send(200, page("Список статей тестового сайта, первая страница"))
        if path == "/Upper-Case":
            return self.send(200, page("Адрес с заглавными буквами тестового сайта"))
        if path == "/%D0%BA%D0%BE%D0%BD%D1%82%D0%B0%D0%BA%D1%82%D1%8B":
            return self.send(200, page("Адрес русскими буквами тестового сайта"))
        if path == "/nolang":
            return self.send(200, page("Страница без указанного языка тестового сайта", lang=False))
        if path == "/head-div":
            return self.send(200, page("Лишний тег в head тестового сайта", head="<div>реклама</div>"))
        if path == "/phone2":
            return self.send(200, page("Страница со старым телефоном тестового сайта",
                                       '<a href="tel:+73472999999">+7 (347) 299-99-99</a>'))
        if path == "/hang":   # сервер принял запрос и молчит: «Сервер не ответил»
            self.close_connection = True
            self.connection.close()
            return
        if path == "/app.js":
            return self.send(200, APP_JS, "application/javascript")
        if path == "/big.jpg":
            return self.send(200, BIG_JPG, "image/jpeg")
        if path == "/og.png":
            return self.send(200, OG_PNG, "image/png")
        if path == "/heavy":
            return self.send(200, page("Тяжёлая страница с большой картинкой тестового сайта", '<img src="/big.jpg" alt="фото">',
                                       head=f'<meta property="og:image" content="{B}/og.png">'))
        if path == "/tmpl":   # заготовка шаблона, которую сайт не подставил
            return self.send(200, page("Шкаф {$color} на заказ - тестовый сайт"))
        if path == "/under_score":
            return self.send(200, page("Адрес с подчёркиванием тестового сайта"))
        if path == "/gone":
            return self.send(404, page("Нет такой страницы"))
        # всё остальное - 200: несуществующая страница не отдаёт 404
        return self.send(200, page("Страница по любому адресу тестового сайта"))

    def do_HEAD(self):
        self.do_GET()


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
