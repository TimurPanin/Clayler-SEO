"""Автотест проверок взлома и мягких 404 (план развития, раздел 5, 21.10.2026). Тестовый сайт поднимается здесь же:
- спрятанная стилем ссылка на казино (hacked_hidden_links, критично), спрятанная ссылка на соцсеть, которая видна
  на той же странице (не в счёт);
- видимая ссылка «микрозайм онлайн» на чужой сайт (hacked_spam_links); тема самого сайта не в счёт;
- мягкие 404: «не найдена» в title, почти пустая страница с текстом «страница не найдена», страница с тем же
  title, что у заведомо несуществующего адреса (сервер на любой неизвестный адрес отвечает 200);
- вторая проверка: новая чужая ссылка сразу на всех страницах - в сравнении проверок («Новые ссылки на чужие сайты»).
Запуск: py -3 тест/проверить_взлом.py (и из проверить_всё.py)."""
import glob
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")   # тестовые сайты - мимо прокси VPN (в его исключениях только *.local)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = 8801
B = f"http://127.0.0.1:{PORT}"
STATE = {"second": False}   # вторая проверка: на всех страницах новая ссылка на чужой сайт

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


TEXT = ("Мы делаем мебель на заказ для кухни, спальни и гостиной. Замер бесплатно, доставка по городу, "
        "сборка в день доставки. ") * 6
PAGES = {
    "/": ("Мебель на заказ - фабрика", "Мебель на заказ",
          '<a href="/a">Кухни</a> <a href="/b">Шкафы</a> <a href="/c">Спальни</a> <a href="/d">Столы</a> '
          '<a href="/e">Стулья</a> <a href="/gone">Старый раздел</a> <a href="/empty">Акция</a> '
          '<a href="/old-item">Старый товар</a> <a href="/f">Шторы</a> <a href="https://vk.com/mebel">Мы ВКонтакте</a>'
          '<a href="/deleted-item">Удалённый товар</a> <a href="/real-item">Стол</a>'
          '<div style="display:none"><div><a href="https://casino-best.example/">онлайн казино</a></div>'
          '<a href="https://vk.com/mebel">вк</a></div>'),
    "/a": ("Кухни на заказ", "Кухни", '<a href="https://zaim-fast.example/go">микрозайм онлайн</a>'),
    "/b": ("Шкафы на заказ", "Шкафы",
          '<a href="https://developers.google.com/search/docs/specialty/ecommerce?hl=ru">Рекомендации по поисковой '
          'оптимизации для сайтов интернет-магазинов</a> <a href="https://blog.example/work">Мы упорно работаем</a>'),
    # кнопка «Поделиться» несёт адрес самого сайта со «спам-словом» - не взлом (thehome.ru, 01.11.2026)
    "/c": ("Спальни на заказ", "Спальни", f'<a href="https://vk.com/share.php?url={B}/promo/sex-on-the-beach/">ВК</a>'),
    # товар с таким названием: слово из title и H1 самой страницы в её ссылках - тема страницы, а не взлом
    "/f": ("Штора для ванной Ridder Sex on the Beach", "Штора Sex on the Beach",
           f'<a href="https://connect.ok.ru/offer?url={B}%2Ff%2F&title=Sex%20on%20the%20Beach">ОК</a>'),
    "/d": ("Столы на заказ", "Столы", ""),
    "/e": ("Стулья на заказ", "Стулья", ""),
    "/gone": ("Страница не найдена", "Ошибка 404", ""),
    # удалённый товар Битрикса (thehome.ru 01.11.2026): код 200, меню и текст на месте, title и H1 пустые, вместо товара
    # отдельная строка «Элемент не найден» - мягкая 404; «Раздел не найден» в блоке похожих на настоящем товаре - нет
    "/deleted-item": ("", "", "<div>Элемент не найден</div><h2>Похожие товары</h2><div>Раздел не найден</div>"),
    "/real-item": ("Стол дубовый купить", "Стол дубовый", "<h2>Похожие товары</h2><div>Раздел не найден</div>"),
}
FAKE = ("Ой, такого у нас нет", "Пусто", "")   # так сайт отвечает на любой неизвестный адрес - с кодом 200


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            body, ctype = b"User-agent: *\nAllow: /\n", "text/plain"
        else:
            if path == "/empty":
                title, h1, extra, text = "Акция месяца", "Акция", "", "Страница не найдена. Вернитесь на главную."
            else:
                title, h1, extra = PAGES.get(path, FAKE)
                text = TEXT if path in PAGES else "Здесь ничего нет."
            if STATE["second"]:
                extra += ' <a href="https://ads-spike.example/">Реклама</a>'
            nav = '<a href="/">Главная</a> <a href="/a">Кухни</a>'
            body = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title>'
                    f'<meta name="viewport" content="width=device-width"></head><body><nav>{nav}</nav>'
                    f'<h1>{h1}</h1><p>{text}</p>{extra}</body></html>').encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def crawl(env, tmp):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), B + "/", "--no-open", "--delay", "0",
                        "--no-exposed", "--no-external"], env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=400)
    folders = sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{PORT}_*")))
    if r.returncode != 0 or not folders:
        print("✗ взлом: тестовый сайт не проверился\n" + (r.stdout + r.stderr)[-1500:])
        sys.exit(1)
    return folders[-1]


