"""Итоговая картинка паутины для клиента: сплетённая паутина, как в окне программы, паучок и цифра здоровья сайта.
Красные участки нити - страницы с ошибкой (4xx, 5xx, нет ответа), жёлтые - с переадресацией, как в живой паутине.

- svg(...) - сама картинка (SVG без интернета и библиотек): первая страница аудита (HTML и PDF, демо тоже) и отчёта
  для клиента.
- write_png(out_dir, meta, summary) - паутина.png 1200×800 (Chrome или Edge в режиме без окна, как PDF): обложка
  для Авито и Kwork, копия - в папке «для клиента».
Геометрия - та же, что у паутины в окне (page/web.js, buildWeb): 24 луча, рамка, спираль в 14 витков. Узор зависит
от адреса сайта: у одного сайта картинка всегда одна и та же."""
import math
import os
import re
import subprocess
import tempfile
import zlib
from urllib.parse import urlsplit

from .fmt import esc, num

FILE = "паутина.png"
W, H = 1200, 800
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window", "page")


def _rng(seed):
    s = [seed & 0xFFFFFFFF]

    def r():
        s[0] = (s[0] * 1664525 + 1013904223) & 0xFFFFFFFF
        return s[0] / 4294967296
    return r


def _line(a, b, n):
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def _sag(a, b, amount, n):  # нить между лучами чуть провисает к центру
    m = ((a[0] + b[0]) / 2 * (1 - amount), (a[1] + b[1]) / 2 * (1 - amount))
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * a[0] + 2 * u * t * m[0] + t * t * b[0], u * u * a[1] + 2 * u * t * m[1] + t * t * b[1]))
    return out


def build(seed, K=24, T=14):
    """Сплетённая паутина в долях радиуса: (лучи и рамка, витки спирали, растяжки к краям, углы лучей)."""
    R = _rng(seed)
    ang, ln = [], []
    for i in range(K):
        ang.append((i + (R() - 0.5) * 0.55) * 2 * math.pi / K - math.pi / 2)
        ln.append(0.84 + R() * 0.16)

    def pt(i, r):
        i %= K
        return (math.cos(ang[i]) * r, math.sin(ang[i]) * r)

    def E(i):
        return pt(i, ln[i % K])
    C = (0.0, 0.0)
    spokes, anchors, spiral = [], [], []
    for k in range(0, K, 2):
        spokes.append(_line(C, E(k), 8))
        if R() < 0.3:
            anchors.append((E(k), ang[k] + (R() - 0.5) * 0.5))
        spokes.append(_sag(E(k), E(k + 1), 0.04, 8))
        spokes.append(_line(E(k + 1), C, 8))
    for i in range(1, K, 2):  # пропущенные куски рамки
        spokes.append(_sag(E(i), E(i + 1), 0.04, 8))
    r0, r1, N = 0.1, 0.97, K * T
    for s in range(N):
        a = pt(s, (r0 + (r1 - r0) * s / N) * ln[s % K])
        b = pt(s + 1, (r0 + (r1 - r0) * (s + 1) / N) * ln[(s + 1) % K])
        spiral.append(_sag(a, b, 0.035 + 0.02 * s / N, 6))
    return spokes, spiral, anchors, ang


def _seed(site):
    h = (urlsplit(site or "").hostname or site or "сайт").lower()
    return zlib.crc32(h.encode("utf-8"))


