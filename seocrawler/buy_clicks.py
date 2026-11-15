"""«Что мешает покупать», вторая часть: программа в браузере нажимает «Купить в один клик», «В корзину»
и «Заказать звонок» на 1-2 страницах каждого вида (товар, раздел каталога, главная, другие страницы с кнопкой) и
смотрит, что открылось: форма с товаром или общая форма «перезвоним» без товара, спрашивает ли форма город, который
уже выбран в шапке, или вообще ничего не происходит. Снимок с красной рамкой - в отчёт.

Формы НИКОГДА не отправляются: отправка форм отменяется в самой странице (submit и form.submit), а запросы,
похожие на заказ или заявку (order, checkout, lead, callback, feedback, send, crm…), браузер не выпускает.
Добавление в корзину пропускается: по нему видно, сработала ли кнопка (корзина живёт только в этом браузере).

Где страницы с кнопками - из pages.shop (seocrawler/shop.py). Нужны интернет и playwright (как для снимков
телефона). Делается при сборке отчёта один раз, результат - meta «buy_clicks», снимки - в папке DIR.
Выключить: CLAYLER_NO_BUY_CLICKS=1. Проблема в отчёте - analyze/checks/buy.py (buy_click)."""
import html as H
import json
import os
import re
from urllib.parse import urlsplit

from .shop import is_product

DIR = "снимки кнопок"
VERSION = 1
PER_KIND = 2
MAX_PAGES = 8
VIEW = (1366, 860)

BLOCK = re.compile(r"(order|zakaz|checkout|lead|feedback|callback|call-?back|send|submit|mail|crm|amocrm|bitrix24|"
                   r"form|zayavk|request|oneclick|one_click|fastorder|quick)", re.I)
CART_OK = re.compile(r"(basket|cart|korzin).*(add|put|buy)|(add|put).*(basket|cart)", re.I)

# что нажимаем: вид кнопки → регулярное выражение по тексту (в браузере)
BUTTONS = [
    ("one_click", r"^\s*(купить|заказать)\s+в\s+(1|один)\s+клик\s*$|^\s*быстрый\s+заказ\s*$"),
    ("cart", r"^\s*(в\s+корзину|добавить\s+в\s+корзину|купить)\s*$"),
    ("callback", r"^\s*(заказать\s+(обратный\s+)?звонок|обратный\s+звонок|перезвоните\s+мне)\s*$"),
]
NAMES = {"one_click": "Купить в один клик", "cart": "В корзину", "callback": "Заказать звонок"}

# отменить отправку любых форм на странице (до загрузки скриптов сайта)
GUARD_JS = r"""(() => {
  const stop = e => { e.preventDefault(); e.stopImmediatePropagation(); };
  window.addEventListener('submit', stop, true);
  HTMLFormElement.prototype.submit = function () {};
  HTMLFormElement.prototype.requestSubmit = function () {};
})();"""

# видимые плашки cookie и кнопки чатов закрывают страницу на снимке: прячем до нажатия (окна сайта не трогаем)
COOKIE_JS = r"""() => {
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (s.position !== 'fixed' || s.display === 'none' || !r.width || r.height > innerHeight * 0.5) continue;
    if (/cookie|куки/i.test(el.innerText || '') || (el.querySelector('iframe') && r.width < 500))
      el.style.setProperty('display', 'none', 'important');
  }
}"""

FIND_JS = r"""([kinds]) => {
  const vis = el => { const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0 && r.width > 4 && r.height > 4; };
  const out = {};
  const els = [...document.querySelectorAll('a, button, input[type=button], input[type=submit], [role=button], span, div')];
  for (const [kind, rx] of kinds) {
    const re = new RegExp(rx, 'i');
    for (const el of els) {
      const t = (el.tagName === 'INPUT' ? el.value : el.innerText || '').replace(/\s+/g, ' ').trim();
      if (!t || t.length > 40 || !re.test(t)) continue;
      if (['SPAN', 'DIV'].includes(el.tagName) && !(el.onclick || el.getAttribute('onclick') || el.dataset && Object.keys(el.dataset).length
          || getComputedStyle(el).cursor === 'pointer')) continue;
      if (el.closest('header, footer, nav, [class*=header], [class*=footer]') && kind !== 'callback') continue;
      if (el.closest('form') && el.type === 'submit') continue;
      if (!vis(el)) continue;
      el.setAttribute('data-clayler-btn', kind);
      out[kind] = t;
      break;
    }
  }
  return out;
}"""