def words():
    """Спам-слова: с начала слова, но слитные названия ловятся (23.10.2026)."""
    from seocrawler.analyze.checks.hacked_links import _what
    for t in ("интернет-магазинов", "упорно работаем", "spin-up"):
        check(not _what(t), f"«{t}» принято за спам: {_what(t)}")
    for t in ("pinupbet.com", "вулканказино", "азино 777", "vulkancasino.com"):
        check(_what(t), f"«{t}» не найдено как спам")
    # адрес своего сайта внутри чужой ссылки (кнопки «Поделиться») и граница домена (проверка кода 01.11.2026)
    from seocrawler.analyze.checks.hacked_links import _own_url_rx, _suspect
    rx = _own_url_rx("https://www.mysite.ru/")
    for href, anchor, bad in (
            ("https://vk.com/share.php?url=https://mysite.ru/catalog/sex-on-the-beach/", "ВК", False),
            ("https://connect.ok.ru/offer?url=https%3A%2F%2Fmysite.ru%2Fp%2F&title=Sex%20on%20the%20Beach", "ОК", False),
            ("https://mysite.ru.casino-xxx.com/porn", "", True),        # чужой домен, начинается как наш
            ("https://mysite.ru-sex.com/", "", True),
            ("https://casino.example/?ref=https://mysite.ru/", "", True),   # наш адрес в параметре - сам сайт казино
            ("https://partner.example/go", "онлайн казино", True),          # спам в тексте ссылки
            ("https://t.me/share?url=https://mysite.ru:8443/sex-on-the-beach/", "", False),   # свой сайт с портом
            ("https://vk.com/share.php?url=https://shop.mysite.ru/sex-on-the-beach/", "", False),   # свой поддомен
            ("https://vk.com/share.php?url=https://mysite.ru./sex-on-the-beach/", "", False),   # точка в конце имени
            ("https://VK.com/share.php?url=HTTPS://MYSITE.RU/Sex-On-The-Beach/", "", False),    # заглавные буквы
            ("https://evil-mysite.ru/sex", "", True),                       # «приставка» к имени - чужой сайт
            ("https://notmysite.ru/porn", "", True),
            ("https://mysite.ru.evil.org/casino", "", True)):
        got = bool(_suspect(href, anchor, rx, set()))
        check(got == bad, f"ссылка {href} «{anchor}»: подозрительная - {got}, ждали {bad}")
    # Tilda на узком экране сдвигает видимые блоки на left:-146px - не спрятано; left:-9999px - спрятано
    from seocrawler.parser import parse_html
    p = parse_html('<div style="top: 511px; left: -146px;"><a href="https://ispring.ru/">ispring</a></div>'
                   '<div style="position:absolute;left:-9999px"><a href="https://casino.example/">x</a></div>'.encode())
    hid = {lk["href"]: lk.get("hidden") for lk in p["links"]}
    check(not hid.get("https://ispring.ru/") and hid.get("https://casino.example/"), f"сдвиг за экран: {hid}")
    # незакрытый спрятанный <li>/<p>/<td> закрывается следующим тегом - ссылки ниже не спрятаны (24.10.2026)
    p = parse_html('<ul><li style="display:none">x<li><a href="https://a.example/">a</a></ul>'
                   '<p style="display:none">x<div><a href="https://b.example/">b</a></div>'
                   '<table><tr><td style="display:none">x<td><a href="https://c.example/">c</a></table>'
                   '<div style="display:none"><span>x<a href="https://casino.example/">x</a></div>'
                   '<a href="https://d.example/">d</a>'.encode())
    hid = {lk["href"]: lk.get("hidden") for lk in p["links"]}
    check(hid == {"https://a.example/": False, "https://b.example/": False, "https://c.example/": False,
                  "https://casino.example/": True, "https://d.example/": False}, f"незакрытые спрятанные теги: {hid}")


