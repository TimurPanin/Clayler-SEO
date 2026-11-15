"""Автотест: одна причина не размножается в отчёте лишними строками (без сети).
- Сертификат https не прошёл проверку (на части подключений, как timurpanin.ru): «Роботу и браузеру
  сайт отдаёт разное» не набирает строк «Браузеру: SSL: ошибка сертификата», склейка домена и проверка 404
  идут без проверки сертификата, а не пропадают (crawler/extra_passes.py _get, check_ua_diff).
- «Вариант адреса перенаправляет неправильно» на копию, которая сама открывается без редиректа, - помечено, что
  исправится вместе с ней (analyze/checks/mirrors.py).
- Орфография: слово, которое Спеллер считает опечаткой только в отдельной строке, а в предложении - нет, в отчёт
  не попадает; настоящая опечатка (и в кавычках) остаётся (speller.contexts, confirm).
Запуск: py -3 tests/проверить_сертификат_и_опечатки.py (и из проверить_всё.py)."""
import io
import json
import os
import sqlite3
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
from seocrawler import speller  # noqa: E402
from seocrawler.analyze.checks import mirrors  # noqa: E402
from seocrawler.crawler import extra_passes  # noqa: E402
from seocrawler.fetcher import Response  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


PAGE = (b"<html><head><title>Page</title><link rel=canonical href='https://site.test/'></head>"
        b"<body><h1>Head</h1><a href='/a'>a</a></body></html>")


class FakeFetcher:
    """verify=True - сертификат не проходит (ошибка SSL), verify=False - сайт отвечает."""
    def __init__(self, ua="", verify_ssl=True, **kw):
        self.user_agent, self.verify = ua, verify_ssl
        self.extra_headers, self.host_headers = {}, {}

    def fetch(self, url, **kw):
        if self.verify:
            return Response(url=url, error="SSL: ошибка сертификата")
        r = Response(url=url, status=200, headers={"content-type": "text/html"}, body=PAGE)
        return r


class GoodConn(FakeFetcher):
    """Робот по уже открытому удачному соединению: отвечает, хоть сертификат и плохой."""
    def fetch(self, url, **kw):
        return Response(url=url, status=200, headers={"content-type": "text/html"}, body=PAGE)


class Store:
    def __init__(self):
        self.meta = {}

    def set_meta(self, k, v):
        self.meta[k] = v

    def get_meta(self, k, default=None):
        return self.meta.get(k, default)


class Cfg:
    timeout, total_timeout, verify_ssl = 5, 10, True


class Crawl(extra_passes.ExtraPassesMixin):
    def __init__(self, fetcher):
        self.fetcher, self.insecure = fetcher, FakeFetcher(verify_ssl=False)
        self.store, self.cfg, self.auth = Store(), Cfg(), {}
        self.limiter = type("L", (), {"wait": lambda s: None})()

    def _sample_pages(self, n):
        return ["https://site.test/", "https://site.test/a"]

    def st(self, **kw):
        pass

    def pace(self, s):
        pass

    def stopped(self):
        return False

    def log(self, s):
        pass


extra_passes.Fetcher = FakeFetcher
# 1. робот отвечает, новый «браузер» попадает на плохой сертификат - различий нет
c = Crawl(GoodConn())
c.check_ua_diff()
ud = c.store.meta.get("ua_diff") or {}
check(ud.get("checked") == 2 and ud.get("diffs") == [], f"роботу и браузеру при плохом сертификате: {ud}")
# 2. сертификат не проходит всегда: склейка видит ответ 200, а не ошибку SSL
c = Crawl(FakeFetcher())
ch = c._follow("https://site.test/")
check(ch == [["https://site.test/", 200]], f"склейка при плохом сертификате: {ch}")
check(c._get("https://site.test/").ssl_note, "нет пометки «Сертификат не прошёл проверку»")

# 3. неправильный редирект на копию, которая сама открывается
got = {}


class Ctx:
    store = Store()

    def add(self, key, *a, **kw):
        got[key] = a[-1]


ctx = Ctx()
ctx.store.meta["mirrors"] = {"main": "https://site.test/", "variants": [
    {"variant": "http://site.test/", "chain": [["http://site.test/", 200]]},
    {"variant": "http://www.site.test/", "chain": [["http://www.site.test/", 301], ["http://site.test/", 200]]},
    {"variant": "https://www.site.test/", "chain": [["https://www.site.test/", 301], ["https://site.tes/", 200]]}]}
mirrors.run(ctx)
mr = {r[0]: r[1] for r in got.get("mirror_redirect", [])}
check("исправится вместе с ним" in mr.get("http://www.site.test/", ""), f"редирект на копию: {mr}")
check("исправится" not in mr.get("https://www.site.test/", "-"), f"обычный неправильный редирект: {mr}")

# 4. орфография: перепроверка в предложении
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE urls (url TEXT, internal INT, kind TEXT)")
db.execute("CREATE TABLE pages (url TEXT, status INT, indexable INT, blocks BLOB)")
text = "Доступ ко всем устройствам и пользователям сразу.\nВместо «предложенный» написано «предложеный» в заголовке."
db.execute("INSERT INTO urls VALUES ('https://site.test/', 1, 'page')")
db.execute("INSERT INTO pages VALUES ('https://site.test/', 200, 1, ?)", (zlib.compress(text.encode("utf-8")),))
errors = {"пользователям": ["пользователем"], "предложеный": ["предложенный"], "нигдеслова": ["x"]}
ctx_words = speller.contexts(db, errors)
# слово в коротких кавычках - пример или цитата, его не проверяем (с 25.10.2026, speller.unquoted): куска текста
# для него нет, а в проверке сайта оно и в ошибки не попадёт (site_words)
check("пользователям" in ctx_words.get("пользователям", "") and "предложеный" not in ctx_words,
      f"куски текста: {ctx_words}")
sent = []


def fake_urlopen(req, timeout=0):
    """Как Спеллер: «пользователям» - ошибка только в отдельной строке, слово в кавычках пропускает."""
    from urllib.parse import parse_qs
    lines = parse_qs(req.data.decode("utf-8"))["text"][0].split("\n")
    sent.extend(lines)
    out = []
    for ln in lines:
        for w in ("пользователям", "предложеный"):
            if w in ln and f"«{w}»" not in ln and (w != "пользователям" or ln == w):
                out.append({"word": w, "s": ["x"]})
    return io.BytesIO(json.dumps(out).encode("utf-8"))


speller.sysproxy.urlopen = fake_urlopen
kept = speller.confirm(errors, ctx_words)
check(sorted(kept) == ["нигдеслова", "предложеный"], f"после перепроверки: {sorted(kept)} (ушло: {sent})")

if fails:
    print("✗ сертификат и опечатки:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ сертификат и опечатки: плохой сертификат не размножается в «роботу и браузеру», склейка видит сайт, "
      "редирект на копию помечен, ложные опечатки убраны")
