"""Сравнение двух проверок одного сайта: что исправили, что сломалось, что изменилось на страницах.
Обе проверки анализируются текущей версией программы, поэтому правила проверок одинаковые."""
import os

from .analyze import cached_analyze, SEV_RU, CRIT, WARN, NOTE
from .fmt import esc as _e, when

FIELDS = [("status", "Код ответа"), ("indexability", "Индексируемость"), ("title", "Title"),
          ("description", "Description"), ("h1", "H1"), ("canonical", "Canonical"),
          ("meta_robots", "Meta robots")]


def _row_key(issue, row):
    """Чем строка проблемы отличается от других: адреса в строке (а не цифры вроде времени ответа)."""
    urls = tuple(str(c) for c in row if isinstance(c, str) and c.startswith(("http://", "https://")))
    return urls or (str(row[0]),)


def _is_grouped(issue):
    """Проблемы-группы (одинаковые title, дубли): в одной строке список адресов через перенос строки."""
    return bool(issue) and any(isinstance(c, str) and "\n" in c and c.startswith("http") for r in issue.rows for c in r)


def _rows(issue, grouped):
    if not issue:
        return {}
    if not grouped:
        return {_row_key(issue, r): r for r in issue.rows}
    # группу разворачиваем по адресам: сравниваем, какие страницы вошли в группы и какие вышли
    out = {}
    for r in issue.rows:
        label = next((str(c) for c in r if not (isinstance(c, str) and c.startswith("http"))), "")
        for c in r:
            if isinstance(c, str) and c.startswith("http"):
                for u in c.split("\n"):
                    if u.startswith("http"):
                        out[(u,)] = [u, label[:120]]
    return out


# Служебные записи проверки: их отсутствие в старой базе не значит, что проверка не делалась
KEEP_META = {"start", "started_at", "finished_at", "render_js", "scope", "max_pages", "config", "summary", "compare",
             "app_version", "work_seconds", "pages_left_in_queue", "problem_shots"}


def missing_data(old_store, new_store):
    """Какие данные собирает новая проверка, а старая не собирала: колонки страниц и картинок, которые в старой базе
    пустые целиком (их добавила новая версия программы), и записи о дополнительных проверках (зеркала, телефон,
    служебные файлы…), которых в старой базе нет. ({таблица: [колонки]}, [записи])."""
    cols = {}
    for t in ("pages", "images"):
        def filled(store):
            names = [r[1] for r in store.db.execute(f"PRAGMA table_info({t})")]
            row = store.db.execute("SELECT " + ", ".join(f"COUNT({c})" for c in names) + f" FROM {t}").fetchone()
            return dict(zip(names, row))
        o, n = filled(old_store), filled(new_store)
        cols[t] = [c for c, v in n.items() if v and not o.get(c)]
    old_meta = {k for (k,) in old_store.db.execute("SELECT key FROM meta")}
    meta = [k for (k,) in new_store.db.execute("SELECT key FROM meta") if k not in old_meta and k not in KEEP_META]
    return cols, meta


def not_collected(old_store, new_store, keys):
    """Какие из проблем keys (в новой проверке есть, в старой нет) старая проверка не могла найти вообще: её данных
    не хватает. Новая проверка анализируется ещё раз, но только с теми данными, что собирала старая (копия базы,
    где лишние колонки и записи стёрты). Если проблема и так находится - она настоящая новая, если нет - в прошлый
    раз эту проверку просто не делали. Общее правило для любых версий программы, без списка проверок."""
    keys = set(keys)
    if not keys:
        return set()
    cols, meta = missing_data(old_store, new_store)
    if not any(cols.values()) and not meta:
        return set()
    print("В прошлой проверке не было части данных - проверяю, какие проблемы она не могла найти", flush=True)
    import sqlite3
    import tempfile
    from .analyze import analyze
    from .storage import Store
    fd, tmp = tempfile.mkstemp(prefix="clayler-cmp-", suffix=".db")
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp)
        new_store.db.backup(dst)
        for t, cs in cols.items():
            if cs:
                dst.execute(f"UPDATE {t} SET " + ", ".join(f"{c}=NULL" for c in cs))
        dst.executemany("DELETE FROM meta WHERE key=?", [(k,) for k in meta])
        dst.commit()
        dst.close()
        st = Store(tmp)
        st.path = new_store.path  # семантика и прочие файлы рядом - из настоящей папки; кеш анализа не пишется
        try:
            found = {i.key for i in analyze(st)[0] if i.rows}
        finally:
            st.db.close()
    finally:
        for f in (tmp, tmp + "-wal", tmp + "-shm"):
            try:
                os.remove(f)
            except OSError:
                pass
    return keys - found


