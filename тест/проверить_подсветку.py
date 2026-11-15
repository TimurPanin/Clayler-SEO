"""Автотест страницы с обведённой проблемой (window/highlight.py, 23.10.2026). Тестовый сайт и окно поднимаются здесь:
- /api/show на адресе окна (127.0.0.1) переводит на show.localhost, а show.localhost отдаёт только /api/show
  (скрипты чужой страницы не достают до кнопок окна);
- в копии страницы есть <base> на настоящий адрес и скрипт подсветки, своя CSP сайта убрана;
- в браузере (если есть playwright) обведены: спрятанная стилем ссылка на казино (и показана), битая ссылка
  на Telegram по href, заголовок по тексту; несуществующее - «Не нашёл».
Запуск: py -3 тест/проверить_подсветку.py (и из проверить_всё.py)."""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
SITE, WIN = 0, 0   # порты - в main()
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


PAGE = ('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
        'content="script-src \'none\'"><title>Тест</title></head><body><h1>Мебель на заказ</h1>'
        '<p>Пишите нам: <a href="tg://resolve?Mebel_bot&amp;start=x">Telegram</a></p>'
        '<p>' + 'Делаем мебель на заказ: кухни и шкафы, мебели много, заказ онлайн. ' * 4 + '</p>'
        '<div style="display:none"><a href="https://casino-best.example/">онлайн казино</a></div>'
        '<img src="/img/sofa.jpg"><script>throw new Error("тест-ошибка")</script>'
        # для правок 01.11.2026 (разбор отчёта thehome.ru): ссылка на саму страницу, логотип-ссылка на главную и
        # картинка с адресом главной, поиск и форма заявки, остаток шаблона, слово с русской «С»
        '<a id="self" href="/mebel">Мебель</a> <a id="logo" href="/">Логотип</a> <img id="badimg" src="/" alt="">'
        '<form id="search" role="search"><input type="search" name="q"></form>'
        '<form id="lead"><input type="tel" name="phone"><button>Оставить заявку</button></form>'
        '<p id="junk">Коллекция: Chrome#Classic#Vanda II</p>'
        '<h2 id="mixed">Унитаз Сeramicplus белый</h2>'
        # 05.11.2026 (thehome.ru): ссылка-обёртка вокруг карточки товара - у самой <a> рамка нулевой высоты
        '<a id="card" href="/product/x/"><div style="width:300px;height:120px">Карточка товара</div></a>'
        '</body></html>').encode()


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(url, host=None, method="GET", origin=None):
    hdr = {**({"Host": host} if host else {}), **({"Origin": origin} if origin else {})}
    req = urllib.request.Request(url, method=method, data=b"{}" if method == "POST" else None, headers=hdr)
    try:
        # без прокси VPN: окно и тестовый сайт - на этом компьютере (через прокси - 502, 28.10.2026)
        r = urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler({})).open(req, timeout=20)
        return r.status, r.headers, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")


