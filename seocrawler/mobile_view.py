"""Как страница выглядит на телефоне: открываем её во встроенном Chromium шириной 375 px (как iPhone и большинство
Android), по-настоящему, с картинками и шрифтами, и смотрим:
- не шире ли страница экрана (горизонтальная прокрутка) и что именно вылезает за край;
- много ли текста мельче 12 px (правило Lighthouse: разборчиво, если так написано не меньше 60% текста);
- кнопки и ссылки меньше 24×24 px (минимум по WCAG 2.2; Google советует 48×48) — кроме ссылок внутри текста;
- сколько весит страница при первом открытии (всё, что браузер скачал, без кеша) и сколько запросов;
- снимок первого экрана.
Работает, только если установлен playwright и скачан Chromium (как режим JavaScript)."""
import os
import time

WIDTH, HEIGHT = 375, 812
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

# Что ищем на странице. Возвращает словарь; все размеры — в CSS-пикселях.
LAYOUT_JS = r"""(W) => {
  // если вёрстка шире экрана, телефон расширяет окно (innerWidth > W) и уменьшает страницу - это тоже «шире экрана»
  const vw = window.innerWidth, de = document.documentElement;
  const sw = Math.max(de.scrollWidth, document.body ? document.body.scrollWidth : 0);
  const visible = el => {
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const name = el => {
    let n = el.tagName.toLowerCase();
    if (el.id) n += '#' + el.id;
    else if (typeof el.className === 'string' && el.className.trim()) n += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.');
    return n;
  };
  // что вылезает за правый край: самые внешние такие элементы (их детей не повторяем)
  const over = [];
  if (sw > W + 1 || vw > W + 1) {
    for (const el of document.body ? document.body.querySelectorAll('*') : []) {
      const r = el.getBoundingClientRect();
      if (r.right <= W + 1 || r.width === 0 || !visible(el)) continue;
      // слайды карусели и прочее внутри блока с обрезкой (overflow: hidden/auto) страницу не расширяют
      let clipped = false;
      for (let a = el.parentElement; a && a !== document.body && a !== de; a = a.parentElement)
        if (getComputedStyle(a).overflowX !== 'visible') { clipped = true; break; }
      if (clipped) continue;
      if (over.some(o => o.contains(el))) continue;
      over.push(el);
      if (over.length >= 5) break;
    }
  }
  // мелкий текст: доля символов, написанных шрифтом меньше 12 px
  let total = 0, small = 0; const smallEx = [];
  const walker = document.createTreeWalker(document.body || de, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode.textContent.trim();
    const el = walker.currentNode.parentElement;
    if (!t || !el || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName) || !visible(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    total += t.length;
    if (fs < 12) {
      small += t.length;
      if (smallEx.length < 3 && t.length >= 3) smallEx.push(`${Math.round(fs * 10) / 10} px: ${t.slice(0, 50)}`);
    }
  }
  // маленькие кнопки и ссылки. Как в WCAG 2.2: маленькая цель - не беда, если вокруг неё хватает места
  // (центры соседних целей дальше 24 px). Ссылки внутри предложения не считаем - их размер задаёт строка текста.
  const all = [];
  for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], [onclick]')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right < 0 || r.left > W) continue;
    all.push([el, r, r.left + r.width / 2, r.top + r.height / 2]);
  }
  const taps = [];
  let tapCount = 0;
  for (const [el, r, cx, cy] of all) {
    if (r.width >= 24 && r.height >= 24) continue;
    const p = el.parentElement;
    if (getComputedStyle(el).display === 'inline' && p && p.textContent.trim().length > el.textContent.trim().length + 20) continue;
    const crowded = all.some(([o, , ox, oy]) => o !== el && !o.contains(el) && !el.contains(o) && Math.hypot(ox - cx, oy - cy) < 24);
    if (!crowded) continue;
    tapCount++;
    if (taps.length < 3) {
      const label = (el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || el.value || name(el)).trim().replace(/\s+/g, ' ');
      taps.push(`«${label.slice(0, 30)}» ${Math.round(r.width)}×${Math.round(r.height)}`);
    }
  }
  return {vw, sw, viewport: !!document.querySelector('meta[name=viewport]'), over: over.map(el => `${name(el)} (до ${Math.round(el.getBoundingClientRect().right)} px)`),
          text_total: total, text_small: small, small_ex: smallEx, taps: tapCount, tap_ex: taps};
}"""