def main():
    words()
    tmp = tempfile.mkdtemp(prefix="clayler-hack-")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1", CLAYLER_NO_SPEED_LAB="1", CLAYLER_REPORTS=tmp)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        urllib.request.urlopen(B + "/", timeout=5)
        first = crawl(env, tmp)
        time.sleep(1.1)   # у второй проверки другое время в имени папки
        STATE["second"] = True
        second = crawl(env, tmp)
    finally:
        srv.shutdown()

    os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
    from seocrawler.storage import Store
    from seocrawler.analyze import analyze
    store = Store(os.path.join(first, "crawl.db"))
    issues = {i.key: i for i in analyze(store)[0]}

    hid = issues.get("hacked_hidden_links")
    check(hid is not None, "hacked_hidden_links не сработала на ссылке в блоке display:none")
    if hid:
        rows = [r for r in hid.rows]
        check(any("casino-best.example" in r[1] and "казино" in r[3] for r in rows),
              f"спрятанной ссылки на казино нет в таблице: {rows}")
        check(not any("vk.com" in r[1] for r in rows), "спрятанная ссылка на ВК в счёт, хотя она видна на странице")
        check(hid.severity == "critical",f"спрятанная ссылка на казино не критична: {hid.severity}")
    spam = issues.get("hacked_spam_links")
    check(spam is not None and any("zaim-fast.example" in r[1] for r in spam.rows),
          "hacked_spam_links не нашла видимую ссылку «микрозайм онлайн»")
    if spam:
        check(not any("casino-best" in r[1] for r in spam.rows), "спрятанная ссылка повторена в видимых спам-ссылках")
        # «азино» внутри «магазинов», «порно» внутри «упорно» - не спам (ложное срабатывание 23.10.2026)
        check(not any("vk.com/share" in r[1] or "ok.ru" in r[1] for r in spam.rows),
              "кнопка «Поделиться» с адресом своего сайта и названием товара принята за взлом: "
              + str([r[1] for r in spam.rows]))
        check(not any("developers.google.com" in r[1] or "blog.example" in r[1] for r in spam.rows),
              f"обычные ссылки приняты за спам: {[r for r in spam.rows if 'zaim-fast' not in r[1]]}")

    soft = issues.get("soft404")
    why = {r[0].replace(B, ""): r[3] for r in (soft.rows if soft else [])}
    check("title или H1" in why.get("/gone", ""), f"мягкая 404 по title не найдена: {why}")
    check("почти пустая" in why.get("/empty", ""), f"мягкая 404 по тексту не найдена: {why}")
    check("несуществующей" in why.get("/old-item", ""), f"мягкая 404 по виду несуществующей страницы: {why}")
    check("«Элемент не найден»" in why.get("/deleted-item", ""), f"удалённый товар «Элемент не найден» не найден: {why}")
    check("/real-item" not in why, f"настоящий товар с пустым блоком «Раздел не найден» принят за мягкую 404: {why}")
    check(not any(u in why for u in ("/", "/a", "/b")), f"обычные страницы в мягких 404: {why}")

    # сайт сам о займах (тема в title большей части страниц) - ссылки про займы не взлом
    db = sqlite3.connect(os.path.join(first, "crawl.db"))
    db.execute("UPDATE pages SET title = title || ' - микрозайм онлайн'")
    db.commit()
    db.close()
    store = Store(os.path.join(first, "crawl.db"))
    issues = {i.key: i for i in analyze(store)[0]}
    check("hacked_spam_links" not in issues, "ссылка про займы на сайте о займах считается взломом")

    # вторая проверка: на всех страницах появилась ссылка на ads-spike.example
    cmp_html = os.path.join(second, "сравнение.html")
    doc = open(cmp_html, encoding="utf-8").read() if os.path.exists(cmp_html) else ""
    check("Новые ссылки на чужие сайты" in doc and "ads-spike.example" in doc,
          "в сравнении проверок нет блока о новой чужой ссылке на всех страницах")
    check("vk.com" not in doc.split("Новые ссылки на чужие сайты")[-1].split("</table>")[0],
          "ссылка на ВК (была и в прошлый раз) попала в новые чужие ссылки")

    # строка «Товар не найден» из шаблона (скрытое окно быстрого просмотра) есть и на нормальных страницах - это не
    # признак пустышки; у удалённых товаров thehome.ru строки на нормальных страницах нет (проверка кода 04.11.2026)
    import zlib
    from seocrawler.analyze.checks import content as CT

    def pg(u, h1, lines):
        return {"url": u, "h1": h1, "blocks": zlib.compress("\n".join(lines).encode("utf-8"))}
    normal = [pg(f"/n{i}", "Товар", ["Описание товара", "Товар не найден"]) for i in range(3)]
    own = {p["url"]: (80,) for p in normal}
    check(CT._template_nf(normal + [pg("/thin", "Товар", ["Товар не найден"])], own) == {"Товар не найден"},
          "строка шаблона «Товар не найден» не узнана")
    real = [pg(f"/r{i}", "Товар", ["Описание товара"]) for i in range(3)] + [pg("/del", "", ["Элемент не найден"])]
    check(CT._template_nf(real, {p["url"]: (80,) for p in real[:3]}) == set(),
          "строка удалённого товара принята за шаблон")

    if fails:
        print("✗ взлом и мягкие 404:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ взлом и мягкие 404: спрятанные и спам-ссылки находятся (тема сайта и видимые соцсети не в счёт), "
          "мягкие 404 по title, тексту и виду несуществующей страницы, новая чужая ссылка в сравнении")


main()
