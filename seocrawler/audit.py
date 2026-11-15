"""Клиентский аудит по 20 пунктам: по каждому пункту короткий вывод и ссылки на полные списки.
Собирается из тех же проверок, что и отчёт. Пункты, для которых нужны внешние данные (Вебмастер, выдача),
честно помечены «нет данных»."""
import os
import html

from .analyze import CRIT, WARN, NOTE
from .analyze.health import ABOUT as HEALTH_ABOUT
from .mobile_view import gallery_html, GALLERY_CSS
from . import brand, buy_clicks, compare, consent_forms, coverage, estimate, fix_files, lightbox, problem_shots, security, sitemap_pic, site_tech, suggest_out, web_cover
from .semantics import client as sem_client
from .fmt import esc as _e, num as _num, pretty_url

# (номер, пункт, проверки программы, что пункт означает для клиента, чего программа не видит)
POINTS = [
    (1, "Индексация", ["noindex", "canonicalised", "robots_blocked", "behind_blocked", "hidden_behind_blocked", "crawl_waste", "ua_diff",
                       "js_noindex_removed", "js_noindex_added", "param_explosion", "sitewide_to_closed",
                       "wm_problems", "wm_removed", "wm_not_in_index", "search_orphans", "gsc_not_indexed", "gsc_canonical_diff",
                       "empty_category", "out_of_stock"],
     "Что из страниц сайта поисковик может взять в выдачу, а что закрыто или скрыто.",
     "Сколько страниц реально в индексе Яндекса и Google - видно только в Вебмастере и Search Console."),
    (2, "Ошибки 404", ["4xx", "broken_links", "any_url_home", "fake404", "soft404", "res_broken", "sitemap_errors", "wm_index_broken", "metrika_broken_landing",
                        "gsc_index_broken", "crumbs_broken"],
     "Битые страницы и ссылки, которые на них ведут.", "Сколько 404 видит сам поисковик - в Вебмастере."),
    (3, "Редиректы 301", ["redirects", "redirect_chains", "redirect_loops", "redirect_noloc", "redirect_to_error", "redirect_to_blocked", "redirect_temp", "links_to_redirect", "sitemap_redirect",
                          "url_variants", "crumbs_redirect"],
     "Перенаправления: цепочки, циклы и ссылки на старые адреса.", ""),
    (4, "Файл robots.txt", ["robots_unavailable", "robots_html", "robots_blocked", "robots_blocked_res", "behind_blocked", "hidden_behind_blocked", "js_blocked"],
     "Правила для поисковых роботов: что закрыто и не закрыто ли лишнее.", ""),
    (5, "Карта сайта sitemap.xml", ["sitemap_none", "sitemap_errors", "sitemap_redirect", "sitemap_nonindex", "orphans",
                                    "not_in_sitemap", "gsc_sitemap"],
     "Список страниц, который сайт отдаёт поисковикам: нет ли в нём мусора и всё ли в нём есть.", ""),
    (6, "Сервер и безопасность", ["slow", "5xx", "too_many_requests", "odd_codes", "noresp", "no_304", "cert_expiry", "domain_expiry", "ssl_own", "exposed_files", "hacked_hidden_links", "hacked_spam_links",
                                  "dir_listing", "security_headers", "server_versions",
                                  "cookie_flags", "wp_users", "wp_xmlrpc", "modx_manager", "dead_script_domain", "old_jquery"],
     "Как быстро и стабильно отвечает сервер и не открыто ли то, что взломщики ищут первым делом: служебные "
     "файлы, пароли, архивы, заголовки защиты. Скорость замерена с компьютера, где запускалась проверка.",
     "Нагрузка по дням и реальные посетители - в Метрике и у хостинга."),
    (7, "Склейка домена и дубли адресов", ["mirror_dup", "mirror_redirect", "mirror_links", "mirror_canonical", "dup_variants", "dup_params", "slash_dup"],
     "Все варианты адреса (www, http, index.php, заглавные буквы) должны вести на один главный.", ""),
    (8, "Мобильная версия", ["viewport_missing", "viewport_zoom", "mobile_diff", "msite_bad", "mobile_wide",
                          "mobile_small_text", "mobile_taps", "mobile_heavy"],
     "Подстроена ли страница под экран телефона, удобно ли её читать и нажимать, сколько она весит "
     "и отдаёт ли сайт телефону то же, что компьютеру.",
     "Удобство на телефоне проверяется выборочно: 15 страниц в браузере шириной 375 px. "
     "Как сайт видят реальные посетители с телефонов - в Метрике (отчёт «Технологии → Устройства»)."),
    (9, "Ошибки HTML", ["head_broken", "head_invalid", "html_multi", "dup_ids", "encoding", "title_multi",
                        "canon_multi"],
     "Ошибки в коде, из-за которых поисковик может не увидеть мета-теги.", ""),
    (10, "Микроразметка Schema.org", ["schema_error", "schema_none", "rich_no_price", "rich_no_price_page", "rich_partial", "rich_no_crumbs",
                                       "rich_org_partial", "crumbs_no_markup", "crumbs_missing", "crumbs_none", "crumbs_self_link"],
     "Разметка для расширенных сниппетов: цена, рейтинг, хлебные крошки, организация.", ""),
    (11, "Open Graph", ["og_missing", "og_image_bad", "og_image_small", "og_image_relative"],
     "Как выглядит ссылка на сайт в мессенджерах и соцсетях.", ""),
    (12, "Скорость загрузки", ["no_cache", "page_weight", "template_weight", "img_big", "img_format", "img_oversized",
                               "no_compress", "res_heavy", "res_no_compress", "mixed_active", "metrika_bounce",
                               "lab_lcp", "lab_cls", "lab_tbt"],
     "Вес страниц и файлов, сжатие, скорость на телефоне с медленным 4G (замер, как в PageSpeed).",
     "Скорость у реальных посетителей (Core Web Vitals за 28 дней) - в PageSpeed Insights и Search Console."),
    (13, "Адреса страниц (ЧПУ)", ["relative_links", "url_issues", "url_style", "tracking_links", "http_links", "url_variants", "weak_anchors"],
     "Понятные адреса без мусора, меток и дублей.", ""),
    (14, "Canonical", ["canon_missing", "canon_bad", "canon_chain", "canon_multi", "canonicalised", "pagination_canon", "js_canonical"],
     "Указание основного адреса страницы.", ""),
    (15, "Title", ["title_missing", "title_dup", "title_cannibal", "title_long", "title_short", "title_city",
                   "js_title_only", "js_title_diff", "mixed_letters_meta", "gsc_low_ctr"],
     "Заголовки страниц в выдаче: есть, уникальны, нужной длины, не спорят друг с другом.", ""),
    (16, "Заголовки H1 и H2", ["h1_missing", "h1_multi", "h1_dup", "h2_missing", "js_h1"],
     "Главный заголовок страницы и подзаголовки текста.", ""),
    (17, "Description", ["desc_missing", "desc_dup", "desc_long", "desc_short", "js_desc", "gsc_low_ctr"],
     "Описание страницы, из которого часто строится сниппет.", ""),
    (18, "Meta keywords", ["keywords"],
     "Устаревший тег: поисковики его почти не учитывают.", ""),
    (19, "Брендовый сниппет и местный поиск", ["contacts_mix", "calltracking", "calltracking_script", "title_city", "org_schema_none", "region_no_urls", "region_not_checked", "region_unlinked",
                                                "region_dup", "region_no_city", "region_wrong_city",
                                                "region_cross_links"],
     "Как сайт выглядит в выдаче по названию компании (быстрые ссылки, карточка организации) и одинаковы ли "
     "контакты на страницах.",
     "Как сниппет выглядит в выдаче, видно поиском по названию компании в Яндексе и Google; там же стоит сверить "
     "карточки в Яндекс Бизнесе, 2ГИС и Google Картах."),
    (20, "Что мешает покупать", ["buy_price_zero", "buy_messenger", "buy_click", "buy_stock_conflict", "buy_schema_price",
                                 "buy_old_price", "buy_club_higher", "buy_club_higher_list", "buy_club_save", "buy_discount_odd", "buy_schema_club",
                                 "buy_discount_outlier", "buy_price_low", "buy_no_photo", "buy_spec_empty", "empty_category",
                                 "buy_phones_differ", "buy_no_consent", "buy_consent_link", "buy_consent_form", "buy_consent_nobox", "buy_policy_company", "buy_policy_noop", "buy_junk", "buy_city", "buy_copyright",
                                 "buy_crumbs_repeat"],
     "То, что посетитель видит на странице перед покупкой или заявкой: цены, наличие, фото, характеристики, телефоны, "
     "мессенджеры, формы и кнопки.",
     "Цены и наличие сверены с тем, что написано на страницах; с 1С или МойСкладом их "
     "сверяет сам магазин."),
]