# Перед снимком: закрыть то, что закрывает сайт (план развития, 6.2). Сначала нажать «Принять», «Понятно», «Да, верно»,
# «Закрыть» внутри всплывающего блока (прикреплённого к экрану или окна-диалога), потом спрятать то, что осталось
# прикреплённым к экрану: большое окно поверх страницы, плашку cookie или выбора города, кнопку чата в нижнем углу.
# Шапку сайта (прикреплена сверху, невысокая) и нижнюю панель на всю ширину (телефон, корзина) не трогаем.
# Ссылки с адресом и кнопки отправки формы не нажимаются. Возвращает, сколько нажато и спрятано.
CLEAN_JS = r"""() => {
  const W = innerWidth, H = innerHeight;
  const OK = /^(принять( все)?|принимаю|согласен|согласна|я согласен|понятно|хорошо|ок|ok|окей|accept( all)?|agree|got it|allow( all)?|да|да, верно|верно|всё верно|все верно|закрыть|close|×|✕|✖|x)$/i;
  const TOPIC = /cookie|куки|персональн|ваш город|выберите город|ваш регион|ваш населённый|подписаться|скидк/i;
  const floating = el => {
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const p = getComputedStyle(a).position;
      if (p === 'fixed' || a.getAttribute('role') === 'dialog' || a.tagName === 'DIALOG' || a.getAttribute('aria-modal') === 'true') return a;
    }
    return null;
  };
  let clicked = 0, hidden = 0;
  for (const b of document.querySelectorAll('button, a, [role=button], input[type=button], [aria-label]')) {
    if (clicked >= 3) break;
    const t = (b.innerText || b.value || b.getAttribute('aria-label') || b.getAttribute('title') || '').trim().replace(/\s+/g, ' ');
    if (!t || t.length > 25 || !OK.test(t)) continue;
    const href = (b.getAttribute('href') || '#').trim();
    if (b.tagName === 'A' && !href.startsWith('#') && !href.toLowerCase().startsWith('javascript')) continue;
    if ((b.getAttribute('type') || '').toLowerCase() === 'submit') continue;
    if (!floating(b)) continue;
    const r = b.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    try { b.click(); clicked++; } catch (e) {}
  }
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if (s.position !== 'fixed' || s.display === 'none' || s.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.bottom < 0 || r.top > H) continue;
    // кнопка чата: её блок бывает нулевого размера, а видимая кнопка внутри - не прикреплённая сама по себе
    const corner = r.width < W * 0.5 && r.height < H * 0.5 && r.left > W * 0.4 && r.top > H * 0.4;
    if ((r.width < 2 || r.height < 2) && !corner) continue;
    const area = Math.min(r.width, W) * Math.min(r.height, H) / (W * H);
    const header = r.top <= 2 && r.height < H * 0.35;   // шапка сайта бывает высокой: адрес, меню, каталог
    const bottomBar = r.bottom >= H - 2 && r.width >= W * 0.9 && r.height < H * 0.15;
    const topic = TOPIC.test((el.innerText || '').slice(0, 400));
    if ((area > 0.25 && !header) || corner || (el.tagName === 'IFRAME' && !header) || (!header && topic)) {
      el.style.setProperty('display', 'none', 'important'); hidden++;
    }
  }
  for (const x of [document.documentElement, document.body]) if (x) { x.style.overflow = ''; x.style.position = ''; }
  return {clicked, hidden};
}"""


