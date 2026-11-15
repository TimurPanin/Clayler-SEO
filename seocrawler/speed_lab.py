"""Скорость как у посетителя с телефона — без ключа Google: страница открывается во встроенном Chromium с теми же
условиями, что у PageSpeed (Lighthouse) для телефона: медленный 4G (1,6 Мбит/с, задержка 150 мс) и процессор
в 4 раза медленнее компьютера. Замеряются главные показатели Google (Core Web Vitals в лаборатории):
- LCP — когда показалось главное (самая большая картинка или блок текста на первом экране): хорошо до 2,5 с;
- FCP — когда появилось хоть что-то: хорошо до 1,8 с;
- CLS — насколько страница «прыгает» при загрузке: хорошо до 0,1;
- TBT — сколько страница «висит» из-за скриптов и не реагирует на нажатия: хорошо до 200 мс.
Это замер с одного компьютера (лаборатория), а не данные реальных посетителей — их даёт PageSpeed с ключом Google."""
import time

from .mobile_view import UA, WIDTH, HEIGHT

LIMITS = {"lcp": (2.5, 4.0), "fcp": (1.8, 3.0), "cls": (0.1, 0.25), "tbt": (200, 600)}  # хорошо до / плохо после
NAMES = {"lcp": "главное на экране (LCP)", "fcp": "первое появление (FCP)", "cls": "сдвиги при загрузке (CLS)",
         "tbt": "подвисание из-за скриптов (TBT)"}

OBSERVE = r"""
window.__m = {lcp: 0, lcp_el: '', cls: 0, fcp: 0, tbt: 0};
const name = el => !el ? '' : el.tagName.toLowerCase() + (el.id ? '#' + el.id : (typeof el.className === 'string' && el.className.trim()
  ? '.' + el.className.trim().split(/\s+/)[0] : '')) + (el.tagName === 'IMG' ? ' ' + (el.currentSrc || el.src || '').split('/').pop().slice(0, 40) : '');
try { new PerformanceObserver(l => { for (const e of l.getEntries()) { window.__m.lcp = e.startTime; window.__m.lcp_el = name(e.element); } })
  .observe({type: 'largest-contentful-paint', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__m.cls += e.value; })
  .observe({type: 'layout-shift', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') window.__m.fcp = e.startTime; })
  .observe({type: 'paint', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__m.tbt += Math.max(0, e.duration - 50); })
  .observe({type: 'longtask', buffered: true}); } catch (e) {}
"""


def measure(urls, log=print, stopped=lambda: False, timeout=60.0):
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for i, url in enumerate(urls, 1):
                if stopped():
                    break
                ctx = browser.new_context(user_agent=UA, viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=2,
                                          is_mobile=True, has_touch=True, ignore_https_errors=True,
                                          service_workers="block", locale="ru-RU")
                ctx.add_init_script(OBSERVE)
                page = ctx.new_page()
                row = {"url": url}
                try:
                    cdp = ctx.new_cdp_session(page)
                    cdp.send("Network.enable")
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                                                                  "downloadThroughput": 1.6 * 1_000_000 / 8,
                                                                  "uploadThroughput": 750_000 / 8})
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    t0 = time.perf_counter()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    try:  # тяжёлая страница может грузиться минуты — главное на экране к тому времени уже видно
                        page.wait_for_load_state("load", timeout=max(1.0, timeout - (time.perf_counter() - t0)) * 1000)
                        row["load"] = round(time.perf_counter() - t0, 1)
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        row.setdefault("load", None)
                    page.wait_for_timeout(1000)
                    m = page.evaluate("window.__m")
                    row.update(lcp=round(m["lcp"] / 1000, 1), fcp=round(m["fcp"] / 1000, 1), cls=round(m["cls"], 3),
                               tbt=round(m["tbt"]), lcp_el=m.get("lcp_el") or "")
                except Exception as e:
                    s = str(e).strip().splitlines()
                    row["error"] = (s[0] if s else type(e).__name__)[:160]
                    if "Timeout" in row["error"]:
                        row["error"] = f"не загрузилась на медленном 4G за {timeout:.0f} с"
                ctx.close()
                out.append(row)
                log(f"   {i}/{len(urls)} {url} - " + (row.get("error") or
                    f"LCP {row['lcp']} с, CLS {row['cls']}, TBT {row['tbt']} мс, загрузка "
                    + (f"{row['load']} с" if row.get("load") else f"дольше {timeout:.0f} с")))
        finally:
            browser.close()
    return out


def grade(key, v):
    good, poor = LIMITS[key]
    return "good" if v <= good else ("poor" if v > poor else "mid")


def _f(x, key):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",") if key == "cls" else \
        (f"{int(x)} мс" if key == "tbt" else f"{x:.1f} с".replace(".", ","))


def report_html(sl, esc):
    """Раздел отчёта «Скорость на телефоне (замер)». Пусто, если замера нет."""
    if not sl or not sl.get("pages"):
        return ""
    rows = []
    for r in sl["pages"]:
        if r.get("error"):
            rows.append(f'<tr><td>{esc(r["url"])}</td><td colspan="4" class="crit">{esc(r["error"])}</td></tr>')
            continue
        cells = "".join(f'<td class="sl-{grade(k, r[k])}">{_f(r[k], k)}</td>' for k in ("lcp", "fcp", "cls", "tbt"))
        rows.append(f'<tr><td><a href="{esc(r["url"])}" target="_blank">{esc(r["url"])}</a>'
                    + (f'<div class="mut">главное на экране: {esc(r["lcp_el"])}</div>' if r.get("lcp_el") else "")
                    + f"</td>{cells}</tr>")
    return ('<h2 class="sec">Скорость на телефоне (замер)</h2><div class="card"><p class="mut" style="margin:0 0 8px">'
            'Страницы открыты во встроенном браузере как на телефоне с медленным 4G (1,6 Мбит/с) и слабым процессором - '
            'так же замеряет PageSpeed. Зелёным - хорошо по меркам Google, жёлтым - средне, красным - плохо. Это замер '
            'с одного компьютера: у реальных посетителей цифры другие (их показывает PageSpeed с ключом Google).</p>'
            '<div class="tw" style="margin:0"><table><thead><tr><th>Страница</th><th>Главное на экране (LCP), хорошо до 2,5 с</th>'
            '<th>Первое появление (FCP), до 1,8 с</th><th>Сдвиги (CLS), до 0,1</th><th>Подвисание (TBT), до 200 мс</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>')


CSS = ".sl-good{color:var(--good);font-weight:600}.sl-mid{color:var(--warn);font-weight:600}.sl-poor{color:var(--crit);font-weight:600}"
