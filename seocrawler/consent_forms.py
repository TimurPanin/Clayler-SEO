"""«Что мешает покупать», согласие на обработку персональных данных в формах.

Статическая проверка (shop.py, buy_no_consent) видит только формы в коде страницы. Здесь страница открывается в
браузере, программа ждёт виджеты, которые скрипт подгружает с задержкой (чаты, «перезвоним», офлайн-формы чатов),
и для каждой формы с телефоном или почтой смотрит:
- есть ли строка согласия и галочка, не стоит ли галочка заранее;
- куда ведут ссылки из строки согласия: адрес как написан в коде (лишние «», кавычки, пробелы, второй http внутри
  адреса, путь без «/» в начале) и что открывается на самом деле (404, главная, чужой сайт, страница без текста
  политики);
- для формы с проблемой - снимок: форма раскрыта (кнопки чатов и «напишите нам» нажимаются сами), проблемная
  ссылка в красной рамке.

Формы НИКОГДА не отправляются: те же защиты, что в buy_clicks.py (submit отменяется в странице, запросы, похожие на
заявку, браузер не выпускает). Ссылки на документы открываются отдельным запросом GET.
Результат - meta «consent_forms», снимки - в папке DIR. Выключить: CLAYLER_NO_CONSENT_CHECK=1.
Проблемы в отчёте - analyze/checks/buy.py (buy_consent_link, buy_consent_form, buy_consent_nobox), что не удалось
открыть - coverage.py («Что не проверено и почему»)."""
import html as H
import json
import os
import re
from urllib.parse import urlsplit

from .buy_clicks import GUARD_JS, guard_route

DIR = "снимки согласия"
VERSION = 3   # 2: компания и ИНН в политике конфиденциальности; 3: документ узнаётся и по заголовку
MAX_PAGES = 4
VIEW = (1366, 860)
WAIT_WIDGETS = 6000   # мс после загрузки: виджеты чатов часто подгружаются через 3-5 секунд
MAX_CLICKS = 8        # сколько кнопок виджетов нажать на странице, чтобы раскрыть форму

QUOTES = re.compile(r"[«»\"'“”„‘’<>]")
ENC_QUOTES = re.compile(r"%(c2%ab|c2%bb|22|27|e2%80%9[cdeg]|3c|3e)", re.I)
DOC_WORDS = re.compile(r"персональн|конфиденциальн|обработк[аиуеойы]", re.I)
# оферта, договор, пользовательское соглашение, правила - тоже документы по ссылкам из строки согласия
DEAL_WORDS = re.compile(r"оферт|договор|акцепт|соглашени|заказчик|исполнител|покупател|продав|сторон[аыуе]", re.I)
# реквизиты: кто оператор персональных данных в политике и чья компания в подвале сайта
INN = re.compile(r"ИНН(?:\s*/\s*КПП)?\s*[:№]?\s*(\d{10}|\d{12})(?!\d)", re.I)
OGRN = re.compile(r"ОГРН(?:ИП)?\s*[:№]?\s*(\d{13}|\d{15})(?!\d)", re.I)
ORG_SHORT = re.compile(r"(?<![А-ЯЁа-яёA-Za-z])(ООО|ОАО|АО|ПАО|ЗАО|ИП|ФГУП|МУП|ГБУ|ГАУ|АНО|НКО)(?![А-ЯЁа-яёA-Za-z])")
ORG_LONG = re.compile(r"индивидуальн\w* предпринимател|обществ\w* с ограниченной|акционерн\w* обществ|учреждени\w|"
                      r"самозанят", re.I)
CONTACTS = re.compile(r"/(?:contacts?|kontakty?|kontakti|контакты|rekvizit\w*|реквизиты|requisites|about(?:-us)?|"
                      r"o-kompanii|о-компании)(?:[/.?]|$)", re.I)
# ссылки на политику в подвале и меню (не только в формах)
FOOT_JS = r"""() => {
  const f = document.querySelector('footer, #footer, [class*=footer]');
  // реквизиты - только из подвала (в статьях бывают ИНН чужих компаний); подвала нет - конец страницы
  const t = f ? f.innerText : (document.body ? document.body.innerText.slice(-1500) : '');
  const links = [...document.querySelectorAll('a[href]')].filter(a => /(политик|персональн|конфиденц)/i.test(a.innerText || '')
    || /(privacy|policy|politika|konfiden)/i.test(a.getAttribute('href'))).map(a => a.href).filter(h => /^https?:/i.test(h));
  return {t, links: [...new Set(links)].slice(0, 6)};
}"""
DOC_TYPES = ("pdf", "msword", "officedocument", "rtf", "opendocument")
# заголовок страницы-документа: «Согласие на рекламную рассылку» - документ, хотя слов о персональных данных в нём
# мало (hightime.agency/ads_agreement: было «открывается страница без текста документа»)
# Целыми словами и сочетаниями: «Расположение офиса», «Персональные тренировки», «Цена договорная», «Правила игры»
# документом не считаются
DOC_TITLE = re.compile(r"\bсогласи[еяю]\b|\bполитик\w* (?:конфиденц|обработ|в отношении|защит|персональн)|"
                       r"\bконфиденциальност|\bперсональных данных|\bоферт[аыу]?\b|\bсоглашени[еяю]\b|\bдоговор\b|"
                       r"\bдоговор\w* (?:оказания|купли|поставки|подряда)|\bправила (?:пользования|сайта|оказания|"
                       r"продажи|обработки|возврата)|\bположени[ея] (?:о|об)\b|\bусловия (?:использования|обработки|"
                       r"оказания|возврата)|\bprivacy\b|\bterms (?:of|and)\b|\bagreement\b|\bconsent\b", re.I)

