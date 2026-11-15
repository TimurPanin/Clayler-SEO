"""Тестовый сайт с ловушками для проверки краулера. Запуск: python tests/testsite.py 8765,
затем: python crawl.py http://127.0.0.1:8765/"""
import gzip
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
B = f"http://127.0.0.1:{PORT}"
hits_429 = {"n": 0}
hits_flaky = {"n": 0}
STATE = {"v": 1}  # GET /__v2 переключает сайт во «вторую версию» — для проверки сравнения двух обходов


def page(title, body, head="", h1=None, desc="Описание страницы для теста, достаточно длинное, чтобы не считаться коротким ок."):
    h = f"<h1>{h1 if h1 is not None else title}</h1>" if h1 != "" else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title>
<meta name="description" content="{desc}">{head}</head><body>{h}{body}</body></html>"""


NAV = """<a href="/about">О нас</a> <a href="/about/">О нас со слешем</a> <a href="/catalog/">Каталог</a>
<a href="/old">Старая</a> <a href="/loop1">Цикл</a> <a href="/missing">Нет такой</a> <a href="/err">Ошибка</a>
<a href="/cp1251">cp1251</a> <a href="/bad-enc">Кривая кодировка</a> <a href="/soft">Мягкий</a>
<a href="/dup1">Дубль 1</a> <a href="/dup2">Дубль 2</a> <a href="/noindex">noindex</a> <a href="/canon">canon</a>
<a href="/?utm_source=test&utm_medium=x">Главная с меткой</a> <a href="/catalog/?sort=price&color=red&size=m&page=2">Фильтр</a>
<a href="/private/secret">Закрыто</a> <a href="/deep/1">Глубоко</a> <a href="/trap/">Ловушка</a>
<a href="/refresh">Refresh</a> <a href="/flaky">Нестабильная</a> <a href="/kurs/">Курсы</a> <a href="/city/ekb">Екб</a> <a href="/city/msk">Мск</a> <a href="/city/spb">Спб</a> <a href="/catalog/?ref=abc">Clean-param</a> <a href="/rate">429</a>
<a href="http://localhost:1/">Внешняя мёртвая</a> <a href="/nf" rel="nofollow">nofollow</a>
<a href="mailto:a@b.ru">почта</a> <a href="/about#team">Якорь</a> <a href="/About">Заглавные</a>
<img src="/img/missing.jpg"> <img src="/img/ok.png" alt="ok">
<script>var x='<a href="/js-only">js</a>';</script>"""

LONG = " ".join(["слово"] * 250)
import random as _r
_r.seed(7)
_VOC = [w for w in "английский язык курс занятие группа преподаватель урок уровень ученик школа время неделя цена программа учебник экзамен разговор грамматика словарь чтение письмо аудирование носитель онлайн офлайн расписание филиал центр метод результат".split()]
CITY_TEXT = " ".join(_r.choice(_VOC) for _ in range(400))


def city_text(city):
    # один шаблон текста, отличается только название города в нескольких местах — почти дубль
    words = CITY_TEXT.split()
    for i in range(0, len(words), 200):
        words[i] = city
    return " ".join(words)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None, gz=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        if gz:
            body = gzip.compress(body)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path
        path = p.split("?")[0]
        # открытые служебные файлы: .git и .env — находятся; /backup.zip отдаёт HTML «200 на всё» — не находится
        if p == "/.git/HEAD":
            return self.send(200, "ref: refs/heads/master\n", "text/plain")
        if p == "/.env":
            return self.send(200, "APP_KEY=test\nDB_PASSWORD=secret\n", "text/plain")
        if p == "/backup.zip":
            return self.send(200, page("Не найдено", "Такой страницы нет"))
        if p == "/robots.txt":
            return self.send(200, f"User-agent: *\nDisallow: /private/\nClean-param: ref /catalog/\n\nSitemap: {B}/sitemap.xml\n", "text/plain")
        if p == "/sitemap.xml":
            urls = ["/", "/about/", "/orphan", "/missing", "/noindex", "/old", "/private/secret", "/new", "/kurs"]
            x = "".join(f"<url><loc>{B}{u}</loc></url>" for u in urls)
            return self.send(200, f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{x}</urlset>', "application/xml")
        if path == "/loop":  # «чужой сайт» (localhost) редиректит сам на себя бесконечно, адрес растёт — как ozon.ru
            n = int((p.split("n=") + ["0"])[1].split("&")[0] or 0)
            return self.send(307, b"", headers={"Location": f"http://localhost:{PORT}/loop?n={n + 1}&x={'0' * n}"})
        if path == "/":
            nav = NAV + ('<a href="/brand-new">Новинка</a>' if STATE["v"] == 2 else "")
            return self.send(200, page("Главная страница тестового сайта для краулера", nav + LONG), gz=True,
                             headers={"Last-Modified": "Mon, 01 Sep 2026 10:00:00 GMT"})
        if path in ("/about", "/about/"):
            t = "О компании — новое название во второй версии" if STATE["v"] == 2 else "О компании — тестовый сайт краулера"
            # телефон и адрес без микроразметки организации — замечание «Нет микроразметки организации»
            return self.send(200, page(t, LONG + ' <a href="/catalog/">кат</a> <img src="/img/missing.jpg">'
                                          ' <a href="tel:+73472000000">+7 (347) 200-00-00</a> г. Уфа, ул. Ленина, д. 10'
                                          f' <a href="http://localhost:{PORT}/loop?n=1">магазин</a>'))
        if path == "/catalog/":
            items = "".join(f'<a href="/catalog/item-{i}">Товар {i}</a>' for i in range(5))
            return self.send(200, page("Каталог товаров тестового сайта краулера", items + LONG))
        if path.startswith("/catalog/item-"):
            return self.send(200, page("Товар", "Коротко", h1="Товар"))
        if path == "/old":
            return self.send(301, "", headers={"Location": "/old2"})
        if path == "/old2":
            return self.send(302, "", headers={"Location": f"{B}/new"})
        if path == "/new":
            return self.send(200, page("Новая страница после цепочки редиректов", LONG))
        if path == "/loop1":
            return self.send(301, "", headers={"Location": "/loop2"})
        if path == "/loop2":
            return self.send(301, "", headers={"Location": "/loop1"})
        if path == "/err":
            return self.send(500, "oops")
        if path == "/cp1251":
            body = page("Кириллица в windows-1251 работает правильно", LONG).replace('charset="utf-8"', 'charset="windows-1251"')
            return self.send(200, body.encode("cp1251"), "text/html; charset=windows-1251")
        if path == "/bad-enc":
            body = page("Сервер врёт про кодировку этой страницы", LONG).replace('charset="utf-8"', "")
            return self.send(200, body.encode("cp1251"), "text/html; charset=utf-8")
        if path == "/soft":
            return self.send(200, page("Страница не найдена", "Такой страницы нет"))
        if path in ("/dup1", "/dup2"):
            return self.send(200, page("Дубль", "Одинаковый текст " + LONG))
        if path == "/noindex":
            return self.send(200, page("Закрытая страница от индексации", LONG, head='<meta name="robots" content="noindex, follow">'))
        if path == "/canon":
            return self.send(200, page("Страница с canonical на другую", LONG, head=f'<link rel="canonical" href="{B}/about/">'))
        if path.startswith("/deep/"):
            n = int(path.split("/")[2])
            nxt = f'<a href="/deep/{n + 1}">дальше</a>' if n < 6 else ""
            return self.send(200, page(f"Глубокая страница номер {n} тестового сайта", nxt + LONG))
        if path.startswith("/trap/"):
            return self.send(200, page("Ловушка относительных ссылок в структуре", '<a href="trap/">ещё</a>' + LONG))
        if path == "/refresh":
            return self.send(200, page("Meta refresh", "", head='<meta http-equiv="refresh" content="0; url=/new">'))
        if path.startswith("/city/"):
            city = path.split("/")[2]
            return self.send(200, page(f"Курсы английского в городе {city} — тестовый сайт", city_text(city)))
        if path == "/__v2":
            STATE["v"] = 2
            return self.send(200, "ok", "text/plain")
        if STATE["v"] == 2 and path == "/missing":  # «починили» битую страницу
            return self.send(200, page("Страница, которую починили во второй версии", LONG))
        if STATE["v"] == 2 and path == "/brand-new":
            return self.send(200, page("Новая страница второй версии сайта", LONG))
        if path == "/kurs":
            return self.send(301, "", headers={"Location": "/kurs/"})
        if path == "/kurs/":
            return self.send(200, page("Курсы — страница, на которую ссылаются со слешем", LONG))
        if path == "/flaky":
            hits_flaky["n"] += 1
            if hits_flaky["n"] == 1:  # первый раз обрываем соединение без ответа
                self.close_connection = True
                self.connection.close()
                return
            return self.send(200, page("Страница, которая открылась со второй попытки", LONG))
        if path == "/rate":
            hits_429["n"] += 1
            if hits_429["n"] == 1:
                return self.send(429, "slow down", headers={"Retry-After": "1"})
            return self.send(200, page("Страница после ответа 429 на первый запрос", LONG))
        if path == "/img/ok.png":
            return self.send(200, b"\x89PNG" + b"0" * 300000, "image/png")
        if path == "/orphan":
            return self.send(200, page("Сирота из sitemap без внутренних ссылок", LONG))
        return self.send(404, page("404", "Нет"))


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
