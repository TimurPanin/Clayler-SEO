"""Карточка сайта: одна страница со всем главным о сайте - дата и время проверки,
здоровье, снимок главной с телефона, движок и хостинг, главные проблемы для исправления, бренды из названий
товаров, семантика, смета и ссылки на файлы проверки. Ничего не считает заново: берёт то, что уже собрано для
отчёта (issues, summary, meta). Файл - карточка.html в папке проверки, в окне - кнопка «Карточка»."""
import base64
import os

from .analyze import CRIT, WARN, NOTE
from .client_report import HIDE, client_text
from .express import _first_sentence
from .fmt import esc as e, num

NAME = "карточка.html"
TOP = 7          # главных проблем
BRANDS_TOP = 15  # брендов в карточке
# тёмная тема: по настройке системы, а в окне программы (тёмное всегда) - по #dark в адресе
DARK = "--bg:#161616;--fg:#ececec;--mut:#9a9aa0;--bd:#2c2c30;--card:#1e1e1e;--good:#4fbf8a;--mid:#e0a84a;--bad:#ef6b6b;--warn:#f0973c;--note:#e3c84a;--acc:#8e9cff"
SEV = {CRIT: ("crit", "критично"), WARN: ("warn", "предупреждение"), NOTE: ("note", "замечание")}
# Вкладка «Отчёты и файлы»: файл, название, для чего. Показываются только те, что есть в папке
FILES = [("отчёт.html", "Полный отчёт", "Все проблемы со списками адресов и советами - для вас"),
         ("отчёт_для_клиента.html", "Отчёт для клиента", "Тот же отчёт без служебных советов, с вашими контактами"),
         ("аудит.html", "Аудит", "По пунктам: что проверено и что исправить"),
         ("аудит.pdf", "Аудит PDF", "Аудит одним файлом для отправки клиенту"),
         ("аудит.docx", "Аудит Word", "Аудит, который можно дописать своими словами"),
         ("отчёт.xlsx", "Таблица Excel", "Все проблемы и страницы таблицей"),
         ("смета.pdf", "Смета PDF", "Работы и часы - предварительная оценка"),
         ("экспресс.pdf", "Экспресс-аудит", "Коротко на одной-двух страницах"),
         ("сравнение.html", "Что изменилось", "Сравнение с прошлой проверкой: исправлено и новое"),
         ("отчёт за месяц.html", "Отчёт за месяц", "Здоровье было и стало, что исправлено за месяц"),
         ("конкуренты.html", "Конкуренты", "Сравнение с сайтами конкурентов"),
         ("семантика.xlsx", "Семантика Excel", "Запросы и группы"),
         ("паутина.png", "Паутина", "Картинка: как страницы связаны ссылками"),
         ("видео обхода.mp4", "Видео обхода", "Как проверка шла по сайту"),
         ("аудит_демо.pdf", "PDF для витрины", "Образец без контактов - для портфолио")]
CLIENT_DIR = "для клиента"


def when(s):
    """«2026-09-28 23:15:04» → «28.09.2026 в 23:15»."""
    s = s or ""
    if len(s) < 16:
        return s
    return f"{s[8:10]}.{s[5:7]}.{s[:4]} в {s[11:16]}"


def top_issues(issues):
    """Главные проблемы для исправления: критичные, потом важные; внутри - по приросту здоровья и числу страниц."""
    todo = [i for i in issues if i.severity in (CRIT, WARN) and i.key not in HIDE]
    todo.sort(key=lambda i: (0 if i.severity == CRIT else 1, -(getattr(i, "gain", 0) or 0), -i.count))
    return todo[:TOP]


def brands(out_dir):
    """Бренды из названий товаров (semantics.models, как в семантике 1.5): [(бренд, товаров)], всего брендов."""
    try:
        from .semantics import models
        names = models.from_db(os.path.join(out_dir, "crawl.db"))
        if len(names) < models.MIN_PRODUCTS:
            return [], 0
        b = models.parse(names)["brands"]
    except Exception:
        return [], 0
    b = sorted(((k, v) for k, v in b.items() if v >= 2), key=lambda x: -x[1])
    return b[:BRANDS_TOP], len(b)


