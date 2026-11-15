"""Семантика в отчёте для клиента (отчёт, отчёт для клиента, аудит HTML и PDF): по каким запросам сайт может
показываться в поиске, какие страницы под них уже есть, что доработать и какие страницы создать.
Берётся семантика этой проверки, а если её собирали по прошлой проверке того же сайта - самая новая из них.
Решения человека на странице «Семантика» учтены (decisions.apply), страницы - по plan.enrich."""
import os
import re
from urllib.parse import urlsplit

from ..fmt import approx, esc as _e, num as _n, plural as _pl
from . import labels as LB

TOP = 12        # главных групп в таблице
CREATE_TOP = 8  # страниц «создать» списком


def _site_key(name):
    return name.rsplit("_", 2)[0].removeprefix("www.") if name.count("_") >= 2 else ""


def find(folder):
    """Папка с семантика.json для этого сайта: сама проверка или прошлая проверка того же сайта."""
    from .export import JSON_NAME
    if os.path.exists(os.path.join(folder, JSON_NAME)):
        return folder
    root, me = os.path.split(os.path.abspath(folder))
    key = _site_key(me)
    if not key:
        return None
    try:
        names = sorted((n for n in os.listdir(root) if _site_key(n) == key), reverse=True)
    except OSError:
        return None
    # сначала прошлые проверки (не новее этой): у старого отчёта, обновлённого позже, семантика его времени, а не
    # собранная через месяц по новой проверке. Нет такой - самая новая
    names = [n for n in names if n <= me] + [n for n in names if n > me]
    for n in names:
        if os.path.exists(os.path.join(root, n, JSON_NAME)):
            return os.path.join(root, n)
    return None


def _path(u):
    p = urlsplit(u)
    return (p.path or "/") + (("?" + p.query) if p.query else "")


def _plain(s):
    """Для клиента: короткий дефис вместо длинного тире, «ёлочки» вместо прямых кавычек."""
    s = re.sub(r"\s+—\s+", " - ", str(s or ""))
    return re.sub(r'"([^"]+)"', r"«\1»", s)