def main():
    os.environ["CLAYLER_NO_USER_SETTINGS"] = "1"
    os.environ["CLAYLER_SHOW_LOCAL"] = "1"   # тестовый сайт на 127.0.0.1 (обычно адреса компьютера закрыты)
    from seocrawler.window.server import H
    global SITE, WIN   # свободные порты от системы: фиксированный может оказаться занят чужим соединением
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), Site), ThreadingHTTPServer(("127.0.0.1", 0), H)]
    SITE, WIN = (srv.server_address[1] for srv in servers)
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    page = f"http://127.0.0.1:{SITE}/mebel"
    find = ["tg://resolve?Mebel_bot&start=x", "https://casino-best.example/", "Мебель на заказ"]
    q = f"/api/show?url={quote(page)}&find={quote(json.dumps(find))}"
    show = f"show.localhost:{WIN}"
    try:
        code, hdr, _ = get(f"http://127.0.0.1:{WIN}{q}")
        check(code == 302 and (hdr.get("Location") or "").startswith(f"http://{show}/api/show"),
              f"/api/show на адресе окна не переводит на show.localhost: {code} {hdr.get('Location')}")
        code, _, doc = get(f"http://127.0.0.1:{WIN}/api/status", host=show)
        check(code == 404 and "копия страницы" in doc, f"show.localhost отдаёт страницы окна: {code} {doc[:100]}")
        check(get(f"http://127.0.0.1:{WIN}/api/delete", host=show, method="POST")[0] == 403,
              "show.localhost принимает действия окна")
        # действия окна с чужого Origin (скрипт копии шлёт прямо на 127.0.0.1) - отказ; со своего - как обычно
        check(get(f"http://127.0.0.1:{WIN}/api/delete", method="POST", origin=f"http://{show}")[0] == 403,
              "окно принимает действие со страницы show.localhost")
        check(get(f"http://127.0.0.1:{WIN}/api/labels", method="POST", origin=f"http://127.0.0.1:{WIN}")[0] != 403,
              "окно отказывает своей же странице")
        # копия не открывает само окно (его отчёты) и локальную сеть
        code, _, doc = get(f"http://127.0.0.1:{WIN}/api/show?url={quote(f'http://127.0.0.1:{WIN}/api/status')}",
                           host=show)
        check("этого компьютера" in doc and '"ok"' not in doc, f"копия открыла страницу окна: {doc[:200]}")
        from seocrawler.window import highlight
        os.environ["CLAYLER_SHOW_LOCAL"] = "0"
        check(highlight.closed(page), f"без разрешения открывается адрес этого компьютера: {page}")
        os.environ["CLAYLER_SHOW_LOCAL"] = "1"
        code, _, doc = get(f"http://127.0.0.1:{WIN}/api/show?url={quote('http://192.168.1.1/')}", host=show)
        check("локальной сети" in doc, f"копия открывает адреса локальной сети: {doc[:200]}")
        code, _, doc = get(f"http://127.0.0.1:{WIN}{q}", host=show)
        check(code == 200 and f'<base href="{page}">' in doc, f"в копии страницы нет <base>: {code} {doc[:200]}")
        check("clayler-show" in doc and "Mebel_bot" in doc, "в копии страницы нет скрипта подсветки")
        check("Content-Security-Policy" not in doc, "CSP сайта осталась и запретит скрипт подсветки")
        check("<script>" in doc and "</script>" in doc.split("<script>", 1)[1].split("<title>")[0],
              "скрипт подсветки разорван")
        code_checks()
        # оценка и готовые варианты страницы - из заголовки.csv последней проверки сайта (05.11.2026)
        import tempfile
        from seocrawler import window as W
        old_reports, W.REPORTS = W.REPORTS, tempfile.mkdtemp(prefix="clayler-hl-")
        for d, sug in (("2026-10-01_10-00-00", "Старый вариант"), ("2026-11-05_10-00-00", "Мебель на заказ в Москве | Тест")):
            os.makedirs(os.path.join(W.REPORTS, f"127.0.0.1_{SITE}_{d}"))
            with open(os.path.join(W.REPORTS, f"127.0.0.1_{SITE}_{d}", "заголовки.csv"), "w", encoding="utf-8-sig") as fh:
                fh.write("Адрес;Что не так;Title сейчас;Предлагаю title;Description сейчас;Предлагаю description;"
                         "H1 сейчас;Предлагаю H1\n"
                         f'{page};"title: короткий (4 симв.); описание: нет описания";Тест;{sug};;Мебель на заказ: кухни '
                         "и шкафы.;Мебель на заказ;Мебель на заказ\n")
            open(os.path.join(W.REPORTS, f"127.0.0.1_{SITE}_{d}", "crawl.db"), "wb").close()
        got = highlight.suggest_row(page)
        check(got.get("title") == "Мебель на заказ в Москве | Тест" and got.get("when") == "05.11.2026"
              and "h1" not in got and "title: короткий (4 симв.)" in got.get("what", []),
              f"оценка страницы из последней проверки: {got}")
        # в новой проверке менять нечего (заголовки.csv нет) - оценка старой проверки не показывается
        newest = os.path.join(W.REPORTS, f"127.0.0.1_{SITE}_2026-11-06_10-00-00")
        os.makedirs(newest)
        open(os.path.join(newest, "crawl.db"), "wb").close()
        check(highlight.suggest_row(page) == {}, f"показана оценка из старой проверки: {highlight.suggest_row(page)}")
        import shutil
        shutil.rmtree(newest)   # дальше в браузере - снова проверка 05.11
        try:
            _browser(f"http://{show}{q}")
        finally:
            W.REPORTS = old_reports
    finally:
        for s in servers:
            s.shutdown()
    if fails:
        print("✗ подсветка проблемы:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ подсветка проблемы: копия страницы на show.localhost, кнопки окна оттуда закрыты, обведены ссылка "
          "по href (спрятанная - показана) и заголовок по тексту")


