"""Автотест: согласие на обработку персональных данных в формах и виджетах (seocrawler/consent_forms.py).
Тестовый сайт: форма на странице с галочкой, поставленной заранее; виджет чата, который скрипт подгружает через
1,5 секунды и раскрывает кнопкой «Напишите нам», а в строке согласия ссылки с «», без «/» в начале, на главную и на
другой сайт; спрятанная форма «Перезвоните», которую раскрыть нечем (должна попасть в «Что не проверено»).
Формы не отправляются - сайт считает, сколько раз ему что-то отправили (должно быть 0).
Нужен playwright с Chromium (как для снимков телефона); без него тест пропускается.
Запуск: py -3 tests/проверить_согласие.py"""
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seocrawler import consent_forms, coverage  # noqa: E402
from seocrawler.analyze.checks import buy  # noqa: E402
from seocrawler.mobile_view import available  # noqa: E402
from seocrawler.storage import Store  # noqa: E402

POSTS = []
PORT = [0]

WIDGET = """<script>setTimeout(function () {
  var b = document.createElement('div');
  b.innerHTML = '<div id="wbtn" style="position:fixed;right:20px;bottom:20px;width:180px;height:44px;background:#09c;'
    + 'color:#fff;cursor:pointer;z-index:50">Напишите нам</div>'
    + '<div id="wform" style="display:none;position:fixed;right:20px;bottom:80px;width:320px;background:#fff;'
    + 'border:1px solid #ccc;z-index:51"><p>Мы не в сети, оставьте сообщение</p>'
    + '<input name="name" placeholder="Имя"><input name="phone" placeholder="Телефон"><textarea></textarea>'
    + '<label><input type="checkbox" name="agree"> Я даю <a href="»http://127.0.0.1:%PORT%/privacy/»">Согласие</a> '
    + 'на обработку персональных данных и принимаю <a href="soglasie/">условия</a>, '
    + '<a href="/old-policy/">политику конфиденциальности</a> и <a href="http://localhost:%PORT%/terms/">правила</a></label>'
    + '<button type="button">Готово</button></div>'
    + '<div id="cb" style="display:none;position:fixed;left:0;top:0;width:300px;background:#fff">'
    + '<input name="phone" type="tel"><button type="button">Перезвоните</button></div>';
  document.body.appendChild(b);
  document.getElementById('wbtn').onclick = function () { document.getElementById('wform').style.display = 'block'; };
}, 1500);</script>"""

POLICY = ("<h1>Политика обработки персональных данных</h1>" + "<p>Оператор обрабатывает персональные данные, "
          "обработка персональных данных ведётся с согласия. Конфиденциальность персональных данных.</p>" * 5)


FOOTER = ('<footer>ООО «Тест», ИНН 7701234567. <a href="/privacy/">Политика конфиденциальности</a> '
          '<a href="/policy2/">Обработка персональных данных</a></footer>')


def page(body):
    return (f'<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Услуги</h1>{body}{FOOTER}'
            + WIDGET + '</body></html>')