def summary(folder, want=()):
    """Короткие данные для отчёта; None - семантику по сайту не собирали. want - ключи запросов (lost_clicks.qkey),
    для которых нужна группа: «Запрос → страница» в «Где теряем клики» (ключ bind)."""
    from . import decisions, export, plan
    sf = find(folder)
    if not sf:
        return None
    data = export.load(sf)
    if not data or not data.get("groups"):
        return None
    data = plan.enrich(decisions.apply(data, sf), sf)
    groups = [g for g in data["groups"] if (g.get("land") or {}).get("st") not in (None, "manual")]
    cnt = {}
    for g in groups:
        cnt[g["land"]["st"]] = cnt.get(g["land"]["st"], 0) + 1

    def ex(g, n=2):
        name = g["name"].lower()
        return [r[0] for r in g.get("q") or [] if not r[7] and r[0] != name][:n]

    def todo(g):
        st, a = g["land"]["st"], g.get("a") or {}
        if st == "ok":
            return LB.STATUS["ok"][1][:1].upper() + LB.STATUS["ok"][1][1:]
        if st == "fix":
            p = a.get("problems") or []
            return _plain(p[0]) + (f" (и ещё {len(p) - 1})" if len(p) > 1 else "")
        if st == "wrong":
            return LB.STATUS["wrong"][1][:1].upper() + LB.STATUS["wrong"][1][1:]
        if st == "create":
            return "Создать страницу"
        return LB.DECIDE[:1].upper() + LB.DECIDE[1:]
    rows = []
    has_real = any(g.get("real") for g in groups)   # настоящие показы есть - главные группы по ним
    key = lambda g: (-((g.get("real") or {}).get("shows") or 0) if has_real else 0, -(g.get("freq") or 0),  # noqa: E731
                     -(g.get("score") or 0))
    for g in sorted(groups, key=key)[:TOP]:
        L, R = g["land"], g.get("real") or {}
        rows.append({"name": _plain(g["name"]), "ex": ex(g), "n": sum(1 for r in g.get("q") or [] if not r[7]),
                     "st": L["st"], "page": _path(L["url"]) if L["url"] else "", "new": L["new"], "todo": todo(g),
                     "shows": R.get("shows") or 0, "pos": R.get("pos") or 0, "freq": g.get("freq") or 0,
                     "other": _path(R["other"]["url"]) if R.get("other") else ""})
    gaps = {}   # темы конкурентов, которых нет у вас: одна тема - один раз, с именами конкурентов
    for e in data.get("rival_gaps") or []:
        for m in e["missing"]:
            x = gaps.setdefault(m["i"], {"name": _plain(m["name"]), "hosts": [], "st": m["st"], "score": m["score"]})
            x["hosts"].append(e["host"])
    gaps = sorted(gaps.values(), key=lambda x: -x["score"])
    other = [g for g in groups if (g.get("real") or {}).get("other")]
    create = [{"name": _plain(g["name"]), "url": g["land"]["url"], "h1": _plain(g["land"]["h1"]), "n": len(g.get("q") or [])}
              for g in groups if g["land"]["st"] == "create"][:CREATE_TOP]
    fix_types = {}
    for g in groups:
        if g["land"]["st"] == "fix":
            for p in (g.get("a") or {}).get("problems") or []:
                # без «…» из сайта и до «:», « - »; скобку не режем: «В описании (description) нет главного запроса»
                t = re.split(r":| - | — ", re.sub(r"\s*«[^»]*»", "", p))[0].strip()
                fix_types[t] = fix_types.get(t, 0) + 1
    real = data.get("real") or {}
    return {"made": (data.get("made") or "").split(" ")[0], "city": data.get("city") or "",
            # те же числа, что в окне, Excel и Telegram: все запросы и все группы (и «Разобрать вручную»)
            "queries": data.get("total") or sum(len(g.get("q") or []) for g in data["groups"]),
            "groups": len(data["groups"]), "cnt": cnt,
            "competitors": data.get("competitors") or [], "rows": rows, "create": create,
            "fix_types": sorted(fix_types.items(), key=lambda x: -x[1])[:4],
            "articles": len(data.get("articles") or []),
            "tz": sum(1 for g in groups if g["land"]["st"] in ("create", "fix")),
            "real": "ok" in (real.get("wm"), real.get("gsc"), real.get("file")),
            "gaps": [x for x in gaps if x["st"] == "absent"][:CREATE_TOP], "gaps_n": len(gaps),
            "gaps_create": sum(1 for x in gaps if x["st"] == "create"),
            "other": [{"name": _plain(g["name"]), "page": _path(g["land"]["url"]) if g["land"]["url"] else "",
                       "shown": _path(g["real"]["other"]["url"])} for g in other][:CREATE_TOP], "other_n": len(other),
            "shows": sum((g.get("real") or {}).get("shows") or 0 for g in groups),
            "clicks": sum((g.get("real") or {}).get("clicks") or 0 for g in groups),
            "freq": any(g.get("freq") for g in groups), "brands": _brands(data, sf), "bind": _bind(groups, want)}


def _bind(groups, want):
    """{ключ запроса: группа и её страница} только для запросов из want."""
    if not want:
        return {}
    from ..lost_clicks import qkey
    want, out = set(want), {}
    for g in groups:
        for r in g.get("q") or []:
            k = qkey(r[0])
            if k in want and k not in out:
                out[k] = {"name": _plain(g["name"]), "page": _path(g["land"]["url"]) if g["land"]["url"] else ""}
    return out


BRANDS_TOP = 12   # брендов в разделе для клиента; все - в Excel
CELLS_TOP = 10    # «стоит создать» бренд × категория


def _brands(data, folder):
    """Бренды для отчёта: главные по спросу и какие страницы «бренд + категория» стоит создать."""
    try:
        from . import brands as BR
        r = BR.build(data, folder)
    except Exception:
        return None
    if not r or not r["brands"]:
        return None
    top = [{"name": _plain(b["name"]), "n": b["n"], "d": b["d"], "st": b["st"], "page": _path(b["page"]) if b["page"] else "",
            "rivals": b["rivals"][:2], "products": b["products"],
            "forms": [f["w"] for f in b["forms"] if f["w"] != b["name"].lower()][:3]} for b in r["brands"][:BRANDS_TOP]]
    cells = sorted(({"brand": _plain(b["name"]), "cat": _plain(c["cat"]), "n": c["n"], "d": c["d"]}
                    for b in r["brands"] for c in b["cats"] if c["cat"] and c["st"] == "create"), key=lambda x: -x["d"])
    return {"top": top, "n": len(r["brands"]), "count": r.get("count") or {}, "cells": cells[:CELLS_TOP],
            "cells_n": len(cells), "freq": r["freq"], "products": r.get("products_known")}


