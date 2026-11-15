"""Снимки страниц с обведённой ошибкой: для нескольких найденных проблем открываем пример страницы
во встроенном Chromium и обводим красной рамкой то, о чём речь: что вылезает за край экрана телефона, все H1,
текст, который выглядит как заголовок, но не H1, маленькие кнопки вплотную, мелкий текст. Клиент видит ошибку
глазами, а не только строкой в таблице.
Снимается при сборке отчёта (нужны интернет и playwright, как для снимков телефона), не больше SHOTS_MAX страниц,
по SHOTS_PER_ISSUE на проблему; результат запоминается в meta «problem_shots», при «Обновить отчёт» снимки
не переснимаются, если файлы на месте. Выключить: CLAYLER_NO_PROBLEM_SHOTS=1."""
import html as H
import os

DIR = "снимки ошибок"
SHOTS_MAX = 8
SHOTS_PER_ISSUE = 2
VERSION = 1
DESKTOP = (1366, 800)

# проблема → (телефон или компьютер, подпись к снимку)
KINDS = {
    "mobile_wide": ("mobile", "На телефоне страница шире экрана. Красным обведено то, что вылезает за край, "
                              "пунктир - край экрана телефона."),
    "h1_missing": ("desktop", "Нет главного заголовка H1. Красным обведён текст, который выглядит как заголовок "
                              "страницы: его стоит сделать H1."),
    "h1_multi": ("desktop", "Несколько H1 на странице. Красным обведены все заголовки H1, оставить нужно один."),
    "mobile_taps": ("mobile", "Маленькие кнопки и ссылки вплотную друг к другу: по ним трудно попасть пальцем. "
                              "Обведены примеры."),
    "mobile_small_text": ("mobile", "Мелкий текст на телефоне (меньше 12 px). Обведены примеры."),
}

