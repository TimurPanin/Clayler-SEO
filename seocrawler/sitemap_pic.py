"""Карта сайта картинкой (как визуализация в SiteAnalyzer и Screaming Frog): каждый раздел — прямоугольник,
площадь — сколько в нём страниц, цвет — здоровье плавной шкалой от красного (0%) к зелёному (100%).
У больших разделов внутри видны подразделы, мелкие разделы собраны в «Прочие разделы».
- Переключатель «Без ошибок шаблона»: убирает проблемы, которые есть почти на всех страницах (ссылка в меню,
  строка в подвале) — они исправляются одной правкой, но красят всю карту. Тогда видно, какие разделы больны сами.
- Нажатие на прямоугольник — список проблем этого раздела с примерами страниц.
Строится из сводки по разделам (summary["sections"]) — SVG и немного JavaScript, без библиотек.
В PDF — та же картинка (здоровье как есть), без переключателя."""
import html
import json

from .fmt import quote

W, H = 1000, 520
MIN_AREA = 9000  # раздел меньше (в пикселях картинки) — в «Прочие разделы»


def _squarify(items, x, y, w, h):
    """items — [(вес, данные)] по убыванию веса → [(x, y, w, h, данные)]. Алгоритм squarified treemap."""
    out = []
    items = [it for it in items if it[0] > 0]
    total = sum(v for v, _ in items)
    if not items or w <= 0 or h <= 0:
        return out
    scale = w * h / total
    rest = [(v * scale, d) for v, d in items]

    def worst(row, side):
        s = sum(a for a, _ in row)
        mx, mn = max(a for a, _ in row), min(a for a, _ in row)
        return max(side * side * mx / (s * s), (s * s) / (side * side * mn))

    while rest:
        side = min(w, h)
        row = [rest.pop(0)]
        while rest and worst(row + [rest[0]], side) <= worst(row, side):
            row.append(rest.pop(0))
        s = sum(a for a, _ in row)
        if w >= h:  # ряд — столбцом слева
            cw = s / h
            yy = y
            for a, d in row:
                ch = a / cw
                out.append((x, yy, cw, ch, d))
                yy += ch
            x, w = x + cw, w - cw
        else:  # ряд — строкой сверху
            rh = s / w
            xx = x
            for a, d in row:
                cw2 = a / rh
                out.append((xx, y, cw2, rh, d))
                xx += cw2
            y, h = y + rh, h - rh
    return out


def color(h):
    """Плавная шкала: 0% — красный, 50% — жёлтый, 100% — зелёный."""
    if h is None:
        return "#8a8f98"
    return f"hsl({round(1.2 * max(0, min(100, h)))},58%,{38 + round(4 * (1 - abs(h - 50) / 50))}%)"


def _merge(secs):
    """Мелкие разделы — в один прямоугольник «Прочие разделы»."""
    total = sum(s["pages"] for s in secs) or 1
    big, small = [], []
    for s in secs:
        (small if s["pages"] / total * W * H < MIN_AREA else big).append(s)
    if len(small) < 2:
        return secs
    pages = sum(s["pages"] for s in small)

    def hl(key):
        hs = [(s[key], s["pages"]) for s in small if s.get(key) is not None]
        return round(sum(h * n for h, n in hs) / sum(n for _, n in hs)) if hs else None
    issues = {}
    for s in small:
        for i in s.get("issues") or []:
            x = issues.setdefault(i["title"], dict(i, n=0, ex=[]))
            x["n"] += i["n"]
            x["ex"] = (x["ex"] + i["ex"])[:5]
    return big + [{"name": f"Прочие разделы ({len(small)})", "path": ", ".join(s["path"] for s in small[:6]),
                   "pages": pages, "health": hl("health"), "health_nt": hl("health_nt"), "sub": [],
                   "issues": sorted(issues.values(), key=lambda i: (i["sev"] != "critical", -i["n"]))}]


def _text(x, y, w, h, s, big, idx):
    e = html.escape
    if w < 40 or h < 16:
        return ""
    fs = 15 if big else 12
    chars = max(3, int((w - 10) / (fs * 0.56)))
    nm = s["name"] if len(s["name"]) <= chars else s["name"][:chars - 1] + "…"
    hl = lambda k: "-" if s.get(k) is None else f"{s[k]}%"  # noqa: E731
    info = f'{s["pages"]} стр. · <tspan class="smh" data-i="{idx}">{hl("health")}</tspan>'
    if h >= fs * 2 + 10:  # название и цифры в две строки
        return (f'<text x="{x + 6:.1f}" y="{y + fs + 3:.1f}" font-size="{fs}" font-weight="{600 if big else 400}" fill="#fff">{e(nm)}</text>'
                f'<text x="{x + 6:.1f}" y="{y + fs * 2 + 6:.1f}" font-size="{fs - 2}" fill="#fff" fill-opacity=".9">{info}</text>')
    chars1 = max(3, int((w - 10) / ((fs - 1) * 0.56)) - 14)  # в одну строку: «Название · 12 стр. · 40%»
    nm1 = s["name"] if len(s["name"]) <= chars1 else s["name"][:max(1, chars1 - 1)] + "…"
    return (f'<text x="{x + 6:.1f}" y="{y + h / 2 + (fs - 1) / 2.8:.1f}" font-size="{fs - 1}" fill="#fff">{e(nm1)} · {info}</text>'
            if w >= 110 else "")