# отметить поля, которые есть сразу после загрузки кода: всё остальное подгрузил скрипт (виджет)
EARLY_JS = r"""() => { for (const i of document.querySelectorAll('input, textarea')) i.setAttribute('data-clayler-early', '1'); }"""

# формы с телефоном или почтой: строка согласия, галочка, ссылки (в том числе в скрытых формах виджетов)
SCAN_JS = r"""() => {
  const PHONE = /(phone|tel\b|tel[_-]|телефон|mobile)/i, MAIL = /(e-?mail|почт)/i, NAME = /(name|имя|фио)/i;
  const CONS = /(персональн|согласи[еяю]|согласен|соглашаюсь|политик|конфиденциальн|152[-\s]?фз)/i;
  const DOCW = /(персональн|согласи|политик|конфиденц|оферт|privacy|policy|soglas|personal|konfid|agreement|oferta|pdn)/i;
  const vis = el => { const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05 && r.width > 2 && r.height > 2; };
  // видно ли поле: обёртки нулевой высоты бывают у видимых виджетов, поэтому смотрим само поле
  const shown = el => { const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && (el.checkVisibility ? el.checkVisibility({opacityProperty: true, visibilityProperty: true})
      : !!el.offsetParent); };
  const fixed = el => { for (let a = el; a; a = a.parentElement) { const s = getComputedStyle(a);
    if (s.position === 'fixed' || a.tagName === 'DIALOG') return true; } return false; };
  const txt = el => ((el.getClientRects().length ? el.innerText : el.textContent) || '').replace(/\s+/g, ' ').trim();
  const attrs = i => [i.type, i.name, i.id, i.placeholder, i.getAttribute('aria-label'), i.getAttribute('autocomplete')].join(' ');
  for (const a of ['data-clayler-form', 'data-clayler-line', 'data-clayler-link'])
    document.querySelectorAll(`[${a}]`).forEach(e => e.removeAttribute(a));
  const units = [], keys = [];
  for (const i of document.querySelectorAll('input, textarea')) {
    const t = (i.type || '').toLowerCase(), a = attrs(i);
    if (['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'search', 'file', 'image'].includes(t)) continue;
    const phone = t === 'tel' || PHONE.test(a), mail = t === 'email' || MAIL.test(a);
    if (!phone && !mail) continue;
    keys.push(i);
    let u = i.closest('form');
    if (!u) for (let p = i.parentElement, k = 0; p && p !== document.body && k < 8; p = p.parentElement, k++)
      if (p.querySelector('button, [type=submit], [role=button], [class*=submit], [class*=btn], [class*=button]')) { u = p; break; }
    if (!u) u = i.parentElement;
    if (u.querySelector('input[type=password]') || /(search|поиск)/i.test(u.getAttribute('role') + ' ' + u.className)) continue;
    let un = units.find(x => x.el === u);
    if (!un) { un = {el: u, phone: false, mail: false, early: true, inputs: []}; units.push(un); }
    un.inputs.push(i);
    un.phone = un.phone || phone; un.mail = un.mail || mail;
    if (!i.hasAttribute('data-clayler-early')) un.early = false;
  }
  const out = [];
  units.forEach((un, n) => {
    const u = un.el;
    // строка согласия: в форме, а если её там нет - рядом (в общем блоке, где нет полей других форм)
    const zones = [u];
    if (!CONS.test(txt(u))) for (let p = u.parentElement, k = 0; p && p !== document.body && k < 4; p = p.parentElement, k++) {
      if (!keys.filter(x => p.contains(x)).every(x => un.inputs.includes(x)) || txt(p).length > 3000) break;
      zones.push(p);
    }
    // самый маленький блок с этими словами, в котором нет полей ввода
    const uvis = un.inputs.some(shown);   // у видимой формы строка согласия тоже видна (скрытые копии виджета - мимо)
    let line = null, best = 1e9;
    for (const z of zones) {
      for (const el of [z, ...z.querySelectorAll('*')]) {
        if (['SCRIPT', 'STYLE', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'BUTTON'].includes(el.tagName)) continue;
        if (el.querySelector('input:not([type=checkbox]):not([type=hidden]), textarea, select')) continue;
        if (uvis && !el.getClientRects().length) continue;
        const t = txt(el);
        if (!t || t.length > 400 || t.length >= best || !CONS.test(t)) continue;
        line = el; best = t.length;
      }
      if (line) break;
    }
    // строка целиком («Я даю Согласие ... в соответствии с Политикой»): вверх, пока нет полей ввода
    if (line) for (let p = line.parentElement; p && p !== u.parentElement && txt(p).length < 300
                   && !p.querySelector('input:not([type=checkbox]):not([type=hidden]), textarea, select, button'); p = p.parentElement) line = p;
    // галочка: в строке, в её label, по label[for] или единственная в форме
    let box = null;
    if (line) {
      box = line.querySelector('input[type=checkbox], [role=checkbox]');
      const lab = line.closest('label') || (line.parentElement && line.parentElement.closest('label'));
      if (!box && lab) box = lab.querySelector('input[type=checkbox], [role=checkbox]') || (lab.htmlFor && document.getElementById(lab.htmlFor));
      if (!box) { const l = line.querySelector('label[for]') || (line.tagName === 'LABEL' && line.htmlFor ? line : null);
        if (l && l.htmlFor) box = document.getElementById(l.htmlFor); }
      if (!box) for (let p = line.parentElement, k = 0; p && k < 3 && !box; p = p.parentElement, k++) {
        const c = [...p.querySelectorAll('input[type=checkbox], [role=checkbox]')];
        if (c.length === 1) box = c[0];
        if (p === u) break;
      }
    }
    if (!box) { const c = [...u.querySelectorAll('input[type=checkbox], [role=checkbox]')]
      .filter(c => CONS.test(c.name + ' ' + c.id + ' ' + txt(c.closest('label') || c.parentElement)) || /agree|consent|soglas|personal|privacy|policy|pdn/i.test(c.name + ' ' + c.id));
      if (c.length === 1) box = c[0]; }
    let state = 'none';
    if (box) state = box.getAttribute('role') === 'checkbox' && box.tagName !== 'INPUT'
      ? (box.getAttribute('aria-checked') === 'true' ? 'checked' : 'unchecked') : (box.checked ? 'checked' : 'unchecked');
    let links = line ? [...line.querySelectorAll('a')] : [];
    // ссылки-кнопки виджета («#», javascript) без слов о документах - не ссылки на документ
    links = links.filter(a => DOCW.test(txt(a) + ' ' + (a.getAttribute('href') || '')) || !/^\s*(javascript:|#)/i.test(a.getAttribute('href') || ''));
    if (!links.length) links = [...u.querySelectorAll('a')].filter(a => DOCW.test(txt(a) + ' ' + (a.getAttribute('href') || '')));
    // один блок бывает в двух формах (вложенные формы виджета): номера через пробел
    const mark = (el, name, v) => el.setAttribute(name, ((el.getAttribute(name) || '') + ' ' + v).trim());
    mark(u, 'data-clayler-form', n);
    if (line) mark(line, 'data-clayler-line', n);
    const NOT = /^(отмена|закрыть|назад|cancel|close|×|x)$/i;
    const bs = [...u.querySelectorAll('button, [type=submit], [role=button]')].concat([...u.querySelectorAll('[class*=submit], [class*=btn], [class*=button]')])
      .filter(b => { const t = b.tagName === 'INPUT' ? b.value : txt(b); return t && t.length < 40 && !NOT.test(t.trim()); });
    const btn = bs[0];
    const fields = [];
    if (u.querySelector('input:not([type=hidden]):not([type=checkbox])') && [...u.querySelectorAll('input')].some(i => NAME.test(attrs(i)))) fields.push('имя');
    if (un.phone) fields.push('телефон');
    if (un.mail) fields.push('почта');
    if (u.querySelector('textarea')) fields.push('сообщение');
    out.push({n, visible: uvis, fixed: fixed(u), early: un.early, fields: fields.join(', '),
              btn: btn ? (btn.tagName === 'INPUT' ? btn.value : txt(btn)).slice(0, 40) : '',
              title: txt(u).slice(0, 80), consent: line ? txt(line).slice(0, 300) : '', box: state,
              links: links.slice(0, 6).map((a, j) => { mark(a, 'data-clayler-link', n + '-' + j);
                return {raw: a.getAttribute('href'), abs: a.href, text: txt(a).slice(0, 80)}; })});
  });
  return out;
}"""

