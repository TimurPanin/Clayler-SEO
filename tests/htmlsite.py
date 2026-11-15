"""Тестовый сайт для проверок версии 6: viewport, ошибки HTML, Schema.org, Open Graph, keywords, H2, склейка домена.
Запуск: python tests/htmlsite.py 8768, затем: python crawl.py http://127.0.0.1:8768/"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8768
B = f"http://127.0.0.1:{PORT}"
VP = '<meta name="viewport" content="width=device-width, initial-scale=1">'
OG = '<meta property="og:title" content="T"><meta property="og:description" content="D"><meta property="og:image" content="/i.png">'
LD = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"X"}</script>'
YM = '<script>ym(10000001, "init", {});</script>'  # счётчик Метрики на всех страницах, кроме /nometrika
MENU = '<nav>' + "".join(f'<a href="/{p}">{p}</a> ' for p in
                         ["ok", "noviewport", "nozoom", "headdiv", "headimg", "twoheads", "dupid", "badld", "product",
                          "noog", "keywords", "longnoh2", "nometrika", "emptycat", "sold"]) + '</nav>'
TEXT = "<p>" + " ".join(f"слово{i}" for i in range(350)) + "</p>"


def page(title, head="", body="", vp=VP, og=OG, ld=LD, canon=True):
    c = f'<link rel="canonical" href="{B}/{title}">' if canon else ""
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Тестовая страница {title} для проверки</title>'
            f'<meta name="description" content="Описание тестовой страницы {title} для проверки краулера, достаточно длинное.">'
            f'{vp}{og}{ld}{YM}{head}{c}</head><body>{MENU}<h1>{title}</h1><h2>Раздел</h2>{body}{TEXT}</body></html>')


PAGES = {
    "/": page("", canon=False),
    "/ok": page("ok", body='<a href="tel:+73472000000">+7 (347) 200-00-00</a>'),  # телефон есть, Organization есть — не ошибка
    "/noviewport": page("noviewport", vp=""),                                   # нет viewport
    "/nozoom": page("nozoom", vp='<meta name="viewport" content="width=device-width, user-scalable=no">'),
    "/headdiv": page("headdiv", head='<div class="counter"></div>'),           # div в head ДО canonical — критично
    "/headimg": page("headimg", head='<noscript><img src="/pixel.gif"></noscript>'),  # в noscript — не ошибка
    "/twoheads": page("twoheads", body="<head><title>x</title></head>"),        # второй head
    "/dupid": page("dupid", body='<div id="a"></div><div id="a"></div>'),
    "/badld": page("badld", ld='<script type="application/ld+json">{"@type": "Product",}</script>'),
    "/product": page("product", ld='<script type="application/ld+json">{"@context":"https://schema.org",'
                                   '"@graph":[{"@type":"Product","name":"P"},{"@type":"BreadcrumbList"}]}</script>'),
    "/noog": page("noog", og="", ld=""),                                          # нет OG и микроразметки
    "/keywords": page("keywords", head='<meta name="keywords" content="котлы, запчасти">'),
    "/longnoh2": page("longnoh2").replace("<h2>Раздел</h2>", ""),               # 350 слов без H2
    "/nometrika": page("nometrika").replace(YM, ""),                            # забыли счётчик Метрики
    "/emptycat": page("emptycat", body="<div>Товаров не найдено</div>"),          # пустой раздел каталога
    "/sold": page("sold", body="<span>Нет в наличии</span><p>Артикул 123</p>"),  # товар закончился
}
# латинская C в H1 и латинская o в тексте — «смешанные буквы»
PAGES["/ok"] = PAGES["/ok"].replace("<h1>ok</h1>", "<h1>Cтроительство ok</h1>").replace("<h2>Раздел</h2>", "<h2>Раздел</h2><p>кoтел</p>")
# товар с ценой и кнопкой «Купить» — сайт коммерческий: проверяются коммерческие факторы (доставки, оплаты и т. д. нет)
PAGES["/product"] = PAGES["/product"].replace("<h2>Раздел</h2>", "<h2>Раздел</h2><p>Цена 12 500 руб. <button>Купить</button></p>")
# как на телефоне (браузер 375 px): /dupid шире экрана, /longnoh2 мелким шрифтом, /noog — мелкие ссылки вплотную
PAGES["/dupid"] = PAGES["/dupid"].replace("<h2>Раздел</h2>", '<h2>Раздел</h2><div class="wide" style="width:600px">широкий блок</div>')
PAGES["/longnoh2"] = PAGES["/longnoh2"].replace("<p>слово0", '<p style="font-size:10px">слово0')
PAGES["/noog"] = PAGES["/noog"].replace("<h2>Раздел</h2>", "<h2>Раздел</h2>" + "".join(
    f'<a href="/ok" style="display:block;font-size:12px;line-height:14px">п{i}</a>' for i in range(3)))
PAGES["/index.php"] = PAGES["/"]  # копия главной без редиректа — ошибка склейки
# Каталог с постраничной навигацией, закрытой в robots.txt: товары 2 и 3 — только на страницах 2 и 3,
# товар 4 — настоящая сирота (есть только в sitemap)
PAGES["/"] = PAGES["/"].replace("</nav>", '<a href="/catalog/">Каталог</a></nav>')
PAGES["/catalog/"] = page("catalog", canon=False, body='<a href="/prod1/">Товар 1</a> <a href="/catalog/?PAGEN_1=2">2</a>')
PAGES["/catalog/?PAGEN_1=2"] = page("catalog2", canon=False, body='<a href="/prod2/">Товар 2</a> <a href="/catalog/?PAGEN_1=3">3</a>')
PAGES["/catalog/?PAGEN_1=3"] = page("catalog3", canon=False, body='<a href="/prod3/">Товар 3</a>')
for i in (1, 2, 3, 4):
    PAGES[f"/prod{i}/"] = page(f"prod{i}", canon=False)
# ошибки сервера: /err-once — 500 один раз, потом открывается (и ведёт на новую страницу); /err-always — 500 всегда
PAGES["/"] = PAGES["/"].replace("</nav>", '<a href="/err-once">e1</a><a href="/err-always">e2</a></nav>')
PAGES["/found-after"] = page("found-after", canon=False)
HITS = {}
PAGES["/robots.txt"] = f"User-agent: *\nDisallow: /*PAGEN*\nSitemap: {B}/sitemap.xml\n"
PAGES["/sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                         + "".join(f"<url><loc>{B}/prod{i}/</loc></url>" for i in (1, 2, 3, 4)) + "</urlset>")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/err-once", "/err-always"):
            HITS[self.path] = HITS.get(self.path, 0) + 1
            if self.path == "/err-always" or HITS[self.path] <= 1:
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<title>Ошибка</title><a href='/'>на главную</a>".encode())
                return
            b = page("err-once", canon=False, body='<a href="/found-after">новая</a>').encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path == "/index.html":  # временный редирект вместо 301
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        body = PAGES.get(self.path)
        # мобильная версия: /keywords телефону отдаёт другой title и без H1; /nozoom уводит телефон на /m/nozoom,
        # а там нет canonical на основную и на основной нет alternate — m.сайт связан неправильно
        if "Mobile" in self.headers.get("User-Agent", ""):
            if self.path == "/nozoom":
                self.send_response(302)
                self.send_header("Location", "/m/nozoom")
                self.end_headers()
                return
            if self.path == "/keywords":
                body = body.replace("<title>Тестовая", "<title>Мобильная").replace("<h1>keywords</h1>", "")
        if self.path == "/m/nozoom":
            body = page("m-nozoom", canon=False)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<title>404</title>")
            return
        b = body.encode("utf-8")
        self.send_response(200)
        ctype = {"/robots.txt": "text/plain", "/sitemap.xml": "application/xml"}.get(self.path, "text/html")
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