PAGES = {
    "/": page('<form action="/lead" method="post"><input name="name"><input name="phone" type="tel">'
              '<label><input type="checkbox" checked> Согласен на обработку персональных данных по '
              '<a href="/privacy/">политике</a></label><button type="submit">Отправить заявку</button></form>'),
    "/article/": page("<p>Статья о сертификации продукции.</p>"),
    # политика с ИНН другой компании и вторая - без оператора
    "/privacy/": f'<!doctype html><html><head><meta charset="utf-8"></head><body>{POLICY}<p>ООО «Другая», '
                 f'ИНН 7709999999</p></body></html>',
    "/policy2/": f'<!doctype html><html><head><meta charset="utf-8"></head><body>{POLICY}</body></html>',
    "/terms/": '<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Магазин</h1><p>Каталог</p></body></html>',
}


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/old-policy/":
            self.send_response(301)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        b = PAGES.get(path, "<h1>Не найдено</h1>").replace("%PORT%", str(PORT[0])).encode()
        self.send_response(200 if path in PAGES else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        POSTS.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


class Ctx:
    def __init__(self, store):
        self.store, self.got = store, {}

    def add(self, key, sev, cat, title, why, fix, columns, rows, page_col=0):
        if rows:
            self.got[key] = rows


def main():
    # проверка адресов - без браузера
    fails = []
    hp = consent_forms.href_problems
    for raw, want in [("»https://site.ru/privacy/»", "лишние символы"), ("https://site.ru/a/https://site.ru/b", "ещё один адрес"),
                      (" /privacy/ ", "пробелы"), ("privacy/", "без «/»"), ("%C2%ABhttps://site.ru/p%C2%BB", "закодированные"),
                      ("javascript:void(0)", "никуда не ведёт"), ("", "нет адреса")]:
        if not any(want in p for p in hp(raw, "https://site.ru/x/" + raw)):
            fails.append(f"адрес {raw!r}: ждали «{want}», получили {hp(raw, '')}")
    for raw in ("/privacy/", "https://site.ru/privacy/", "//site.ru/p", "https://site.ru/go?url=https://x.ru"):
        if hp(raw, raw):
            fails.append(f"адрес {raw!r} в порядке, а найдено {hp(raw, raw)}")
    # что открывается по ссылке: оферта и пользовательское соглашение - тоже документы, витрина - нет
    op = consent_forms.open_problems
    offer = ("Публичная оферта. Настоящий договор между Продавцом и Покупателем. Акцепт оферты означает согласие "
             "сторон. Покупатель оплачивает заказ, Продавец передаёт товар. Договор вступает в силу.")
    for text, ok in [(offer, True), ("Каталог. Котлы. Цены. Купить. Доставка.", False)]:
        got = op({"status": 200, "url": "https://site.ru/oferta/", "type": "text/html", "text": text},
                 "https://site.ru/oferta/", {"site.ru"})
        if bool(got) == ok:
            fails.append(f"страница «{text[:30]}…»: {'документ' if ok else 'не документ'}, а получено {got}")
    # браузерный запрос не удался - документ открывается так же, как при обходе (и по редиректу), а не пишется
    # «сервер не ответил»; не открылся никак - в тексте настоящая причина (dom-primer.ru)
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class Doc(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/old/":
                self.send_response(301)
                self.send_header("Location", "/policy/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = ("<html><head><title>Политика обработки персональных данных</title></head><body>"
                    + offer * 5 + "</body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class Broken:
        def get(self, *a, **k):
            raise RuntimeError("Target page, context or browser has been closed")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Doc)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        res = consent_forms._fetch(Broken(), base + "/old/", {})
        if res.get("status") != 200 or not res.get("url", "").endswith("/policy/") or "Продавцом" not in res.get("text", ""):
            fails.append(f"документ не открыт запасным способом: {str(res)[:200]}")
        res = consent_forms._fetch(Broken(), "http://127.0.0.1:9/nothing/", {})
        got = op(res, "http://127.0.0.1:9/nothing/", {"127.0.0.1"})
        if not got or "не открылся при проверке (" not in got[0] or "сервер не ответил" == got[0]:
            fails.append(f"неоткрывшийся документ без причины: {got}")
    finally:
        srv.shutdown()
    # согласие на рассылку: слов о персональных данных мало, но заголовок - документ (primerline.agency)
    ads = ("Согласие на рекламную и информационную рассылку. Настоящим я даю согласие на получение сообщений. " * 20)
    got = op({"status": 200, "url": "https://site.ru/ads_agreement", "type": "text/html", "text": ads,
              "title": "Согласие на рекламную и информационную рассылку"}, "https://site.ru/ads_agreement", {"site.ru"})
    if got:
        fails.append(f"согласие на рассылку не признано документом: {got}")
    got = op({"status": 200, "url": "https://site.ru/blog/", "type": "text/html", "text": "Блог. " * 400,
              "title": "Блог компании"}, "https://site.ru/blog/", {"site.ru"})
    if not got:
        fails.append("страница блога признана документом")
    for title, ok in (("Политика обработки персональных данных", True), ("Пользовательское соглашение", True),
                      ("Расположение офиса", False), ("Персональные тренировки", False), ("Цена договорная", False),
                      ("Правила игры", False)):
        if bool(consent_forms.DOC_TITLE.search(title)) != ok:
            fails.append(f"заголовок «{title}»: {'документ' if ok else 'не документ'}")
    # сайт закрыл доступ: дочитывание цен и форм останавливается через несколько страниц и не запоминается
    from seocrawler import shop
    calls = []
    t0 = tempfile.mkdtemp(prefix="clayler-shopstop-")
    s0 = Store(os.path.join(t0, "crawl.db"))
    for i in range(30):
        u = f"http://site.test/p{i}/"
        s0.enqueue(u, 1, True, "page", "http://site.test/", "done")
        s0.save_page({"url": u, "status": 200, "content_type": "text/html", "indexable": 1})
    s0.commit()
    shop.ensure(s0, fetch=lambda u: calls.append(u), log=lambda *a: None)
    if len(calls) != shop.STOP_AFTER or s0.get_meta("shop_sampled", None) is not None:
        fails.append(f"дочитывание при закрытом сайте: открыто {len(calls)} страниц, meta {s0.get_meta('shop_sampled', None)}")
    # прошлая версия запомнила «дочитано 0 страниц» - сайт снова открылся, дочитать
    s0.set_meta("shop_sampled", {"pages": 0, "of": 30, "v": shop.VERSION})
    s0.commit()
    shop.ensure(s0, fetch=lambda u: b"<html><body><h1>T</h1></body></html>", log=lambda *a: None)
    if not (s0.get_meta("shop_sampled", None) or {}).get("pages"):
        fails.append(f"после «дочитано 0» страницы не дочитаны снова: {s0.get_meta('shop_sampled', None)}")
    if not available():
        print("• согласие в формах: playwright не установлен - браузерная часть пропущена")
        if fails:
            print("✗ согласие в формах:\n   " + "\n   ".join(fails))
            sys.exit(1)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    PORT[0] = srv.server_port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    tmp = tempfile.mkdtemp(prefix="clayler-consent-")
    st = Store(os.path.join(tmp, "crawl.db"))
    st.set_meta("start", base + "/")
    for path in ("/", "/article/"):
        st.enqueue(base + path, 0 if path == "/" else 2, True, "page", base + "/", "done")
        st.save_page({"url": base + path, "status": 200, "indexable": 1})
    st.commit()
    todo = consent_forms.pick(st)
    if sorted(todo) != [base + "/", base + "/article/"]:
        fails.append(f"какие страницы открывать: {todo}")
    res = consent_forms.ensure(st, tmp, log=lambda *a: None)
    srv.shutdown()
    forms = {f["btn"]: f for f in (res or {}).get("forms", [])}
    page_form = forms.get("Отправить заявку")
    if not page_form:
        fails.append(f"форма на странице не найдена: {list(forms)}")
    else:
        if not any("заранее" in p for p in page_form["problems"]):
            fails.append(f"галочка заранее не замечена: {page_form['problems']}")
        if any(lk["problems"] for lk in page_form["links"]):
            fails.append(f"хорошая ссылка на политику отмечена как плохая: {page_form['links']}")
        if not page_form.get("file"):
            fails.append("нет снимка формы на странице")
    w = forms.get("Готово")
    if not w:
        fails.append(f"форма виджета не найдена: {list(forms)}")
    else:
        if w["where"] != "виджет или всплывающее окно" or not w["shown"]:
            fails.append(f"виджет: где «{w['where']}», раскрыт {w['shown']}")
        if not w.get("file") or not os.path.exists(os.path.join(tmp, consent_forms.DIR, w["file"])):
            fails.append("виджет: нет снимка")
        if sorted(w["pages"]) != [base + "/", base + "/article/"]:
            fails.append(f"виджет: страницы {w['pages']}")
        if w["box"] != "unchecked":
            fails.append(f"виджет: галочка {w['box']}")
        got = {lk["text"]: "; ".join(lk["problems"]) for lk in w["links"]}
        for text, want in [("Согласие", "лишние символы"), ("Согласие", "открывается ошибка 404"),
                           ("условия", "без «/»"), ("политику конфиденциальности", "главная"),
                           ("правила", "другой сайт")]:
            if want not in got.get(text, ""):
                fails.append(f"ссылка «{text}»: ждали «{want}», получили «{got.get(text)}»")
    if not any(x["btn"] == "Перезвоните" for x in res.get("not_opened", [])):
        fails.append(f"нераскрытая форма «Перезвоните» не отмечена: {res.get('not_opened')}")
    if "Перезвоните" in forms:
        fails.append("нераскрытая форма без строки согласия попала в проблемы")
    ctx = Ctx(st)
    buy.consent(ctx)
    if len(ctx.got.get("buy_consent_link", [])) != 4:
        fails.append(f"проблема со ссылками: {ctx.got.get('buy_consent_link')}")
    if not ctx.got.get("buy_consent_form"):
        fails.append("нет проблемы «Согласие в формах оформлено с ошибкой»")
    if [r[0].replace(base, "") for r in ctx.got.get("buy_policy_company", [])] != ["/privacy/"]:
        fails.append(f"политика с чужим ИНН: {ctx.got.get('buy_policy_company')}")
    if [r[0].replace(base, "") for r in ctx.got.get("buy_policy_noop", [])] != ["/policy2/"]:
        fails.append(f"политика без оператора: {ctx.got.get('buy_policy_noop')}")
    cov = coverage.collect(st, {"pages": 2})
    if not any("не удалось раскрыть" in r["what"] for r in cov["rows"]):
        fails.append(f"в «Что не проверено» нет нераскрытой формы: {cov['rows']}")
    html = consent_forms.html_block(res)
    if "Согласие на обработку персональных данных в формах" not in html or consent_forms.DIR not in html:
        fails.append("нет раздела со снимками")
    if POSTS:
        fails.append(f"формы отправились: {POSTS}")
    if fails:
        print("✗ согласие в формах:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ согласие в формах: чужой ИНН и нет оператора в политике, галочка заранее, ссылки с «», без «/», на главную и чужой сайт, виджет раскрыт, "
          "нераскрытая форма - в «Что не проверено», формы не отправлены")


if __name__ == "__main__":
    main()