# что видно на экране: окна, формы, текст корзины — до и после нажатия
STATE_JS = r"""() => {
  const vis = el => { const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.1 && r.width > 40 && r.height > 40
      && r.bottom > 0 && r.top < innerHeight; };
  const pops = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.hasAttribute('data-clayler')) continue;
    const s = getComputedStyle(el);
    const modal = s.position === 'fixed' || el.tagName === 'DIALOG' || el.getAttribute('aria-modal') === 'true'
      || /(modal|popup|fancybox|mfp-|dialog|overlay|lightbox)/i.test(el.className && el.className.baseVal === undefined ? el.className : '');
    if (!modal || !vis(el)) continue;
    if (pops.some(p => p.contains(el))) continue;
    pops.push(el);
  }
  const cart = [...document.querySelectorAll('[class*=cart], [class*=basket], [id*=cart], [id*=basket], [class*=korzin]')]
    .map(e => e.innerText || '').join('|').replace(/\s+/g, ' ').slice(0, 500);
  return {url: location.href, pops: pops.map(p => (p.innerText || '').replace(/\s+/g, ' ').slice(0, 600)),
          forms: pops.reduce((n, p) => n + p.querySelectorAll('input:not([type=hidden]), textarea, select').length, 0),
          city: pops.some(p => [...p.querySelectorAll('input, select, label')].some(i =>
            /город|city/i.test((i.name || '') + ' ' + (i.placeholder || '') + ' ' + (i.innerText || '') + ' ' + (i.id || '')))),
          cart, len: document.body ? document.body.innerText.length : 0};
}"""

FRAME_JS = r"""([sel, label, popText, color]) => {
  const box = (r, text, color) => {
    const d = document.createElement('div');
    d.setAttribute('data-clayler', '1');
    d.style.cssText = `position:absolute;left:${r.left + scrollX - 6}px;top:${r.top + scrollY - 6}px;width:${r.width + 12}px;` +
      `height:${r.height + 12}px;border:4px solid ${color};border-radius:8px;z-index:2147483647;pointer-events:none;box-sizing:border-box`;
    const t = document.createElement('div');
    t.setAttribute('data-clayler', '1');
    t.textContent = text;
    t.style.cssText = `position:absolute;left:-4px;top:-32px;background:${color};color:#fff;font:600 14px/1.4 Arial,sans-serif;` +
      'padding:3px 10px;border-radius:4px;white-space:nowrap';
    d.appendChild(t);
    document.body.appendChild(d);
  };
  const b = document.querySelector(sel);
  if (b) box(b.getBoundingClientRect(), label, color);
  if (popText) {
    // окно, которое открылось: поле ввода в «прибитом» к экрану слое, от него вверх - до карточки окна с фоном
    let best = null;
    for (const inp of document.querySelectorAll('input:not([type=hidden]), textarea, select')) {
      const r0 = inp.getBoundingClientRect();
      if (!r0.width || !r0.height) continue;
      let fixed = false;
      for (let a = inp; a; a = a.parentElement) if (getComputedStyle(a).position === 'fixed' || a.tagName === 'DIALOG') { fixed = true; break; }
      if (!fixed) continue;
      for (let a = inp.parentElement; a && a !== document.body; a = a.parentElement) {
        const s = getComputedStyle(a), r = a.getBoundingClientRect();
        const bg = s.backgroundColor && !/rgba\(.*, ?0\)|transparent/.test(s.backgroundColor);
        if (r.width >= 240 && r.width < innerWidth * 0.95 && bg) { best = a; break; }
      }
      if (best) break;
    }
    if (best) box(best.getBoundingClientRect(), popText, color);
  }
}"""