def svg(summary, uid="sm"):
    """SVG-картинка карты сайта и данные для подсказок: (svg, [данные плиток]); ("", []) — если разделов меньше двух."""
    secs = [s for s in (summary.get("sections") or []) if s.get("pages")]
    if len(secs) < 2:
        return "", []
    secs = _merge(secs)
    e = html.escape
    parts, data = [], []

    def tile(x, y, w, h, s, big, stroke):
        idx = len(data)
        data.append({"name": s["name"], "path": s.get("path", ""), "pages": s["pages"], "h": s.get("health"),
                     "hn": s.get("health_nt"), "issues": s.get("issues") or []})
        parts.append(f'<rect class="smt" data-i="{idx}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                     f'fill="{color(s.get("health"))}" stroke="#fff" stroke-width="{stroke}"><title>{e(s["name"])} - '
                     f'{s["pages"]} стр. Нажмите, чтобы увидеть проблемы раздела</title></rect>')
        return idx

    total = sum(s["pages"] for s in secs)
    # «Прочие разделы» и совсем мелкие — не меньше ~2,5% картинки, иначе это нечитаемая полоска
    weight = lambda s: max(s["pages"], 0.025 * total)  # noqa: E731
    for x, y, w, h, s in _squarify(sorted(((weight(s), s) for s in secs), key=lambda it: -it[0]), 0, 0, W, H):
        idx = tile(x, y, w, h, s, True, 3)
        subs = [t for t in (s.get("sub") or []) if t.get("pages")]
        if subs and w > 160 and h > 110:
            inner = s["pages"] - sum(t["pages"] for t in subs)
            items = [(t["pages"], t) for t in subs] + ([(inner, None)] if inner > 0 else [])
            items.sort(key=lambda it: -it[0])
            top = 26
            for sx, sy, sw, sh, t in _squarify(items, x + 4, y + top, w - 8, h - top - 4):
                if t is None:  # остальные подразделы раздела — одним блоком
                    lab = (f"другие подразделы - {inner} стр." if sw > 150 else
                           f"другие - {inner}" if sw > 70 else f"ещё {inner}" if sw > 34 else "")
                    parts.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="#fff" '
                                 f'fill-opacity=".1" pointer-events="none"><title>другие подразделы - {inner} стр.</title></rect>' + (
                                     f'<text x="{sx + 5:.1f}" y="{sy + 15:.1f}" font-size="11" fill="#fff" fill-opacity=".85" '
                                     f'pointer-events="none">{lab}</text>' if lab and sh > 18 else ""))
                    continue
                j = tile(sx, sy, sw, sh, t, False, 1.5)
                parts.append(f'<g pointer-events="none">{_text(sx, sy, sw, sh, t, False, j)}</g>')
            parts.append(f'<g pointer-events="none">{_text(x, y, w, top, s, True, idx)}</g>')
        else:
            parts.append(f'<g pointer-events="none">{_text(x, y, w, h, s, True, idx)}</g>')
    pic = (f'<svg id="{uid}" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Карта сайта по разделам" '
           f'style="display:block;border-radius:10px;overflow:hidden;font-family:system-ui,Segoe UI,sans-serif;cursor:pointer">'
           f'{"".join(parts)}</svg>')
    return pic, data


