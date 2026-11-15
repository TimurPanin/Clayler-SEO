"""Тестовый сайт, где часть содержимого создаёт JavaScript.
Запуск: python тест/jssite.py 8766, затем: python crawl.py http://127.0.0.1:8766/ --js"""
import json
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
WORDS = " ".join(["слово"] * 300)


def page(title, body="", head="", script=""):
    t = f"<title>{title}</title>" if title else ""
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">{t}'
            f'<meta name="description" content="Тестовая страница сайта с JavaScript для проверки краулера.">'
            f'{head}</head><body>{body}<script>{script}</script></body></html>')


PAGES = {
    # Главная: title и H1 ставит скрипт, половину меню рисует скрипт
    "/": page("Загрузка…", '<a href="/static">Обычная страница</a><div id="menu"></div>', script="""
        document.title = 'Главная страница сайта на JavaScript';
        document.body.insertAdjacentHTML('afterbegin', '<h1>Главная</h1>');
        document.getElementById('menu').innerHTML =
          '<a href="/spa/a">Каталог</a> <a href="/spa/b">Услуги</a> <a href="/noidx">Скрытая</a>' +
          '<a href="/jsredir">Старая акция</a> <a href="/addnoindex">Черновик</a> <a href="/usesblocked">Со скриптом</a>' +
          '<a href="/notitle">Без title</a> <a href="/jsdesc">Описание</a> <a href="/hang">Зависает</a> <a href="/bigimg">Фото</a>';
    """),
    "/static": page("Обычная страница без JavaScript, всё в HTML", '<h1>Обычная</h1><a href="/rnd">Случайное</a>' + WORDS),
    # Текст подгружается запросом к API
    "/spa/a": page("Каталог товаров сайта на JavaScript для теста", '<h1>Каталог</h1><div id="c"></div>', script="""
        fetch('/api/text').then(r => r.json()).then(d => { document.getElementById('c').textContent = d.text; });
    """),
    # Скрипт меняет canonical
    "/spa/b": page("Услуги компании — тестовая страница на JavaScript",
                   "<h1>Услуги</h1>" + WORDS, head='<link rel="canonical" href="/spa/b">', script="""
        document.querySelector('link[rel=canonical]').href = '/static';
    """),
    # noindex в HTML, скрипт его убирает
    "/noidx": page("Страница с noindex, который убирает скрипт", "<h1>Скрытая</h1>" + WORDS,
                   head='<meta name="robots" content="noindex">', script="""
        document.querySelector('meta[name=robots]').remove();
    """),
    # Скрипт добавляет noindex
    "/addnoindex": page("Страница, которой скрипт добавляет noindex", "<h1>Черновик</h1>" + WORDS, script="""
        var m = document.createElement('meta'); m.name = 'robots'; m.content = 'noindex'; document.head.appendChild(m);
    """),
    # Редирект скриптом
    "/jsredir": page("Старая акция", "<h1>Акция закончилась</h1>", script="location.replace('/static');"),
    # В HTML title нет совсем, его ставит скрипт; description меняет скрипт (15.10.2026)
    "/notitle": page("", "<h1>Без title</h1>" + WORDS, script="document.title = 'Title, который поставил скрипт';"),
    "/jsdesc": page("Страница, где скрипт меняет описание", "<h1>Описание</h1>" + WORDS, script="""
        document.querySelector('meta[name=description]').content = 'Описание, которое поставил скрипт, а не HTML.';
    """),
    # Скрипт зависает: страница не отрисовывается
    "/hang": page("Страница, где скрипт зависает навсегда", "<h1>Зависает</h1>" + WORDS, script="while (true) {}"),
    # Картинка 2000×2000 показана 100×100
    "/bigimg": page("Страница с огромной картинкой в маленькой рамке", '<h1>Фото</h1><img src="/big.png" width="100" '
                    'height="100" alt="фото">' + WORDS),
    # Скрипт закрыт в robots.txt
    "/usesblocked": page("Страница со скриптом, закрытым в robots.txt",
                         '<h1>Со скриптом</h1><div id="x"></div>' + WORDS,
                         head='<script src="/blocked-js/app.js"></script>'),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/robots.txt":
            return self.send(200, "User-agent: *\nDisallow: /blocked-js/\n", "text/plain")
        if p == "/api/text":
            return self.send(200, json.dumps({"text": WORDS}), "application/json")
        if p == "/big.png":   # заголовок PNG 2000×2000 и 200 КБ данных
            body = (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + (2000).to_bytes(4, "big")
                    + (2000).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"\x00" * 4 + b"0" * 200000)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if p == "/blocked-js/app.js":
            return self.send(200, "document.getElementById('x').textContent='из скрипта';", "application/javascript")
        if p == "/rnd":  # меню со случайным пунктом: при каждом запросе разное (не должно считаться JS)
            lang = random.choice(["fr", "es", "cn", "de", "it"])
            return self.send(200, page("Страница со случайным пунктом меню для проверки",
                                       f'<h1>Случайное</h1><a href="/lang/{lang}">Язык</a>' + WORDS))
        if p.startswith("/lang/"):
            return self.send(200, page("Язык " + p, "<h1>Язык</h1>" + WORDS))
        if p in PAGES:
            return self.send(200, PAGES[p])
        return self.send(404, page("404", "Нет"))


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