MARK_JS = r"""([mode, W]) => {
  const de = document.documentElement, sx = window.scrollX, sy = window.scrollY;
  const visible = el => {
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const found = [];
  let note = '';
  if (mode === 'mobile_wide') {
    const sw = Math.max(de.scrollWidth, document.body ? document.body.scrollWidth : 0);
    if (sw > W + 1 || window.innerWidth > W + 1) {
      for (const el of document.body ? document.body.querySelectorAll('*') : []) {
        const r = el.getBoundingClientRect();
        if (r.right <= W + 1 || r.width === 0 || !visible(el)) continue;
        let clipped = false;
        for (let a = el.parentElement; a && a !== document.body && a !== de; a = a.parentElement)
          if (getComputedStyle(a).overflowX !== 'visible') { clipped = true; break; }
        if (clipped || found.some(o => o.el.contains(el))) continue;
        found.push({el, label: 'за краем экрана'});
        if (found.length >= 6) break;
      }
    }
  } else if (mode === 'h1_multi') {
    const all = [...document.querySelectorAll('h1')];
    all.filter(visible).slice(0, 6).forEach((el, i) => found.push({el, label: 'H1 №' + (i + 1)}));
    const hidden = all.length - all.filter(visible).length;
    if (hidden > 0) note = 'ещё скрытых H1: ' + hidden;
  } else if (mode === 'h1_missing') {
    // самый крупный текст в первых 1200 px страницы, не в меню и не ссылка
    let best = null, bestFs = 19;
    for (const el of document.body ? document.body.querySelectorAll('*') : []) {
      if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG'].includes(el.tagName)) continue;
      const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
      if (own.length < 4 || !visible(el)) continue;
      if (el.closest('a, nav, header, footer, button, [role=navigation]')) continue;
      const r = el.getBoundingClientRect();
      if (r.top + sy > 1200) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs > bestFs) { best = el; bestFs = fs; }
    }
    // в подписи - что это на самом деле (05.11.2026, просьба пользователя): «это H2, а главный заголовок - H1»
    if (best) {
      const tag = best.tagName.toLowerCase(), hx = /^h[2-6]$/.test(tag);
      found.push({el: best, label: hx ? `это ${tag.toUpperCase()}, а главный заголовок страницы должен быть H1`
                                      : `выглядит как заголовок, но это <${tag}>, а не H1`});
    }
  } else if (mode === 'mobile_taps') {
    const all = [];
    for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], [onclick]')) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right < 0 || r.left > W) continue;
      all.push([el, r, r.left + r.width / 2, r.top + r.height / 2]);
    }
    for (const [el, r, cx, cy] of all) {
      if (r.width >= 24 && r.height >= 24) continue;
      const p = el.parentElement;
      if (getComputedStyle(el).display === 'inline' && p && p.textContent.trim().length > el.textContent.trim().length + 20) continue;
      if (!all.some(([o, , ox, oy]) => o !== el && !o.contains(el) && !el.contains(o) && Math.hypot(ox - cx, oy - cy) < 24)) continue;
      found.push({el, label: Math.round(r.width) + '×' + Math.round(r.height)});
      if (found.length >= 12) break;
    }
  } else if (mode === 'mobile_small_text') {
    const seen = new Set();
    const walker = document.createTreeWalker(document.body || de, NodeFilter.SHOW_TEXT);
    while (walker.nextNode() && found.length < 12) {
      const t = walker.currentNode.textContent.trim(), el = walker.currentNode.parentElement;
      if (t.length < 3 || !el || seen.has(el) || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName) || !visible(el)) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < 12) { seen.add(el); found.push({el, label: (Math.round(fs * 10) / 10) + ' px'}); }
    }
  }
  // рисуем рамки поверх страницы (в координатах документа, чтобы не уезжали при прокрутке)
  const box = (x, y, w, h, css) => {
    const d = document.createElement('div');
    d.setAttribute('data-clayler', '1');
    d.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;z-index:2147483647;pointer-events:none;box-sizing:border-box;` + css;
    de.appendChild(d);
    return d;
  };
  // рамка - по тому, что видно (текст - по самим словам, а не по блоку во всю ширину), и сама переставляется, когда
  // меняется ширина окна или разметка (05.11.2026: в копии страницы рамка съезжала с заголовка при сужении окна)
  // по словам - только у «нет H1» (крупный текст); у «шире экрана» и «маленьких кнопок» проблема - сам размер
  // элемента, рамка по нему (ревью 05.11.2026). По словам, но не шире самого элемента: спрятанное подменю не растянет
  const rectOf = el => {
    const own = el.getBoundingClientRect();
    if (mode !== 'h1_missing' || !el.firstChild) return own;
    let r = null;
    try { const rg = document.createRange(); rg.selectNodeContents(el); r = rg.getBoundingClientRect(); } catch (e) {}
    if (!r || r.width < 2 || r.height < 2) return own;
    const L = Math.max(r.left, own.left), T = Math.max(r.top, own.top), R = Math.min(r.right, own.right), B = Math.min(r.bottom, own.bottom);
    return R - L >= 2 && B - T >= 2 ? {left: L, top: T, width: R - L, height: B - T} : own;
  };
  const placed = [];
  const place = ([el, b, t]) => {
    const r = rectOf(el), x = r.left + window.scrollX, y = r.top + window.scrollY;
    Object.assign(b.style, {left: (x - 3) + 'px', top: (y - 3) + 'px', width: (r.width + 6) + 'px', height: (r.height + 6) + 'px'});
    Object.assign(t.style, {left: Math.max(0, x - 3) + 'px', top: Math.max(0, y - 25) + 'px'});
    return [y, r];
  };
  const tops = [], bottoms = [];
  for (const {el, label} of found) {
    const b = box(0, 0, 0, 0, 'border:3px solid #e0201b;border-radius:4px;box-shadow:0 0 0 2px rgba(255,255,255,.8)');
    const t = box(0, 0, 'auto', 'auto',
      'background:#e0201b;color:#fff;font:600 13px/1.5 Arial,sans-serif;padding:1px 7px;border-radius:4px;white-space:nowrap;width:auto;height:auto');
    t.textContent = label;
    const [y, r] = place([el, b, t]);
    placed.push([el, b, t]);
    tops.push(y); bottoms.push(y + r.height);
  }
  if (placed.length) {
    const again = () => placed.forEach(place);
    window.addEventListener('resize', again);
    try { new ResizeObserver(again).observe(document.body); } catch (e) {}
    setInterval(again, 700);
  }
  if (mode === 'mobile_wide' && found.length) {
    const h = Math.max(de.scrollHeight, document.body ? document.body.scrollHeight : 0);
    box(W, 0, 0, h, 'border-left:3px dashed #e0201b');
    const t = box(W + 6, sy + 8, 'auto', 'auto', 'background:#e0201b;color:#fff;font:600 13px/1.5 Arial,sans-serif;padding:1px 7px;border-radius:4px;white-space:nowrap;width:auto;height:auto');
    t.textContent = 'край экрана';
  }
  if (mode === 'h1_missing' && !found.length) {
    const t = box(sx + 10, sy + 10, 'auto', 'auto', 'background:#e0201b;color:#fff;font:600 15px/1.5 Arial,sans-serif;padding:4px 10px;border-radius:4px;width:auto;height:auto');
    t.textContent = 'На странице нет заголовка H1';
    tops.push(sy);
  }
  return {n: found.length, top: tops.length ? Math.min(...tops) : null, note,
          bottom: bottoms.length ? Math.max(...bottoms) : null,
          dw: Math.max(de.scrollWidth, document.body ? document.body.scrollWidth : 0, window.innerWidth),
          dh: Math.max(de.scrollHeight, document.body ? document.body.scrollHeight : 0)};
}"""