def _brands_html(b):
    """Раздел «Бренды» в отчёте для клиента."""
    if not b:
        return ""
    c = b["count"]
    parts = [LB.count(k, c.get(k, 0), "brand") for k in ("have", "create", "decide") if c.get(k)]
    lines = "; ".join(p if i == 0 else p[:1].lower() + p[1:] for i, p in enumerate(parts))
    # пример написаний: бренд латиницей и как его пишут по-русски («Baxi» и «бакси»)
    ex = next((x for x in b["top"] if x["forms"] and bool(re.search(r"[а-я]", x["forms"][0]))
               != bool(re.search(r"[а-я]", x["name"].lower()))), None)
    same = (f'Разные написания считаются одним брендом: {_e(x["name"])} и «{_e(ex["forms"][0])}». ' if (x := ex) else "")
    rows = "".join(
        f'<tr><td><b>{_e(x["name"])}</b>' + (f'<div class="mut">{_e(", ".join(x["forms"]))}</div>' if x["forms"] else "")
        + f'</td><td>{_n(x["n"])} {_pl(x["n"], "запрос", "запроса", "запросов")}</td>'
        + f'<td>{_e(x["page"]) if x["page"] else "нет"}' + (f'<div class="mut">товаров: {_n(x["products"])}</div>'
                                                           if x["products"] else "") + '</td>'
        + f'<td><b class="{BST[x["st"]][1]}">{_e(BST[x["st"]][0])}</b>'
        + (f'<div class="mut">есть у {_e(", ".join(x["rivals"]))}</div>' if x["rivals"] else "") + '</td></tr>'
        for x in b["top"])
    cells = ""
    if b["cells"]:
        cells = ('<p style="margin:12px 0 4px;break-after:avoid"><b>Страницы «категория + бренд», которые стоит создать</b>'
                 f'{" (всего " + _n(b["cells_n"]) + ")" if b["cells_n"] > len(b["cells"]) else ""}</p><ul>'
                 + "".join(f'<li>{_e(x["cat"])} {_e(x["brand"])} <span class="mut">- {_n(x["n"])} '
                           f'{_pl(x["n"], "запрос", "запроса", "запросов")}</span></li>' for x in b["cells"]) + '</ul>')
    return (f'<p style="margin:16px 0 4px;break-after:avoid"><b>Бренды</b></p>'
            f'<p class="mut" style="margin:0 0 6px">Люди ищут {_n(b["n"])} {_pl(b["n"], "бренд", "бренда", "брендов")}. '
            f'{same}{_e(lines)}.</p>'
            f'<div class="tw" style="margin:0"><table class="rg"><thead><tr><th>Бренд</th><th>Ищут</th>'
            f'<th>Страница бренда</th><th>Что сделать</th></tr></thead><tbody>{rows}</tbody></table></div>' + cells)


CSS = (".semt{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.semt div{background:var(--card,#f4f4f6);border-radius:10px;"
       "padding:8px 12px;font-size:14px;color:var(--mut)}.semt b{display:block;font-size:22px}"
       ".semt b.ok,.rg b.ok{color:var(--good,var(--ok))}.semt b.warn{color:var(--warn)}.semt b.crit{color:var(--crit)}"
       ".semt b.mut{color:var(--mut)}@media print{.semt,.rg tr{break-inside:avoid}}"
       ".semkey{border-left:3px solid var(--accent,#3b6fd8);padding:2px 0 2px 12px;margin:0 0 10px;break-inside:avoid}"
       ".semkey ul{margin:4px 0 0;padding-left:18px}.semkey li{margin:2px 0}")
BST = {"have": (LB.TREE["have"], "ok"), "create": (LB.TREE["create"], "warn"), "decide": (LB.TREE["decide"], "mut")}
ST = {k: (LB.STATUS[k][0], cls) for k, cls in (("ok", "ok"), ("fix", "warn"), ("wrong", "crit"), ("create", "crit"),
                                                 ("absent", "mut"))}


