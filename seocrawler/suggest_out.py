"""Готовые title / description / H1 и план перелинковки - вывод в отчёт, аудит, Word, Excel и CSV.
Считаются при анализе (analyze/checks/meta_suggest.py и link_plan.py) и лежат в summary["meta_suggest"],
summary["link_plan"]. Здесь только показ."""
import os

from .fmt import esc as _e, num as _n, quote

META_CSV = "заголовки.csv"
LINKS_CSV = "перелинковка.csv"
META_COLS = ["Адрес", "Что не так", "Title сейчас", "Предлагаю title", "Description сейчас", "Предлагаю description",
             "H1 сейчас", "Предлагаю H1", "Тип страницы", "Откуда название", "Что меняется"]
LINK_COLS = ["Куда нужна ссылка", "Название страницы", "Почему", "Ссылок на неё сейчас", "Кликов от главной",
             "Станет кликов", "Откуда поставить ссылку", "Название страницы-донора", "Текст ссылки", "Почему отсюда"]


def meta_rows(summary):
    """В «Предлагаю …» там, где менять не нужно, - текущий текст: таблицу загружают импортом в движок, и пустая ячейка
    стёрла бы title или описание на сайте (отчёт market-primer.ru). Что именно меняется - в последней колонке."""
    out = []
    for r in summary.get("meta_suggest") or []:
        what = [n for n, k in (("title", "title"), ("description", "desc"), ("H1", "h1")) if r.get(k)]
        # несколько H1 склеены « | » - такую строку в «Предлагаю H1» не ставим: импорт сделал бы из неё один H1
        many = (r.get("h1_n") or 0) > 1 or (r.get("h1_n") is None and " | " in (r["h1_now"] or ""))
        out.append([r["url"], r["why"], r["title_now"], r["title"] or r["title_now"], r["desc_now"],
                    r["desc"] or r["desc_now"], r["h1_now"], r["h1"] or ("" if many else r["h1_now"]), r["kind"],
                    r["src"], ", ".join(what)])
    return out


def link_rows(summary):
    out = []
    for x in summary.get("link_plan") or []:
        for r in x["links"]:
            out.append([x["url"], x["name"], x["why"], x["inlinks"],
                        "новая страница" if x.get("new") else x["depth"] if x["inlinks"] else "нет ссылок",
                        x["new_depth"], r["from"], r["from_name"], r["anchor"], r["reason"]])
    return out


def write_csvs(summary, out_dir):
    from .report import write_csv
    for name, cols, rows in ((META_CSV, META_COLS, meta_rows(summary)), (LINKS_CSV, LINK_COLS, link_rows(summary))):
        path = os.path.join(out_dir, name)
        if rows:
            write_csv(path, cols, rows)
        elif os.path.exists(path):
            os.remove(path)


META_INTRO = ("Программа не только нашла страницы без title и описания, с одинаковыми, слишком длинными или короткими "
              "заголовками, но и предлагает готовый текст. Название берётся из главного запроса семантики, своего H1, "
              "начала title или текста ссылок на страницу; к нему - город и название компании (если они стоят в title "
              "у многих страниц), цена и наличие товара, первое предложение своего текста страницы. Ничего не "
              "придумывается, но перед вставкой на сайт прочитайте глазами.")
LINK_INTRO = ("Каким страницам не хватает внутренних ссылок (нет ни одной, одна-две, далеко от главной, важные для "
              "семантики) и с каких страниц их поставить: раздел выше по адресу и страницы на ту же тему, на которые "
              "самих ведёт больше ссылок. Текст ссылки - главный и другие запросы группы из семантики, иначе название "
              "страницы. Для страниц, которые по семантике нужно создать, - готовый адрес и откуда поставить на них "
              "ссылки после создания. Ссылка из текста или блока «Похожие» весит больше, чем из меню.")


def _diff(now, new):
    if not new:
        return f'<span class="mut">{_e(now) or "-"}</span>'
    return (f'<div class="mut" style="text-decoration:line-through">{_e(now) or "нет"}</div>'
            f'<div><b>{_e(new)}</b></div>')


def meta_html(summary, limit=150, cls="card", h2="h2", h2_cls="sec", link=True):
    rows = summary.get("meta_suggest") or []
    if not rows:
        return ""
    body = "".join(
        f'<tr><td><a href="{_e(r["url"])}" target="_blank" rel="noopener">{_e(r["url"])}</a>'
        f'<div class="mut">{_e(r["why"])}</div></td><td>{_diff(r["title_now"], r["title"])}</td>'
        f'<td>{_diff(r["desc_now"], r["desc"])}</td><td>{_diff(r["h1_now"], r["h1"])}</td></tr>'
        for r in rows[:limit])
    more = (f'<p class="mut">Показаны первые {limit} из {len(rows):,}. '.replace(",", " ")
            + (f'Все - в файле <a href="{META_CSV}">{META_CSV}</a> и на листе «Готовые заголовки» в отчёт.xlsx.</p>'
               if link else "Все - в Excel-таблице к аудиту, лист «Готовые заголовки».</p>")) if len(rows) > limit else (
        f'<p class="mut">Эти же строки - в файле <a href="{META_CSV}">{META_CSV}</a>.</p>' if link else "")
    return (f'<{h2} class="{h2_cls}">Готовые title, description и H1 - {_n(len(rows))} стр.</{h2}>'
            + f'<div class="{cls}"><p class="mut" style="margin:0 0 8px">{META_INTRO}</p>'
            f'<div class="tw" style="margin:0"><table class="rg"><thead><tr><th>Страница и что не так</th><th>Title</th>'
            f'<th>Description</th><th>H1</th></tr></thead><tbody>{body}</tbody></table></div>{more}</div>')