def _checked(store):
    return {u for (u,) in store.db.execute("SELECT url FROM pages")}


NEW_EXT_MIN, NEW_EXT_SHARE = 5, 0.2   # новая чужая ссылка сразу на стольких страницах (и доле общих) - подозрительно


def _ext_hosts(store, pages):
    """Чужие сайты, на которые ссылаются страницы из pages: {сайт: {страница: ссылка}}."""
    from . import urls as U
    out = {}
    for src, dst in store.db.execute("SELECT src, dst FROM links WHERE internal=0 AND kind='a'"):
        if src in pages and dst and dst.startswith("http"):
            out.setdefault(U.host_of(dst), {}).setdefault(src, dst)
    return out


def new_external(old_store, new_store, both):
    """Чужие сайты, на которые в новой проверке ссылаются сразу многие страницы, а в прошлой - ни одна (только по
    страницам, открытым обеими проверками). Так выглядит взлом шаблона или вставка рекламы.
    → [[сайт, страниц, пример страницы, пример ссылки]]"""
    if not both:
        return []
    old, new = _ext_hosts(old_store, both), _ext_hosts(new_store, both)
    need = max(NEW_EXT_MIN, NEW_EXT_SHARE * len(both))
    rows = [[h, len(pg), *next(iter(pg.items()))] for h, pg in new.items() if h not in old and len(pg) >= need]
    return sorted(rows, key=lambda r: -r[1])


def compare(old_store, new_store):
    old_issues, old_pages, old_sum = cached_analyze(old_store)
    new_issues, new_pages, new_sum = cached_analyze(new_store)
    oi = {i.key: i for i in old_issues}
    ni = {i.key: i for i in new_issues}
    # «исправлено» и «новое» - только по адресам, которые открывали обе проверки. Если следующий обход дошёл до других
    # страниц (лимит; у market-primer 10 000 из ~51 тыс. адресов в очереди), ошибка с непроверенной страницы не
    # «исправлена», а просто не проверялась. Адреса, которых нет ни в одной проверке (строка без адреса), не мешают
    oc, nc_ = _checked(old_store), _checked(new_store)
    both, seen_any = oc & nc_, oc | nc_
    seen = lambda k: all(u in both for u in k if u in seen_any)
    unseen = 0
    issues = []
    for key in list(ni) + [k for k in oi if k not in ni]:
        o, n = oi.get(key), ni.get(key)
        ref = n or o
        grouped = _is_grouped(o) or _is_grouped(n)
        orow = _rows(o, grouped)
        nrow = _rows(n, grouped)
        fixed = [orow[k] for k in orow if k not in nrow and seen(k)]
        added = [nrow[k] for k in nrow if k not in orow and seen(k)]
        if ref.severity != NOTE:
            unseen += sum(1 for k in orow if k not in nrow and not seen(k)) + sum(1 for k in nrow if k not in orow and not seen(k))
        issues.append({"key": key, "title": ref.title, "severity": ref.severity, "category": ref.category,
                       "columns": ["Адрес", "Группа"] if grouped else ref.columns, "old": len(orow), "new": len(nrow), "fixed": fixed, "added": added,
                       "sitewide": bool(o and o.sitewide) or bool(n and n.sitewide)})
    # проблемы, которых в старой проверке нет: не потому ли, что она таких данных вообще не собирала
    nc = not_collected(old_store, new_store, [i["key"] for i in issues if i["new"] and not i["old"]])
    for i in issues:
        if i["key"] in nc:
            i["not_collected"], i["added"] = True, []
    order = {CRIT: 0, WARN: 1, NOTE: 2}
    issues.sort(key=lambda x: (order[x["severity"]], -(len(x["added"]) + len(x["fixed"]))))

    op = {p["url"]: p for p in old_pages}
    np_ = {p["url"]: p for p in new_pages}
    appeared = sorted(u for u in np_ if u not in op)
    gone = sorted(u for u in op if u not in np_)
    changes = []
    for u in sorted(set(op) & set(np_)):
        for f, label in FIELDS:
            a, b = op[u].get(f), np_[u].get(f)
            if (a or "") != (b or "") and not (a in (None, "") and b in (None, "")):
                changes.append([u, label, "" if a is None else a, "" if b is None else b])
    return {"issues": issues, "appeared": appeared, "gone": gone, "changes": changes, "unseen": unseen,
            "both_pages": len(both), "new_ext": new_external(old_store, new_store, both),
            "not_collected": [{"title": i["title"], "severity": i["severity"], "new": i["new"]}
                              for i in issues if i.get("not_collected")],
            "old_sum": old_sum, "new_sum": new_sum,
            "old_meta": {k: old_store.get_meta(k, "") for k in ("start", "started_at", "finished_at")},
            "new_meta": {k: new_store.get_meta(k, "") for k in ("start", "started_at", "finished_at")},
            "old_js": bool(old_store.get_meta("render_js", False)), "new_js": bool(new_store.get_meta("render_js", False))}


