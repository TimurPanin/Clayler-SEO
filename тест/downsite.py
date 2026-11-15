"""Тестовый сайт, который падает посреди обхода: первые N запросов - нормальные страницы со ссылками,
потом на всё отвечает 502 Bad Gateway (как domeo.ru 08.10.2026). Для тест/проверить_очередь.py.
Запуск: python тест/downsite.py 8798 [N]"""
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8798
GOOD = int(sys.argv[2]) if len(sys.argv) > 2 else 6
_n = [0]
_lock = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self.path in ("/robots.txt", "/sitemap.xml"):
            self.send_response(404)
            self.end_headers()
            return
        with _lock:
            _n[0] += 1
            n = _n[0]
        if n > GOOD:
            body = b"<html><body><h1>502 Bad Gateway</h1></body></html>"
            self.send_response(502)
        else:
            links = "".join(f'<a href="/p{i}">p{i}</a> ' for i in range(1, 200))
            body = (f"<!doctype html><html><head><meta charset=utf-8><title>Страница {self.path}</title></head>"
                    f"<body><h1>Страница {self.path}</h1>{links}</body></html>").encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
