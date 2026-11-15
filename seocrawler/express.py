"""Экспресс-аудит на один лист — чтобы зацепить потенциального клиента: здоровье сайта, 5 главных проблем
простыми словами (чем вредят и что сделать) и ваши контакты. Собирается вместе с отчётом (экспресс.html и
экспресс.pdf); быстрее всего — проверка на 300 страниц (в окне «300 — экспресс-аудит», в боте /express site.ru)."""
import html
import re

from .analyze import CRIT, WARN
from . import brand

TOP = 5


def _first_sentence(t, min_len=70):
    """Начало текста — целыми предложениями, пока не наберётся хотя бы min_len символов (не длиннее 300)."""
    out = ""
    for m in re.finditer(r".+?[.!?](?=\s|$)", t or ""):
        out += m.group(0)
        if len(out.strip()) >= min_len:
            break
    return (out.strip() or (t or ""))[:300]


def top_issues(issues):
    """Главные проблемы: критичные, потом предупреждения; внутри — по приросту здоровья и числу страниц."""
    todo = [i for i in issues if i.severity in (CRIT, WARN)]
    todo.sort(key=lambda i: (0 if i.severity == CRIT else 1, -(getattr(i, "gain", 0) or 0), -i.count))
    return todo[:TOP]


def write(path, meta, issues, summary):
    e = html.escape
    site = meta.get("start", "")
    h = summary.get("health", 0)
    hc = "#2e7d32" if h >= 90 else ("#b26a00" if h >= 70 else "#c62828")
    items = []
    for n, i in enumerate(top_issues(issues), 1):
        gain = getattr(i, "gain", 0) or 0
        items.append(
            f'<li><div class="t"><span class="n">{n}</span><b>{e(i.title)}</b> <span class="c">- {e(i.count_text)}</span>'
            + (f' <span class="g">+{str(gain).replace(".", ",")}% к здоровью</span>' if gain >= 1 else "")
            + f'</div><p><span class="k">Чем вредит:</span> {e(_first_sentence(i.why))}</p>'
              f'<p><span class="k">Что сделать:</span> {e(_first_sentence(i.fix))}</p></li>')
    contacts = brand.contacts_line()
    cta = ("Полный аудит по 20 пунктам со списками всех адресов и планом работ - по запросу"
           + (f": {e(contacts)}." if contacts else "."))
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Экспресс-аудит {e(site)}</title><style>
:root{{--bd:#e3e3e6;--mut:#6b6b70}}
@page{{size:A4;margin:14mm}}
body{{background:#fff;color:#1d1d1f;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:760px;margin:0 auto;padding:20px 16px}}.mut{{color:var(--mut)}}
h1{{font-size:22px;margin:0 0 2px}}.head{{display:flex;gap:18px;align-items:center;margin:12px 0 14px}}
.hl{{font-size:44px;font-weight:700;line-height:1;color:{hc}}}.hl small{{display:block;font-size:12px;font-weight:400;color:var(--mut)}}
ol{{list-style:none;padding:0;margin:0}}li{{border-top:1px solid var(--bd);padding:8px 0}}li p{{margin:3px 0 0 30px}}
.n{{display:inline-block;width:22px;height:22px;border-radius:11px;background:#f1f1f3;text-align:center;font-size:12px;line-height:22px;margin-right:8px}}
.c{{color:var(--mut)}}.g{{color:#2e7d32;font-weight:600;white-space:nowrap}}.k{{color:var(--mut)}}
.cta{{margin-top:14px;padding:10px 12px;background:#f5f6fb;border-radius:8px}}
{brand.BRAND_CSS}
</style></head><body><main>
{brand.header_html()}
<h1>Экспресс-аудит сайта</h1>
<p class="mut">{e(site)} · {e(meta.get("finished_at", ""))} · проверено страниц: {f"{summary.get('pages', 0):,}".replace(",", " ")}</p>
<div class="head"><div class="hl">{h}%<small>здоровье сайта</small></div>
<div class="mut">Доля страниц без серьёзных проблем. Найдено видов проблем: критичных - <b>{summary.get("crit", 0)}</b>,
предупреждений - <b>{summary.get("warn", 0)}</b>. Ниже - пять, которые стоит исправить первыми.</div></div>
<ol>{"".join(items) or "<li>Серьёзных проблем не найдено.</li>"}</ol>
<p class="cta">{cta}</p>
</main></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