def code_checks():
    """То, чего не видно на странице, - строками кода с номерами (23.10.2026): лишний тег в <head>, одинаковые id,
    пустой og:description; «[Р]ассмотрение (латинская Р)» из отчёта ищется как само слово."""
    from seocrawler.window import highlight as h
    from seocrawler.report import SHOW_JS
    doc = ('<html>\n<head>\n<title>T</title>\n<meta property="og:description" content="">\n<script>var a="<div>"</script>\n'
           '<div class="tg">x</div>\n</head>\n<body><svg><clipPath id="c1"></clipPath></svg>\n'
           '<svg><clipPath id="c1"></clipPath></svg><div data-elem-id="5"></div><div data-elem-id="5"></div></body></html>')
    hd = h.code_lines(doc, "head_invalid")
    check("строка 6" in hd.get("title", "") and any(l[0] == 6 and l[2] and "tg" in l[1] for l in hd["lines"]),
          f"лишний тег в <head>: {hd}")
    ids = h.code_lines(doc, "dup_ids")
    check(ids.get("ids") == ["c1"] and len(ids["lines"]) == 2, f"одинаковые id (data-elem-id не в счёт): {ids}")
    og = dict((k, v) for k, _n, v in h.code_rows(doc))["og"]
    check("og:description: (пусто)" in og and "og:title: (нет)" in og, f"Open Graph: {og}")
    # как parser.py: <div> внутри <noscript> в <head> - не обрыв; id без кавычек и заглавными - считается;
    # id в комментарии - нет; повтор <head> - для «повторяются теги»
    doc2 = ('<html>\n<head>\n<noscript><div><img src=x></div></noscript>\n<!-- <p id=z> -->\n<title>T</title>\n'
            '<span>x</span>\n</head>\n<body><DIV ID=item></DIV>\n<div id=item></div><!-- <i id=z></i> -->\n'
            '<head><title>2</title></head></body></html>')
    hd2 = h.code_lines(doc2, "head_broken")
    check("<span>" in hd2.get("title", "") and "строка 6" in hd2["title"], f"обрыв <head> (noscript не в счёт): {hd2}")
    ids2 = h.code_lines(doc2, "dup_ids")
    check(ids2.get("ids") == ["item"], f"id без кавычек и в комментариях: {ids2}")
    mul = h.code_lines(doc2, "html_multi")
    check("<head> ×2" in mul.get("title", "") and len(mul["lines"]) == 2, f"повтор <head>: {mul}")
    # «Что нашлось» в коммерческих факторах: кусок одной строки текста, найденное внутри, режим работы - диапазоном
    import re as _re
    from seocrawler.analyze.checks import commercial as cm
    t = "Старая цена 2 500\n1 990 ₽ за штуку"
    check(cm._snippet(t, cm.PRICE.search(t)) == "1 990 ₽ за штуку", f"цена: {cm._snippet(t, cm.PRICE.search(t))!r}")
    long = "x" * 200 + " купить сейчас"
    check("купить" in cm._snippet(long, cm.ORDER.search(long)), "найденное не попало в кусок текста")
    hours = _re.compile(next(f[2] for f in cm.FACTORS if f[0] == "Режим работы"), _re.I)
    for s, ok in (("Ежедневно 10-22", True), ("Вт–Вс 11:00–20:00", True), ("Круглосуточно", True),
                  ("с понедельника по пятницу", True), ("В понедельник вышла статья", False)):
        check(bool(hours.search(s)) == ok, f"режим работы «{s}»")
    # проблемы телефона: копия как телефон (390 px, браузер телефона), «телефону не то» - обе версии рядом;
    # «Ошибки на снимках» - на копии та же разметка, что на снимке (problem_shots.MARK_JS)
    page = f"http://127.0.0.1:{SITE}/mebel"
    fr = h.frames(page, "[]", WIN, "mobile_diff", "Телефону не то", True, "Что отличается: ссылок")
    check(fr.count("<iframe") == 2 and "ua=phone" in fr and "Что отличается: ссылок" in fr, f"компьютер и телефон: {fr[:300]}")
    fr = h.frames(page, "[]", WIN, "mobile_taps", "Мелкие кнопки", False)
    check(fr.count("<iframe") == 1 and "width:390px" in fr, "копия как телефон")
    check("mobile_taps" in h.render(page, "[]", WIN, "mobile_taps", "", "phone") and "found.push" in
          h.render(page, "[]", WIN, "mobile_taps", "", "phone"), "разметка снимков не вставлена в копию")
    from seocrawler.problem_shots import html_block
    check('data-key="h1_multi"' in html_block([{"key": "h1_multi", "file": "a.png", "url": page}]),
          "у адреса под снимком нет data-key - клик не откроет копию")
    # в ячейке «адрес → адрес» или «адрес - с 17 стр.; адрес» ссылками становятся только сами адреса
    from seocrawler.report import _cell
    c = _cell("https://a.ru/ → https://a.ru/razbor")
    check(c.count("<a ") == 2 and 'href="https://a.ru/razbor"' in c and "%20" not in c, f"ссылки в ячейке: {c}")
    # очистка слова в отчёте: тот же код, что в SHOW_JS, на Node (если он есть)
    import shutil
    import subprocess
    js = SHOW_JS.split("const raw=")[1].split(";\n")[0]
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, "-e", f"const raw={js};console.log(raw('[Р]ассмотрение (латинская Р)'))"],
                             capture_output=True, text=True, encoding="utf-8").stdout.strip()
        check(out == "Рассмотрение", f"слово с пометкой не очищается: {out!r}")