def links_html(summary, limit=100, cls="card", h2="h2", h2_cls="sec", link=True):
    plan = summary.get("link_plan") or []
    if not plan:
        return ""
    n_links = sum(len(x["links"]) for x in plan)
    body = []
    for x in plan[:limit]:
        lk = "".join(f'<li>с <a href="{_e(r["from"])}" target="_blank" rel="noopener">{_e(r["from_name"] or r["from"])}</a>'
                     f' - текстом <b>{_e(quote(r["anchor"]))}</b> <span class="mut">({_e(r["reason"])})</span></li>'
                     for r in x["links"])
        dep = (f'новая → {x["new_depth"]}' if x.get("new")
               else f'{x["depth"]} → {x["new_depth"]}' if x["inlinks"] and x["new_depth"] < x["depth"]
               else str(x["depth"]) if x["inlinks"] else f'нет ссылок → {x["new_depth"]}')
        body.append(f'<tr><td><a href="{_e(x["url"])}" target="_blank" rel="noopener">{_e(x["name"] or x["url"])}</a>'
                    f'<div class="mut">{_e(x["why"])}</div></td><td>{dep}</td><td><ul style="margin:0;padding-left:18px">'
                    f'{lk}</ul></td></tr>')
    more = (f'<p class="mut">Показаны первые {limit} страниц из {len(plan):,}. '.replace(",", " ")
            + (f'Весь план - в файле <a href="{LINKS_CSV}">{LINKS_CSV}</a> и на листе «Перелинковка» в отчёт.xlsx.</p>'
               if link else "Весь план - в Excel-таблице к аудиту, лист «Перелинковка».</p>")) if len(plan) > limit else (
        f'<p class="mut">Этот же план - в файле <a href="{LINKS_CSV}">{LINKS_CSV}</a>.</p>' if link else "")
    return (f'<{h2} class="{h2_cls}">План перелинковки - {_n(len(plan))} стр., {_n(n_links)} ссылок</{h2}>'
            + f'<div class="{cls}"><p class="mut" style="margin:0 0 8px">{LINK_INTRO}</p>'
            f'<div class="tw" style="margin:0"><table class="rg"><thead><tr><th>Какой странице нужны ссылки</th>'
            f'<th>Кликов от главной</th><th>Откуда поставить и каким текстом</th></tr></thead><tbody>{"".join(body)}'
            f'</tbody></table></div>{more}</div>')


def audit_html(summary, for_pdf=False):
    """Для аудита (HTML/PDF): по 15 примеров, полные списки — в файлах."""
    out = ""
    m = meta_html(summary, limit=15, cls="", h2="h2", h2_cls="", link=not for_pdf)
    if m:
        out += f'<section class="pt">{m}</section>'
    lk = links_html(summary, limit=15, cls="", h2="h2", h2_cls="", link=not for_pdf)
    if lk:
        out += f'<section class="pt">{lk}</section>'
    return out


def docx_paras(summary, _para, _run):
    """Абзацы для Word: что найдено, 5 примеров, где полный список."""
    body = []
    ms = summary.get("meta_suggest") or []
    if ms:
        body.append(_para([_run(f"Готовые title, description и H1 - {len(ms)} стр.", bold=True, size=28)], 80, keep=True))
        body.append(_para([_run(META_INTRO, color="6B6B70", size=20)], 80))
        for r in ms[:5]:
            body.append(_para([_run(r["url"], size=18, color="6B6B70")], 20))
            for lab, now, new in (("Title", r["title_now"], r["title"]), ("Description", r["desc_now"], r["desc"]),
                                  ("H1", r["h1_now"], r["h1"])):
                if new:
                    body.append(_para([_run(f"{lab}: ", color="6B6B70", size=20), _run(new, bold=True, size=20),
                                       _run(f"  (сейчас: {now or 'нет'})", color="6B6B70", size=18)], 20, indent=360))
        body.append(_para([_run(f"Все {len(ms)} - в Excel-таблице к аудиту, лист «Готовые заголовки».",
                                color="6B6B70", size=20)], 160))
    plan = summary.get("link_plan") or []
    if plan:
        n = sum(len(x["links"]) for x in plan)
        body.append(_para([_run(f"План перелинковки - {len(plan)} стр., {n} ссылок", bold=True, size=28)], 80, keep=True))
        body.append(_para([_run(LINK_INTRO, color="6B6B70", size=20)], 80))
        for x in plan[:5]:
            body.append(_para([_run(x["name"] or x["url"], bold=True, size=20),
                               _run(f"  {x['url']} · {x['why']}", color="6B6B70", size=18)], 20))
            for r in x["links"]:
                body.append(_para([_run(f"• с {r['from']} - текстом {quote(r['anchor'])}", size=20)], 20, indent=360))
        body.append(_para([_run("Весь план - в Excel-таблице к аудиту, лист «Перелинковка».",
                                color="6B6B70", size=20)], 160))
    return body
