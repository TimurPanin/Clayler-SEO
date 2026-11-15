"""Автотест хостинг-платформ (seocrawler/site_tech.py PLATFORMS, checks caching/exposed_files/mirrors):
сайт на GitHub Pages (данные как у timurpanin.ru) узнаётся как «GitHub Pages», а не «скрыт за Fastly»; кеш и заголовки
защиты там - «ограничение хостинга» с важностью «Замечание» и без работ в смете; /index.html с canonical на главную -
не «Критично». Обычный хостинг - всё как раньше. Без интернета."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import site_tech as T  # noqa: E402
from seocrawler.analyze.checks import caching, exposed_files, mirrors  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


GH = {"checked_at": "2026-10-05", "host": "timurpanin.ru", "ips": ["185.199.108.153", "185.199.109.153"],
      "ns": ["patrick.ns.cloudflare.com"], "mx": [], "dns_provider": "Cloudflare",
      "net": {"ip": "185.199.108.153", "rdns": "cdn-185-199-108-153.github.com", "asn": 54113,
              "holder": "FASTLY - Fastly, Inc.", "net": "US-GITHUB-20170413", "org": "GitHub Admin"},
      "home": {"url": "https://timurpanin.ru/", "status": 200, "server": "GitHub.com"}, "engines": [], "tech": [],
      "shields": [{"name": "Fastly", "how": "x-fastly-request-id: 1"}], "hosting": ""}
PLAIN = {**GH, "ips": ["5.101.152.1"], "dns_provider": "Beget", "hosting": "Beget",
         "net": {"ip": "5.101.152.1", "rdns": "srv1.beget.com", "holder": "Beget LLC"},
         "home": {"url": "https://a.ru/", "status": 200, "server": "nginx"}, "shields": []}

# ---- узнаём платформу по сохранённым данным: заголовок Server, имя сервера, блок адресов, IP
check((T.platform(GH) or {}).get("name") == "GitHub Pages", "GitHub Pages не узнан")
only_ip = {"ips": ["185.199.111.153"], "home": {}, "net": {}}
check((T.platform(only_ip) or {}).get("name") == "GitHub Pages", "GitHub Pages не узнан по одному IP")
check((T.platform({"home": {"server": "Netlify"}}) or {}).get("name") == "Netlify", "Netlify не узнан")
check((T.platform({"platform_headers": {"x-vercel-id": "fra1::x"}}) or {}).get("name") == "Vercel", "Vercel не узнан")
check((T.platform({"engines": [{"name": "Tilda"}]}) or {}).get("name") == "Tilda", "Tilda не узнана")
check(T.platform(PLAIN) is None, "обычный хостинг принят за платформу")
rows = {r[0]: r for r in T.rows(GH)}
check(rows["Хостинг"][1] == "GitHub Pages", f"хостинг: {rows['Хостинг'][1]}")
check("отдельно её не подключали" in rows["Защита и CDN"][2], "Fastly показан как отдельная защита")
check(rows["Движок сайта"][1] == "нет, готовые HTML-файлы", f"движок: {rows['Движок сайта'][1]}")
check(T.rows(PLAIN)[0][1] == "не определён" and {r[0]: r for r in T.rows(PLAIN)}["Хостинг"][1] == "Beget",
      "обычный хостинг показывается иначе, чем раньше")


# ---- проверки отчёта на маленькой базе
def make_db(cache):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE urls (url TEXT, internal INT, kind TEXT)")
    db.execute("CREATE TABLE pages (url TEXT, status INT, content_type TEXT, cache_control TEXT, canonical TEXT)")
    db.execute("CREATE TABLE links (src TEXT, dst TEXT, anchor TEXT, kind TEXT)")   # «Ссылки на копию сайта» (mirrors.py)
    db.executemany("INSERT INTO urls VALUES (?,1,?)", [("https://timurpanin.ru/", "page"),
                                                       ("https://timurpanin.ru/a.css", "resource")])
    db.executemany("INSERT INTO pages VALUES (?,200,?,?,?)", [
        ("https://timurpanin.ru/", "text/html", "max-age=600", "https://timurpanin.ru/"),
        ("https://timurpanin.ru/a.css", "text/css", cache, None)])
    return db


MIRRORS = {"main": "https://timurpanin.ru/", "variants": [
    {"variant": "https://www.timurpanin.ru/", "chain": [["https://www.timurpanin.ru/", 301], ["https://timurpanin.ru/", 200]]},
    {"variant": "https://timurpanin.ru/index.html", "chain": [["https://timurpanin.ru/index.html", 200]]}]}
SEC = {"https": True, "url": "https://timurpanin.ru/", "headers": {"server": "GitHub.com"}, "found": []}


def run(st, mirr=MIRRORS, cache="max-age=600"):
    got = {}
    meta = {"site_tech": st, "mirrors": mirr, "security": SEC}
    db = make_db(cache)

    class Ctx:
        class store:
            get_meta = staticmethod(lambda k, d=None: meta.get(k, d))
        store.db = db
        add = staticmethod(lambda key, sev, cat, title, why, fix, cols, rows, page_col=0:
                           rows and got.__setitem__(key, (sev, fix, rows)))
    Ctx.db = db
    for m in (caching, exposed_files, mirrors):
        m.run(Ctx)
    return got


g = run(GH)
check(g.get("no_cache", ("",))[0] == "notice" and T.LIMIT in g["no_cache"][1], f"кеш на GitHub Pages: {g.get('no_cache')}")
check("Cloudflare" in g["no_cache"][1], "нет подсказки про Cloudflare при DNS у Cloudflare")
sh = g.get("security_headers", ("", "", []))
check(sh[0] == "notice" and T.LIMIT in sh[1], f"заголовки на GitHub Pages: {sh[:2]}")
meta_col = {r[0]: r[2] for r in sh[2]}
check(meta_col.get("Referrer-Policy", "").startswith("можно") and meta_col.get("X-Frame-Options", "").startswith("нельзя")
      and meta_col.get("HSTS", "").startswith("нельзя"), f"колонка «мета-тегом»: {meta_col}")
check("mirror_dup" not in g and g.get("mirror_canonical", ("",))[0] == "notice", f"index.html с canonical: {g.keys()}")
g2 = run(GH, mirr={**MIRRORS, "variants": [{**MIRRORS["variants"][1], "canonical": ""}]})
check(g2.get("mirror_dup", ("",))[0] == "critical" and "canonical" in g2["mirror_dup"][1],
      f"index.html без canonical на GitHub Pages: {g2.get('mirror_dup')}")
p = run(PLAIN, mirr={**MIRRORS, "variants": [{**MIRRORS["variants"][0], "chain": [["https://www.timurpanin.ru/", 200]]}]})
check(p.get("no_cache", ("",))[0] == "warning" and T.LIMIT not in p["no_cache"][1], "кеш на обычном хостинге")
check(p.get("security_headers", ("",))[0] == "warning", "заголовки на обычном хостинге")
check(p.get("mirror_dup", ("",))[0] == "critical" and "301" in p["mirror_dup"][1], "www без редиректа - критично")
# варианта нет в DNS (за него ответил прокси VPN, обход пометил «нет в DNS») - не находка; вариант есть, но отвечает
# 403 или 5xx - находка с понятной причиной, а не «ведёт не на главный адрес»
none = run(PLAIN, mirr={**MIRRORS, "variants": [{"variant": "http://www.timurpanin.ru/",
                                                "chain": [["http://www.timurpanin.ru/", "нет в DNS (ответил прокси)"]]}]})
check("mirror_redirect" not in none and "mirror_dup" not in none, f"несуществующий вариант - находка: {none.keys()}")
bad = run(PLAIN, mirr={**MIRRORS, "variants": [{"variant": f"http://www{i}.timurpanin.ru/", "chain": [[f"http://www{i}.timurpanin.ru/", c]]}
                                               for i, c in enumerate((403, 500))]})
why = [r[1] for r in bad.get("mirror_redirect", ("", "", []))[2]]
check(why == ["отвечает ошибкой 403 вместо редиректа на главный адрес", "отвечает ошибкой 500 вместо редиректа на главный адрес"],
      f"вариант с ошибкой: {why}")
wrong = run(PLAIN, mirr={**MIRRORS, "variants": [{"variant": "http://www.timurpanin.ru/", "chain": [
    ["http://www.timurpanin.ru/", 302], ["https://timurpanin.ru/", 200]]}]})
check("mirror_redirect" in wrong, "временный редирект варианта не найден")

from seocrawler import estimate  # noqa: E402


class I:  # noqa: E742
    def __init__(self, key, sev, fix):
        self.key, self.severity, self.fix, self.title, self.rows, self.sitewide, self.count_text = \
            key, sev, fix, "x", [1], True, "1"


works = estimate.build([I("no_cache", "notice", g["no_cache"][1]), I("no_cache", "warning", p["no_cache"][1])])
check(len(works) == 1, f"в смете работы по ограничению хостинга: {works}")

if fails:
    print("ОШИБКИ в хостинг-платформах:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ платформы: GitHub Pages и другие узнаются, ограничения хостинга - замечания, index.html с canonical не критично")
