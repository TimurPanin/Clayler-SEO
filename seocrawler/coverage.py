"""«Что не проверено и почему»: сколько адресов отброшено как фильтры и
сортировки, сколько не успели из-за лимита, сколько закрыто (robots.txt, вход, ошибки), сверены ли страницы из
поиска. Чтобы клиент видел: проверено всё, что можно, а остальное не открывалось по понятной причине.
collect(store, summary) → {"pages", "checked", "rows": [{what, n, why, cls}], "all_done"} — кладётся в
summary["coverage"] (crawl.py), показывается в отчёте, отчёте для клиента, аудите (HTML, PDF, Word) и Excel.
cls: ok — всё в порядке, info — так задумано, warn — стоит знать (не успели, не открылись)."""
from .fmt import esc as _e, num as _n, plural as _plural, quote

HEAD = "Что не проверено и почему"

SEARCH_STATE = {
    "not_connected": "доступ к {name} не подключён",
    "no_access": "нет доступа к сайту в {name}",
    "no_data": "у {name} пока нет данных по сайту",
    "error": "{nom} не ответил",
}
SEARCH_NAME = {"yandex": ("Яндекс Вебмастер", "Яндекс Вебмастеру", "поиска Яндекса"),
               "google": ("Google Search Console", "Google Search Console", "поиска Google")}


# ---------- закон сохранения полноты (ИНЖЕНЕРНЫЕ_ПРАВИЛА.md, раздел 1а, корень 3): каждый адрес своего
# сайта - ровно в одном ящике, сумма ящиков = все адреса своего сайта в базе. Раньше строки этого раздела собирались
# по одной («найди X»), и что не подходило ни под одну, пропадало молча: 47 067 непроверенных картинок market-primer.ru,
# копии сайта с www, адреса sitemap, закрытые в robots.txt, - а отчёт писал «проверено всё».
SKIP_BOXES = [   # (ящик, как узнать причину пропуска); новая причина без ящика попадает в «other» - и видна
    ("robots", lambda r: r.startswith("Закрыт в robots")),
    ("params", lambda r: r.startswith("Больше ") and "параметр" in r),
    ("depth", lambda r: r.startswith("Глубина больше")),
    ("trap", lambda r: r.startswith("Повторяющийся путь") or r.startswith("URL длиннее")),
    ("excluded", lambda r: r.startswith("Исключён правилом")),
    ("mirror", lambda r: r.startswith("Копия сайта")),   # mirror_copy.SKIP
    ("files_off", lambda r: r == "Проверка картинок выключена"),
]
GROUPS = {"page": "page", "sitemap": "sitemap", "resource": "file"}


def box(state, reason):
    """В какой ящик попадает адрес своего сайта: checked, broken (открыт, разобран не целиком), left (не дошла
    очередь), один из SKIP_BOXES или other (непонятное - тоже ящик, а не пропуск)."""
    reason = reason or ""
    if state == "done":
        return "broken" if reason.startswith("Сбой обработки") else "checked"
    if state in ("queued", "fetching"):
        return "left"
    if state == "skipped":
        for name, test in SKIP_BOXES:
            if test(reason):
                return name
    return "other"


def ledger(db):
    """({(группа, ящик): число}, {причина: число} для ящика other). Группа: page, sitemap, file или other."""
    out, other = {}, {}
    for kind, state, reason, n in db.execute("SELECT kind, state, skip_reason, COUNT(*) FROM urls WHERE internal=1 "
                                             "GROUP BY kind, state, skip_reason"):
        key = (GROUPS.get(kind, "other"), box(state, reason))
        out[key] = out.get(key, 0) + n
        if key[1] == "other":
            why = f"{state}: {reason or 'причина не записана'}"
            other[why] = other.get(why, 0) + n
    return out, other


