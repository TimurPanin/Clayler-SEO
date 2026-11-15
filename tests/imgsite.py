"""Тестовый сайт с проблемными картинками, стилями и скриптами.
Запуск: python tests/imgsite.py 8767, затем: python crawl.py http://127.0.0.1:8767/ (можно с --js)"""
import os
import struct
import sys
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8767


def png(w, h, noisy=True):
    """PNG без сторонних библиотек. noisy=True — случайный шум, чтобы файл плохо сжимался и был тяжёлым."""
    raw = b"".join(b"\x00" + (os.urandom(w * 3) if noisy else b"\xff" * (w * 3)) for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


FILES = {
    "/big.png": png(800, 600),          # ~1.4 МБ, показывается 200×150
    "/pic.png": png(300, 300),          # ~270 КБ, внутри <picture> с WebP
    "/small.png": png(10, 10, False),
    "/long.png": png(20, 20, False),
    "/chunked.png": png(400, 300),      # отдаётся без Content-Length
}
JS = ("var a = '" + "x" * 400_000 + "';").encode()  # 400 КБ без сжатия

HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Страница с картинками для проверки краулера</title>
<meta name="description" content="Тестовая страница с тяжёлыми и неправильными картинками, стилями и скриптами.">
<link rel="stylesheet" href="/missing.css"><script src="/app.js"></script></head><body>
<h1>Картинки</h1>
<img src="/big.png" width="200" height="150">
<img src="/small.png" alt="" width="10" height="10">
<img src="/fake.jpg" alt="Фото">
<img src="/long.png" alt="{long}">
<picture><source srcset="/pic.webp" type="image/webp"><img src="/pic.png" alt="Картинка в picture" width="300" height="300"></picture>
<img src="/chunked.png" alt="Без длины">
<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="/big.png" alt="Ленивая" width="200" height="150">
<img src="/small.png" srcset="/small.png 1x, /missing@2x.png 2x" alt="С вариантами" width="10" height="10">
<a href="/page2">Вторая</a>
<p>{text}</p></body></html>"""
LONG_ALT = "Очень длинное описание картинки " * 5
TEXT = " ".join(["слово"] * 250)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype, length=True, cache=""):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if cache:
            self.send_header("Cache-Control", cache)
        if length:
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:  # размер заранее не сообщаем — отдаём кусками (chunked)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(0, len(body), 16384):
                part = body[i:i + 16384]
                self.wfile.write(b"%x\r\n%s\r\n" % (len(part), part))
            self.wfile.write(b"0\r\n\r\n")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/robots.txt":
            return self.send(200, b"User-agent: *\n", "text/plain")
        if p in ("/", "/page2"):
            body = HTML.replace("{long}", LONG_ALT).replace("{text}", TEXT)
            if p == "/page2":
                body = body.replace('<a href="/page2">Вторая</a>', '<a href="/">Главная</a>')
            return self.send(200, body.encode(), "text/html; charset=utf-8")
        if p == "/app.js":
            return self.send(200, JS, "application/javascript")
        if p == "/fake.jpg":  # вместо картинки — HTML-страница
            return self.send(200, b"<html><body>not an image</body></html>", "text/html")
        if p == "/chunked.png":
            return self.send(200, FILES[p], "image/png", length=False, cache="no-cache")  # кеширование: плохо
        if p in FILES:  # картинки кешируются на год — хорошо; app.js без указаний — плохо
            return self.send(200, FILES[p], "image/png", cache="public, max-age=31536000")
        return self.send(404, b"not found", "text/plain")


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