def _count(s):
    """«9 016 запросов»; без настоящих данных (Вебмастер, Search Console, Вордстат) - «около 9 000 запросов»: часть
    запросов из подсказок может оказаться не про сайт, точное число выглядело бы точнее, чем оно есть."""
    n = s["queries"]
    if s.get("real") or s.get("freq") or approx(n) == n:
        return f'{_n(n)} {_pl(n, "запрос", "запроса", "запросов")}'
    return f'около {_n(approx(n))} запросов'


def key_points(s):
    """Главное для клиента - 3-4 вывода одной строкой каждый: под сколько групп страница на сайте есть, что создать в первую
    очередь, где поиск показывает не ту страницу или что доработать, чего нет по сравнению с конкурентами."""
    c = s["cnt"]
    have, nfix, n = c.get("ok", 0) + c.get("fix", 0) + c.get("wrong", 0), c.get("fix", 0) + c.get("wrong", 0), s["groups"]
    out = [f'Под {_n(have)} из {_n(n)} {_pl(n, "группы", "групп", "групп")} запросов на сайте уже есть страница'
           + (f', {_n(nfix)} из них стоит доработать.' if nfix else '.')]
    if s["create"]:
        names = ", ".join(f'«{x["h1"] or x["name"]}»' for x in s["create"][:3])
        k = c.get("create", 0)
        out.append(f'Главный рост - новые страницы: {names}' + (f' и ещё {_n(k - 3)}.' if k > 3 else '.'))
    if s.get("other_n"):
        out.append(f'По {_n(s["other_n"])} {_pl(s["other_n"], "группе", "группам", "группам")} запросов поиск показывает '
                   f'не ту страницу - это исправляется без новых страниц.')
    elif s["fix_types"]:
        t, k = s["fix_types"][0]
        out.append(f'Самая частая доработка: {t[:1].lower() + t[1:]} - {_n(k)} {_pl(k, "страница", "страницы", "страниц")}.')
    if s.get("gaps_n"):
        out.append(f'У конкурентов есть {_n(s["gaps_n"])} {_pl(s["gaps_n"], "тема", "темы", "тем")}, которых нет у вас.')
    elif s["articles"]:
        out.append(f'Для блога: {_n(s["articles"])} {_pl(s["articles"], "тема", "темы", "тем")} из вопросов людей.')
    return out[:4]