def page_gaps(store):
    """Открытые страницы своего сайта, у которых проверка неполная: {js_fail, js_none, truncated: число}.
    js_none - проверка с JavaScript, а страница в браузере не открывалась вовсе (остановили проверку, браузер
    не работал). Внешние страницы в браузере не открываются - так и задумано, их здесь нет."""
    db = store.db
    cols = {r[1] for r in db.execute("PRAGMA table_info(pages)")}
    if not {"truncated", "js_error", "js_time"} <= cols:
        return {}   # очень старая база: этих данных при проверке ещё не записывали
    # рабочая страница - как в анализе (analyze/prepare.html_ok): 200, HTML, без ошибки загрузки
    own = ("FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind IN ('page', 'sitemap') "
           "AND p.status=200 AND p.content_type IN ('text/html', 'application/xhtml+xml') AND COALESCE(p.error, '')=''")
    out = {"truncated": db.execute(f"SELECT COUNT(*) {own} AND p.truncated=1").fetchone()[0]}
    if store.get_meta("render_js", False):
        out["js_fail"] = db.execute(f"SELECT COUNT(*) {own} AND COALESCE(p.js_error, '')<>''").fetchone()[0]
        out["js_none"] = db.execute(f"SELECT COUNT(*) {own} AND COALESCE(p.js_error, '')='' "
                                    "AND p.js_time IS NULL").fetchone()[0]
    return out


