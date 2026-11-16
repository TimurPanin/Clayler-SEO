"""Блоки отчёта «Ошибки по шаблонам» (analyze/templates.py) и «Куда уходит вес ссылок» (analyze/weight.py).
Обычный HTML без скриптов: одинаково в отчёте, отчёте для клиента и при печати."""
import html

from .fmt import num as _num, plural as _pl, quote

CSS = """
.tpl{margin:10px 0 0;padding:12px 14px;border:1px solid var(--bd);border-radius:10px;background:var(--card)}
.tpl h3{margin:0 0 2px;font-size:15px;font-weight:600}.tpl .mut{font-size:13px;overflow-wrap:anywhere}
.tpl .win{margin:6px 0;font-size:14px}.tpl ul{margin:4px 0 0;padding-left:0;list-style:none;font-size:14px}
.tpl li{margin:3px 0;display:flex;gap:8px;align-items:baseline}.tpl li .dot{position:relative;top:-1px}
.tpl li .n{color:var(--mut);white-space:nowrap;margin-left:auto}
.wt .row{display:grid;grid-template-columns:minmax(120px,220px) 1fr 150px;gap:8px;align-items:center;font-size:13px;margin:5px 0}
.wt .row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wt .tr{position:relative;height:14px;background:var(--bg);border-radius:4px;overflow:hidden}
.wt .tr .w{position:absolute;left:0;top:0;bottom:0;background:var(--acc);opacity:.75}
.wt .tr .p{position:absolute;left:0;top:10px;height:4px;background:var(--mut);opacity:.6}
.wt .row .v{color:var(--mut);text-align:right}.wt h4{margin:14px 0 6px;font-size:14px;font-weight:600}
.wt table td{overflow-wrap:anywhere}
@media (max-width:640px){.wt .row{grid-template-columns:90px 1fr 110px}}
"""


def _pct(x):
    return f"{x:g}".replace(".", ",") + "%"


def _times(x, num, plural):
    """«в 12 раз», «в 2,5 раза» или «-», если страница сильнее средней меньше чем в полтора раза."""
    if x < 1.5:
        return "-"
    if x >= 10:
        return f"в {num(round(x))} {plural(round(x), 'раз', 'раза', 'раз')}"
    return "в " + str(x).replace(".", ",") + " раза"


def templates_html(summary):
    t = summary.get("templates")
    if not t or not t.get("templates"):
        return ""
    e = html.escape
    cards = []
    for b in t["templates"]:
        where = (f'{_num(b["pages"])} {_pl(b["pages"], "страница", "страницы", "страниц")}'
                 + (f' вида {e(b["pattern"])}' if b["pattern"] != "все страницы" else "")
                 + (f', например <a href="{e(b["example"])}" target="_blank">{e(b["example"])}</a>' if b["example"] else ""))
        gain = (f' Здоровье сайта вырастет на <b>{_pct(b["gain"])}</b>.' if b["gain"] >= 1 else "")
        win = (f'Исправьте шаблон один раз - проблемы уйдут сразу с <b>{_num(b["touched"])}</b> '
               f'{_pl(b["touched"], "страницы", "страниц", "страниц")}.{gain}')
        items = "".join(
            f'<li class="{ {"critical": "crit", "warning": "warn"}.get(i["sev"], "note") }"><span class="dot"></span>'
            f'<a href="#{e(i["key"])}" onclick="var d=document.getElementById(\'{e(i["key"])}\');if(d)d.open=true">'
            f'{e(i["title"])}</a><span class="n">{_num(i["n"])} стр.</span></li>' for i in b["issues"])
        more = f'<li class="mut">и ещё {b["more"]}</li>' if b["more"] else ""
        cards.append(f'<div class="tpl"><h3>{e(b["name"])}</h3><div class="mut">{where}</div>'
                     f'<div class="win">{win}</div><ul>{items}{more}</ul></div>')
    return (f'<h2 class="sec">Ошибки по шаблонам: одна правка - сразу много страниц</h2>'
            f'<style>{CSS}</style><div class="card"><p style="margin:0">Страницы одного типа (карточки товаров, '
            f'страницы каталога, статьи) собираются по одному шаблону. Если проблема есть почти на всех страницах '
            f'типа, её исправляют один раз в шаблоне, и она уходит со всех этих страниц сразу. Ниже - такие шаблоны '
            f'и что в каждом поправить.</p>{"".join(cards)}</div>')