def _cell(v):
    parts = ("" if v is None else str(v)).split("\n")
    return "<br>".join(f'<a href="{_e(p)}" target="_blank">{_e(p)}</a>' if p.startswith(("http://", "https://"))
                       else _e(p) for p in parts)


def _table(cols, rows, limit=200):
    if not rows:
        return ""
    head = "".join(f"<th>{_e(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in r) + "</tr>" for r in rows[:limit])
    more = f'<p class="mut">…и ещё {len(rows) - limit}. Полный список - в файле сравнение.csv</p>' if len(rows) > limit else ""
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{more}'


def _new_ext_html(rows):
    if not rows:
        return ""
    return ('<h2>Новые ссылки на чужие сайты сразу на многих страницах</h2><p class="warnbox">В прошлый раз ни одна '
            'из этих страниц не ссылалась на эти сайты, а теперь ссылаются сразу многие. Если ссылки ставили не вы '
            '(новый партнёр, счётчик, соцсеть), это похоже на взлом шаблона или вставку чужой рекламы: откройте '
            'страницу, найдите ссылку в коде (Ctrl+U) и передайте разработчику.</p><div class="box">'
            + _table(["Чужой сайт", "Страниц", "Например, на странице", "Ссылка"], rows) + '</div>')


def write_compare(out_dir, res):
    """Пишет сравнение.html и сравнение.csv в папку новой проверки. Возвращает короткую сводку."""
    from .report import write_csv  # здесь, а не вверху: report и audit сами берут отсюда блок для клиента
    # проблема «на всём сайте» — одна настройка: считаем её одной, а не тысячами строк
    fixed = sum(min(len(i["fixed"]), 1) if i.get("sitewide") else len(i["fixed"]) for i in res["issues"] if i["severity"] != NOTE)
    added = sum(min(len(i["added"]), 1) if i.get("sitewide") else len(i["added"]) for i in res["issues"] if i["severity"] != NOTE)
    os_, ns = res["old_sum"], res["new_sum"]
    rows_csv = []
    for i in res["issues"]:
        for r in i["fixed"]:
            rows_csv.append(["исправлено", SEV_RU[i["severity"]], i["title"]] + [str(c) for c in r])
        for r in i["added"]:
            rows_csv.append(["новое", SEV_RU[i["severity"]], i["title"]] + [str(c) for c in r])
    for u in res["appeared"]:
        rows_csv.append(["новая страница", "", "", u])
    for u in res["gone"]:
        rows_csv.append(["страница пропала", "", "", u])
    for c in res["changes"]:
        rows_csv.append(["изменение на странице", "", c[1], c[0], c[2], c[3]])
    write_csv(os.path.join(out_dir, "сравнение.csv"), ["Что", "Важность", "Проблема / поле", "Данные"], rows_csv)

    sections = []
    for i in res["issues"]:
        if not i["fixed"] and not i["added"]:
            continue
        sev = {CRIT: "crit", WARN: "warn", NOTE: "note"}[i["severity"]]
        trend = ("good" if i["new"] < i["old"] else "bad" if i["new"] > i["old"] else "")
        sections.append(
            f'<details class="issue {sev}"><summary><span class="dot"></span><span class="it">{_e(i["title"])}</span>'
            f'<span class="cnt {trend}">{i["old"]} → {i["new"]}</span>'
            f'<span class="pill good">исправлено {len(i["fixed"])}</span><span class="pill bad">новых {len(i["added"])}</span></summary>'
            + (f'<h4>Исправлено</h4>{_table(i["columns"], i["fixed"])}' if i["fixed"] else "")
            + (f'<h4>Появилось</h4>{_table(i["columns"], i["added"])}' if i["added"] else "")
            + "</details>")
    note = ""
    if res.get("old_js") != res.get("new_js"):
        mode = lambda js: "с JavaScript" if js else "без JavaScript"
        note += (f'<p class="warnbox">Прошлая проверка была {mode(res["old_js"])}, эта - {mode(res["new_js"])}. '
                 'В разных режимах программа видит разные страницы: скрипты добавляют картинки, ссылки и текст. '
                 'Поэтому многие «исправлено» и «новое» ниже - разница режимов, а не изменения на сайте. '
                 'Для честного сравнения запускайте обе проверки в одном режиме.</p>\n')
    if res.get("not_collected"):
        note += ('<div class="warnbox"><b>Эти проверки в прошлый раз не делались</b> (прошлая проверка сделана '
                 'старой версией программы или в другом режиме). Поэтому они не считаются «новыми проблемами»: '
                 'сравнивать их пока не с чем, со следующей проверки сравнение будет полным.<ul>'
                 + "".join(f'<li>{_e(x["title"])} <span class="mut">(сейчас {x["new"]})</span></li>'
                           for x in res["not_collected"]) + '</ul></div>\n')
    if res.get("unseen"):
        note += (f'<p class="warnbox">Сравнивали только адреса, которые открывали обе проверки ({res.get("both_pages", 0)}). '
                 f'Ещё {res["unseen"]} строк проблем - на страницах, которые открывала только одна из проверок: они не '
                 f'считаются ни исправленными, ни новыми.</p>')
    elif os_["pages"] and abs(ns["pages"] - os_["pages"]) / max(os_["pages"], 1) > 0.2:
        note += (f'<p class="warnbox">В проверках разное число страниц ({os_["pages"]} и {ns["pages"]}). Скорее всего, '
                f'разный лимит или часть сайта не обошлась. Тогда «исправлено» и «новое» частично означают просто '
                f'«страница не попала в одну из проверок».</p>')
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Сравнение проверок {_e(res["new_meta"]["start"])}</title><style>
:root{{--bg:#f7f6f3;--card:#fff;--tx:#1f1e1c;--mut:#6b6a66;--bd:#e4e2dc;--crit:#c0392b;--warn:#d9730d;--note:#b08d00;--good:#2f855a;--acc:#3b5bdb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#181817;--card:#222220;--tx:#ecebe7;--mut:#a3a19b;--bd:#3a3936;--crit:#ef6f5e;--warn:#f0973c;--note:#e3c84a;--good:#58c08a;--acc:#8ea6ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 60px}}h1{{font-size:24px;margin:0 0 4px;font-weight:600}}
h2{{font-size:18px;font-weight:600;margin:28px 0 10px}}h4{{margin:10px 14px 6px;font-weight:600}}.mut{{color:var(--mut)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px}}
.card b{{display:block;font-size:28px;font-weight:600}}.card span{{color:var(--mut);font-size:13px}}
.good{{color:var(--good)}}.bad{{color:var(--crit)}}
.issue{{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin:8px 0}}
.issue summary{{cursor:pointer;padding:12px 14px;display:flex;gap:10px;align-items:center;list-style:none;flex-wrap:wrap}}
.issue summary::-webkit-details-marker{{display:none}}.it{{flex:1;min-width:200px}}
.dot{{width:9px;height:9px;border-radius:50%}}.crit .dot{{background:var(--crit)}}.warn .dot{{background:var(--warn)}}.note .dot{{background:var(--note)}}
.cnt{{font-weight:600;font-variant-numeric:tabular-nums}}.pill{{font-size:12px;border:1px solid var(--bd);border-radius:20px;padding:1px 8px}}
.tw{{overflow-x:auto;margin:0 14px 12px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);vertical-align:top}}th{{color:var(--mut);font-weight:500}}
td{{word-break:break-word;max-width:480px}}a{{color:var(--acc);text-decoration:none}}
.warnbox{{background:var(--card);border:1px solid var(--warn);border-radius:10px;padding:12px 14px}}
.box{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:4px 0 8px}}
</style></head><body><main>
<h1>Что изменилось на сайте</h1>
<p class="mut">{_e(res["new_meta"]["start"])} · прошлая проверка {_e(when(res["old_meta"]["finished_at"]))} → эта проверка {_e(when(res["new_meta"]["finished_at"]))}</p>
{note}
<div class="grid">
<div class="card"><b>{os_["health"]}% → {ns["health"]}%</b><span>здоровье сайта</span></div>
<div class="card"><b class="good">{fixed}</b><span>проблем исправлено (критичные и предупреждения)</span></div>
<div class="card"><b class="bad">{added}</b><span>новых проблем (критичные и предупреждения)</span></div>
<div class="card"><b>{os_["pages"]} → {ns["pages"]}</b><span>страниц проверено</span></div>
</div>
<h2>Проблемы: что исправлено и что появилось</h2>
<p class="mut">Нажмите на строку, чтобы увидеть адреса. Цифры «было → стало» - сколько строк в этой проблеме.</p>
{"".join(sections) or '<p>Проблемы не изменились.</p>'}
{_new_ext_html(res.get("new_ext"))}
<h2>Изменения на страницах</h2>
<p class="mut">Страницы, которые есть в обеих проверках, но у них поменялся код ответа, индексируемость, title, description, H1, canonical или meta robots.</p>
<div class="box">{_table(["Страница", "Что", "Было", "Стало"], res["changes"]) or '<p style="margin:10px 14px">Изменений нет.</p>'}</div>
<h2>Новые страницы ({len(res["appeared"])})</h2>
<div class="box">{_table(["Адрес"], [[u] for u in res["appeared"]]) or '<p style="margin:10px 14px">Нет.</p>'}</div>
<h2>Пропавшие страницы ({len(res["gone"])})</h2>
<p class="mut">Были в прошлой проверке, а в этой не встретились: удалены, на них больше нет ссылок или не хватило лимита.</p>
<div class="box">{_table(["Адрес"], [[u] for u in res["gone"]]) or '<p style="margin:10px 14px">Нет.</p>'}</div>
</main></body></html>"""
    with open(os.path.join(out_dir, "сравнение.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    top_fixed, top_added, new_crit = _brief(res)
    return {"fixed": fixed, "added": added, "health_old": os_["health"], "health_new": ns["health"],
            "old_finished": res["old_meta"]["finished_at"], "new_finished": res["new_meta"]["finished_at"], "top_fixed": top_fixed, "top_added": top_added,
            "new_crit": new_crit, "not_collected": [x["title"] for x in res.get("not_collected") or []],
            "unseen": res.get("unseen") or 0}


# ---------- для отчёта клиенту, окна и Telegram

def _brief(res):
    """Коротко, какие проблемы исправлены и какие появились (критичные и предупреждения) — для отчёта клиенту,
    окна и Telegram. Проблема «на всём сайте» — одна настройка: считается одной."""
    fixed, added, new_crit = [], [], []
    for i in res["issues"]:
        if i["severity"] == NOTE:
            continue
        nf = min(len(i["fixed"]), 1) if i.get("sitewide") else len(i["fixed"])
        na = min(len(i["added"]), 1) if i.get("sitewide") else len(i["added"])
        base = {"title": i["title"], "sev": i["severity"], "old": i["old"], "new": i["new"]}
        # в списках — только то, где стало лучше или хуже в целом: «16 → 17» не пишем в «исправлено». Считаем по
        # страницам, которые открывали обе проверки (fixed/added), а не по общим «было → стало»: при другом охвате
        # обхода общие числа меняются и без правок на сайте
        if nf and nf > na:
            fixed.append(dict(base, n=nf))
        if na and na > nf:
            added.append(dict(base, n=na))
        if i["severity"] == CRIT and na and not i["old"] and not i.get("not_collected"):
            new_crit.append(i["title"])
    key = lambda x: ({CRIT: 0, WARN: 1}[x["sev"]], -x["n"])
    return sorted(fixed, key=key)[:10], sorted(added, key=key)[:10], new_crit


def _ru_date(s):
    """«2026-10-04 13:45:05» → «04.10.2026»."""
    s = str(s or "")
    return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) >= 10 and s[4] == "-" else s


def history(out_dir):
    """[(дата окончания, здоровье)] законченных проверок этого сайта в том же режиме, по порядку, включая эту."""
    from .window.reports_list import read_check, site_key
    out_dir = os.path.abspath(out_dir)
    base, me = os.path.dirname(out_dir), read_check(os.path.dirname(out_dir), os.path.basename(out_dir))
    if not me:
        return []
    pts = []
    for d in os.listdir(base):
        c = me if d == os.path.basename(out_dir) else read_check(base, d)
        if not c or site_key(c["site"]) != me["key"] or c["js"] != me["js"] or c["scope"] != me["scope"]:
            continue
        h = (c.get("summary") or {}).get("health")
        if c["finished"] and h is not None and (c["finished"] <= me["finished"] or c is me):
            pts.append((c["finished"], h))
    return sorted(pts)[-12:]


def _chart(pts):
    """Маленький график здоровья по проверкам (SVG, без библиотек)."""
    if len(pts) < 2:
        return ""
    w, h, pad = 560, 120, 26
    step = (w - 2 * pad) / (len(pts) - 1)
    xy = [(pad + i * step, 14 + (100 - v) / 100 * (h - 40)) for i, (_, v) in enumerate(pts)]
    line = " ".join(f"{x:.0f},{y:.0f}" for x, y in xy)
    days = [_ru_date(d)[:5] for d, _ in pts]  # две проверки в один день — у второй время
    labels = [str(d)[11:16] if k and days[k - 1] == days[k] else days[k] for k, d in enumerate(d for d, _ in pts)]
    dots = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.5"/><text x="{x:.0f}" y="{y - 7:.0f}" '
                   f'text-anchor="middle" class="v">{v}%</text><text x="{x:.0f}" y="{h - 4}" text-anchor="middle" '
                   f'class="d">{_e(lb)}</text>' for (x, y), (d, v), lb in zip(xy, pts, labels))
    return (f'<svg class="hchart" viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px" role="img" aria-label="Здоровье сайта '
            # <style> внутри SVG действует на всю страницу: только .hchart, иначе красит круг и подписи паутины
            f'по проверкам"><style>.hchart polyline{{fill:none;stroke:var(--acc,#3b5bdb);stroke-width:2.5}}'
            f'.hchart circle{{fill:var(--acc,#3b5bdb)}}.hchart text{{font:12px system-ui,sans-serif;fill:var(--mut,#6b6a66)}}'
            f'.hchart text.v{{fill:var(--tx,#1f1e1c);font-weight:600}}</style><polyline points="{line}"/>{dots}</svg>')


def client_html(cmp, pts=(), h2="h2", h2_cls="sec", cls="card"):
    """«Что изменилось с прошлой проверки»: здоровье было → стало, график, что исправлено и что появилось."""
    if not cmp:
        return ""
    d = cmp["health_new"] - cmp["health_old"]
    trend = "выросло" if d > 0 else "снизилось" if d < 0 else "не изменилось"

    def lst(items, empty):
        if not items:
            return f'<p class="mut">{empty}</p>'
        return "<ul>" + "".join(f'<li>{_e(x["title"])} <span class="mut">({x["old"]} → {x["new"]})</span></li>'
                                for x in items) + "</ul>"
    return (f'<{h2} class="{h2_cls}">Что изменилось с прошлой проверки</{h2}><div class="{cls}">'
            f'<p>Прошлая проверка - {_e(_ru_date(cmp["old_finished"]))}. Здоровье сайта {trend}: '
            f'<b>{cmp["health_old"]}% → {cmp["health_new"]}%</b>. Исправлено проблем: <b>{cmp["fixed"]}</b>, '
            f'появилось новых: <b>{cmp["added"]}</b> (критичные и предупреждения).</p>{_chart(list(pts))}'
            f'<h3>Исправлено</h3>{lst(cmp.get("top_fixed"), "Ничего из прошлых проблем пока не исправлено.")}'
            f'<h3>Появилось нового</h3>{lst(cmp.get("top_added"), "Новых проблем нет.")}'
            '<p class="mut">В скобках - сколько адресов с этой проблемой было и стало.</p>'
            + (f'<p class="mut">{_e(UNSEEN_TEXT)}.</p>' if cmp.get("unseen") else "")
            + (f'<p class="mut">{_e(NOT_COLLECTED_TEXT)}: {_e(", ".join(cmp["not_collected"]))}.</p>'
               if cmp.get("not_collected") else "") + '</div>')


UNSEEN_TEXT = ("Исправленное и новое считали только по страницам, которые проверялись оба раза: на остальных "
               "страницах изменения не оценивались")
NOT_COLLECTED_TEXT = ("Эти проверки в прошлый раз не делались, поэтому их результаты не считаются новыми "
                      "проблемами, сравнение по ним будет со следующей проверки")


def audit_html(summary):
    b = client_html(summary.get("compare"), summary.get("history") or (), h2_cls="", cls="")
    return f'<section class="pt">{b}</section>' if b else ""


def docx_paras(cmp, _para, _run):
    if not cmp:
        return []
    body = [_para([_run("Что изменилось с прошлой проверки", bold=True, size=28)], 80, keep=True),
            _para([_run(f"Прошлая проверка - {_ru_date(cmp['old_finished'])}. Здоровье сайта: "
                        f"{cmp['health_old']}% → {cmp['health_new']}%. Исправлено проблем: {cmp['fixed']}, "
                        f"появилось новых: {cmp['added']}.", size=20)], 80)]
    for head, items in (("Исправлено", cmp.get("top_fixed")), ("Появилось нового", cmp.get("top_added"))):
        if items:
            body.append(_para([_run(head, bold=True, size=20)], 40, keep=True))
            body += [_para([_run(f"• {x['title']} ({x['old']} → {x['new']})", size=20)], 20, indent=360) for x in items]
    if cmp.get("unseen"):
        body.append(_para([_run(UNSEEN_TEXT + ".", size=18)], 40))
    if cmp.get("not_collected"):
        body.append(_para([_run(f"{NOT_COLLECTED_TEXT}: {', '.join(cmp['not_collected'])}.", size=18)], 40))
    body.append(_para([], 120))
    return body
