"""Автотест проверки безопасности (04.10.2026, seocrawler/security.py и checks/exposed_files.py): маленький сайт
на этом компьютере с открытым .env.local, копией wp-config, списком файлов папки и сервером, который сообщает
старый PHP. Проверяем, что всё найдено, что из .env взяты только ИМЕНА переменных (значений нигде нет) и что
страница «404 с кодом 200» не даёт ложной тревоги.
С 30.10.2026: cookie сессии без HttpOnly, сайт на WordPress (логин admin через /wp-json/wp/v2/users и /?author=1,
открытый xmlrpc.php, версия в мета-теге generator), старый jQuery и скрипт с домена, которого нет в DNS."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import security as S  # noqa: E402

SECRET_VALUE = "s3cr3t-Value-42"
FILES = {
    "/.env.local": ("text/plain", f"APP_NAME=shop\nDB_PASSWORD={SECRET_VALUE}\nMAIL_PASSWORD={SECRET_VALUE}\n"
                                  f"STRIPE_SECRET_KEY={SECRET_VALUE}\n"),
    "/wp-config.php.bak": ("text/plain", "<?php\ndefine( 'DB_NAME', 'shop' );\ndefine( 'DB_PASSWORD', 'x' );\n"),
    "/uploads/": ("text/html", "<html><head><title>Index of /uploads</title></head><body>a.pdf</body></html>"),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/?author=1":   # WordPress: переход на страницу автора выдаёт логин
            self.send_response(301)
            self.send_header("Location", "http://127.0.0.1:8771/author/admin/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        cookie = False
        if self.path == "/":
            body, ctype = ('<html><head><meta name="generator" content="WordPress 6.4.2"></head><body><h1>Главная</h1>'
                           '<link rel="stylesheet" href="/wp-content/themes/a/style.css"></body></html>'), "text/html"
            cookie = True
        elif self.path == "/wp-json/wp/v2/users":
            body, ctype = json.dumps([{"id": 1, "slug": "admin", "name": "Admin"}]), "application/json"
        elif self.path == "/xmlrpc.php":
            body, ctype = "XML-RPC server accepts POST requests only.", "text/plain"
        elif self.path in FILES:
            ctype, body = FILES[self.path]
        else:  # «не найдено», но с кодом 200 — ложной тревоги быть не должно
            body, ctype = "<html><body>Страница не найдена</body></html>", "text/html"
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Server", "Apache/2.4.29 (Ubuntu)")
        self.send_header("X-Powered-By", "PHP/7.4.3")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", "PHPSESSID=abc123; path=/")
            self.send_header("Set-Cookie", "theme=dark; path=/; SameSite=Lax")
        self.end_headers()
        self.wfile.write(b)


fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


srv = ThreadingHTTPServer(("127.0.0.1", 8771), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    sec = S.check("http://127.0.0.1:8771/", None, True, log=lambda *a: None,
                  ext=[("https://cdn.clayler-test-gone.invalid/lib.js", "http://127.0.0.1:8771/")],
                  libs=["http://127.0.0.1:8771/js/jquery-1.12.4.min.js", "http://127.0.0.1:8771/js/jquery-3.7.1.min.js"])
finally:
    srv.shutdown()

found = {f["url"].split("8771", 1)[1]: f["what"] for f in sec["found"]}
check(set(found) == set(FILES), f"найдено: {found}")
keys = sec["env_keys"].get("http://127.0.0.1:8771/.env.local")
check(keys == ["DB_PASSWORD", "MAIL_PASSWORD", "STRIPE_SECRET_KEY"], f"имена из .env: {keys}")
check(SECRET_VALUE not in json.dumps(sec), "значение пароля из .env попало в результат")
check(sec["headers"].get("x-content-type-options") == "nosniff" and not sec["https"], f"заголовки: {sec['headers']}")
vs = S.versions(sec["headers"])
check(sec["set_cookie"] == [("PHPSESSID", ["HttpOnly", "SameSite"], True)], f"cookie: {sec['set_cookie']}")
check(sec["wp"]["users"] and all(u["logins"] == ["admin"] for u in sec["wp"]["users"]) and len(sec["wp"]["users"]) == 2
      and sec["wp"]["xmlrpc"].endswith("/xmlrpc.php"), f"WordPress: {sec.get('wp')}")
check(sec["generator"] == "WordPress 6.4.2", f"generator: {sec.get('generator')}")
check([x[2] for x in sec["libs"]] == ["1.12.4"], f"jQuery: {sec['libs']}")
check([x[0] for x in sec["dead_hosts"]] == ["cdn.clayler-test-gone.invalid"], f"мёртвые домены: {sec['dead_hosts']}")
check(len(vs) == 2 and "не получает" in vs[1][1] and "не получает" not in vs[0][1], f"версии: {vs}")
check(S.versions({"server": "nginx", "x-powered-by": "PHP/8.3.1"}) == [("X-Powered-By: PHP/8.3.1",
      "версия видна всем - по ней подбирают известные уязвимости")], "PHP 8.3 - не устаревший")


class Ctx:  # проблемы из найденного — через ту же проверку, что в отчёте
    issues = []

    class store:
        @staticmethod
        def get_meta(k, d=None):
            return {"security": sec}.get(k, d)

    @staticmethod
    def add(key, sev, cat, title, why, fix, columns, rows, page_col=0):
        if rows:
            Ctx.issues.append((key, sev, rows))


from seocrawler.analyze.checks import exposed_files  # noqa: E402
exposed_files.run(Ctx)
got = {k: (sev, rows) for k, sev, rows in Ctx.issues}
check(len(got.get("exposed_files", ("", []))[1]) == 2, f"служебные файлы: {got.get('exposed_files')}")
check(any("DB_PASSWORD" in r[1] for r in got["exposed_files"][1]), "в строке про .env нет имён переменных")
check(got.get("dir_listing", ("", []))[1] == [["http://127.0.0.1:8771/uploads/"]], f"папки: {got.get('dir_listing')}")
check("server_versions" in got and got["server_versions"][0] == "warning", "старый PHP - предупреждение")
check("security_headers" not in got, "заголовки защиты для http-сайта не проверяются (нужен https)")
check(got.get("cookie_flags", ("", []))[0] == "warning" and got["cookie_flags"][1][0][:3] == ["PHPSESSID", "HttpOnly, SameSite", "да"],
      f"cookie: {got.get('cookie_flags')}")
check(len(got.get("wp_users", ("", []))[1]) == 2 and "wp_xmlrpc" in got, f"WordPress: {got.get('wp_users')}")
check(got.get("dead_script_domain", ("", []))[0] == "critical", f"мёртвый домен: {got.get('dead_script_domain')}")
check(got.get("old_jquery", ("", []))[1][0][2] == "1.12.4" if "old_jquery" in got else False, "старый jQuery")
check(any("generator" in r[0] for r in got["server_versions"][1]), "версия WordPress в «Сервер сообщает версии»")
html = S.html_block(sec, [])
check("DB_PASSWORD" in html and SECRET_VALUE not in html and "—" not in html, "блок «Проверка безопасности»")

# «домен можно купить» - только если DNS точно ответил «такого имени нет» и нет самого домена (проверка кода 04.11):
# удалённый поддомен живого домена и временный сбой DNS - не находка. DNS подменён, без сети
import socket  # noqa: E402
real_dns = socket.getaddrinfo


def fake_dns(host, *a, **k):
    if host in ("site.ru", "client.ru", "cdn.ok.ru"):
        return [()]
    if host == "flaky.net":
        raise socket.gaierror(getattr(socket, "EAI_AGAIN", 11002), "временный сбой")
    raise socket.gaierror(socket.EAI_NONAME, "такого имени нет")


socket.getaddrinfo = fake_dns
try:
    dh = S.dead_hosts([("https://old-cdn.client.ru/a.js", "/"), ("https://flaky.net/b.js", "/"),
                       ("https://gone-shop.ru/c.js", "/"), ("https://cdn.ok.ru/d.js", "/")], "site.ru")
finally:
    socket.getaddrinfo = real_dns
check([x[0] for x in dh] == ["gone-shop.ru"], f"мёртвые домены (поддомен живого, сбой DNS): {dh}")
# стили и скрипты при обходе не собирались - «нет мёртвых доменов» и «jQuery не найден» не зелёные, а «не проверялось»
rows = {n: (ok, d) for ok, n, d in S.summary_rows({"set_cookie": [], "headers": {}, "https": True,
                                                    "res_checked": False}, [])}
check(rows["Скрипты и стили с несуществующих доменов"][0] is None and rows["Старый jQuery (до 3.5)"][0] is None
      and rows["Флаги защиты у cookie"][0] is True, f"без стилей и скриптов: {rows}")
check("не проверялось" in S.html_block({"set_cookie": [], "headers": {}, "https": True, "res_checked": False}, []),
      "в блоке нет «не проверялось»")

if fails:
    print("ОШИБКИ в проверке безопасности:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ безопасность: служебные файлы, имена из .env без значений, списки папок, версии, заголовки, cookie, "
      "логины WordPress, xmlrpc, старый jQuery, скрипты с несуществующих доменов")