def pick(store):
    """[(вид страницы, адрес)]: по PER_KIND страниц товара, раздела каталога, главной и других с кнопкой."""
    rows = store.db.execute("SELECT p.url, p.shop FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND "
                            "u.kind='page' AND p.status=200 AND p.shop IS NOT NULL ORDER BY u.depth, p.url").fetchall()
    start = store.get_meta("start", "")
    kinds = {"товар": [], "раздел каталога": [], "главная": [], "другая страница": []}
    secs = set()
    for url, raw in rows:
        try:
            f = json.loads(raw)
        except ValueError:
            continue
        has = f.get("buy") or f.get("one_click") or f.get("callback")
        if not has:
            continue
        if url.rstrip("/") == start.rstrip("/") or urlsplit(url).path in ("", "/"):
            k = "главная"
        elif is_product(f) or (f.get("sname") and (f.get("buy") or f.get("one_click"))):
            k = "товар"
        elif f.get("prices", 0) >= 4:
            k = "раздел каталога"
        else:
            k = "другая страница"
        sec = urlsplit(url).path.strip("/").split("/")[0]
        if len(kinds[k]) >= PER_KIND or (k == "товар" and (sec, k) in secs and len(rows) > 20):
            continue
        secs.add((sec, k))
        kinds[k].append(url)
    out = [(k, u) for k, us in kinds.items() for u in us]
    return out[:MAX_PAGES]