def collect(store, summary):
    db = store.db
    led, other = ledger(db)

    shown = set()   # какие ящики уже в строках раздела: остальные непроверенные - в строку «по другой причине»

    def take(*boxes, groups=("page", "sitemap")):
        keys = [k for k in led if k[1] in boxes and k[0] in groups]
        shown.update(keys)
        return sum(led[k] for k in keys)

    rows = []

    def row(what, n, why, cls="info", ledger=False):
        if n:
            rows.append({"what": what, "n": n, "why": why, "cls": cls})
            if ledger:   # число из учёта адресов (take): строка - часть закона сохранения
                rows[-1]["ledger"] = True

    cfg = store.get_meta("config", {}) or {}
    pages = summary.get("pages") or 0
    left = take("left", groups=("page",))
    limit = store.get_meta("max_pages", None) or cfg.get("max_pages")
    if left:
        if limit and pages >= limit:
            row(f"Не успели проверить: набран лимит {_n(limit)} страниц", left,
                "Эти страницы найдены по ссылкам, но в проверку не вошли. Остальные данные отчёта - по проверенным "
                "страницам. Чтобы проверить сайт целиком, нужна проверка с большим лимитом.", "warn", ledger=True)
        else:
            row("Не успели проверить: проверка остановлена раньше конца", left,
                "Эти страницы найдены по ссылкам, но проверка была остановлена до них.", "warn", ledger=True)
    row("Адреса из sitemap: не успели проверить", take("left", groups=("sitemap",)),
        "Сайт перечислил эти адреса в sitemap, но проверка была остановлена раньше, чем до них дошла очередь.", "warn",
        ledger=True)
    row("Картинки и файлы сайта: не успели проверить", take("left", groups=("file",)),
        "Найдены на проверенных страницах, но проверка была остановлена раньше, чем до них дошла очередь: битые "
        "картинки и файлы среди них не видны. «Продолжить прошлую проверку» проверит их, страницы заново не "
        "открываются.", "warn", ledger=True)
    row("Адреса фильтров и сортировок каталога", take("params"),
        f"Адреса с {cfg.get('max_params', 3) + 1} и больше параметрами (цвет, размер, цена, порядок). Это те же "
        "страницы каталога с другим отбором, их бывают десятки тысяч, и поисковику они обычно не нужны. Сами страницы "
        "каталога проверены.", ledger=True)
    marks = db.execute("SELECT COUNT(DISTINCT raw) FROM param_links").fetchone()[0]
    row("Ссылки с метками (utm, yclid) и лишними параметрами", marks,
        "Проверены по адресу без меток: метки не меняют страницу, а считать их отдельными страницами - значит "
        "насчитать лишние дубли.")
    # то же условие, что у проблемы «Адреса, закрытые в robots.txt» (checks/indexing.py): числа должны совпадать
    row("Закрыто правилами сайта для поисковых роботов (robots.txt)", take("robots", groups=("page",)),
        "Сайт сам запрещает роботам заходить на эти адреса, поэтому при проверке они тоже не открывались. Список - "
        "в проблеме «Адреса, закрытые в robots.txt»: стоит убедиться, что среди них нет нужных страниц.", ledger=True)
    row("Адреса из sitemap, закрытые в robots.txt", take("robots", groups=("sitemap",)),
        "Сайт перечислил эти адреса в sitemap, но сам же запретил роботам на них заходить, поэтому при проверке они "
        "не открывались. Это противоречие: такие адреса стоит убрать из sitemap или открыть в robots.txt.",
        ledger=True)
    row("Картинки и файлы, закрытые в robots.txt", take("robots", groups=("file",)),
        "Сайт запрещает роботам загружать эти файлы, поэтому при проверке они тоже не открывались. Если среди них "
        "картинки товаров, стили или скрипты страниц, поисковик их тоже не увидит.", ledger=True)
    row("Слишком глубоко от главной", take("depth"),
        f"Страницы дальше {cfg.get('max_depth', 50)} кликов от главной, которых нет в sitemap. Дальше этой глубины "
        "проверка не идёт, чтобы бесконечные ссылки (календарь, листание без конца) не заняли её целиком. Если среди "
        "них настоящие страницы, до них слишком долго добираться и посетителю, и поисковику: стоит сократить путь "
        "или добавить их в sitemap.", ledger=True)
    row("Адреса-ловушки", take("trap", groups=("page", "sitemap", "file")),
        "Адреса с повторяющимся куском пути или длиннее 2 000 символов: так выглядят бесконечные ссылки, "
        "которые сайт создаёт сам. Настоящих страниц за ними нет.", ledger=True)
    row("Исключены настройками проверки", take("excluded", groups=("page", "sitemap", "file")),
        "Адреса, которые попросили не проверять (например, личный кабинет или корзина)."
        + (" Маски: " + ", ".join(quote(m) for m in cfg.get("skip_masks")[:10]) + "." if cfg.get("skip_masks") else ""),
        ledger=True)
    row("Копия сайта с www или без www", take("mirror"),
        "Сайт открывается по двум адресам без перенаправления. Вторую копию целиком не обходили: это те же страницы. "
        "Сама проблема - в пункте «Вариант адреса сайта открывается без редиректа», ссылки на копию - в «Ссылки на "
        "копию сайта».", ledger=True)
    row("Картинки и файлы сайта не проверялись", take("files_off", groups=("page", "sitemap", "file")),
        "Проверка картинок и файлов была выключена в настройках.", ledger=True)
    row("Разобраны не целиком: сбой при проверке", take("broken", groups=("page", "sitemap", "file")),
        "Адрес открылся, но при проверке его не удалось разобрать до конца: данные по нему могут быть неполными.",
        "warn", ledger=True)
    # закон сохранения: всё непроверенное, что не попало ни в одну строку выше (новая причина пропуска, новый вид
    # адреса), - здесь, а не пропадает. Тест проверить_полноту: сумма строк = все непроверенные адреса
    rest = {k: n for k, n in led.items() if k[1] != "checked" and k not in shown}
    if rest:
        why = dict(other)
        for (g, b), n in rest.items():
            if b != "other":
                why[f"{g}: {b}"] = why.get(f"{g}: {b}", 0) + n
        row("Не проверены по другой причине", sum(rest.values()),
            "Причины: " + "; ".join(f"{w} ({_n(n)})" for w, n in sorted(why.items(), key=lambda x: -x[1])[:5]) + ".",
            "warn", ledger=True)
    gaps = page_gaps(store)
    rechecked = store.get_meta("js_rechecked", None)
    row("Не открылись в браузере с JavaScript", gaps.get("js_fail"),
        "Страница открылась, но в браузере с JavaScript - нет (браузер не дождался загрузки или сам не работал)"
        + (f"; после обхода такие страницы открывали ещё раз: {_n(rechecked.get('checked') or 0)}, открылись "
           f"{_n(rechecked.get('fixed') or 0)}" if rechecked else "")
        + ". Для них в отчёте данные только из исходного кода страницы: то, что добавляют скрипты (текст, ссылки, "
        "цены), не проверено.", "warn")
    row("Не открывались в браузере с JavaScript", gaps.get("js_none"),
        "Проверка шла с JavaScript, но до этих страниц браузер не дошёл (проверку остановили или браузер не "
        "работал). Для них данные только из исходного кода страницы.", "warn")
    row("Страницы больше 5 МБ: разобраны только по началу", gaps.get("truncated"),
        "Код страницы слишком большой (или сжатые данные оборвались): ссылки и текст после обрыва не проверены. "
        "Такая тяжёлая страница сама по себе медленно грузится.", "warn")
    errs = db.execute("SELECT COUNT(*) FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND "
                      "u.kind<>'resource' AND ((p.error IS NOT NULL AND p.error<>'') OR p.status>=500)").fetchone()[0]
    row("Не открылись: сервер не ответил или выдал ошибку", errs,
        "Эти страницы открывали ещё раз после обхода, но они так и не открылись. Для посетителей и поисковика это "
        "такая же ошибка; список - в проблемах про ошибки сервера.", "warn")
    auth = db.execute("SELECT COUNT(*) FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND "
                      "u.kind<>'resource' AND p.status IN (401, 403)").fetchone()[0]
    row("Закрыты входом или паролем (код 401 или 403)", auth,
        "Без входа эти страницы не открываются ни посетителю, ни поисковику. Если это личный кабинет - так и должно "
        "быть; если обычные страницы - это ошибка.")
    ext =db.execute("SELECT COUNT(*) FROM urls WHERE state='skipped' AND internal=0 AND skip_reason LIKE "
                     "'Фото или файл с другого сайта%'").fetchone()[0]
    row("Фото и файлы с других сайтов - проверены выборочно", ext,
        "Картинки, которые лежат на чужом сервере (CDN), проверены выборкой: по 1 000 с каждого сервера. Если "
        "среди них нашлась хоть одна битая, проверены все.")
    ext_links = db.execute("SELECT COUNT(*) FROM urls WHERE state='skipped' AND internal=0 AND skip_reason LIKE "
                           "'Ссылка на другой сайт%'").fetchone()[0]
    row("Ссылки на другие сайты - проверены выборочно", ext_links,
        "На один сайт ведёт очень много ссылок (например, кнопки «Поделиться» на каждой странице или поддомены): "
        "проверены до 300 ссылок на каждый сайт (на все поддомены вместе) и до 20 адресов, которые отличаются только параметрами.")
    no_ext = db.execute("SELECT COUNT(*) FROM urls WHERE state='skipped' AND internal=0 AND "
                        "skip_reason='Внешняя ссылка не проверялась'").fetchone()[0]
    row("Ссылки на другие сайты не проверялись", no_ext, "Проверка ссылок на другие сайты была выключена.")
    has_sm = db.execute("SELECT 1 FROM sitemap LIMIT 1").fetchone()
    if has_sm and not store.get_meta("sitemap_checked", False) and not store.get_meta("scope", None) and left:
        row("Страницы из sitemap без ссылок не искали", 1,
            "Сайт обойдён не целиком, поэтому нельзя сказать, на какие страницы из sitemap нет ссылок.", "warn")
    su = store.get_meta("search_urls", None)
    if su:
        for key, (name, dat, gen) in SEARCH_NAME.items():
            s = (su.get("sources") or {}).get(key)
            if not su.get("complete"):
                rows.append({"what": f"Страницы из {gen} не сверялись", "n": None, "cls": "warn",
                             "why": "Сайт обойдён не целиком, поэтому нельзя сказать, на какие страницы из поиска нет "
                                    "ссылок."})
                break
            if not s:
                continue
            if s["state"] == "ok":
                rows.append({"what": f"Страницы из {gen} сверены с сайтом", "n": s["n"], "cls": "ok",
                             "why": f"Адреса, которые знает {name}, проверены: на какие из них нет ссылок на сайте - "
                                    "в проблеме «Страницы, которые знает поиск, но на сайте на них нет ссылок»."})
            else:
                why = SEARCH_STATE.get(s["state"], SEARCH_STATE["error"]).format(name=dat, nom=name)
                rows.append({"what": f"Страницы из {gen} не сверялись", "n": None, "cls": "info",
                             "why": why[:1].upper() + why[1:] + ". Остальная проверка от этого не зависит."})
    cf = store.get_meta("consent_forms", None)
    if cf and cf.get("skipped") == "no_browser":
        rows.append({"what": "Формы и виджеты чатов в браузере не открывались", "n": None, "cls": "warn",
                     "why": "Согласие на обработку персональных данных проверено только в коде страниц: виджеты, которые "
                            "подгружаются скриптом, и ссылки на политику в них не проверены."})
    elif cf:
        hidden = list(dict.fromkeys(x.get("btn") or "" for x in cf.get("not_opened") or []))
        if hidden:
            rows.append({"what": "Формы виджетов, которые не удалось раскрыть", "n": len(hidden), "cls": "warn",
                         "why": "Формы есть в коде страницы, но спрятаны в виджете и не появились на экране после нажатия "
                                "кнопок виджета: " + ", ".join(f"«{h}»" for h in hidden if h)[:300] + ". Строка согласия "
                                "в таких формах часто появляется только при открытии, поэтому она в них не проверена."})
        if cf.get("failed"):
            rows.append({"what": "Страницы, на которых формы не проверены: не открылись в браузере",
                         "n": len(cf["failed"]), "cls": "warn",
                         "why": "Остальные страницы с формами проверены." if len(cf["failed"]) < len(cf.get("pages") or [])
                         else "Сайт не открылся в браузере (не ответил или временно закрыл доступ), поэтому формы и "
                              "виджеты чатов проверены только в коде страниц."})
    done = not any(r["cls"] == "warn" for r in rows)
    return {"pages": pages, "checked": summary.get("checked") or 0, "rows": rows, "all_done": done}