# Всплывающие окна, баннер cookie, чат и затемнение закрывают страницу: прячем всё, что «прибито» к экрану
# (position: fixed), и возвращаем прокрутку, которую окна иногда отключают. Вызывается перед разметкой и перед снимком
# (окно может выскочить по таймеру уже после разметки).
HIDE_JS = r"""() => {
  for (const el of document.querySelectorAll('body *')) {
    if (el.hasAttribute('data-clayler')) continue;
    const s = getComputedStyle(el);
    if (s.position === 'fixed' || ((el.tagName === 'DIALOG' || el.getAttribute('aria-modal') === 'true') && s.display !== 'none'))
      el.style.setProperty('display', 'none', 'important');
  }
  for (const el of [document.documentElement, document.body]) if (el) {
    el.style.setProperty('overflow', 'visible', 'important');
    if (getComputedStyle(el).position === 'fixed') el.style.setProperty('position', 'static', 'important');
  }
}"""


def _pick(issues):
    """[(ключ проблемы, адрес)] — по SHOTS_PER_ISSUE примеров, всего не больше SHOTS_MAX, страницы не повторяются."""
    by_key = {i.key: i for i in issues}
    out, used = [], set()
    for key in KINDS:
        i = by_key.get(key)
        if not i:
            continue
        n = 0
        for r in i.rows:
            url = r[0] if r else ""
            if not isinstance(url, str) or not url.startswith("http") or (key, url) in used:
                continue
            out.append((key, url))
            used.add((key, url))
            n += 1
            if n >= SHOTS_PER_ISSUE or len(out) >= SHOTS_MAX:
                break
        if len(out) >= SHOTS_MAX:
            break
    return out


def take(todo, shots_dir, log=print, timeout=30.0):
    from playwright.sync_api import sync_playwright
    from .mobile_view import UA, WIDTH, HEIGHT
    os.makedirs(shots_dir, exist_ok=True)
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for k, (key, url) in enumerate(todo, 1):
                mode = KINDS[key][0]
                if mode == "mobile":
                    ctx = browser.new_context(user_agent=UA, viewport={"width": WIDTH, "height": HEIGHT},
                                              device_scale_factor=2, is_mobile=True, has_touch=True,
                                              ignore_https_errors=True, service_workers="block", locale="ru-RU")
                else:
                    ctx = browser.new_context(viewport={"width": DESKTOP[0], "height": DESKTOP[1]},
                                              ignore_https_errors=True, service_workers="block", locale="ru-RU")
                page = ctx.new_page()
                try:
                    # не ждём, пока догрузятся счётчики и виджеты: на тяжёлых сайтах «load» бывает дольше 30 с
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    for state, ms in (("load", 10000), ("networkidle", 3000)):
                        try:
                            page.wait_for_load_state(state, timeout=ms)
                        except Exception:
                            pass
                    page.evaluate(HIDE_JS)
                    res = page.evaluate(MARK_JS, [key, WIDTH])
                    if res["n"] or key == "h1_missing":
                        page.wait_for_timeout(500)
                        page.evaluate(HIDE_JS)
                        # кусок страницы от первой рамки вниз на экран; по ширине — вся страница, чтобы было видно,
                        # что вылезает за край телефона
                        vh = HEIGHT if mode == "mobile" else DESKTOP[1]
                        y = max(0, min((res["top"] or 0) - 90, res["dh"] - vh))
                        # все рамки (несколько H1 по всей странице) — но не выше 2,5 экрана
                        h = min(max(vh, (res["bottom"] or 0) - y + 60), int(vh * 2.5), res["dh"] - y)
                        name = f"{k:02d}.jpg"
                        page.screenshot(path=os.path.join(shots_dir, name), type="jpeg", quality=72, full_page=True,
                                        clip={"x": 0, "y": y, "width": res["dw"], "height": h})
                        out.append({"key": key, "url": url, "file": name, "n": res["n"], "note": res.get("note") or "",
                                    "mode": mode})
                        log(f"   {k}/{len(todo)} {url} - обведено: {res['n']}")
                    else:
                        log(f"   {k}/{len(todo)} {url} - ошибка на странице сейчас не видна, снимок не нужен")
                except Exception as e:
                    s = str(e).strip().splitlines()
                    log(f"   {k}/{len(todo)} {url} - не открылась: {(s[0] if s else type(e).__name__)[:120]}")
                finally:
                    ctx.close()
        finally:
            browser.close()
    return out