def weight_html(summary):
    w = summary.get("weight")
    if not w:
        return ""
    e = html.escape
    out = [f'<style>{CSS}</style><div class="card wt" style="margin-bottom:12px"><h3>Куда уходит вес ссылок</h3>'
           '<p class="mut" style="margin:0 0 8px">Внутренние ссылки передают страницам силу - так её считает '
           'поисковик. Чем больше силы у страницы, тем выше её шансы в поиске. Синяя полоса - доля всей силы '
           'сайта у раздела, серая черта под ней - доля страниц раздела. Если синяя заметно короче серой, разделу '
           'достаётся меньше, чем он весит по числу страниц.</p>']
    mx = max([s["share"] for s in w["sections"]] + [s["pages_pct"] for s in w["sections"]] + [1])
    for s in w["sections"]:
        out.append(f'<div class="row"><span class="nm" title="{e(s["path"])}">{e(s["name"])}</span>'
                   f'<span class="tr"><span class="w" style="width:{100 * s["share"] / mx:.1f}%"></span>'
                   f'<span class="p" style="width:{100 * s["pages_pct"] / mx:.1f}%"></span></span>'
                   f'<span class="v">{_pct(s["share"])} силы · {_pct(s["pages_pct"])} стр.</span></div>')
    if w["service"]:
        lots = w["service_share"] >= 5
        out.append(f'<h4>Служебные страницы забирают {_pct(w["service_share"])} всей силы ссылок</h4>'
                   f'<p style="margin:0 0 6px;font-size:14px">Политика конфиденциальности, правила, вход, корзина и '
                   f'другие служебные страницы ({w["service_count"]}) в поиске не нужны, но ссылки на них часто стоят на '
                   f'каждой странице, в меню и подвале, и забирают силу у разделов и товаров.'
                   + (' Это заметная доля.' if lots else ' Доля небольшая, но её можно отдать важным страницам.')
                   + '</p><div class="tw" style="margin:0"><table><thead><tr><th>Страница</th><th>Доля силы</th>'
                   '<th>Больше средней страницы</th></tr></thead><tbody>'
                   + "".join(f'<tr><td><a href="{e(s["url"])}" target="_blank">{e(s.get("path") or s["url"])}</a>'
                             + (f'<br><span class="mut">{e(s["title"])}</span>' if s["title"] else "") + '</td>'
                             f'<td>{_pct(s["share"])}</td><td>{_times(s["x_avg"], _num, _pl)}</td></tr>'
                             for s in w["service"])
                   + '</tbody></table></div><p class="mut" style="margin:6px 0 0;font-size:13px">Что сделать: оставьте '
                   'в подвале одну ссылку на страницу «Документы» или «Правовая информация», а уже с неё - на политику, '
                   'оферту и правила. Вход, корзину и сравнение лучше делать кнопками без обычной ссылки. nofollow не '
                   'помогает: сила по такой ссылке всё равно уходит, просто никому не достаётся.</p>')
    if w["weak"]:
        ts = w.get("top_service") or {}
        out.append(f'<h4>Важные разделы, которым достаётся мало силы ({_num(w["weak_total"])})</h4>'
                   '<p style="margin:0 0 6px;font-size:14px">Это страницы-разделы: внутри них много страниц, и их '
                   'стоит продвигать. Но силы ссылок у них меньше, чем у служебной страницы или у средней страницы '
                   'сайта. Поставьте на них ссылки с главной, из меню и из похожих разделов.</p>'
                   '<div class="tw" style="margin:0"><table><thead><tr><th>Раздел</th><th>Страниц внутри</th>'
                   '<th>Доля силы</th><th>Почему мало</th></tr></thead><tbody>'
                   + "".join(f'<tr><td><a href="{e(x["url"])}" target="_blank">{e(x["url"])}</a>'
                             + (f'<br><span class="mut">{e(x["title"])}</span>' if x["title"] else "")
                             + f'</td><td>{_num(x["inside"])}</td><td>{_pct(x["share"])}</td><td>'
                             + (f'меньше, чем у {e(ts.get("path") or "")} ({_pct(ts["share"])})' if ts else "меньше, чем у служебной страницы"
                                if x["why"] == "service" else "меньше средней страницы сайта")
                             + '</td></tr>' for x in w["weak"])
                   + '</tbody></table></div>')
    if w.get("sem_weak"):
        ts = w.get("top_service") or {}
        out.append(f'<h4>Страницы под запросы из семантики, которым достаётся мало силы ({_num(w["sem_weak_total"])})</h4>'
                   '<p style="margin:0 0 6px;font-size:14px">Эти страницы выбраны под группы запросов семантики, их '
                   'продвигают. Силы ссылок у них меньше, чем у служебной страницы или у средней страницы сайта. '
                   'Поставьте на них ссылки из меню, похожих разделов и статей - готовые ссылки есть в «Плане '
                   'перелинковки».</p>'
                   '<div class="tw" style="margin:0"><table><thead><tr><th>Страница и запрос</th><th>Доля силы</th>'
                   '<th>Почему мало</th><th>В плане перелинковки</th></tr></thead><tbody>'
                   + "".join(f'<tr><td><a href="{e(x["url"])}" target="_blank">{e(x["url"])}</a>'
                             f'<br><span class="mut">{e(quote(x["main"]))}</span></td><td>{_pct(x["share"])}</td><td>'
                             + (f'меньше, чем у {e(ts.get("path") or "")} ({_pct(ts["share"])})' if ts else "меньше, чем у служебной страницы"
                                if x["why"] == "service" else "меньше средней страницы сайта")
                             + f'</td><td>{(_num(x["plan"]) + " " + _pl(x["plan"], "ссылка", "ссылки", "ссылок")) if x["plan"] else "-"}</td></tr>'
                             for x in w["sem_weak"])
                   + '</tbody></table></div>')
    out.append("</div>")
    return "".join(out)