def clean(page, url):
    """Закрыть всплывающие окна перед снимком. Если нажатие увело на другую страницу - вернуться и снять как есть."""
    try:
        res = page.evaluate(CLEAN_JS)
        page.wait_for_timeout(600)
        if page.url.split("#")[0] != url.split("#")[0] and res.get("clicked"):
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(1500)
            return {}
        return res
    except Exception:
        return {}


DESKTOP_W, DESKTOP_H = 1366, 768   # самый частый размер экрана ноутбука
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0.0.0 Safari/537.36")
DESKTOP_SHOT = "главная_компьютер.jpg"


def desktop_shot(url, shots_dir, timeout=30.0, wait_seconds=5.0):
    """Снимок первого экрана главной на компьютере (план развития, 6.1). → {"url", "shot", "load_s"} или {"error"}."""
    from playwright.sync_api import sync_playwright
    os.makedirs(shots_dir, exist_ok=True)
    row = {"url": url}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=DESKTOP_UA, viewport={"width": DESKTOP_W, "height": DESKTOP_H},
                                      ignore_https_errors=True, service_workers="block", locale="ru-RU")
            page = ctx.new_page()
            try:
                t0 = time.perf_counter()
                page.goto(url, wait_until="load", timeout=timeout * 1000)
                row["load_s"] = round(time.perf_counter() - t0, 1)
                try:
                    page.wait_for_load_state("networkidle", timeout=wait_seconds * 1000)
                except Exception:
                    pass
                row["clean"] = clean(page, url)
                page.screenshot(path=os.path.join(shots_dir, DESKTOP_SHOT), type="jpeg", quality=75)
                row["shot"] = DESKTOP_SHOT
            except Exception as e:
                s = str(e).strip().splitlines()
                row["error"] = (s[0] if s else type(e).__name__)[:160]
            ctx.close()
        finally:
            browser.close()
    return row


def available():
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def sample_pages(db, n_pages):
    """Страницы для выборочных проверок: три самые близкие к главной и случайные из первых 300 (всегда одни и те же)."""
    import random
    rows = [r[0] for r in db.execute(
        "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE p.status=200 AND u.internal=1 AND u.kind='page' "
        "AND p.content_type IN ('text/html','application/xhtml+xml') ORDER BY u.depth, p.url LIMIT 300")]
    return rows[:3] + random.Random(2).sample(rows[3:], min(n_pages - 3, max(len(rows) - 3, 0)))


DIR = "мобильная"


def ensure(store, out_dir, log=print, n_pages=15):
    """Снимки телефона при сборке отчёта: у проверок, сделанных до 30.09 (тогда их ещё не было), или если обход их
    не сделал (не было браузера, остановили) или папку «мобильная» удалили. Уже снятые не переснимаются."""
    shots_dir = os.path.join(out_dir, DIR)
    old = store.get_meta("mobile_view", None)
    if os.environ.get("CLAYLER_NO_MOBILE_VIEW") == "1" or not available():
        return old
    if old and old.get("pages") is not None and all(os.path.exists(os.path.join(shots_dir, r["shot"]))
                                                    for r in old["pages"] if r.get("shot")):
        if "desktop" not in old and any(r.get("shot") for r in old["pages"]):   # проверки до 21.10.2026: без компьютера
            log("Делаю снимок главной на компьютере...")
            old["desktop"] = _desktop(store.get_meta("start", "") or old["pages"][0]["url"], shots_dir, log)
            store.set_meta("mobile_view", old)
            store.commit()
        return old
    pick = sample_pages(store.db, n_pages)
    if not pick:
        return old
    log(f"Смотрю, как {len(pick)} страниц выглядят на телефоне, и делаю снимки...")
    try:
        rows = check_pages(pick, shots_dir, log=log, give_up_after=2)
    except Exception as e:
        log("Снимки телефона не сделаны: " + (str(e).strip().splitlines() or [type(e).__name__])[0][:150])
        return old
    if not any(r.get("shot") for r in rows):  # сайт не открылся - не запоминаем, попробуем при следующей сборке
        log("Снимки телефона не сделаны: страницы не открылись.")
        return old
    res = {"width": WIDTH, "pages": rows,
           "desktop": _desktop(store.get_meta("start", "") or pick[0], shots_dir, log)}
    store.set_meta("mobile_view", res)
    store.commit()
    return res