def html_block(s, h2="h2", h2_cls="", cls="", for_audit=False):
    """Раздел «Семантика» для отчёта (h2 class="sec", карточка) и аудита (section.pt)."""
    if not s:
        return ""
    c = s["cnt"]
    head = (f'Собрано {_count(s)}, которые люди набирают в Яндексе '
            f'и Google по товарам и услугам сайта{(" (" + _e(s["city"]) + ")") if s["city"] else ""}, '
            f'и разбито на {_n(s["groups"])} {_pl(s["groups"], "группу", "группы", "групп")}: одна группа - одна страница сайта. '
            f'Чтобы сайт показывался по запросам группы, под неё нужна своя страница, где эти запросы есть в title, '
            f'H1 и тексте.')
    if s.get("shows"):
        head += (f' Уже сейчас сайт показывается по этим запросам: {_n(s["shows"])} '
                 f'{_pl(s["shows"], "показ", "показа", "показов")}' + (f' и {_n(s["clicks"])} '
                 f'{_pl(s["clicks"], "переход", "перехода", "переходов")}' if s.get("clicks") else "") + ' за 4 недели.')
    tiles = [(c.get("ok", 0), "ok", "ok"), (c.get("fix", 0) + c.get("wrong", 0), "fix", "warn"),
             (c.get("create", 0), "create", "crit"), (c.get("absent", 0), "absent", "mut")]
    tiles_html = "".join(f'<div><b class="{k}">{_n(v)}</b>{_e(LB.tile(st, v))}</div>' for v, st, k in tiles if v)
    rows = "".join(
        f'<tr><td><b>{_e(r["name"])}</b>' + (f'<div class="mut">{_e(", ".join(r["ex"]))}</div>' if r["ex"] else "")
        + (f'<div class="mut">спрос {_n(r["freq"])} в месяц</div>' if r.get("freq") else "")
        + (f'<div class="mut">{_n(r["shows"])} {_pl(r["shows"], "показ", "показа", "показов")}'
           + (f', {str(r["pos"]).replace(".", ",")} место' if r["pos"] else "") + '</div>' if r.get("shows") else "")
        + f'</td><td>{_e(r["page"]) + (" <span class=mut>(новая)</span>" if r["new"] else "") if r["page"] else "-"}</td>'
        f'<td><b class="{ST[r["st"]][1]}">{ST[r["st"]][0]}</b><div class="mut">{_e(r["todo"])}</div>'
        + (f'<div class="mut">Google показывает {_e(r["other"])}</div>' if r.get("other") else "") + '</td></tr>'
        for r in s["rows"])
    steps = []
    if s["create"]:
        n = c.get("create", 0)
        lst = "".join(f'<li>{_e(x["h1"] or x["name"])} <span class="mut">- {_e(_path(x["url"]))}</span></li>' for x in s["create"])
        steps.append(f'<li><b>Создать {_n(n)} {_pl(n, "страницу", "страницы", "страниц")}</b> под запросы, для которых на '
                     f'сайте нет подходящей страницы{":" if lst else "."}<ul>{lst}</ul>'
                     + (f'<span class="mut">и ещё {_n(n - len(s["create"]))}.</span>' if n > len(s["create"]) else "") + '</li>')
    nfix = c.get("fix", 0) + c.get("wrong", 0)
    if nfix:
        ft = "; ".join(f'{_e(t[:1].lower() + t[1:])} - {_n(k)}' for t, k in s["fix_types"])
        steps.append(f'<li><b>Доработать {_n(nfix)} {_pl(nfix, "страницу", "страницы", "страниц")}</b>: запросы группы '
                     f'раскрыты слабо{". Чаще всего: " + ft if ft else ""}.</li>')
    if s["tz"]:
        steps.append('<li><b>Тексты по техническим заданиям</b>: для каждой новой и дорабатываемой страницы готовы title, H1, '
                     'описание, слова для текста, объём по страницам конкурентов и подзаголовки.</li>')
    if s.get("other_n"):
        lst = "".join(f'<li>{_e(x["name"])} <span class="mut">- показывается {_e(x["shown"])}'
                      + (f', а нужна {_e(x["page"])}' if x["page"] else "") + '</span></li>' for x in s["other"])
        steps.insert(0, f'<li><b>Поиск показывает не ту страницу</b> по {_n(s["other_n"])} '
                        f'{_pl(s["other_n"], "группе", "группам", "группам")} запросов: сделать главной ту, что показывается, '
                        f'или усилить нужную (title, H1, текст, внутренние ссылки).<ul>{lst}</ul></li>')
    if s.get("gaps_n"):
        n = s["gaps_n"]
        lst = "".join(f'<li>{_e(x["name"])} <span class="mut">- есть у {_e(", ".join(x["hosts"]))}</span></li>' for x in s["gaps"])
        k = s.get("gaps_create") or 0
        rest = n - k
        steps.append(f'<li><b>Темы конкурентов, которых нет у вас: {_n(n)}</b>. Люди их ищут, у конкурентов под них есть '
                     f'страницы.' + (f' {_n(k)} из них уже в списке «создать» выше: товары или раздел рядом у вас есть.' if k else "")
                     + (f' Остальные - товары и услуги, которых у вас нет: добавлять ли их, решаете вы. Например:'
                        f'<ul>{lst}</ul>' if lst else "") + (f'<span class="mut">и ещё {_n(rest - len(s["gaps"]))}.</span>' if rest > len(s["gaps"]) else "")
                     + '</li>')
    if s["articles"]:
        steps.append(f'<li><b>Статьи для блога</b>: {_n(s["articles"])} {_pl(s["articles"], "тема", "темы", "тем")} из '
                     f'вопросов людей («как выбрать», «что такое»), каждая со ссылкой на страницу товара или услуги.</li>')
    note = ("Спрос в месяц - по частотности запросов в Яндексе (Вордстат). " if s.get("freq") else "")
    note += ("Показы, переходы и места в поиске - из Яндекс Вебмастера и Google Search Console за последние 4 недели. "
             if s["real"] else "" if s.get("freq") else
             "Спрос по группам оценён по подсказкам Яндекса и Google, это не число показов в месяц. ")
    note += ("Своя страница под запрос не обещает места в поиске, но без неё сайт по этому запросу почти не показывается."
             + (f' Запросы собраны {_e(s["made"])}.' if s["made"] else ""))
    key = '<div class="semkey"><b>Главное</b><ul>' + ''.join(f'<li>{_e(x)}</li>' for x in key_points(s)) + '</ul></div>'
    body = (f'<style>{CSS}</style>{key}<p class="mut" style="margin:0 0 8px">{head}</p><div class="semt">{tiles_html}</div>'
            f'<p style="margin:12px 0 4px;break-after:avoid"><b>Главные группы запросов</b></p>'
            f'<div class="tw" style="margin:0"><table class="rg"><thead><tr><th>Что ищут</th><th>Страница на сайте</th>'
            f'<th>Что сделать</th></tr></thead><tbody>{rows}</tbody></table></div>' + _brands_html(s.get("brands"))
            + (f'<p style="margin:14px 0 4px;break-after:avoid"><b>Что сделать, чтобы сайт показывался по этим запросам</b></p><ol>{"".join(steps)}</ol>' if steps else "")
            + f'<p class="mut">{note}</p>')
    title = "Семантика: по каким запросам сайт может быть в поиске"
    if for_audit:
        return f'<section class="pt sem"><{h2}>{title}</{h2}>{body}</section>'
    return f'<{h2} class="{h2_cls}">{title}</{h2}><div class="{cls}">{body}</div>'