# пункты, для которых нужны данные новых версий программы: без них вывод «ошибок нет» был бы неправдой
NEEDS = {7: "has_mirrors", 8: "has_v6", 9: "has_v6", 10: "has_v6", 11: "has_v6", 19: "has_v6", 20: "has_shop"}


SEV_ORDER = {CRIT: 0, WARN: 1, NOTE: 2}
INFO_KEYS = {"calltracking", "calltracking_script"}


def regions_html(summary, h2="h2", cls="pt"):
    """Раздел «По городам»: каждый город — адрес, страниц, здоровье, главные проблемы. Пусто, если городов нет."""
    rows = summary.get("regions") or []
    if not rows:
        return ""
    tr = "".join(
        f'<tr><td><b>{_e(r["city"])}</b><br><span class="mut">{_e(r["url"])}</span></td><td>{r["pages"]}</td>'
        f'<td>{"-" if r["health"] is None else str(r["health"]) + "%"}</td>'
        f'<td>{"<br>".join(_e(t) for t in r["top"]) or "-"}</td></tr>' for r in rows)
    return (f'<section class="{cls}"><{h2}>По городам</{h2}><p class="mut">У сайта есть городские версии. Для каждой - '
            f'сколько страниц проверено, здоровье (доля страниц без критичных проблем и предупреждений) и три главные '
            f'проблемы. Проблемы, общие для всех городов, собраны в пункте 19.</p>'
            f'<table class="rg"><thead><tr><th>Город</th><th>Страниц</th><th>Здоровье</th><th>Главные проблемы '
            f'(страниц)</th></tr></thead><tbody>{tr}</tbody></table></section>')