def intro(cov):
    p = f"Проверено {_n(cov['pages'])} {_plural(cov['pages'], 'страница', 'страницы', 'страниц')} сайта"
    p += f" и {_n(cov['checked'])} адресов вместе с картинками и ссылками." if cov.get("checked") else "."
    if cov["all_done"]:
        p += (" Проверено всё, что можно было открыть. Ниже - адреса, которые не открывались специально, и почему."
              if cov["rows"] else " Не открывать пришлось ничего: проверено всё.")
    else:
        p += " Ниже - что осталось непроверенным и почему."
    return p


def _cnt(r):
    return "" if r["n"] is None else _n(r["n"])


def html_block(cov, h2="h2", h2_cls="sec", cls="card"):
    if not cov:
        return ""
    trs = "".join(f'<tr><td><b class="{ {"ok": "ok", "warn": "warn"}.get(r["cls"], "")}">{_e(r["what"])}</b><br>'
                  f'<span class="mut" style="font-size:13px">{_e(r["why"])}</span></td>'
                  f'<td style="white-space:nowrap;text-align:right">{_cnt(r)}</td></tr>' for r in cov["rows"])
    table = (f'<div class="tw" style="margin:0"><table class="rg"><thead><tr><th>Что</th><th style="text-align:right">'
             f'Адресов</th></tr></thead><tbody>{trs}</tbody></table></div>') if trs else ""
    return (f'<{h2} class="{h2_cls}">{HEAD}</{h2}><div class="{cls}"><p style="margin:0 0 8px">{_e(intro(cov))}</p>'
            f'{table}</div>')


def audit_html(summary):
    b = html_block(summary.get("coverage"), h2="h2", h2_cls="", cls="")
    return f'<section class="pt">{b}</section>' if b else ""


def docx_paras(cov, _para, _run):
    if not cov:
        return []
    body = [_para([_run(HEAD, bold=True, size=28)], 80, keep=True), _para([_run(intro(cov), size=20)], 80)]
    for r in cov["rows"]:
        body.append(_para([_run(r["what"], bold=True, size=20)] + ([_run(f" - {_cnt(r)}", size=20)] if _cnt(r) else []),
                          20, indent=360, keep=True))
        body.append(_para([_run(r["why"], color="6B6B70", size=18)], 60, indent=360))
    body.append(_para([], 120))
    return body


def xlsx_rows(cov):
    """Строки для вкладки «Сводка»: (что, сколько адресов, почему)."""
    if not cov:
        return []
    return [(r["what"], _cnt(r), r["why"]) for r in cov["rows"]]