def _spider_png():
    try:
        with open(os.path.join(PAGE, "web_spider.js"), encoding="utf-8") as f:
            m = re.search(r'CLAYLER_SPIDER_PNG = "(data:image/png;base64,[^"]+)"', f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def counts(summary):
    """Сколько страниц сайта с ошибкой и с переадресацией - для красных и жёлтых участков."""
    bad = warn = 0
    for r in summary.get("by_status") or []:
        s, n = str(r.get("s")), r.get("n") or 0
        code = int(s) if s.isdigit() else 0
        if code == 0 or code >= 400:
            bad += n
        elif code >= 300:
            warn += n
    return bad, warn


def _spots(n, cap):
    """Участков на паутине: не по числу страниц, а заметно больше при большем числе, но не сплошь."""
    return 0 if n <= 0 else min(cap, 1 + int(math.log2(n) * 1.5))


def health_color(h):
    return "#4fbf8a" if h >= 90 else "#e5a54b" if h >= 70 else "#ff8f80"


def svg(site, health, pages=None, bad=0, warn=0, when="", width=None, cls="", demo=False):
    """SVG 1200×800 (масштабируется по ширине: width="100%")."""
    spokes, spiral, anchors, ang = build(_seed(site))
    cx, cy, Ry = W / 2, H / 2 - 10, 340
    Rx = Ry * 1.2

    def xy(p):
        return f"{cx + p[0] * Rx:.1f},{cy + p[1] * Ry:.1f}"

    def path(lines):
        return " ".join("M" + " L".join(xy(p) for p in pts) for pts in lines)
    spoke_d, spiral_d = path(spokes), path(spiral)
    anc = " ".join(f"M{xy(a)} L{cx + a[0] * Rx + math.cos(d) * Ry * 2:.1f},{cy + a[1] * Ry + math.sin(d) * Ry * 2:.1f}"
                   for a, d in anchors)
    nodes = "".join(f'<circle cx="{cx + p[-1][0] * Rx:.1f}" cy="{cy + p[-1][1] * Ry:.1f}" r="3.2" fill="url(#node)"/>'
                    for p in spiral)
    # красные и жёлтые участки на витках спирали, равномерно по паутине, снаружи центральной плашки
    marks = []
    outer = [i for i, p in enumerate(spiral) if math.hypot(*p[3]) > 0.38]
    nb, nw = _spots(bad, 9), _spots(warn, 6)
    kinds = sorted([((j + 0.5) / nb, True) for j in range(nb)] + [((j + 0.25) / nw, False) for j in range(nw)])
    for j, (_k, err) in enumerate(kinds):  # вперемешку и равномерно по виткам
        i = outer[int((j + 0.5) * len(outer) / len(kinds)) % len(outer)]
        marks.append((err, "M" + " L".join(xy(p) for p in spiral[i][1:6])))
    mark_svg = "".join(
        f'<path d="{d}" stroke="{"rgba(255,40,60,.5)" if e else "rgba(255,170,40,.32)"}" stroke-width="{12 if e else 9}" '
        f'fill="none" stroke-linecap="round" filter="url(#blur)"/>'
        f'<path d="{d}" stroke="{"#ff5f6e" if e else "#ffc45a"}" stroke-width="{2.6 if e else 2.1}" fill="none" stroke-linecap="round"/>'
        for e, d in marks)
    # паучок на луче справа сверху, головой к центру
    k = min(range(len(ang)), key=lambda i: abs(math.atan2(math.sin(ang[i] + 0.95), math.cos(ang[i] + 0.95))))
    sx, sy = cx + math.cos(ang[k]) * 0.6 * Rx, cy + math.sin(ang[k]) * 0.6 * Ry
    rot = math.degrees(math.atan2(-math.sin(ang[k]) * Ry, -math.cos(ang[k]) * Rx)) - 90
    sp = _spider_png()
    size = 116
    spider = (f'<g transform="translate({sx:.1f},{sy:.1f}) rotate({rot:.1f})" filter="url(#sglow)">'
              f'<image href="{sp}" x="{-size * 0.49:.1f}" y="{-size / 2:.1f}" width="{size * 0.98:.1f}" height="{size}"/>'
              f'<path d="M{-size * 0.06:.1f},{-size * 0.24:.1f} L{size * 0.06:.1f},{-size * 0.24:.1f} L0,{-size * 0.14:.1f} '
              f'L{size * 0.06:.1f},{-size * 0.04:.1f} L{-size * 0.06:.1f},{-size * 0.04:.1f} L0,{-size * 0.14:.1f} Z" '
              f'fill="#6fd0ff" filter="url(#mglow)"/></g>') if sp else ""
    hc = health_color(health if isinstance(health, (int, float)) else 0)
    host = (urlsplit(site or "").hostname or site or "").removeprefix("www.")
    bottom = " · ".join(x for x in [f"проверка {when}" if when else "", f"страниц проверено: {num(pages)}" if pages else "",
                                    f"с ошибкой: {num(bad)}" if bad else "", f"с переадресацией: {num(warn)}" if warn else ""] if x)
    font = "font-family=\"'Golos Text',system-ui,'Segoe UI',sans-serif\""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{width or W}" {'' if width else f'height="{H}" '}class="{cls}" role="img" aria-label="Паутина сайта {esc(host)}: здоровье {health}%">
<defs>
<radialGradient id="bg" cx="50%" cy="50%" r="75%"><stop offset="0" stop-color="#0d1b3d"/><stop offset=".55" stop-color="#081330"/><stop offset="1" stop-color="#040a1c"/></radialGradient>
<radialGradient id="hub" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="rgba(120,190,255,.38)"/><stop offset="1" stop-color="rgba(120,190,255,0)"/></radialGradient>
<radialGradient id="node"><stop offset="0" stop-color="rgba(200,235,255,.95)"/><stop offset=".4" stop-color="rgba(200,235,255,.35)"/><stop offset="1" stop-color="rgba(200,235,255,0)"/></radialGradient>
<filter id="blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.5"/></filter>
<filter id="sglow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#50aaff" flood-opacity=".95"/><feDropShadow dx="0" dy="0" stdDeviation="2" flood-color="#50aaff" flood-opacity=".9"/></filter>
<filter id="mglow" x="-100%" y="-100%" width="300%" height="300%"><feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="#5abeff" flood-opacity="1"/></filter>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<ellipse cx="{cx}" cy="{cy}" rx="{Rx * 0.62:.0f}" ry="{Ry * 0.62:.0f}" fill="url(#hub)"/>
<path d="{anc}" stroke="rgba(150,205,255,.16)" stroke-width="1.6" fill="none"/>
<path d="{spoke_d}" stroke="rgba(70,160,255,.18)" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<path d="{spoke_d}" stroke="rgba(235,248,255,.9)" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<path d="{spiral_d}" stroke="rgba(70,160,255,.16)" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<path d="{spiral_d}" stroke="rgba(225,244,255,.78)" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
{nodes}
{mark_svg}
<circle cx="{cx}" cy="{cy}" r="104" fill="rgba(5,11,28,.86)" stroke="{hc}" stroke-width="3"/>
<text x="{cx}" y="{cy + 8}" text-anchor="middle" {font} font-size="72" font-weight="800" fill="{hc}">{health}%</text>
<text x="{cx}" y="{cy + 44}" text-anchor="middle" {font} font-size="23" font-weight="600" fill="#f2f6ff">здоровье сайта</text>
{spider}
<text x="40" y="54" {font} font-size="22" font-weight="600" fill="#e8f0ff">Технический аудит сайта{' · пример' if demo else ''}</text>
<text x="40" y="{H - 58}" {font} font-size="34" font-weight="700" fill="#ffffff">{esc(host)}</text>
<text x="40" y="{H - 26}" {font} font-size="19" fill="#9fb2d6">{esc(bottom)}</text>
</svg>"""


def _when(meta):
    d = (meta.get("finished_at") or "")[:10]
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) == 10 and d[4] == "-" else ""


def for_report(meta, summary, cls="webcover", demo=False):
    """Картинка для первой страницы аудита и отчёта для клиента (растягивается по ширине)."""
    bad, warn = counts(summary)
    return svg(meta.get("start", ""), summary.get("health", 0), summary.get("pages"), bad, warn, _when(meta),
               width="100%", cls=cls, demo=demo)


CSS = ".webcover{display:block;width:100%;height:auto;border-radius:12px;margin:14px 0 6px}" \
      "@media print{.webcover{break-inside:avoid}}"


def write_png(out_dir, meta, summary, timeout=90):
    """паутина.png в папке проверки. Возвращает "" или текст ошибки (нет Chrome и Edge - картинки просто нет)."""
    from .pdf import find_browser
    exe = find_browser()
    if not exe:
        return "не найден Chrome или Edge"
    bad, warn = counts(summary)
    doc = ("<!doctype html><meta charset='utf-8'><style>html,body{margin:0;background:#040a1c;overflow:hidden}"
           f"svg{{display:block}}</style>{svg(meta.get('start', ''), summary.get('health', 0), summary.get('pages'), bad, warn, _when(meta))}")
    tmp = os.path.join(out_dir, ".паутина.html")
    dst = os.path.join(out_dir, FILE)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(doc)
    profile = tempfile.mkdtemp(prefix="clayler-png-")
    try:
        if os.path.exists(dst):
            os.remove(dst)
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                        f"--user-data-dir={profile}", f"--window-size={W},{H}", "--force-device-scale-factor=1",
                        f"--screenshot={os.path.abspath(dst)}", "file:///" + os.path.abspath(tmp).replace("\\", "/")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except PermissionError:
        return "картинка открыта в другой программе - закройте её"
    except Exception as e:
        return str(e)[:150]
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return "" if os.path.exists(dst) and os.path.getsize(dst) > 0 else "браузер не создал картинку"

