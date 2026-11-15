"""Тестовый сайт по https с самоподписанным сертификатом (тест/https_test.crt - только для тестов, 15.10.2026).
Ловушки: сертификат сайта не проходит проверку, ссылки на свой сайт по http://, скрипт и картинка по http:// на
https-странице (смешанный контент), ссылка на «чужой сайт» (localhost) с тем же непроверяемым сертификатом.
Запуск: python тест/httpssite.py 8771, затем: python crawl.py https://127.0.0.1:8771/"""
import os
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
HERE = os.path.dirname(os.path.abspath(__file__))
B = f"https://127.0.0.1:{PORT}"
TEXT = " ".join(["Текст страницы тестового сайта по защищённому протоколу."] * 30)


def page(title, body=""):
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title>'
            '<meta name="description" content="Описание страницы тестового сайта по https, достаточно длинное для теста.">'
            f'</head><body><h1>{title}</h1><a href="/">Главная</a> <a href="/about">О нас</a> {body}<p>{TEXT}</p></body></html>')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            return self.send(200, "User-agent: *\nAllow: /\n", "text/plain")
        if path == "/":
            return self.send(200, page("Главная тестового сайта по https",
                                       f'<a href="http://127.0.0.1:{PORT}/about">О нас по http</a> '
                                       f'<a href="https://localhost:{PORT}/ext">Чужой сайт</a>'))
        if path == "/about":
            return self.send(200, page("О компании, тестовый сайт по https",
                                       f'<script src="http://127.0.0.1:{PORT}/app.js"></script>'
                                       f'<img src="http://127.0.0.1:{PORT}/logo.png" alt="логотип">'))
        if path == "/ext":
            return self.send(200, page("Страница чужого сайта"))
        if path == "/app.js":
            return self.send(200, "var a = 1;", "application/javascript")
        if path == "/logo.png":
            return self.send(200, b"\x89PNG" + b"0" * 100, "image/png")
        return self.send(404, page("Нет такой страницы"))


srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(os.path.join(HERE, "https_test.crt"), os.path.join(HERE, "https_test.key"))
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.serve_forever()