# кнопки, которые раскрывают виджет: «Напишите нам», «Заказать звонок», значки чатов в углу экрана
TRIGGER_JS = r"""() => {
  const RX = /(напиш|чат|звон|позвон|перезвон|вопрос|заявк|консультац|связ|онлайн|online|сообщени|не в сети|offline|chat|callback|contact)/i;
  const vis = el => { const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.1 && r.width > 8 && r.height > 8
      && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth; };
  const fixed = el => { for (let a = el; a; a = a.parentElement) if (getComputedStyle(a).position === 'fixed') return true; return false; };
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.hasAttribute('data-clayler-done') || el.closest('form') || el.type === 'submit' || el.closest('[data-clayler]')) continue;
    if (['SCRIPT', 'STYLE', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'IFRAME', 'svg', 'path'].includes(el.tagName)) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 420 || r.height > 320 || !vis(el) || !fixed(el)) continue;
    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    const sig = t + ' ' + el.className + ' ' + el.id + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '');
    if (/cookie|куки|recaptcha|наверх|scroll.?top|up\b/i.test(sig) || t.length > 80) continue;
    const pointer = getComputedStyle(el).cursor === 'pointer' || ['A', 'BUTTON'].includes(el.tagName) || el.onclick;
    if (!pointer || !RX.test(sig)) continue;
    if (out.some(o => o.contains(el) || el.contains(o))) {   // из вложенных - самый маленький
      const i = out.findIndex(o => el.contains(o) || o.contains(el));
      if (out[i].contains(el)) out[i] = el;
      continue;
    }
    out.push(el);
  }
  return out.slice(0, 6).map((el, i) => { el.setAttribute('data-clayler-trg', i); return (el.innerText || el.className || '').toString().replace(/\s+/g, ' ').trim().slice(0, 40); });
}"""