def _desktop(url, shots_dir, log=print):
    try:
        return desktop_shot(url, shots_dir)
    except Exception as e:
        log("Снимок на компьютере не сделан: " + (str(e).strip().splitlines() or [type(e).__name__])[0][:150])
        return {"url": url, "error": str(e)[:160]}


def check_pages(urls, shots_dir, log=print, stopped=lambda: False, wait_seconds=5.0, timeout=30.0, give_up_after=None):
    """Открывает страницы по очереди и возвращает список словарей (по странице). Снимки — в shots_dir/NN.jpg.
    give_up_after: если первые столько страниц не открылись, остальные не открываем (сайт недоступен)."""
    from playwright.sync_api import sync_playwright
    os.makedirs(shots_dir, exist_ok=True)
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for i, url in enumerate(urls, 1):
                if stopped() or (give_up_after and len(out) == give_up_after and all(r.get("error") for r in out)):
                    break
                # новый профиль на каждую страницу — первое открытие, без кеша
                ctx = browser.new_context(user_agent=UA, viewport={"width": WIDTH, "height": HEIGHT},
                                          device_scale_factor=2, is_mobile=True, has_touch=True,
                                          ignore_https_errors=True, service_workers="block", locale="ru-RU")
                page = ctx.new_page()
                row = {"url": url}
                sizes, types, reqs = {}, {}, {}
                try:
                    cdp = ctx.new_cdp_session(page)
                    cdp.send("Network.enable")
                    cdp.on("Network.responseReceived",
                           lambda e: types.__setitem__(e["requestId"], e.get("type", "Other")))
                    cdp.on("Network.loadingFinished",
                           lambda e: sizes.__setitem__(e["requestId"], e.get("encodedDataLength", 0)))
                    cdp.on("Network.requestWillBeSent", lambda e: reqs.__setitem__(e["requestId"], 1))
                    t0 = time.perf_counter()
                    page.goto(url, wait_until="load", timeout=timeout * 1000)
                    row["load_s"] = round(time.perf_counter() - t0, 1)
                    try:
                        page.wait_for_load_state("networkidle", timeout=wait_seconds * 1000)
                    except Exception:
                        pass
                    row.update(page.evaluate(LAYOUT_JS, WIDTH))
                    row["clean"] = clean(page, url)   # всплывающие окна - после замеров, только для снимка
                    shot = f"{i:02d}.jpg"
                    page.screenshot(path=os.path.join(shots_dir, shot), type="jpeg", quality=70)
                    row["shot"] = shot
                except Exception as e:
                    s = str(e).strip().splitlines()
                    row["error"] = (s[0] if s else type(e).__name__)[:160]
                by_type = {}
                for rid, n in sizes.items():
                    t = {"Image": "картинки", "Script": "скрипты", "Stylesheet": "стили", "Font": "шрифты",
                         "Document": "HTML", "Media": "видео"}.get(types.get(rid, ""), "прочее")
                    by_type[t] = by_type.get(t, 0) + n
                row["bytes"] = sum(sizes.values())
                row["by_type"] = by_type
                row["requests"] = len(reqs)
                out.append(row)
                ctx.close()
                log(f"   {i}/{len(urls)} {url} - " + (row.get("error") or
                    f"{row['bytes'] / 1048576:.1f} МБ, запросов {row['requests']}"
                    + (", шире экрана" if max(row.get("sw", 0), row.get("vw", 0)) > WIDTH + 1 else "")))
        finally:
            browser.close()
    return out


# ---------- показ в отчёте и аудите
SLOW_4G_MBIT = 1.6   # «медленный 4G» Lighthouse: 1,6 Мбит/с — по нему оцениваем, сколько грузится страница


