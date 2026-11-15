"""Тестовый сайт с городами (режим «Сайт с городами», --regions), ревизия 15.10.2026: проверки раздела «Города».
Москва - основной сайт, Санкт-Петербург и Екатеринбург - разделы /spb/ и /ekb/. Ловушки:
- у городов одинаковый текст, отличается только название города (region_dup);
- в Екатеринбурге в title и H1 нет названия города (region_no_city);
- на московской странице цен в title и H1 написан Екатеринбург (region_wrong_city);
- из Петербурга ссылка в текст Екатеринбурга (region_cross_links).
Запуск: python тест/citysite.py 8770, затем: python crawl.py http://127.0.0.1:8770/ --regions"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
CITIES = {"": "Москва", "spb": "Санкт-Петербург", "ekb": "Екатеринбург"}
IN = {"": "в Москве", "spb": "в Санкт-Петербурге", "ekb": "в Екатеринбурге"}
WORDS = ("ремонт квартир под ключ бригада мастер смета материалы сроки гарантия дизайн проект плитка ламинат "
         "обои потолок электрика сантехника демонтаж штукатурка покраска").split()
# текст своей страницы: у каждой страницы свой, у одной и той же страницы в разных городах - один (почти дубль)
# (слова с номерами: словарь большой, и название города почти не меняет набор слов страницы)
TEXT = {w: " ".join(f"{WORDS[(i * k) % len(WORDS)]}{i}" for i in range(300)) for w, k in (("", 7), ("uslugi", 3), ("ceny", 5))}


def switcher(cur):
    items = "".join(f'<li class="city-item{" is-active" if k == cur else ""}"><a href="/{k + "/" if k else ""}">{v}</a></li>'
                    for k, v in CITIES.items())
    return f'<div class="city-select"><p>Выберите город</p><ul>{items}</ul></div>'


def page(cur, title, h1, body):
    pre = f"/{cur}" if cur else ""
    nav = f'<a href="{pre}/">Главная</a> <a href="{pre}/uslugi/">Услуги</a> <a href="{pre}/ceny/">Цены</a>'
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title>'
            f'<meta name="description" content="Ремонт квартир {IN[cur]}: сроки, цены, гарантия на работы, выезд мастера.">'
            f'</head><body>{switcher(cur)}<h1>{h1}</h1>{nav}<p>{body}</p></body></html>')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=""):
        body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            return self.send(200, "User-agent: *\nAllow: /\n")
        parts = [x for x in path.split("/") if x]
        cur = parts[0] if parts and parts[0] in ("spb", "ekb") else ""
        rest = parts[1:] if cur else parts
        what = rest[0] if rest else ""
        if what not in ("", "uslugi", "ceny"):
            return self.send(404, "<h1>Нет</h1>")
        name = {"": "Ремонт квартир", "uslugi": "Услуги по ремонту квартир", "ceny": "Цены на ремонт квартир"}[what]
        title = h1 = f"{name} {IN[cur]}"
        if cur == "ekb":   # забыли город
            title = h1 = name
        if cur == "" and what == "ceny":   # скопировали со страницы Екатеринбурга
            title = h1 = f"{name} {IN['ekb']}"
        body = f"Ремонт квартир {IN[cur]}. " + TEXT[what]
        if cur == "spb" and what == "uslugi":
            body += ' <a href="/ekb/ceny/">цены</a>'
        return self.send(200, page(cur, title, h1, body))


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