def ensure(store, issues, out_dir, log=print):
    """Снимки для этой проверки: из meta, если файлы на месте, иначе снимаем заново. Возвращает список снимков."""
    shots_dir = os.path.join(out_dir, DIR)
    old = store.get_meta("problem_shots", None)
    if old and old.get("version") == VERSION and all(os.path.exists(os.path.join(shots_dir, s["file"]))
                                                      for s in old.get("shots", [])):
        return old["shots"]
    if os.environ.get("CLAYLER_NO_PROBLEM_SHOTS") == "1":
        return []
    from .mobile_view import available
    todo = _pick(issues)
    if not todo or not available():
        return []
    log(f"Снимаю страницы с обведённой ошибкой ({len(todo)} шт.)...")
    if os.path.isdir(shots_dir):
        for f in os.listdir(shots_dir):
            try:
                os.remove(os.path.join(shots_dir, f))
            except OSError:
                pass
    try:
        shots = take(todo, shots_dir, log)
    except Exception as e:
        log("Снимки с ошибками не сделаны: " + str(e)[:150])
        return []
    store.set_meta("problem_shots", {"version": VERSION, "shots": shots})
    store.commit()
    return shots


CSS = """.psh{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin:10px 0}
.psh figure{margin:0;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:8px;break-inside:avoid}
.psh img{width:100%;border-radius:6px;border:1px solid var(--bd);display:block}
.psh figure.m img{max-width:260px;margin:0 auto}
.psh figcaption{font-size:13px;line-height:1.45;margin-top:6px;overflow-wrap:anywhere}"""


def html_block(shots, h2="h2", h2_cls="sec", limit=None):
    if not shots:
        return ""
    cards = []
    for s in shots[:limit]:
        cap = KINDS.get(s["key"], ("", ""))[1]
        note = f' ({H.escape(s["note"])})' if s.get("note") else ""
        cards.append(f'<figure class="{"m" if s.get("mode") == "mobile" else "d"}">'
                     f'<img src="{DIR}/{H.escape(s["file"])}" loading="lazy" alt="">'
                     f'<figcaption><b>{H.escape(cap)}</b>{note}<br><a href="{H.escape(s["url"])}" data-key="{H.escape(s["key"])}" target="_blank" '
                     f'rel="noopener">{H.escape(s["url"])}</a></figcaption></figure>')
    return (f'<{h2} class="{h2_cls}">Ошибки на снимках страниц</{h2}>'
            '<p class="mut">Несколько примеров, чтобы ошибку было видно глазами: страница открыта в браузере, '
            'проблемное место обведено красной рамкой. Полные списки страниц - в разделах с проблемами.</p>'
            f'<div class="psh">{"".join(cards)}</div>')


def audit_html(summary):
    b = html_block(summary.get("problem_shots"), h2="h2", h2_cls="", limit=6)
    return f'<section class="pt">{b}</section>' if b else ""