# обведён ли элемент: есть видимая рамка (window/highlight.frame) именно для него
FRJS = ("var FR=function(el){return (window.__claylerFrames||[]).some(function(f){return f.el===el&&"
        "f.box.style.display!=='none'&&f.box.getBoundingClientRect().height>4})};")


def _browser(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("   (playwright нет - подсветка в браузере не проверена)")
        return
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            p = b.new_page()
            p.goto(url, wait_until="load", timeout=30000)
            p.wait_for_function("document.getElementById('clayler-show-msg')"
                                "&&!/ищу/.test(document.getElementById('clayler-show-msg').textContent)", timeout=15000)
            got = p.evaluate("""() => ({
                msg: document.getElementById('clayler-show-msg').textContent,
                tg: FR(document.querySelector('a[href^="tg:"]')),
                casino: FR(document.querySelector('a[href*="casino"]')),
                shown: getComputedStyle(document.querySelector('a[href*="casino"]').parentElement).display !== 'none',
                h1: FR(document.querySelector('h1')),
                path: location.pathname})""".replace("() => (", "() => {" + FRJS + " return (") + "}")
            check(got["tg"] and got["casino"], f"ссылки не обведены: {got}")
            check(got["shown"], "спрятанная ссылка не показана")
            check(not got["h1"], "заголовок обведён по тексту, хотя ссылки по адресу уже нашлись")
            check("Обведено красным: 2" in got["msg"] and "спрятано" in got["msg"], f"подпись: {got['msg']}")
            check(got["path"] == "/mebel", f"адрес в строке браузера не как у страницы сайта: {got['path']}")
            # «Что в коде»: title и H1 из HTML, ошибка JavaScript; у проблемы title - панель открыта, поле обведено
            p.goto(url.split("&find=")[0] + "&key=title_long&find=" + quote("[]"), wait_until="load")
            p.wait_for_function("document.getElementById('clayler-code-js')", timeout=15000)
            code = p.evaluate("document.getElementById('clayler-code').innerText")
            check("Тест" in code and "Мебель на заказ" in code and "тест-ошибка" in code, f"панель «Что в коде»: {code[:300]}")
            check(p.evaluate("[...document.querySelectorAll('#clayler-code tr')].some(t => t.style.outline && "
                             "t.innerText.startsWith('Title'))"), "у проблемы title поле Title не обведено")
            # качество существующего и готовый вариант с «Скопировать» (заголовки.csv последней проверки)
            check("4 симв." in code and "короткий (4 симв.) (проверка 05.11.2026)" in code
                  and "Предлагаю: Мебель на заказ в Москве | Тест" in code and "Старый вариант" not in code,
                  f"панель: нет оценки или варианта: {code[:500]}")
            p.click("#clayler-code a[data-copy]")
            p.wait_for_timeout(300)
            check(p.evaluate("document.querySelector('#clayler-code a[data-copy]').textContent") == "Скопировано",
                  "кнопка «Скопировать» не сработала")
            # «Тошнота»: частые слова подсвечены (все формы), название проблемы - в плашке
            p.goto(url.split("&find=")[0] + "&key=text_nausea&t=" + quote("Слова повторяются") + "&find="
                   + quote(json.dumps(["мебель - 3, заказ - 2"])), wait_until="load")
            p.wait_for_function("!/ищу/.test(document.getElementById('clayler-show-msg').textContent)", timeout=15000)
            got = p.evaluate("({n: document.querySelectorAll('mark').length, msg: document.getElementById('clayler-show').innerText})")
            check(got["n"] >= 2 and "Проблема: Слова повторяются" in got["msg"] and "мебель" in got["msg"],
                  f"частые слова: {got}")
            # слово через дефис не ломает подсветку; «Вода» - слова без счёта
            for words in ("онлайн-заказ - 2, мебель - 3", "мебели, заказ"):
                p.goto(url.split("&find=")[0] + "&key=text_water&find=" + quote(json.dumps([words])), wait_until="load")
                p.wait_for_function("!/ищу/.test(document.getElementById('clayler-show-msg').textContent)", timeout=15000)
                msg = p.evaluate("document.getElementById('clayler-show-msg').textContent")
                check("Подсвечены" in msg and p.evaluate("document.getElementById('clayler-code').hidden"),
                      f"частые слова «{words}»: {msg}")
            # «Нет H2»: обведены блоки текста
            p.goto(url.split("&find=")[0] + "&key=h2_missing&find=" + quote("[]"), wait_until="load")
            p.wait_for_function("!/ищу/.test(document.getElementById('clayler-show-msg').textContent)", timeout=15000)
            check("Подзаголовков H2" in p.evaluate("document.getElementById('clayler-show-msg').textContent"),
                  "нет H2: блоки текста не обведены")
            # только текст: заголовок находится; несуществующее - «Не нашёл»
            base = url.split("&find=")[0]
            p.goto(base + "&find=" + quote(json.dumps(["Мебель на заказ"])), wait_until="load")
            p.wait_for_function("!/ищу/.test(document.getElementById('clayler-show-msg').textContent)", timeout=15000)
            check(p.evaluate("() => {" + FRJS + " return FR(document.querySelector('h1'))}"), "заголовок не обведён по тексту")
            p.goto(base + "&find=" + quote(json.dumps(["https://nowhere.example/"])), wait_until="load")
            p.wait_for_function("/Не нашёл/.test(document.getElementById('clayler-show-msg').textContent)",
                                timeout=20000)
            wait = "!/ищу/.test(document.getElementById('clayler-show-msg').textContent)"
            ol = "(id => (" + FRJS.replace("var FR=", "") .rstrip(";") + ")(document.getElementById(id)))"
            # 5xx: ищем ссылки на саму страницу - своя плашка («Открыть настоящую страницу») не обводится
            p.goto(base + "&key=5xx&find=" + quote(json.dumps([f"http://127.0.0.1:{SITE}/mebel"])), wait_until="load")
            p.wait_for_function(wait, timeout=15000)
            got = p.evaluate("({self: " + ol + "('self'), panel: (window.__claylerFrames||[]).some(f => "
                             "f.el.closest('#clayler-show'))})")
            check(got["self"] and not got["panel"], f"ссылка на страницу / своя плашка: {got}")
            # картинка с адресом главной: обведена картинка, а не логотип-ссылка на главную
            p.goto(base + "&key=img_bad_type&find=" + quote(json.dumps([f"http://127.0.0.1:{SITE}/"])), wait_until="load")
            p.wait_for_function(wait, timeout=15000)
            got = p.evaluate("({img: " + ol + "('badimg'), logo: " + ol + "('logo')})")
            check(got["img"] and not got["logo"], f"картинка с адресом главной: {got}")
            # согласие в форме: обведена форма заявки, а не поиск
            p.goto(base + "&key=buy_consent_form&find=" + quote(json.dumps(["«Оставить заявку»", "на странице"])),
                   wait_until="load")
            p.wait_for_function(wait, timeout=15000)
            got = p.evaluate("({lead: " + ol + "('lead'), search: " + ol + "('search')})")
            check(got["lead"] and not got["search"], f"форма заявки / поиск: {got}")
            # остаток шаблона: подсвечен сам кусок, а не вся строка
            p.goto(base + "&key=buy_junk&find=" + quote(json.dumps(["Ножки", "«#Classic#», «#Classic#»"])),
                   wait_until="load")
            p.wait_for_function(wait, timeout=15000)
            got = p.evaluate("[...document.querySelectorAll('#junk mark')].map(m => m.textContent)")
            check(got == ["#Classic#"], f"остаток шаблона подсвечен не кусок: {got}")
            # смешанные буквы: подсвечено слово, русская «С» - отдельно
            p.goto(base + "&key=mixed_letters_meta&find=" + quote(json.dumps(
                ["title", "[С]eramicplus (русская С)", "Унитаз Сeramicplus белый"])), wait_until="load")
            p.wait_for_function(wait, timeout=15000)
            got = p.evaluate("({m: [...document.querySelectorAll('#mixed mark')].map(m => m.textContent),"
                             " b: [...document.querySelectorAll('#mixed mark b')].map(b => b.textContent),"
                             " h2: " + ol + "('mixed')})")
            check(got["m"] == ["Сeramicplus"] and got["b"] == ["С"] and not got["h2"],
                  f"смешанные буквы: {got}")
            # ссылка-обёртка вокруг карточки: рамка по карточке (высота ~120), а не нулевая; страница сдвинулась
            # (сузили окно, открыли инструменты разработчика) - рамка переехала вместе с карточкой
            p.goto(base + "&key=5xx&find=" + quote(json.dumps([f"http://127.0.0.1:{SITE}/product/x/"])), wait_until="load")
            p.wait_for_function(wait, timeout=15000)
            box = "(() => {var f=(window.__claylerFrames||[]).find(f => f.el.id==='card'); if(!f) return null;"                   " var r=f.box.getBoundingClientRect(), c=f.el.firstChild.getBoundingClientRect();"                   " return {h: r.height, dx: Math.round(r.left - c.left), shown: f.box.style.display!=='none'}})()"
            got = p.evaluate(box)
            check(got and got["shown"] and got["h"] >= 120 and abs(got["dx"] + 4) <= 2, f"карточка-ссылка: рамка {got}")
            p.evaluate("document.body.style.paddingLeft='240px'")
            p.wait_for_timeout(1000)
            got = p.evaluate(box)
            check(got and abs(got["dx"] + 4) <= 2, f"страница сдвинулась, а рамка осталась на месте: {got}")
            # снимок «нет H1» (problem_shots): подпись говорит, что это за тег; рамка - по словам, а не по блоку во
            # всю ширину, и переезжает, когда страница сдвинулась
            from seocrawler.problem_shots import MARK_JS as SHOT
            p.set_content('<html><body style="margin:0"><div style="width:1000px"><h2 style="font-size:32px">Доставка'
                          '</h2><p>Текст страницы про доставку.</p></div></body></html>')
            p.evaluate(SHOT, ["h1_missing", 1366])
            box = ("() => {const d=[...document.querySelectorAll('[data-clayler]')], rg=document.createRange();"
                   " rg.selectNodeContents(document.querySelector('h2')); const t=rg.getBoundingClientRect(),"
                   " b=d[0].getBoundingClientRect(); return {label: d[1].textContent, extra: Math.round(b.width - t.width),"
                   " dx: Math.round(b.left - t.left)}}")
            got = p.evaluate(box)
            check("это H2" in got["label"] and "H1" in got["label"] and 0 <= got["extra"] <= 10,
                  f"снимок «нет H1»: {got}")
            p.evaluate("document.body.style.paddingLeft='300px'")
            p.wait_for_timeout(1000)
            check(abs(p.evaluate(box)["dx"] - got["dx"]) <= 1, "снимок «нет H1»: рамка не переехала за заголовком")
        except Exception as e:
            fails.append(f"браузер: {str(e)[:300]}")
        finally:
            b.close()


main()