# плашки cookie закрывают форму на снимке: прячем (только по тексту, виджеты не трогаем)
COOKIE_JS = r"""() => {
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (s.position !== 'fixed' || s.display === 'none' || !r.width || r.height > innerHeight * 0.5) continue;
    if (/cookie|куки/i.test(el.innerText || '') && !el.querySelector('[data-clayler-form]') && !el.closest('[data-clayler-form]'))
      el.style.setProperty('display', 'none', 'important');
  }
}"""

FRAME_JS = r"""([n, bad, label, color]) => {
  const box = (el, text, color, w) => {
    const r = el.getBoundingClientRect();
    const d = document.createElement('div');
    d.setAttribute('data-clayler', '1');
    d.style.cssText = `position:absolute;left:${r.left + scrollX - 4}px;top:${r.top + scrollY - 4}px;width:${r.width + 8}px;` +
      `height:${r.height + 8}px;border:${w}px solid ${color};border-radius:6px;z-index:2147483647;pointer-events:none;box-sizing:border-box`;
    if (text) {
      const t = document.createElement('div');
      t.setAttribute('data-clayler', '1');
      t.textContent = text;
      t.style.cssText = `position:absolute;left:-4px;top:-28px;background:${color};color:#fff;font:600 13px/1.4 Arial,sans-serif;` +
        'padding:2px 8px;border-radius:4px;white-space:nowrap';
      d.appendChild(t);
    }
    document.body.appendChild(d);
  };
  const f = document.querySelector(`[data-clayler-form~="${n}"]`);
  if (f) box(f, '', '#f08c00', 3);
  let first = true;
  for (const j of bad) {
    const a = document.querySelector(`[data-clayler-link~="${n}-${j}"]`);
    if (a) { box(a, first ? label : '', color, 3); first = false; }
  }
  if (first) { const l = document.querySelector(`[data-clayler-line~="${n}"]`) || f; if (l) box(l, label, color, 3); }
}"""