def _hl(h):
    if h is None:
        return "-"
    cls = "ok" if h >= 90 else ("warn" if h >= 70 else "crit")
    return f'<b class="{cls}">{h}%</b>'


def sections_html(summary, h2="h2", cls="pt"):
    """Раздел «По разделам сайта»: здоровье и главные проблемы каталога, статей, услуг… Пусто, если раздел один."""
    rows = summary.get("sections") or []
    if not rows:
        return ""
    tr = []

    def idx(s):
        # «индексируются» и «закрыты»: в проверках, собранных раньше, их нет до «Обновить отчёт»
        if s.get("idx") is None:
            return "<td>-</td><td>-</td>"
        return f'<td>{_num(s["idx"])}</td><td>{_num(s["closed"]) if s["closed"] else "-"}</td>'

    for r in rows:
        path = f'<br><span class="mut">{_e(r["path"])}</span>' if r["path"] and r["path"] != r["name"] else ""
        tr.append(f'<tr><td><b>{_e(r["name"])}</b>{path}</td><td>{_num(r["pages"])}</td>{idx(r)}<td>{_hl(r["health"])}</td>'
                  f'<td>{"<br>".join(_e(t) for t in r["top"]) or "-"}</td></tr>')
        for s in r.get("sub") or []:
            tr.append(f'<tr class="sub"><td>↳ {_e(s["name"])}<br><span class="mut">{_e(s["path"])}</span></td>'
                      f'<td>{_num(s["pages"])}</td>{idx(s)}<td>{_hl(s["health"])}</td>'
                      f'<td>{"<br>".join(_e(t) for t in s["top"]) or "-"}</td></tr>')
    return (f'<section class="{cls}"><{h2}>По разделам сайта</{h2}><p class="mut">Где на сайте больше всего проблем. '
            f'Раздел - первая папка в адресе страницы; у больших разделов показаны и подразделы. «Индексируются» - '
            f'страницы, которые поисковик может показать в поиске; «закрыты» - рабочие страницы, закрытые от поиска '
            f'(запрет индексации или указана другая главная версия страницы); остальные страницы раздела - с ошибкой '
            f'(404, нет ответа). Здоровье - доля страниц раздела без критичных проблем и предупреждений; рядом - три '
            f'главные проблемы и на скольких страницах раздела они есть.</p>'
            f'<table class="rg"><thead><tr><th>Раздел</th><th>Страниц</th><th>Индексируются</th><th>Закрыты</th>'
            f'<th>Здоровье</th><th>Главные проблемы (страниц)</th></tr></thead><tbody>{"".join(tr)}</tbody></table></section>')


def _lc(t):
    """Строчная буква после двоеточия: «Ограничения проверки: сколько…» (кроме аббревиатур: «PageSpeed», «SSL»)."""
    return t[:1].lower() + t[1:] if t[:1].isupper() and not t[1:2].isupper() else t


def _ru_when(meta):
    """«2026-10-04 13:45:05» → «04.10.2026»: клиенту время до секунды не нужно."""
    d = (meta.get("finished_at") or "")[:10]
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) == 10 and d[4] == "-" else d


def _took(meta, summary):
    """« · проверка заняла 1 ч 20 мин (≈160 страниц в минуту)» — сколько шла проверка."""
    from .duration import text
    t = text(meta, summary.get("pages"))
    return " · " + t[0].lower() + t[1:] if t else ""