SCRIPT = r"""<script>(() => {
const D = %s, svg = document.getElementById('%s'), box = document.getElementById('%s-box'), sw = document.getElementById('%s-sw');
if (!svg) return;
let nt = false;
const col = h => h == null ? '#8a8f98' : `hsl(${Math.round(1.2 * Math.max(0, Math.min(100, h)))},58%%,${38 + Math.round(4 * (1 - Math.abs(h - 50) / 50))}%%)`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
function paint() {
  svg.querySelectorAll('rect.smt').forEach(r => { const d = D[r.dataset.i]; r.setAttribute('fill', col(nt ? d.hn : d.h)); });
  svg.querySelectorAll('tspan.smh').forEach(t => { const d = D[t.dataset.i], h = nt ? d.hn : d.h; t.textContent = h == null ? '-' : h + '%%'; });
  if (sw) sw.querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.nt === '1') === nt));
}
if (sw) sw.addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; nt = b.dataset.nt === '1'; paint(); if (box.dataset.i) show(+box.dataset.i); });
function show(i) {
  const d = D[i], h = nt ? d.hn : d.h;
  const list = d.issues.filter(x => !(nt && x.template));
  box.dataset.i = i;
  box.innerHTML = `<div class="smb-h"><b>${esc(d.name)}</b> <span class="mut">${esc(d.path)} · ${d.pages} стр. · здоровье ${h == null ? '-' : h + '%%'}</span>
    <button type="button" class="smb-x" aria-label="Закрыть">×</button></div>` + (list.length ? '<ul>' + list.map(x =>
    `<li><span class="smb-d ${x.sev === 'critical' ? 'c' : 'w'}"></span><a class="smb-t" href="${document.getElementById(x.key) ? '#' + x.key : 'проблемы/' + x.key + '.html'}"${document.getElementById(x.key) ? '' : ' target="_blank"'}>${esc(x.title)}</a> - ${x.n} стр.${x.template ? ' <span class="mut">(ошибка шаблона)</span>' : ''}
     <div class="smb-ex">${x.ex.map(u => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join('')}</div></li>`).join('') + '</ul>'
    : (h != null && h < 100 ? '<p class="mut">Список проблем раздела не собран - нажмите в окне программы «Ещё → Обновить отчёт».</p>'
                            : '<p class="mut">Критичных проблем и предупреждений в этом разделе нет.</p>'));
  box.hidden = false;
}
svg.addEventListener('click', e => { const r = e.target.closest('rect.smt'); if (r) show(+r.dataset.i); });
box.addEventListener('click', e => {
  if (e.target.closest('.smb-x')) { box.hidden = true; box.dataset.i = ''; }
  const a = e.target.closest('a.smb-t'); const t = a && a.getAttribute('href').startsWith('#') && document.getElementById(a.getAttribute('href').slice(1));
  if (t && t.tagName === 'DETAILS') t.open = true;  // в отчёте - раскрыть проблему со всеми адресами
});
})();</script>"""

CSS = """.sm-sw{display:inline-flex;border:1px solid var(--bd,#ddd);border-radius:8px;overflow:hidden;margin:0 0 10px}
.sm-sw button{border:0;background:transparent;color:inherit;font:inherit;font-size:13px;padding:6px 12px;cursor:pointer}
.sm-sw button.on{background:var(--acc,#3b5bdb);color:#fff}
.sm-scale{display:flex;align-items:center;gap:8px;font-size:12px;margin:8px 0 0;color:var(--mut,#777)}
.sm-scale i{display:inline-block;width:160px;height:8px;border-radius:4px;background:linear-gradient(90deg,hsl(0,58%,38%),hsl(60,58%,42%),hsl(120,58%,38%))}
.smb{border:1px solid var(--bd,#ddd);border-radius:10px;padding:10px 12px;margin-top:10px}
.smb-h{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.smb-x{margin-left:auto;border:0;background:transparent;color:inherit;font-size:20px;cursor:pointer;line-height:1}
.smb ul{margin:8px 0 0;padding:0;list-style:none}.smb li{padding:6px 0;border-top:1px solid var(--bd,#ddd)}
.smb-t{font-weight:600;color:inherit}.smb-d{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}.smb-d.c{background:#c0392b}.smb-d.w{background:#c98a1b}
.smb-ex{display:flex;flex-direction:column;font-size:12px;margin:2px 0 0 14px}.smb-ex a{overflow-wrap:anywhere}
@media print{.sm-sw,.smb,.sm-hint{display:none}}"""


def html_block(summary, h2="h2", cls="pt", uid="sm"):
    pic, data = svg(summary, uid)
    if not pic:
        return ""
    tmpl = (summary.get("sections") or [{}])[0].get("template_issues") or []
    e = html.escape
    sw = (f'<div class="sm-sw" id="{uid}-sw"><button type="button" data-nt="0" class="on">Как есть</button>'
          f'<button type="button" data-nt="1" title="{e("; ".join(tmpl))}">Без ошибок шаблона ({len(tmpl)})</button></div>'
          if tmpl else "")
    # названия проблем — в кавычках («Битые ссылки: где именно исправлять»), иначе двоеточие на двоеточии;
    # про кнопку — только на экране (sm-hint), в PDF кнопки нет
    tmpl_note = (f' Почти на всех страницах есть {"проблема" if len(tmpl) == 1 else "проблемы"} '
                 f'{e(", ".join(quote(t) for t in tmpl[:3]))} - это ошибки шаблона, они исправляются одной правкой и '
                 f'красят всю карту.<span class="sm-hint"> Кнопка «Без ошибок шаблона» показывает, какие разделы больны '
                 f'сами по себе.</span>' if tmpl else "")
    js = SCRIPT % (json.dumps(data, ensure_ascii=False).replace("</", "<\\/"), uid, uid, uid)
    return (f'<section class="{cls}"><style>{CSS}</style><{h2}>Карта сайта по разделам</{h2}><p class="mut">Каждый прямоугольник - '
            f'раздел сайта: чем больше страниц, тем он крупнее. Цвет - здоровье раздела, от красного (0%) до зелёного (100%). '
            f'Внутри больших разделов - подразделы.<span class="sm-hint"> Нажмите на раздел - появится список его проблем '
            f'с примерами страниц.</span>{tmpl_note}</p>{sw}{pic}'
            f'<div class="sm-scale">0%<i></i>100% здоровья</div><div class="smb" id="{uid}-box" hidden></div>{js}</section>')