def _host(u):
    h = (urlsplit(u).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def href_problems(raw, abs_url):
    """Что не так в адресе ссылки, как он написан в коде страницы: [текст]."""
    if raw is None or not raw.strip():
        return ["у ссылки нет адреса"]
    r = raw.strip()
    if r == "#" or r.lower().startswith("javascript:"):
        return ["ссылка никуда не ведёт (вместо адреса «#» или javascript)"]
    out = []
    q = sorted(set(QUOTES.findall(raw)))
    if q:
        out.append("в адресе лишние символы " + " ".join(q))
    if ENC_QUOTES.search(raw):
        out.append("в адресе закодированные кавычки (%C2%BB, %22)")
    if raw != r or re.search(r"\s", r):
        out.append("в адресе пробелы")
    m = re.search(r"https?:/", r[1:], re.I)
    if m and r[m.start()] not in "=?&" and not r[:m.start() + 1].lower().endswith(("%3d", "url=")):
        out.append("внутри адреса ещё один адрес с http")
    plain = QUOTES.sub("", r).strip()
    if not re.match(r"(?i)(https?:)?//|/|#|mailto:|tel:", r):
        if out and re.match(r"(?i)https?://", plain):
            out.append(f"из-за этого браузер считает адрес относительным и открывает {abs_url}")
        elif not out:
            out.append("адрес без «/» в начале: с разных страниц ведёт в разные места")
    return out


def open_problems(res, abs_url, site):
    """Что открывается по ссылке: [текст]. res - {status, url, type, text} или {"error"}."""
    if not abs_url or not re.match(r"(?i)https?://", abs_url):
        return []
    if res.get("error"):
        # причина - как есть: раньше любая неудача (в том числе сбой самой проверки) писалась «сервер не ответил»,
        # а документ при обходе открывался (thehome.ru: политика - 200 за 0,15 с)
        return [f"документ не открылся при проверке ({res['error']})"]
    st = res.get("status") or 0
    if st >= 400:
        return [f"открывается ошибка {st}" + (" (страница не найдена)" if st in (404, 410) else "")]
    text = res.get("text") or ""
    doc = (any(t in (res.get("type") or "") for t in DOC_TYPES) or len(DOC_WORDS.findall(text)) >= 4
           or len(DEAL_WORDS.findall(text)) >= 6 or (bool(DOC_TITLE.search(res.get("title") or "")) and len(text) >= 1500))
    final = res.get("url") or abs_url
    # на главной слова о персональных данных бывают в подвале и формах - документом она всё равно не считается
    if urlsplit(final).path in ("", "/") and not urlsplit(final).query and urlsplit(abs_url).path not in ("", "/"):
        return ["вместо документа открывается главная страница"]
    if not doc:
        h = _host(final)
        if h and h not in site:
            return [f"ведёт на другой сайт ({h}), документа там нет"]
        return ["открывается страница без текста документа (политики, согласия, оферты)"]
    return []


def ids(text):
    """Реквизиты из текста: ИНН, ОГРН и есть ли название организации (ООО, ИП...)."""
    text = text or ""
    return {"inn": sorted(set(INN.findall(text))), "ogrn": sorted(set(OGRN.findall(text))),
            "named": bool(ORG_SHORT.search(text) or ORG_LONG.search(text))}


def operator(req, cache, site, site_text, doc_urls, log=print):
    """Политика конфиденциальности на сайте: указан ли оператор и совпадает ли ИНН/ОГРН с реквизитами сайта."""
    me = ids(site_text)
    docs = []
    for u in doc_urls:
        if len(docs) >= 3 or _host(u) not in site:
            continue
        r = _fetch(req, u, cache)
        text = r.get("text") or ""
        # политика - длинный документ: слова о персональных данных в нём десятки раз (а не в подвале и форме входа)
        if r.get("error") or (r.get("status") or 0) >= 400 or len(DOC_WORDS.findall(text)) < 10:
            continue
        if any(d["final"] == r.get("url") for d in docs):
            continue
        d = ids(text)
        d.update({"url": u, "final": r.get("url") or u})
        other = (d["inn"] and me["inn"] and not set(d["inn"]) & set(me["inn"])) or                 (d["ogrn"] and me["ogrn"] and not set(d["ogrn"]) & set(me["ogrn"]))
        d["problem"] = ("other" if other else "none" if not (d["inn"] or d["ogrn"] or d["named"]) else "")
        docs.append(d)
        if d["problem"]:
            log(f"   {u}: " + ("в политике реквизиты другой компании" if other else "в политике не указан оператор"))
    return {"site": me, "docs": docs}


def form_problems(f):
    """Проблемы самой формы (без ссылок): [(ключ, текст)]."""
    out = []
    if not f["consent"]:
        if not f["early"]:   # форма в коде страницы - это buy_no_consent, здесь только подгруженные скриптом
            out.append(("form", "в форме нет согласия на обработку персональных данных"))
        return out
    if f["box"] == "checked":
        out.append(("form", "галочка согласия стоит заранее - такое согласие не считается добровольным"))
    elif f["box"] == "none":
        out.append(("nobox", "нет галочки согласия"))
    if not f["links"]:
        out.append(("form", "в строке согласия нет ссылки на политику или текст согласия"))
    return out


def pick(store):
    """Страницы: главная, 1-2 с формами из разных разделов, одна обычная поглубже (статья, услуга)."""
    rows = store.db.execute("SELECT p.url, p.shop, u.depth FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 "
                            "AND u.kind='page' AND p.status=200 AND (p.indexable=1 OR p.indexable IS NULL) "
                            "ORDER BY u.depth, p.url LIMIT 3000").fetchall()
    if not rows:
        return []
    start = store.get_meta("start", "") or rows[0][0]
    out, secs = [], set()
    home = next((u for u, _, _ in rows if u.rstrip("/") == start.rstrip("/") or urlsplit(u).path in ("", "/")), rows[0][0])
    out.append(home)
    secs.add(urlsplit(home).path.strip("/").split("/")[0])
    for u, raw, _ in rows:
        if len(out) >= MAX_PAGES - 1:
            break
        try:
            f = json.loads(raw) if raw else {}
        except ValueError:
            f = {}
        forms = [fm for fm in f.get("forms") or [] if fm.get("phone") or fm.get("email")]
        sec = urlsplit(u).path.strip("/").split("/")[0]
        if forms and u not in out and sec not in secs:
            out.append(u)
            secs.add(sec)
    deep = [u for u, _, d in rows if d and d >= 2 and u not in out and urlsplit(u).path.strip("/").split("/")[0] not in secs]
    if not deep:
        deep = [u for u, _, d in rows if u not in out]
    out += deep[:MAX_PAGES - len(out)]
    return out[:MAX_PAGES]


def _sig(f):
    """Одна и та же форма: надпись на кнопке и поля (строка согласия у виджетов появляется, когда их раскрывают)."""
    return (f["btn"], f["fields"])


def _scan(page):
    """[(frame, форма)] по всем фреймам страницы."""
    out = []
    for fr in page.frames:
        try:
            for f in fr.evaluate(SCAN_JS):
                out.append((fr, f))
        except Exception:
            pass
    return out


def _doc(status, url, typ, body):
    text = title = ""
    if "html" in typ or "text" in typ:
        body = body[:600000]
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
        title = " ".join(H.unescape(m.group(1)).split()) if m else ""
        body = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", body)
        text = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", body)))
    return {"status": status, "url": url, "type": typ, "text": text[:200000], "title": title}


def _why(e):
    s = str(e).split("\n")[0]
    return "сервер не ответил за 20 с" if "timeout" in s.lower() or "timed out" in s.lower() else s[:120]


def _fetch(req, url, cache):
    """Документ по ссылке из формы. Не открылся через браузер - ещё раз, потом так же, как при обходе (fetcher):
    одна неудачная попытка не должна становиться «документ не открывается» (thehome.ru: политика при
    обходе - 200 за 0,15 с, а в отчёте «сервер не ответил»). Не открылся никак - {"error": причина}."""
    if url in cache:
        return cache[url]
    why = ""
    for _ in range(2):
        try:
            r = req.get(url, timeout=20000, max_redirects=10, fail_on_status_code=False)
            typ = (r.headers.get("content-type") or "").lower()
            res = _doc(r.status, r.url, typ, r.text() if "html" in typ or "text" in typ else "")
            r.dispose()
            cache[url] = res
            return res
        except Exception as e:
            why = _why(e)
    try:
        from urllib.parse import urljoin
        from .fetcher import Fetcher, UA_PRESETS
        f, u = Fetcher(UA_PRESETS["chrome"], timeout=20), url
        try:
            for _ in range(6):   # загрузчик программы по редиректам сам не идёт
                r = f.fetch(u)
                if not (300 <= (r.status or 0) < 400 and r.location):
                    break
                u = urljoin(u, r.location)
        finally:
            f.close()   # соединения не копятся: документов на сайте с формами бывает много
        if r.status and not r.error:
            res = _doc(r.status, u, r.content_type, (r.body or b"").decode("utf-8", "replace"))
            cache[url] = res
            return res
        why = r.error or why
    except Exception as e:
        why = why or _why(e)
    res = {"error": why or "причина не записана"}
    cache[url] = res
    return res


def _open(page, url, timeout):
    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
    try:
        page.evaluate(EARLY_JS)
    except Exception:
        pass
    for state, ms in (("load", 12000), ("networkidle", 5000)):
        try:
            page.wait_for_load_state(state, timeout=ms)
        except Exception:
            pass
    page.wait_for_timeout(WAIT_WIDGETS)


def _click(page, sel):
    try:
        page.locator(sel).first.click(timeout=2500)
    except Exception:
        try:
            page.evaluate(f"() => {{ const e = document.querySelector('{sel}'); if (e) e.click(); }}")
        except Exception:
            return False
    return True


def _reveal(page, sig, url, timeout):
    """Раскрыть скрытую форму виджета: нажимать кнопки чатов и «напишите нам», пока форма не станет видна.
    → (frame, форма) или None."""
    clicks = 0
    for _ in range(4):
        names = page.evaluate(TRIGGER_JS)
        if not names:
            return None
        for i in range(len(names)):
            if clicks >= MAX_CLICKS:
                return None
            sel = f'[data-clayler-trg="{i}"]'
            try:
                page.evaluate(f"() => {{ const e = document.querySelector('{sel}'); if (e) e.setAttribute('data-clayler-done', '1'); }}")
            except Exception:
                continue
            if not _click(page, sel):
                continue
            clicks += 1
            page.wait_for_timeout(1500)
            if page.url.split("#")[0] != url.split("#")[0]:   # кнопка увела на другую страницу - вернуться
                _open(page, url, timeout)
                return None
            for fr, f in _scan(page):
                if f["visible"] and _sig(f) == sig:
                    return fr, f
        page.evaluate("() => document.querySelectorAll('[data-clayler-trg]').forEach(e => e.removeAttribute('data-clayler-trg'))")
    return None


def _check(f, ctx, cache, site):
    for lk in f["links"]:
        lk["problems"] = href_problems(lk["raw"], lk["abs"])
        if re.match(r"(?i)https?://", lk["abs"] or ""):
            lk["problems"] += open_problems(_fetch(ctx.request, lk["abs"], cache), lk["abs"], site)
    fp = form_problems(f)
    return fp, [j for j, lk in enumerate(f["links"]) if lk["problems"]]


def take(urls, shots_dir, site, log=print, timeout=30.0, extra=()):
    from playwright.sync_api import sync_playwright
    os.makedirs(shots_dir, exist_ok=True)
    forms, seen, cache, not_opened, failed = [], {}, {}, [], []
    site_text, doc_urls = [], []
    blocked = []

    route = guard_route(blocked)

    n_shot = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for url in urls:
                ctx = browser.new_context(viewport={"width": VIEW[0], "height": VIEW[1]}, ignore_https_errors=True,
                                          service_workers="block", locale="ru-RU")
                ctx.add_init_script(GUARD_JS)
                ctx.route("**/*", route)
                page = ctx.new_page()
                try:
                    _open(page, url, timeout)
                    try:
                        foot = page.evaluate(FOOT_JS)
                        site_text.append(foot["t"])
                        doc_urls.extend(foot["links"])
                    except Exception:
                        pass
                    found = _scan(page)
                    dirty = False   # на странице уже что-то нажимали: перед следующей формой открыть заново
                    for fr, f in found:
                        key = _sig(f)
                        if key in seen:
                            seen[key]["pages"].append(url)
                            continue
                        same = (f["consent"][:100], tuple(lk["raw"] or "" for lk in f["links"]))
                        if f["links"] and same in seen:   # та же строка согласия во вложенной форме виджета
                            seen[same]["pages"].append(url)
                            continue
                        fp, bad = _check(f, ctx, cache, site)
                        widget = f["fixed"] or not f["early"]
                        if not f["visible"] and f["early"] and not f["consent"] and not bad:
                            seen[key] = {"pages": [url]}   # форма из кода страницы без согласия - это buy_no_consent
                            continue
                        if not f["visible"] and (bad or fp or not f["consent"]):
                            if dirty:
                                _open(page, url, timeout)
                            dirty = True
                            got = _reveal(page, key, url, timeout)
                            if got:
                                fr, f = got
                                fp, bad = _check(f, ctx, cache, site)
                            elif not bad and not f["consent"]:
                                # скрытая форма без строки согласия: строка часто появляется только при открытии
                                not_opened.append({"url": url, "btn": f["btn"] or f["fields"]})
                                log(f"   {url}: форму «{f['btn'] or f['fields']}» не удалось раскрыть - не проверена")
                                seen[key] = {"pages": [url]}
                                continue
                            else:
                                fp = [x for x in fp if "нет согласия" not in x[1]]
                        rec = {"url": url, "pages": [url], "where": "виджет или всплывающее окно" if widget else "на странице",
                               "btn": f["btn"], "fields": f["fields"], "consent": f["consent"], "box": f["box"],
                               "early": f["early"], "links": f["links"], "problems": [t for k, t in fp if k == "form"],
                               "nobox": any(k == "nobox" for k, _ in fp), "file": "", "shown": f["visible"]}
                        seen[key] = rec
                        if f["links"]:
                            seen[(f["consent"][:100], tuple(lk["raw"] or "" for lk in f["links"]))] = rec
                        forms.append(rec)
                        doc_urls.extend(lk["abs"] for lk in f["links"] if not lk["problems"] and lk.get("abs"))
                        if not bad and not rec["problems"]:
                            continue
                        if not f["visible"]:
                            log(f"   {url}: форму «{f['btn'] or f['fields']}» не удалось показать, проблема найдена в коде")
                            continue
                        try:
                            page.evaluate(COOKIE_JS)
                            fr.locator(f'[data-clayler-form~="{f["n"]}"]').first.scroll_into_view_if_needed(timeout=3000)
                            page.wait_for_timeout(400)
                            label = ("Ссылка не открывает документ" if bad else
                                     "Галочка стоит заранее" if f["box"] == "checked" else "Нет согласия")
                            fr.evaluate(FRAME_JS, [f["n"], bad, label, "#e0201b"])
                            n_shot += 1
                            rec["file"] = f"{n_shot:02d}.jpg"
                            page.screenshot(path=os.path.join(shots_dir, rec["file"]), type="jpeg", quality=74)
                            fr.evaluate("() => document.querySelectorAll('[data-clayler]').forEach(e => e.remove())")
                        except Exception as e:
                            log(f"   {url}: снимок формы не сделан - {str(e).splitlines()[0][:100]}")
                    log(f"   {url}: форм с телефоном или почтой - {len(found)}")
                except Exception as e:
                    s = str(e).strip().splitlines()
                    failed.append(url)
                    from .plain_errors import browser_error
                    log(f"   {url}: страница не открылась - {browser_error(s[0] if s else type(e).__name__)}")
                finally:
                    ctx.close()
            op = None
            if len(failed) < len(urls):
                req = pw.request.new_context(ignore_https_errors=True, extra_http_headers={"Accept-Language": "ru-RU"})
                try:
                    for u in extra:   # контакты и реквизиты: ИНН сайта часто только там
                        site_text.append(_fetch(req, u, cache).get("text") or "")
                    op = operator(req, cache, site, " ".join(site_text), list(dict.fromkeys(u.split("#")[0] for u in doc_urls)), log)
                finally:
                    req.dispose()
        finally:
            browser.close()
    for r in forms:
        r["pages"] = sorted(set(r["pages"]))
    return {"forms": forms, "not_opened": not_opened, "failed": failed, "blocked": len(blocked), "operator": op}


def ensure(store, out_dir, log=print):
    shots_dir = os.path.join(out_dir, DIR)
    old = store.get_meta("consent_forms", None)
    # сайт не открылся совсем (временная блокировка, нет интернета) - в следующий раз попробовать снова
    if old and old.get("version") == VERSION and not (old.get("failed") and not old.get("forms")) and all(os.path.exists(os.path.join(shots_dir, f["file"]))
                                                      for f in old.get("forms", []) if f.get("file")):
        return old
    if os.environ.get("CLAYLER_NO_CONSENT_CHECK") == "1":
        return old
    urls = pick(store)
    if not urls:
        return old
    from .mobile_view import available
    if not available():
        res = {"version": VERSION, "skipped": "no_browser", "pages": [], "forms": []}
        store.set_meta("consent_forms", res)
        store.commit()
        return res
    log(f"Проверяю согласие на обработку персональных данных в формах и виджетах на {len(urls)} страницах "
        "(формы не отправляются)...")
    if os.path.isdir(shots_dir):
        for f in os.listdir(shots_dir):
            try:
                os.remove(os.path.join(shots_dir, f))
            except OSError:
                pass
    start = store.get_meta("start", "") or urls[0]
    site = {_host(start), _host(urls[0])}
    extra = [r[0] for r in store.db.execute(
        "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND p.status=200 ORDER BY u.depth, "
        "length(p.url) LIMIT 2000") if CONTACTS.search(urlsplit(r[0]).path)][:2]
    try:
        res = take(urls, shots_dir, site, log, extra=extra)
    except Exception as e:
        log("Формы не проверены: " + str(e)[:150])
        return old
    res.update({"version": VERSION, "pages": urls})
    store.set_meta("consent_forms", res)
    store.commit()
    return res


def bad_forms(res):
    return [f for f in (res or {}).get("forms") or [] if f.get("problems") or any(lk.get("problems") for lk in f["links"])]


def html_block(res, h2="h2", h2_cls="sec", limit=None):
    items = bad_forms(res)
    if not items:
        return ""
    cards = []
    for f in items[:limit]:
        what = [f"ссылка «{H.escape(lk['text'] or lk['raw'] or '')}»: " + H.escape("; ".join(lk["problems"]))
                for lk in f["links"] if lk.get("problems")] + [H.escape(p) for p in f["problems"]]
        img = (f'<img src="{DIR}/{H.escape(f["file"])}" loading="lazy" alt="">' if f.get("file") else
               '<p class="mut" style="padding:20px">Форму не удалось показать на экране: она спрятана в виджете и не '
               'раскрылась. Проблема найдена в коде формы.</p>')
        cards.append(f'<figure class="d">{img}<figcaption><b style="color:var(--crit)">Форма «'
                     f'{H.escape(f["btn"] or f["fields"] or "без надписи")}» ({H.escape(f["where"])})</b><br>'
                     + "<br>".join(w[:1].upper() + w[1:] + "." for w in what)
                     + f'<br><span class="mut">Например:</span> <a href="{H.escape(f["url"])}" target="_blank" '
                     f'rel="noopener">{H.escape(f["url"])}</a></figcaption></figure>')
    return (f'<{h2} class="{h2_cls}">Согласие на обработку персональных данных в формах</{h2}>'
            f'<p class="mut">Формы и виджеты (чаты, «перезвоним», офлайн-формы) открыли в браузере и проверили '
            f'строку согласия: есть ли галочка и открываются ли документы по ссылкам. Формы не отправлялись. '
            f'Форм с проблемой: {len(items)}.</p><div class="psh">{"".join(cards)}</div>')


def audit_html(summary):
    b = html_block(summary.get("consent_forms"), h2="h2", h2_cls="", limit=4)
    return f'<section class="pt">{b}</section>' if b else ""