def audit_data(issues, summary):
    """Общие данные аудита для HTML и Word: пункты с выводом и проблемами, список «что исправить первым»."""
    by_key = {i.key: i for i in issues}
    points = []
    for num, name, keys, what, blind in POINTS:
        found = sorted([by_key[k] for k in dict.fromkeys(keys) if k in by_key], key=lambda i: SEV_ORDER[i.severity])
        # сведения, а не ошибки («На сайте коллтрекинг» - «это не ошибка»): в перечне есть, на вывод не влияют
        worst = next((i.severity for i in found if i.key not in INFO_KEYS), None)
        need = NEEDS.get(num)
        if need and not summary.get(need):
            verdict, cls = "Нет данных", "na"
            blind = ("Проверка сделана старой версией программы, этих данных в ней нет - проверьте сайт заново. "
                     + blind).strip()
        elif not keys:
            verdict, cls = "Нет данных", "na"
        elif worst in (CRIT, WARN):
            verdict, cls = ("Критично" if worst == CRIT else "Есть проблемы"), ("crit" if worst == CRIT else "warn")
        elif worst == NOTE:
            verdict, cls = "Замечания", "note"
        else:
            verdict, cls = "Ошибок нет", "ok"
        points.append({"num": num, "name": name, "what": what, "blind": blind, "verdict": verdict, "cls": cls,
                       "found": found})
    todo = []
    for i in issues:
        if i.severity in (CRIT, WARN) and i.key not in {x["key"] for x in todo}:
            todo.append({"key": i.key, "sev": i.severity, "title": i.title, "cnt": i.count_text, "fix": i.fix,
                         "gain": getattr(i, "gain", 0) or 0})
    # сначала критичные, внутри — по тому, насколько вырастет здоровье сайта
    todo.sort(key=lambda x: (0 if x["sev"] == CRIT else 1, -x["gain"]))
    return points, todo


def _gain(x):
    return f' - +{str(x["gain"]).replace(".", ",")}% к здоровью сайта' if x["gain"] >= 1 else ""


LIST_CSS = """body{background:#fff;color:#1d1d1f;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}
main{max-width:1100px;margin:0 auto;padding:24px 16px 60px}h1{font-size:22px;margin:0 0 6px}.mut{color:#6b6b70}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e3e3e6;
vertical-align:top;overflow-wrap:break-word}td.u{overflow-wrap:anywhere}th{color:#6b6b70;font-weight:500}a{color:#2f4bc0}
@media (prefers-color-scheme:dark){body{background:#161618;color:#ececef}th,.mut{color:#9a9aa2}td,th{border-color:#2c2c30}a{color:#8ea6ff}}"""


def _cell(v):
    t = "" if v is None else str(v)
    if t.startswith(("http://", "https://")) and "\n" not in t:
        return f'<a href="{_e(t)}" target="_blank">{_e(pretty_url(t))}</a>'   # текст - как в браузере
    return _e(t).replace("\n", "<br>")


def _td(v):
    """Ячейка таблицы. Переносить посреди слова можно только длинные адреса (класс u): иначе узкая колонка
    рвёт обычные слова по буквам («Телефо-н»)."""
    t = "" if v is None else str(v)
    long = "://" in t or any(len(w) > 25 for w in t.split())
    return f'<td{" class=u" if long else ""}>{_cell(v)}</td>'