def _img(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def home_shot(out_dir, meta):
    """Снимки главной «Компьютер / Телефон» (проверка мобильной версии, mobile_view; всплывающие окна закрыты перед
    снимком) - картинками внутри файла, чтобы карточку можно было переслать одним файлом. Переключатель без скриптов."""
    mv = meta.get("mobile_view") or {}
    if not isinstance(mv, dict):
        return ""
    shots = []
    d = mv.get("desktop") or {}
    if d.get("shot"):
        data = _img(os.path.join(out_dir, "мобильная", d["shot"]))
        if data:
            shots.append(("pc", "Компьютер", data, d.get("load_s")))
    pages = mv.get("pages") or []
    if pages:
        start = (meta.get("start") or "").rstrip("/")
        p = next((p for p in pages if (p.get("url") or "").rstrip("/") == start), pages[0])
        data = _img(os.path.join(out_dir, "мобильная", p.get("shot") or "")) if p.get("shot") else ""
        if data:
            shots.append(("ph", "Телефон", data, p.get("load_s")))
    if not shots:
        return ""
    sec = lambda x: f", загрузка {str(x).replace('.', ',')} с" if x else ""
    tabs = "".join(f'<input type="radio" name="shot" id="s-{k}"{" checked" if n == 0 else ""}>'
                   f'<label for="s-{k}">{lab}</label>' for n, (k, lab, _d, _s) in enumerate(shots)) if len(shots) > 1 else ""
    figs = "".join(f'<figure class="shot s-{k}"><img src="data:image/jpeg;base64,{data}" alt="Главная страница: '
                   f'{lab.lower()}"><figcaption>Главная, {lab.lower()}{sec(ld)}</figcaption></figure>'
                   for k, lab, data, ld in shots)
    return f'<div class="shots">{tabs}{figs}</div>'


def _size(n):
    return f"{n / 1048576:.1f} МБ".replace(".", ",") if n >= 1048576 else f"{max(1, round(n / 1024))} КБ"


def files_html(out_dir):
    """Вкладка «Отчёты и файлы»: каждый файл проверки карточкой (что это, размер, когда собран) и папка «для клиента»."""
    import time
    from urllib.parse import quote

    def card(rel, title, what):
        path = os.path.join(out_dir, rel)
        st = os.stat(path)
        ext = rel.rsplit(".", 1)[-1].upper() if "." in rel else ""
        href = "/".join(quote(x) for x in rel.replace(os.sep, "/").split("/"))
        return (f'<a class="fc" href="{href}" target="_blank"><span class="ext">{e(ext)}</span><b>{e(title)}</b>'
                f'<span class="mut">{e(what)}</span><small>{_size(st.st_size)} · '
                f'{time.strftime("%d.%m.%Y %H:%M", time.localtime(st.st_mtime))}</small></a>')
    own = "".join(card(f, t, w) for f, t, w in FILES if os.path.isfile(os.path.join(out_dir, f)))
    cdir = os.path.join(out_dir, CLIENT_DIR)
    client = ""
    if os.path.isdir(cdir):
        client = "".join(card(os.path.join(CLIENT_DIR, f), f.rsplit(".", 1)[0], "Готово к отправке клиенту")
                         for f in sorted(os.listdir(cdir)) if os.path.isfile(os.path.join(cdir, f)))
    if not own and not client:
        return '<section><p class="mut">Файлов отчёта в папке проверки нет.</p></section>'
    return ((f'<section><h2>Отчёты проверки</h2><div class="fcs">{own}</div></section>' if own else "")
            + (f'<section><h2>Для клиента</h2><p class="mut">Папка «{CLIENT_DIR}»: эти файлы можно отправлять как есть.'
               f'</p><div class="fcs">{client}</div></section>' if client else ""))


def tech_rows(meta):
    t = meta.get("site_tech") or {}
    rows = []
    eng = ", ".join(x["name"] + (f' {x["version"]}' if x.get("version") else "") for x in t.get("engines") or [])
    if eng:
        rows.append(("Движок", eng))
    if t.get("tech"):
        rows.append(("Технологии", ", ".join(t["tech"])))
    if t.get("hosting"):
        rows.append(("Хостинг", t["hosting"]))
    dom = t.get("domain") or {}
    if dom.get("created") or dom.get("expires"):
        rows.append(("Домен", ", ".join(x for x in (
            f'зарегистрирован {when(dom["created"] + " 00:00")[:10]}' if dom.get("created") else "",
            f'оплачен до {when(dom["expires"] + " 00:00")[:10]}' if dom.get("expires") else "",
            f'регистратор {dom["registrar"]}' if dom.get("registrar") else "") if x)))
    cert = t.get("cert") or {}
    if cert.get("expires"):
        rows.append(("Сертификат HTTPS", f'{cert.get("issuer") or ""}, до {when(cert["expires"] + " 00:00")[:10]}'.lstrip(", ")))
    if t.get("mail"):
        rows.append(("Почта", t["mail"]))
    if t.get("services"):
        rows.append(("Сервисы", ", ".join(t["services"])))
    return rows


def write(out_dir, meta, issues, summary):
    from .duration import fmt, seconds
    site = meta.get("start", "")
    host = site.split("//")[-1].strip("/")
    h = summary.get("health", 0)
    hc = "good" if h >= 90 else ("mid" if h >= 70 else "bad")
    took = fmt(seconds(meta))
    cmp_ = summary.get("compare") or {}
    sub = [f"проверено страниц: {num(summary.get('pages', 0))}"] + ([f"обход {took}"] if took else [])
    if summary.get("queue_left"):
        sub.append(f"не проверено ещё {num(summary['queue_left'])}")
    counts = (f'<div class="cnt"><span class="crit">{summary.get("crit", 0)}</span> критичных · '
              f'<span class="warn">{summary.get("warn", 0)}</span> важных · '
              f'<span class="note">{summary.get("note", 0)}</span> замечаний</div>')
    if cmp_.get("old_finished"):
        counts += (f'<div class="mut">С проверки {e(when(cmp_["old_finished"]))}: исправлено {cmp_.get("fixed", 0)}, '
                   f'новых {cmp_.get("added", 0)}</div>')

    probs = []
    for n, i in enumerate(top_issues(issues), 1):
        cls, lab = SEV[i.severity]
        gain = getattr(i, "gain", 0) or 0
        probs.append(
            f'<li><div class="t"><span class="n">{n}</span><span class="sev {cls}">{lab}</span> '
            f'<b>{e(client_text(i.title))}</b> <span class="mut">- {e(i.count_text)}</span>'
            + (f' <span class="g">+{str(gain).replace(".", ",")}% к здоровью</span>' if gain >= 1 else "")
            + f'</div><p>{e(_first_sentence(client_text(i.fix)))}</p></li>')
    probs_html = "".join(probs) or "<li>Серьёзных проблем не найдено.</li>"

    from . import country as C
    c_head, c_why = C.text(summary.get("country"))
    c_srv = C.server_text((summary.get("country") or {}).get("server"))
    c_row = (f'<tr><th>Страна</th><td>{c_head}' + (f'<div class="mut">{e("; ".join(x for x in (c_why, c_srv) if x))}</div>'
             if c_why or c_srv else "") + "</td></tr>") if c_head else ""
    tech = c_row + "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in tech_rows(meta))
    tech_html = f'<section><h2>Сайт</h2><table class="kv">{tech}</table></section>' if tech else ""

    top_b, all_b = brands(out_dir)
    brands_html = ""
    if top_b:
        chips = "".join(f'<span class="chip">{e(b)} <i>{num(n)}</i></span>' for b, n in top_b)
        brands_html = (f'<section><h2>Бренды на сайте <span class="mut">{all_b}</span></h2>'
                       f'<p class="mut">По названиям товаров; число - товаров бренда.</p><div class="chips">{chips}</div></section>')

    sem = summary.get("semantics") or {}
    sem_html = ""
    if sem:
        cnt = sem.get("cnt") or {}
        sem_html = (f'<section><h2>Семантика</h2><p>Запросов {num(sem.get("queries", 0))}, групп {num(sem.get("groups", 0))}'
                    + (f', регион {e(sem["city"])}' if sem.get("city") else "")
                    + (f', собрана {e(sem["made"])}' if sem.get("made") else "") + '.</p>'
                    + f'<p class="mut">Страница есть и подходит: {cnt.get("ok", 0)}, доработать: {cnt.get("fix", 0)}, '
                      f'не та страница: {cnt.get("wrong", 0)}, создать: {cnt.get("create", 0)}.</p></section>')

    works = summary.get("works") or []
    est_html = ""
    if works:
        from .estimate import totals
        t = totals(works)
        # «1. Срочно: мешает индексации…» → «срочно»
        st = ", ".join(f"{e(k.split(':')[0].split('. ', 1)[-1].lower())} {str(v).replace('.', ',').removesuffix(',0')} ч" for k, v in t["stages"].items())
        est_html = (f'<section><h2>Смета</h2><p>Работ {len(works)}, около '
                    f'{str(t["hours"]).replace(".", ",").removesuffix(",0")} ч: {st}.</p></section>')


    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Карточка сайта {e(host)}</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--bd:#e3e3e6;--card:#f6f6f8;--good:#2e7d32;--mid:#b26a00;--bad:#c62828;--warn:#d9730d;--note:#b08d00;--acc:#4a5bd4}}
@media (prefers-color-scheme:dark){{:root{{{DARK}}}}}
:root.dark{{{DARK}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:980px;margin:0 auto;padding:20px 16px}}.mut{{color:var(--mut)}}a{{color:var(--acc)}}
h1{{font-size:24px;margin:0}}h1 a{{color:inherit;text-decoration:none}}h2{{font-size:16px;margin:0 0 8px}}
.top{{display:grid;grid-template-columns:1fr 260px;gap:20px;align-items:start}}
.head{{display:flex;gap:20px;align-items:center;margin:14px 0}}
.hl{{font-size:56px;font-weight:700;line-height:1}}.hl small{{display:block;font-size:12px;font-weight:400;color:var(--mut)}}
.good{{color:var(--good)}}.mid{{color:var(--mid)}}.bad{{color:var(--bad)}}
.cnt .crit{{color:var(--bad);font-weight:700}}.cnt .warn{{color:var(--warn);font-weight:700}}.cnt .note{{color:var(--note);font-weight:700}}
section{{background:var(--card);border-radius:10px;padding:14px 16px;margin:14px 0}}
ol{{list-style:none;padding:0;margin:0}}li{{border-top:1px solid var(--bd);padding:8px 0}}li:first-child{{border-top:0}}
li p{{margin:3px 0 0 30px;color:var(--mut)}}
.n{{display:inline-block;width:22px;height:22px;border-radius:11px;background:var(--bd);text-align:center;font-size:12px;line-height:22px;margin-right:6px}}
.sev{{font-size:11px;border-radius:4px;padding:1px 6px;margin-right:4px;white-space:nowrap}}
.sev.crit{{background:var(--bad);color:#fff}}.sev.warn{{background:var(--warn);color:#fff}}.sev.note{{background:var(--note);color:#fff}}
.g{{color:var(--good);font-weight:600;white-space:nowrap}}
.kv{{border-collapse:collapse;width:100%}}.kv th{{text-align:left;font-weight:400;color:var(--mut);width:170px;padding:3px 10px 3px 0;vertical-align:top}}.kv td{{padding:3px 0}}
.chips,.files{{display:flex;flex-wrap:wrap;gap:6px}}.chip{{background:var(--bg);border:1px solid var(--bd);border-radius:14px;padding:2px 10px}}
.chip i{{font-style:normal;color:var(--mut);font-size:12px}}
.files a{{background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;text-decoration:none}}
.shot{{margin:0}}.shot img{{width:100%;border:1px solid var(--bd);border-radius:12px;max-height:440px;object-fit:cover;object-position:top}}
.shot figcaption{{font-size:12px;color:var(--mut);text-align:center}}
.shots input,.tabs input{{position:absolute;opacity:0;pointer-events:none}}
.shots label,.tabs label{{display:inline-block;padding:3px 10px;border:1px solid var(--bd);border-radius:14px;cursor:pointer;margin:0 4px 6px 0;font-size:13px}}
.shots input:checked+label,#t-main:checked~.tl [for=t-main],#t-files:checked~.tl [for=t-files]{{background:var(--acc);border-color:var(--acc);color:#fff}}
.shots input:focus-visible+label,#t-main:focus-visible~.tl [for=t-main],#t-files:focus-visible~.tl [for=t-files]{{outline:2px solid var(--acc);outline-offset:2px}}
.tl{{margin:12px 0 0}}
#s-pc:checked~.s-ph,#s-ph:checked~.s-pc{{display:none}}
#t-main:checked~.p-files,#t-files:checked~.p-main{{display:none}}
.fcs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}}
.fc{{display:flex;flex-direction:column;gap:3px;background:var(--bg);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;text-decoration:none;color:var(--fg)}}
.fc:hover{{border-color:var(--acc)}}.fc small{{color:var(--mut);font-size:12px}}
.fc .ext{{font-size:11px;font-weight:700;color:var(--acc);letter-spacing:.04em}}
@media (max-width:640px){{.top{{grid-template-columns:1fr}}.shot img{{max-height:300px}}.kv th{{width:120px}}}}
</style><script>if (location.hash === "#dark") document.documentElement.classList.add("dark")</script></head><body><main>
<div class="tabs"><input type="radio" name="tab" id="t-main" checked><input type="radio" name="tab" id="t-files">
<h1>{C.flag_svg(summary["country"]["code"], 22) + " " if c_head else ""}<a href="{e(site)}" target="_blank">{e(host)}</a></h1>
<div class="mut">Проверка {e(when(meta.get("finished_at") or meta.get("started_at")))} · {" · ".join(sub)}</div>
<div class="tl"><label for="t-main">Главное</label><label for="t-files">Отчёты и файлы</label></div>
<div class="p-main"><div class="top"><div>
<div class="head"><div class="hl {hc}">{h}%<small>здоровье сайта</small></div><div>{counts}</div></div>
<section><h2>Что исправить первым</h2><ol>{probs_html}</ol></section>
</div>{home_shot(out_dir, meta)}</div>
{tech_html}{brands_html}{sem_html}{est_html}
</div><div class="p-files">{files_html(out_dir)}</div></div>
</main></body></html>"""
    path = os.path.join(out_dir, NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