def docx_paras(s, _para, _run):
    """Тот же раздел для аудита в Word."""
    if not s:
        return []
    GREY = "6B6B70"
    c = s["cnt"]
    out = [_para([_run("Семантика: по каким запросам сайт может быть в поиске", bold=True, size=28)], 80, keep=True),
           _para([_run("Главное", bold=True)], 40, keep=True)]
    out += [_para([_run("• " + x, size=20)], 30, indent=240) for x in key_points(s)]
    out.append(_para([_run(f'Собрано {_count(s)} по товарам и услугам '
                       f'сайта, {_n(s["groups"])} {_pl(s["groups"], "группа", "группы", "групп")}: одна группа - одна страница. '
                       + "; ".join(LB.count(st, v) for st, v in (("ok", c.get("ok", 0)), ("fix", c.get("fix", 0) + c.get("wrong", 0)),
                                                               ("create", c.get("create", 0)), ("absent", c.get("absent", 0))) if v)
                       + ".", color=GREY, size=20)], 100))
    for r in s["rows"]:
        out.append(_para([_run(r["name"], bold=True), _run(f' · {r["page"] or "-"}' + (" (новая)" if r["new"] else ""), color=GREY, size=20),
                          _run(f' · {ST[r["st"]][0]}: {r["todo"]}', size=20)], 40, indent=360))
    if s["create"]:
        out.append(_para([_run("Создать страницы: ", bold=True),
                          _run("; ".join(f'{x["h1"] or x["name"]} ({_path(x["url"])})' for x in s["create"]), size=20)], 60))
    if s.get("other"):
        out.append(_para([_run("Поиск показывает не ту страницу: ", bold=True),
                          _run("; ".join(f'{x["name"]} (показывается {x["shown"]})' for x in s["other"]), size=20)], 60))
    b = s.get("brands")
    if b:
        c = b["count"]
        out.append(_para([_run(f'Бренды ({_n(b["n"])}): ', bold=True),
                          _run("; ".join(LB.count(k, c.get(k, 0), "brand") for k in ("have", "create", "decide") if c.get(k))
                               + ". Главные: " + "; ".join(f'{x["name"]} - {BST[x["st"]][0].lower()}' for x in b["top"][:8])
                               + (". Создать страницы «категория + бренд»: "
                                  + ", ".join(f'{x["cat"]} {x["brand"]}' for x in b["cells"][:6]) if b["cells"] else "") + ".",
                               size=20)], 60))
    if s.get("gaps"):
        out.append(_para([_run(f'Темы конкурентов, которых нет у вас ({_n(s["gaps_n"])}): ', bold=True),
                          _run("; ".join(f'{x["name"]} (у {", ".join(x["hosts"])})' for x in s["gaps"]), size=20)], 60))
    out.append(_para([_run(("Показы и места - из Яндекс Вебмастера и Google Search Console. " if s.get("shows") else
                            "Спрос оценён по подсказкам Яндекса и Google, это не число показов. ") + "Своя страница под запрос не "
                           "обещает места в поиске, но без неё сайт по этому запросу почти не показывается.", color=GREY, size=18)], 160))
    return out