def _table(i, limit=None):
    rows = i.rows if limit is None else i.rows[:limit]
    head = "".join(f"<th>{_e(c)}</th>" for c in i.columns)
    body = "".join("<tr>" + "".join(_td(v) for v in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def write_lists(folder, issues):
    """проблемы/<ключ>.html — полный список по каждой проблеме: открывается прямо в браузере (CSV — для Excel)."""
    os.makedirs(folder, exist_ok=True)
    for i in issues:
        with open(os.path.join(folder, f"{i.key}.html"), "w", encoding="utf-8") as f:
            f.write(f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" '
                    f'content="width=device-width,initial-scale=1"><title>{_e(i.title)}</title><style>{LIST_CSS}</style>'
                    f'</head><body><main><h1>{_e(i.title)}</h1><p class="mut">{_e(i.count_text)} · {_e(i.why)}</p>'
                    f'<p><b>Что сделать.</b> {_e(i.fix)}</p>{_table(i, 50000)}</main></body></html>')


def scope_text(scope):
    """Пояснение, если проверялась часть сайта («Только этот раздел», «Мой список адресов»), иначе ""."""
    if not scope:
        return ""
    if scope.get("mode") == "list":
        n = scope.get("count") or 0
        return (f"Проверены только адреса из списка ({n:,} шт.)".replace(",", " ") + ": по ссылкам на другие страницы "
                "проверка не шла. Поэтому здесь нет проблем, которые видны только на всём сайте: глубина страниц, "
                "страницы-сироты, входящие ссылки и план перелинковки.")
    return (f"Проверен только раздел {scope.get('prefix', '')}: страницы вне раздела не открывались. Поэтому здесь "
            "нет проблем, которые видны только на всём сайте: глубина страниц, страницы-сироты, входящие ссылки "
            "и план перелинковки. Здоровье - по страницам раздела.")


DEMO_FILE = "аудит_демо.pdf"
# служебные данные проверки, нужные отчёту и аудиту (из таблицы meta базы)
REPORT_META = ("start", "started_at", "finished_at", "app_version", "mobile_view", "security", "webmaster", "gsc", "metrika",
               "work_seconds", "speed_lab", "site_tech", "scope", "access", "ua_switched", "shaky", "site_down", "extract_rules")
# PDF — сам документ: «в отчёте» в нём означает полный HTML-отчёт из папки для клиента
PDF_REPLACE = [("остальные - в отчёте.", "остальные - в полном отчёте.")]


def _signature(demo):
    """Подпись в конце аудита: в демо — только имя, без телефона, почты и Telegram."""
    if demo:
        return "" if os.environ.get("CLAYLER_NO_USER_SETTINGS") == "1" else brand.load().get("name", "")
    return brand.contacts_line()


def _mask_phone(m):
    return m.group(1) + " XXX XXX-XX-XX"


def _demo_text(doc):
    """Демо: телефоны и почты сайта в тексте документа скрыты (атрибуты и картинки не трогаем)."""
    import re
    phone = re.compile(r"(\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
    mail = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
    return re.sub(r">([^<]+)<", lambda m: ">" + mail.sub("***@***", phone.sub(_mask_phone, m.group(1))) + "<", doc)


def _demo_issues(issues):
    """Демо: в «разных телефонах и адресах» значения скрыты — в витрине не должно быть контактов чужого сайта."""
    import copy
    out = []
    for i in issues:
        if i.key == "contacts_mix":
            i = copy.copy(i)
            i.rows = [[r[0], "скрыто"] + list(r[2:]) for r in i.rows]
        elif i.key == "calltracking":   # оба номера коллтрекинга - тоже контакты сайта
            i = copy.copy(i)
            i.rows = [[r[0], "скрыто", "скрыто"] + list(r[3:]) for r in i.rows]
        out.append(i)
    return out


def write_audit(path, meta, issues, summary, for_pdf=False, demo=False):
    """for_pdf — вариант для PDF: «список» ведёт в приложение в конце документа (первые 30 строк каждой проблемы),
    потому что ссылки на файлы рядом в PDF у клиента не откроются. Тексты — как в отчёте для клиента.
    demo — PDF для витрины (Kwork и т. п.): пометка «Пример отчёта», ваше имя без контактов и ссылок,
    телефоны, почты и адреса сайта скрыты."""
    from .xlsx_report import full_list_where   # здесь, а не наверху файла: xlsx_report сам импортирует report
    for_pdf = for_pdf or demo
    if demo:
        issues = _demo_issues(issues)
    site = meta.get("start", "")
    points, todo_list = audit_data(issues, summary)
    if not for_pdf:
        write_lists(os.path.join(os.path.dirname(os.path.abspath(path)), "проблемы"), issues)
    rows_html = []
    appendix = []
    for pt in points:
        items = "".join(
            f'<li class="{ {CRIT: "crit", WARN: "warn", NOTE: "note"}[i.severity] }">{_e(i.title)} - '
            f'<b>{_e(i.count_text)}</b> <a href="{"#p-" + i.key if for_pdf else "проблемы/" + i.key + ".html"}"'
            f'{"" if for_pdf else " target=_blank"}>список</a></li>' for i in pt["found"])
        if for_pdf:
            for i in pt["found"]:
                # count_text бывает и словами («на всём сайте (5 110 из 5 351 стр.)») — тогда считаем строки
                total = i.count_text if i.count_text[:1].isdigit() else f"{len(i.rows):,}".replace(",", " ")
                more = (f'<p class="mut">Показаны первые 30 из {_e(total)}. '
                        f'{_e(full_list_where(len(i.rows), "в Excel-таблице к аудиту"))}</p>' if len(i.rows) > 30 else "")
                appendix.append(f'<section class="ap" id="p-{_e(i.key)}"><h3>{pt["num"]}. {_e(i.title)} - '
                                f'{_e(i.count_text)}</h3>{_table(i, 30)}{more}</section>')
        rows_html.append(
            f'<section class="pt"><h2><span class="n">{pt["num"]}</span>{_e(pt["name"])} '
            f'<span class="v {pt["cls"]}">{pt["verdict"]}</span></h2>'
            f'<p class="mut">{_e(pt["what"])}</p>' + (f"<ul>{items}</ul>" if items else "")
            + (gallery_html(meta.get("mobile_view"), limit=4, heading=False) if pt["num"] == 8 else "")
            + (f'<p class="blind">Ограничения проверки: {_e(_lc(pt["blind"]))}</p>' if pt["blind"] else "") + "</section>")
    scope_p = f'<p class="mut"><b>{_e(scope_text(meta.get("scope")))}</b></p>' if meta.get("scope") else ""
    todo = "".join(f'<li class="{ "crit" if x["sev"] == CRIT else "warn" }"><b>{_e(x["title"])}</b> ({_e(x["cnt"])})'
                   + (f"<b>{_e(_gain(x))}</b>" if x["gain"] >= 1 else "") + f'. {_e(x["fix"])}</li>' for x in todo_list)
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Технический аудит {_e(site)}</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--bd:#e3e3e6;--crit:#c0392b;--warn:#d9730d;--note:#b08d00;--ok:#2e7d32;--card:#f7f7f8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161618;--fg:#ececef;--mut:#9a9aa2;--bd:#2c2c30;--crit:#ef6f5e;--warn:#f0973c;--note:#e3c84a;--ok:#6cc070;--card:#1e1e21}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:880px;margin:0 auto;padding:28px 16px 60px}}h1{{font-size:26px;margin:0 0 4px}}
.mut{{color:var(--mut)}}.pt{{border-top:1px solid var(--bd);padding:14px 0}}
h2{{font-size:18px;margin:0 0 4px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.n{{display:inline-block;min-width:26px;height:26px;border-radius:13px;background:var(--card);text-align:center;font-size:14px;line-height:26px}}
.v{{font-size:13px;font-weight:600;padding:2px 10px;border-radius:12px;border:1px solid currentColor}}
.crit{{color:var(--crit)}}.warn{{color:var(--warn)}}.note{{color:var(--note)}}.ok{{color:var(--ok)}}.na{{color:var(--mut)}}
ul{{margin:6px 0;padding-left:20px}}li{{margin:3px 0}}li b{{color:var(--fg)}}a{{color:inherit}}
.blind{{font-size:14px;color:var(--mut);background:var(--card);padding:6px 10px;border-radius:8px}}
.sum{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}.sum div{{background:var(--card);border-radius:10px;padding:10px 14px}}
.sum b{{display:block;font-size:22px}}
.ap h3{{font-size:15px;margin:18px 0 6px}}.ap table{{border-collapse:collapse;width:100%;font-size:12px}}
.ap th,.ap td{{text-align:left;padding:4px 6px;border-bottom:1px solid var(--bd);vertical-align:top}}
.ap td{{overflow-wrap:break-word}}.ap td.u{{overflow-wrap:anywhere}}.ap th{{font-weight:500;color:var(--mut)}}
.mob img{{{"aspect-ratio:750/975;object-fit:cover;object-position:top" if demo else ""}}}
.demo{{display:inline-block;font-size:14px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#5a6b8c;border:1.5px solid currentColor;border-radius:8px;padding:3px 12px;margin:0 0 10px}}
.wm{{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-55deg);font-size:120px;font-weight:800;letter-spacing:.08em;color:rgba(120,120,130,.13);pointer-events:none;z-index:9;white-space:nowrap}}
.rg{{border-collapse:collapse;width:100%;font-size:14px}}.rg th,.rg td{{text-align:left;padding:6px;border-bottom:1px solid var(--bd);vertical-align:top}}
.rg td{{overflow-wrap:anywhere}}.rg th{{font-weight:500;color:var(--mut)}}.rg tr.sub td{{font-size:14px}}.rg tr.sub td:first-child{{padding-left:18px}}
{GALLERY_CSS}
{problem_shots.CSS}
{web_cover.CSS}
{lightbox.CSS}
{brand.BRAND_CSS}
@media print{{.pt h2{{break-after:avoid}}.pt li,.blind,.sum{{break-inside:avoid}}a{{text-decoration:none}}}}
</style></head><body><main>
{brand.header_html(contacts=not demo)}
{'<p class="demo">Пример отчёта</p><div class="wm" aria-hidden="true">ОБРАЗЕЦ</div>' if demo else ""}
<h1>Технический аудит сайта</h1>
<p class="mut">{_e(site)} · проверка {_e(_ru_when(meta))} · страниц проверено: {_num(summary.get("pages") or 0)}{_e(_took(meta, summary))}{"" if for_pdf else " · версия программы " + _e(meta.get("app_version") or "до 6.3")}</p>
{scope_p}
{web_cover.for_report(meta, summary, demo=demo)}
<div class="sum"><div><b>{summary.get("health", "-")}%</b>здоровье сайта</div>
<div><b class="crit">{summary.get("crit", 0)}</b>видов критичных проблем</div>
<div><b class="warn">{summary.get("warn", 0)}</b>видов предупреждений</div></div>
<p class="mut">{_e(HEALTH_ABOUT)}</p>
<p class="mut">{"По каждому пункту - вывод и найденные проблемы; «список» ведёт к примерам в приложении в конце документа."
 if for_pdf else "По каждому пункту - вывод и найденные проблемы; «список» открывает полный список адресов. Подробные пояснения к каждой проблеме - в «отчёт.html»."}</p>
{compare.audit_html(summary)}
{security.audit_html(meta.get("security"), issues)}
{site_tech.audit_html(meta.get("site_tech"), _e, country=summary.get("country"))}
{"".join(rows_html)}
{coverage.audit_html(summary)}
{problem_shots.audit_html(summary)}
{buy_clicks.audit_html(summary)}
{consent_forms.audit_html(summary)}
{sitemap_pic.html_block(summary)}
{sections_html(summary)}
{regions_html(summary)}
{suggest_out.audit_html(summary, for_pdf)}
{fix_files.audit_html(summary, for_pdf)}
{sem_client.html_block(summary.get("semantics"), for_audit=True)}
{estimate.audit_html(summary)}
<section class="pt"><h2>Что исправить в первую очередь</h2><ol>{todo or "<li>Критичных проблем и предупреждений нет.</li>"}</ol></section>
{('<section class="pt"><h2>Приложение: примеры адресов по каждой проблеме</h2>' + "".join(appendix) + "</section>") if appendix else ""}
{f'<p class="mut" style="border-top:1px solid var(--bd);padding-top:12px">Аудит подготовил: {_e(c)}</p>' if (c := _signature(demo)) else ""}
</main>{"" if for_pdf else "<script>" + lightbox.JS + "</script>"}</body></html>"""
    if for_pdf:  # PDF уходит клиенту: без подсказок оператору, как в отчёте для клиента
        from .client_report import REPLACE
        for a, b in REPLACE + PDF_REPLACE:
            doc = doc.replace(a, b)
    if demo:
        doc = _demo_text(doc)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


# ---------- Word (.docx) без сторонних библиотек: минимальный документ WordprocessingML
def _x(t):
    return html.escape("" if t is None else str(t), quote=False)


def _run(text, bold=False, size=None, color=None):
    pr = ("<w:b/>" if bold else "") + (f'<w:color w:val="{color}"/>' if color else "") \
        + (f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>' if size else "")
    return f'<w:r>{f"<w:rPr>{pr}</w:rPr>" if pr else ""}<w:t xml:space="preserve">{_x(text)}</w:t></w:r>'


def _para(runs, space_after=120, indent=0, keep=False):
    ppr = f'<w:spacing w:after="{space_after}"/>' + (f'<w:ind w:left="{indent}"/>' if indent else "") \
        + ("<w:keepNext/>" if keep else "")
    return f"<w:p><w:pPr>{ppr}</w:pPr>{''.join(runs)}</w:p>"


COLORS = {"crit": "C62828", "warn": "B26A00", "note": "5A6B8C", "ok": "2E7D32", "na": "6B6B70"}


def write_audit_docx(path, meta, issues, summary):
    import zipfile
    from .xlsx_report import MAX_ISSUE_ROWS   # здесь, а не наверху файла: xlsx_report сам импортирует report
    site = meta.get("start", "")
    points, todo_list = audit_data(issues, summary)
    who = brand.contacts_line()
    body = ([_para([_run("Подготовил: ", color="6B6B70", size=20), _run(who, bold=True, size=20)], 200)] if who else []) + [
            _para([_run("Технический аудит сайта", bold=True, size=36)], 80),
            _para([_run(f"{site} · проверка {_ru_when(meta)} · страниц проверено: "
                        f"{_num(summary.get('pages') or 0)}{_took(meta, summary)}",
                        color="6B6B70", size=20)], 200)] + (
            [_para([_run(scope_text(meta.get("scope")), bold=True, size=20)], 200)] if meta.get("scope") else []) + [
            _para([_run(f"Здоровье сайта: {summary.get('health', '-')}%   ", bold=True, size=24),
                   _run(f"критичных видов проблем: {summary.get('crit', 0)}   ", color=COLORS["crit"]),
                   _run(f"предупреждений: {summary.get('warn', 0)}", color=COLORS["warn"])], 80),
            _para([_run(HEALTH_ABOUT, color="6B6B70", size=18)], 200),
            _para([_run("По каждому пункту - вывод и найденные проблемы. Полные списки адресов - в Excel-таблице к аудиту"
                        + (f" (самые длинные - первые {_num(MAX_ISSUE_ROWS)} строк, полный список - по запросу)."
                           if any(len(i.rows) > MAX_ISSUE_ROWS for i in issues) else "."),   #
                        size=20)], 240)]
    tech = site_tech.rows(meta.get("site_tech"))
    if tech:
        body.append(_para([_run("На чём сделан сайт и где размещён", bold=True, size=28)], 80, keep=True))
        body.append(_para([_run(f"{site_tech.INTRO} Данные на {site_tech._ru_date(meta['site_tech'].get('checked_at'))}.",
                                color="6B6B70", size=20)], 100))
        for name, val, note, lvl in tech:
            body.append(_para([_run(name + ": ", color="6B6B70"), _run(val, bold=True, color=COLORS.get(lvl)),
                               _run("  " + note, color="6B6B70", size=18)], 60, indent=360))
        body.append(_para([], 120))
    for pt in points:
        body.append(_para([_run(f"{pt['num']}. {pt['name']}  ", bold=True, size=28),
                           _run(pt["verdict"], bold=True, size=24, color=COLORS[pt["cls"]])], 60, keep=True))
        body.append(_para([_run(pt["what"], color="6B6B70", size=20)], 80))
        for i in pt["found"]:
            c = {CRIT: "crit", WARN: "warn", NOTE: "note"}[i.severity]
            body.append(_para([_run("• ", color=COLORS[c]), _run(i.title), _run(" - "), _run(i.count_text, bold=True)], 40, indent=360))
        if pt["blind"]:
            body.append(_para([_run("Ограничения проверки: " + _lc(pt["blind"]), color="6B6B70", size=18)], 160, indent=360))
        else:
            body.append(_para([], 120))
    if summary.get("sections"):
        body.append(_para([_run("По разделам сайта", bold=True, size=28)], 120, keep=True))
        for r in summary["sections"]:
            for s, ind in [(r, 0)] + [(x, 360) for x in r.get("sub") or []]:
                hl = "-" if s["health"] is None else f"{s['health']}%"
                body.append(_para([_run(("↳ " if ind else "") + s["name"], bold=not ind),
                                   _run(f" · {s['path']} · страниц: {_num(s['pages'])}"
                                        + (f" (индексируются {_num(s['idx'])}, закрыты {_num(s['closed'])})"
                                           if s.get("idx") is not None else "")
                                        + f" · здоровье: {hl}", color="6B6B70",
                                        size=20)], 20, indent=ind))
                if s["top"] and not ind:
                    body.append(_para([_run("Главные проблемы: " + "; ".join(s["top"]), size=18, color="6B6B70")], 60,
                                      indent=360))
        body.append(_para([], 120))
    if summary.get("regions"):
        body.append(_para([_run("По городам", bold=True, size=28)], 120, keep=True))
        for r in summary["regions"]:
            hl = "-" if r["health"] is None else f"{r['health']}%"
            body.append(_para([_run(f"{r['city']}", bold=True), _run(f" · {r['url']} · страниц: {r['pages']} · "
                                                                     f"здоровье: {hl}", color="6B6B70", size=20)], 40))
            for t in r["top"]:
                body.append(_para([_run("• " + t, size=20)], 20, indent=360))
        body.append(_para([], 120))
    body += compare.docx_paras(summary.get("compare"), _para, _run)
    body += coverage.docx_paras(summary.get("coverage"), _para, _run)
    body += suggest_out.docx_paras(summary, _para, _run)
    body += fix_files.docx_paras(summary, _para, _run)
    body += sem_client.docx_paras(summary.get("semantics"), _para, _run)
    body.append(_para([_run("Что исправить в первую очередь", bold=True, size=28)], 120, keep=True))
    for n, x in enumerate(todo_list, 1):
        body.append(_para([_run(f"{n}. ", bold=True), _run(x["title"], bold=True, color=COLORS["crit" if x["sev"] == CRIT else "warn"]),
                           _run(f" ({x['cnt']})"), _run(_gain(x), bold=True), _run(". " + x["fix"])], 100))
    if not todo_list:
        body.append(_para([_run("Критичных проблем и предупреждений нет.")]))
    from .client_report import client_text   # Word уходит клиенту: без подсказок оператору
    save_docx(path, [client_text(x) for x in body])


def save_docx(path, body):
    """Записать файл Word из абзацев _para(...): минимальный .docx без сторонних модулей."""
    import zipfile
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                + "".join(body) +
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
                'w:left="1134" w:header="709" w:footer="709" w:gutter="0"/></w:sectPr></w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults>'
              '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/>'
              '<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