def verdict(kind, before, after, h1, city, page_kind="товар"):
    """(что произошло, проблема или ""). page_kind - тип страницы из pick(): общая форма «в один клик» без названия
    товара - ошибка только на карточке товара; на главной и в разделе каталога у кнопки нет «своего» товара в H1."""
    if after["url"].split("#")[0] != before["url"].split("#")[0]:
        return f"открылась страница {after['url']}", ""
    new = [t for t in after["pops"] if t not in before["pops"]]
    cart_changed = after["cart"] != before["cart"]
    if not new and not cart_changed and abs(after["len"] - before["len"]) < 15:
        return "ничего не произошло", "нажали, а на экране ничего не изменилось"
    if kind == "cart":
        return ("товар добавлен в корзину" if cart_changed or new else "страница изменилась"), ""
    text = " ".join(new)
    words = [w for w in re.findall(r"[\wёЁ]{4,}", (h1 or "").lower())][:4]
    has_item = bool(words) and sum(w in text.lower() for w in words) >= max(1, len(words) // 2)
    if kind == "one_click" and new and not has_item and page_kind == "товар":
        return "открылась общая форма без названия товара", "форма «купить в один клик» не показывает, какой товар заказывают"
    if new and after.get("city") and city:
        return "открылась форма с полем «Город»", f"форма спрашивает город, хотя в шапке уже выбран город {city}"
    return ("открылась форма" + (" с товаром" if has_item else "")), ""


def guard_route(blocked):
    """Для ctx.route: отправка форм (заказ, заявка, звонок; не «в корзину») на сайт не уходит, адрес - в blocked."""
    def route(r):
        req = r.request
        if req.method in ("POST", "PUT") and BLOCK.search(req.url) and not CART_OK.search(req.url):
            blocked.append(req.url)
            return r.abort()
        return r.continue_()
    return route


def take(todo, shots_dir, log=print, timeout=30.0):
    from playwright.sync_api import sync_playwright
    os.makedirs(shots_dir, exist_ok=True)
    out, n = [], 0
    blocked = []

    route = guard_route(blocked)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for kind_page, url in todo:
                for bkind, rx in BUTTONS:
                    ctx = browser.new_context(viewport={"width": VIEW[0], "height": VIEW[1]}, ignore_https_errors=True,
                                              service_workers="block", locale="ru-RU")
                    ctx.add_init_script(GUARD_JS)
                    ctx.route("**/*", route)
                    page = ctx.new_page()
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                        for state, ms in (("load", 10000), ("networkidle", 3000)):
                            try:
                                page.wait_for_load_state(state, timeout=ms)
                            except Exception:
                                pass
                        found = page.evaluate(FIND_JS, [[(bkind, rx)]])
                        if bkind not in found:
                            continue
                        h1 = page.evaluate("() => (document.querySelector('h1') || {}).innerText || ''")
                        city = page.evaluate(r"""() => { const m = (document.querySelector('header, [class*=header]') || document.body)
                            .innerText.match(/(?:ваш город|ваш регион|город)\s*[:\-]?\s*([А-ЯЁ][а-яё]+)/); return m ? m[1] : ''; }""")
                        sel = f'[data-clayler-btn="{bkind}"]'
                        page.locator(sel).first.scroll_into_view_if_needed(timeout=3000)
                        page.wait_for_timeout(300)
                        page.evaluate(COOKIE_JS)
                        before = page.evaluate(STATE_JS)
                        try:
                            page.locator(sel).first.click(timeout=4000)
                        except Exception:
                            page.evaluate(f"() => document.querySelector('{sel}').click()")
                        page.wait_for_timeout(2000)
                        after = page.evaluate(STATE_JS)
                        what, problem = verdict(bkind, before, after, h1, city, kind_page)
                        n += 1
                        name = f"{n:02d}.jpg"
                        if not what.startswith("открылась страница"):
                            page.evaluate(FRAME_JS, [sel, f"Нажали «{found[bkind]}»" + (": ничего не произошло"
                                                                                          if what == "ничего не произошло" else ""),
                                                     ("Общая форма: товара в ней нет" if "товар" in problem else
                                                      "Форма снова спрашивает город" if "город" in problem else
                                                      "Что открылось") if what.startswith("открылась") else "",
                                                     "#e0201b" if problem else "#2e7d32"])
                        page.screenshot(path=os.path.join(shots_dir, name), type="jpeg", quality=72)
                        out.append({"url": url, "page": kind_page, "kind": bkind, "button": found[bkind], "what": what,
                                    "problem": problem, "file": name})
                        log(f"   {url}: «{found[bkind]}» - {what}")
                    except Exception as e:
                        s = str(e).strip().splitlines()
                        log(f"   {url}: не получилось нажать - {(s[0] if s else type(e).__name__)[:120]}")
                    finally:
                        ctx.close()
        finally:
            browser.close()
    return out, blocked


def ensure(store, out_dir, log=print):
    shots_dir = os.path.join(out_dir, DIR)
    old = store.get_meta("buy_clicks", None)
    if old and old.get("version") == VERSION and all(os.path.exists(os.path.join(shots_dir, s["file"]))
                                                      for s in old.get("items", [])):
        return old
    if os.environ.get("CLAYLER_NO_BUY_CLICKS") == "1":
        return old
    todo = pick(store)
    if not todo:
        return old
    from .mobile_view import available
    if not available():
        return old
    log(f"Нажимаю кнопки покупки и заявки на {len(todo)} страницах (формы не отправляются)...")
    if os.path.isdir(shots_dir):
        for f in os.listdir(shots_dir):
            try:
                os.remove(os.path.join(shots_dir, f))
            except OSError:
                pass
    try:
        items, blocked = take(todo, shots_dir, log)
    except Exception as e:
        log("Кнопки не нажаты: " + str(e)[:150])
        return old
    res = {"version": VERSION, "items": items, "pages": len(todo), "blocked": len(blocked)}
    store.set_meta("buy_clicks", res)
    store.commit()
    return res


def problem(s):
    """Проблема нажатия. Общая форма «в один клик» без названия товара на главной и в разделе - не ошибка: так
    отсеиваются и записи проверок, собранные до этого правила (см. verdict)."""
    if "без названия товара" in (s.get("what") or "") and s.get("page", "товар") != "товар":
        return ""
    return s.get("problem") or ""


def html_block(res, h2="h2", h2_cls="sec", limit=None):
    items = [dict(s, problem=problem(s)) for s in (res or {}).get("items") or []]
    if not items:
        return ""
    cards = []
    for s in sorted(items, key=lambda s: not s["problem"])[:limit]:
        color = "var(--crit)" if s["problem"] else "var(--good, #2e7d32)"
        cards.append(f'<figure class="d"><img src="{DIR}/{H.escape(s["file"])}" loading="lazy" alt="">'
                     f'<figcaption><b style="color:{color}">«{H.escape(s["button"])}» - {H.escape(s["what"])}</b>'
                     + (f'<br>{H.escape(s["problem"][:1].upper() + s["problem"][1:])}.' if s["problem"] else "")
                     + f'<br><span class="mut">{H.escape(s["page"])}:</span> <a href="{H.escape(s["url"])}" '
                     f'target="_blank" rel="noopener">{H.escape(s["url"])}</a></figcaption></figure>')
    bad = sum(1 for s in items if s["problem"])
    return (f'<{h2} class="{h2_cls}">Кнопки покупки и заявки на снимках</{h2}>'
            f'<p class="mut">На нескольких страницах каждого вида нажали «Купить в один клик», «В корзину» и «Заказать '
            f'звонок» и посмотрели, что видит покупатель. Формы не отправлялись. Нажатий: {len(items)}, с проблемой: '
            f'{bad}.</p><div class="psh">{"".join(cards)}</div>')


def audit_html(summary):
    b = html_block(summary.get("buy_clicks"), h2="h2", h2_cls="", limit=6)
    return f'<section class="pt">{b}</section>' if b else ""