def verdicts(row):
    """Что не так со страницей на телефоне: список коротких фраз (пустой — всё хорошо)."""
    from .settings import MOBILE_HEAVY_MB
    out = []
    w = max(row.get("sw", 0), row.get("vw", 0))
    if w > WIDTH + 1:
        out.append(f"шире экрана: {w} px вместо {WIDTH}")
    if row.get("text_total") and row.get("text_small", 0) / row["text_total"] > 0.4:
        out.append(f"мелкий текст: {100 * row['text_small'] // row['text_total']}% текста мельче 12 px")
    if row.get("taps"):
        out.append(f"маленькие кнопки и ссылки вплотную друг к другу: {row['taps']}")
    if row.get("bytes", 0) > MOBILE_HEAVY_MB * 1048576:
        out.append(f"тяжёлая: {_ru(row['bytes'] / 1048576)} МБ")
    return out


def _ru(x):
    return f"{x:.1f}".replace(".", ",")


def load_seconds(nbytes):
    return nbytes * 8 / (SLOW_4G_MBIT * 1_000_000)


GALLERY_CSS = """.mob{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin:10px 0}
.mob figure{margin:0;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:8px;break-inside:avoid}
.mob img{width:100%;border-radius:6px;border:1px solid var(--bd);display:block}
.mob figcaption{font-size:12px;line-height:1.4;margin-top:6px;overflow-wrap:anywhere}
.mob .bad{color:var(--crit)}.mob .good{color:var(--ok,var(--good,#2e7d32))}"""


def gallery_html(mv, limit=None, heading=True):
    """Снимки экрана телефона с выводами. limit — показать не больше стольких (сначала страницы с проблемами)."""
    import html as H
    if not mv or not mv.get("pages"):
        return ""
    rows = [r for r in mv["pages"] if r.get("shot")]
    if not rows:
        return ""
    rows.sort(key=lambda r: -len(verdicts(r)))
    total = sum(r.get("bytes", 0) for r in rows) / len(rows)
    cards = []
    for r in rows[:limit]:
        v = verdicts(r)
        mb = r.get("bytes", 0) / 1048576
        img = r.get("by_type", {}).get("картинки", 0) / 1048576
        facts = (f"{_ru(mb)} МБ (картинки {_ru(img)}), запросов {r.get('requests', 0)}, "
                 f"на медленном 4G ≈ {load_seconds(r.get('bytes', 0)):.0f} с")
        if r.get("viewport") is False:
            facts += "<br>Нет meta viewport - телефон показывает страницу как на компьютере"
        elif r.get("over"):
            facts += "<br>За край вылезает: " + H.escape(", ".join(r["over"][:3]))
        cards.append(f'<figure><img src="мобильная/{H.escape(r["shot"])}" loading="lazy" alt="">'
                     f'<figcaption><a href="{H.escape(r["url"])}" target="_blank">{H.escape(r["url"])}</a><br>'
                     + ("".join(f'<b class="bad">{H.escape(x)}</b><br>' for x in v) if v else '<b class="good">всё в порядке</b><br>')
                     + f'<span style="color:var(--mut)">{facts}</span></figcaption></figure>')
    bad = sum(1 for r in rows if verdicts(r))
    intro = (f'<p style="color:var(--mut)">Программа открыла {len(rows)} страниц в браузере шириной {mv.get("width", WIDTH)} px, '
             f'как на телефоне, по-настоящему - с картинками, шрифтами и скриптами, без кеша (первое посещение). '
             f'С замечаниями - {bad} из {len(rows)}. Средний вес страницы - {_ru(total / 1048576)} МБ. '
             'На снимке - первый экран. Время на медленном 4G (1,6 Мбит/с) - оценка по весу, без учёта задержек.</p>')
    more = (f'<p style="color:var(--mut)">Показаны {limit} из {len(rows)} снимков, остальные - в отчёте.</p>'
            if limit and len(rows) > limit else "")
    head = '<h2 class="sec">Как сайт выглядит на телефоне</h2>' if heading else ""
    return f'{head}{intro}<div class="mob">{"".join(cards)}</div>{more}'
