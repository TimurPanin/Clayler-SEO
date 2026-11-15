"""Смета и план работ для клиента (идея «Вау» 3): из найденных проблем - список работ по этапам
(сначала критичное, потом предупреждения, потом улучшения), кто делает, сколько часов и, если в «Пороги и проверки»
указана ставка, сколько это стоит. Часы — оценка для типовой работы с готовыми файлами из папки «файлы для
разработчика» (редиректы, sitemap, таблица title): база + немного на каждую найденную строку, с потолком.
Проблема «на всём сайте» или в шаблоне сайта правится один раз — только база.
Файлы: смета.xlsx и смета.pdf в папке проверки, копии в «для клиента»; блок «План работ и смета» в отчётах."""
import os

from .fmt import esc as _e, num as _n

DEV, CONTENT, SEO = "разработчик", "контент-менеджер", "SEO-специалист"
STAGES = {"critical": "1. Срочно: мешает индексации и посетителям",
          "warning": "2. Важно: заметно влияет на позиции и удобство",
          "notice": "3. Улучшения: по желанию, после первых двух этапов"}

# ключ проблемы → (кто, часов база, часов на строку, потолок часов)
WORK = {
    "4xx": (DEV, 1, 0.02, 6), "broken_links": (CONTENT, 0.5, 0.03, 8), "5xx": (DEV, 2, 0.1, 8),
    "noresp": (DEV, 1, 0, 2), "soft404": (DEV, 2, 0, 3), "any_url_home": (DEV, 4, 0, 4), "fake404": (DEV, 1, 0, 2),
    "redirect_loops": (DEV, 1, 0.25, 4), "redirect_noloc": (DEV, 1, 0.05, 3), "redirect_to_error": (DEV, 1, 0.05, 4), "redirect_to_blocked": (DEV, 1, 0.02, 3), "redirect_temp": (DEV, 0.5, 0.02, 2), "odd_codes": (DEV, 1, 0.02, 3), "too_many_requests": (DEV, 0.5, 0, 1), "robots_unavailable": (DEV, 0.5, 0, 1), "redirect_chains": (DEV, 1, 0.02, 3), "links_to_redirect": (CONTENT, 0.5, 0.05, 6),
    "title_missing": (CONTENT, 0.5, 0.02, 10), "title_dup": (CONTENT, 0.5, 0.02, 10),
    "title_long": (CONTENT, 0.5, 0.01, 6), "title_short": (CONTENT, 0.5, 0.01, 6), "title_multi": (DEV, 1, 0, 2),
    "title_cannibal": (SEO, 1, 0.1, 6), "desc_missing": (CONTENT, 0.5, 0.02, 10), "desc_dup": (CONTENT, 0.5, 0.02, 10),
    "desc_long": (CONTENT, 0.5, 0.01, 4), "desc_short": (CONTENT, 0.5, 0.01, 4),
    "h1_missing": (CONTENT, 0.5, 0.03, 8), "h1_multi": (DEV, 1, 0.01, 3), "h1_dup": (CONTENT, 0.5, 0.02, 6),
    "dup_content": (DEV, 2, 0.05, 6), "near_dup": (SEO, 1, 0.1, 8), "slash_dup": (DEV, 1, 0, 2),
    "dup_variants": (DEV, 1.5, 0, 3), "dup_params": (DEV, 1, 0, 2), "mirror_dup": (DEV, 1, 0, 2),
    "mirror_redirect": (DEV, 1, 0, 2), "mirror_links": (CONTENT, 0.5, 0.05, 4), "canon_bad": (DEV, 1.5, 0.02, 4), "canon_chain": (DEV, 1, 0.02, 3),
    "canon_multi": (DEV, 1, 0, 2), "canon_missing": (DEV, 1, 0, 2), "head_broken": (DEV, 1, 0, 2),
    "sitemap_none": (DEV, 1, 0, 1), "robots_html": (DEV, 0.5, 0, 1), "sitemap_errors": (DEV, 0.5, 0, 1), "sitemap_redirect": (DEV, 0.5, 0, 1), "sitemap_nonindex": (DEV, 0.5, 0, 1),
    "orphans": (SEO, 1, 0.02, 4), "search_orphans": (SEO, 1, 0.02, 4), "not_in_sitemap": (DEV, 0.5, 0, 1), "behind_blocked": (DEV, 1, 0, 2), "hidden_behind_blocked": (DEV, 1, 0, 2),
    "js_blocked": (DEV, 0.5, 0, 1), "robots_blocked_res": (DEV, 0.5, 0, 1), "sitewide_to_closed": (DEV, 1, 0, 2), "tracking_links": (CONTENT, 0.5, 0.01, 4),
    "relative_links": (DEV, 1, 0, 2), "deep": (SEO, 2, 0.01, 6), "one_inlink": (SEO, 1, 0.01, 4), "anchors_menu_only": (SEO, 1, 0.05, 4), "anchor_many_pages": (SEO, 1, 0.05, 4),
    "img_alt_missing": (CONTENT, 0.5, 0.01, 8), "img_big": (DEV, 2, 0.005, 6), "img_format": (DEV, 2, 0, 4),
    "img_oversized": (DEV, 1, 0.005, 4), "img_no_size": (DEV, 1, 0, 3), "img_bad_type": (DEV, 0.5, 0.05, 2),
    "page_weight": (DEV, 3, 0.02, 8), "template_weight": (DEV, 3, 0, 6), "slow": (DEV, 3, 0, 8),
    "no_compress": (DEV, 0.5, 0, 1), "no_cache": (DEV, 1, 0, 2), "res_broken": (DEV, 1, 0.05, 4),
    "res_heavy": (DEV, 2, 0, 4), "res_no_compress": (DEV, 0.5, 0, 1), "no_lastmod": (DEV, 1, 0, 2),
    "no_304": (DEV, 1, 0, 2), "viewport_missing": (DEV, 2, 0, 4), "viewport_zoom": (DEV, 0.5, 0, 1),
    "mobile_diff": (DEV, 2, 0.2, 6), "msite_bad": (DEV, 2, 0, 4), "mobile_wide": (DEV, 2, 0.5, 8),
    "mobile_small_text": (DEV, 1, 0.3, 4), "mobile_taps": (DEV, 1, 0.2, 4), "mobile_heavy": (DEV, 2, 0.2, 6),
    "exposed_files": (DEV, 1, 0.5, 4), "hacked_hidden_links": (DEV, 2, 0.1, 8), "hacked_spam_links": (DEV, 1, 0.05, 6), "dir_listing": (DEV, 0.5, 0, 1), "security_headers": (DEV, 1, 0, 2),
    "server_versions": (DEV, 1, 0, 3), "cookie_flags": (DEV, 1, 0, 2), "wp_users": (DEV, 1, 0, 2),
    "wp_xmlrpc": (DEV, 0.5, 0, 1), "modx_manager": (DEV, 0.5, 0, 1), "dead_script_domain": (DEV, 0.5, 0.1, 2), "old_jquery": (DEV, 2, 0, 6), "ssl_own": (DEV, 1, 0, 2), "cert_expiry": (DEV, 0.5, 0, 1), "domain_expiry": (DEV, 0.25, 0, 0.5),
    "mixed_active": (DEV, 1, 0.02, 4), "mixed_passive": (DEV, 1, 0.01, 3), "private_host": (DEV, 1, 0.02, 3),
    "encoding": (DEV, 2, 0, 4), "html_multi": (DEV, 1, 0, 2), "schema_error": (DEV, 1, 0.05, 3),
    "schema_none": (DEV, 3, 0, 4), "rich_no_price": (DEV, 1, 0, 2), "rich_partial": (DEV, 1, 0, 2),
    "rich_no_crumbs": (DEV, 2, 0, 3), "org_schema_none": (DEV, 1, 0, 2), "og_missing": (DEV, 1, 0, 2),
    "og_image_bad": (DEV, 0.5, 0, 1), "thin": (CONTENT, 1, 0.3, 30), "text_water": (CONTENT, 0.5, 0.3, 12), "text_nausea": (CONTENT, 0.5, 0.3, 12),
    "h2_missing": (CONTENT, 0.5, 0.1, 8),
    "spelling": (CONTENT, 0.5, 0.02, 4), "mixed_letters_meta": (CONTENT, 0.5, 0.02, 3), "keywords": (DEV, 0.5, 0, 1),
    "no_lang": (DEV, 0.5, 0, 1), "contacts_mix": (CONTENT, 0.5, 0.02, 2), "empty_category": (CONTENT, 1, 0.05, 4),
    "js_title_only": (DEV, 3, 0, 6), "js_h1": (DEV, 3, 0, 6), "js_canonical": (DEV, 2, 0, 4), "js_links": (DEV, 3, 0, 6),
    "js_text": (DEV, 4, 0, 8), "js_noindex_removed": (DEV, 1, 0, 2), "js_redirects": (DEV, 1, 0.1, 3),
    "region_no_urls": (SEO, 3, 0, 6), "region_dup": (CONTENT, 2, 0.2, 12), "region_no_city": (CONTENT, 1, 0.02, 4),
    "crawl_waste": (DEV, 2, 0, 4), "param_explosion": (DEV, 1, 0, 3), "url_issues": (DEV, 1, 0, 2),
    "ua_diff": (DEV, 2, 0, 4), "ext_broken": (CONTENT, 0.5, 0.02, 3), "gsc_index_broken": (DEV, 1, 0.05, 4),
    "gsc_not_indexed": (SEO, 2, 0, 4), "gsc_low_ctr": (CONTENT, 0.5, 0.1, 6), "gsc_near_top": (SEO, 1, 0.2, 8), "metrika_broken_landing": (DEV, 1, 0.05, 4), "counter_none": (DEV, 0.5, 0, 1),
    # что мешает покупать
    "buy_price_zero": (CONTENT, 0.5, 0.05, 8), "buy_price_low": (CONTENT, 0.5, 0.05, 4),
    "buy_stock_conflict": (DEV, 2, 0, 4), "buy_schema_price": (DEV, 2, 0, 4), "buy_old_price": (CONTENT, 0.5, 0.05, 3),
    "buy_no_photo": (CONTENT, 1, 0.1, 16), "buy_spec_empty": (CONTENT, 1, 0.1, 16), "buy_phones_differ": (CONTENT, 0.5, 0, 1),
    "buy_messenger": (DEV, 0.5, 0, 1), "buy_no_consent": (DEV, 2, 0, 4), "buy_copyright": (DEV, 0.5, 0, 1),
    "buy_junk": (DEV, 1, 0.05, 4), "buy_city": (DEV, 2, 0, 4), "buy_crumbs_repeat": (DEV, 1, 0, 2),
    # хлебные крошки (analyze/checks/crumbs.py): правка шаблона
    "crumbs_missing": (DEV, 1, 0, 3), "crumbs_none": (DEV, 2, 0, 4), "crumbs_no_markup": (DEV, 1, 0, 2), "crumbs_broken": (DEV, 1, 0, 2),
    "crumbs_redirect": (DEV, 0.5, 0, 1), "crumbs_self_link": (DEV, 0.5, 0, 1),
    "buy_click": (DEV, 2, 0.5, 8),
    "buy_consent_link": (DEV, 0.5, 0.25, 2), "buy_consent_form": (DEV, 1, 0.5, 4), "buy_policy_company": (CONTENT, 1, 0, 2),
    "buy_club_higher": (DEV, 2, 0.05, 6), "buy_club_higher_list": (DEV, 2, 0, 4), "buy_club_save": (DEV, 2, 0, 4), "buy_discount_odd": (CONTENT, 0.5, 0.05, 4),
    "buy_schema_club": (DEV, 2, 0, 4), "buy_discount_outlier": (CONTENT, 0.5, 0.05, 3),
}


def _hours(i, w):
    who, base, per, cap = w
    if i.sitewide:  # одна настройка сайта или шаблона — правится один раз
        return who, max(base, 1)
    h = min(cap, base + per * len(i.rows))
    return who, max(0.5, round(h * 2) / 2)


def build(issues):
    """Работы по этапам: [{stage, sev, title, fix, who, count, hours, gain}]."""
    from .client_report import HIDE, client_text
    from .site_tech import LIMIT
    order = {"critical": 0, "warning": 1, "notice": 2}
    out = []
    for i in issues:
        w = WORK.get(i.key)
        if not w or i.key in HIDE or LIMIT in (i.fix or ""):  # ограничение хостинга - работ нет
            continue
        who, h = _hours(i, w)
        out.append({"key": i.key, "stage": STAGES[i.severity], "sev": i.severity, "title": client_text(i.title),
                    "fix": client_text(i.fix), "who": who, "count": i.count_text, "hours": h,
                    "gain": getattr(i, "gain", 0) or 0})
    out.sort(key=lambda x: (order[x["sev"]], -x["gain"], -x["hours"]))
    return out


def totals(works, rate=0):
    st = {}
    for w in works:
        st[w["stage"]] = st.get(w["stage"], 0) + w["hours"]
    total = sum(st.values())
    return {"stages": st, "hours": total, "money": round(total * rate) if rate else 0}


def _h(x):
    return (f"{x:g}").replace(".", ",")


def _rub(x):
    return f"{_n(int(round(x)))} ₽"


# «предварительная оценка» - на виду, а не мелким текстом внизу (разбор отчёта rsmarket24.ru)
NOTE = ("Это предварительная оценка, не договорная цена: часы - для типовой работы, с готовыми файлами из папки «файлы для разработчика» "
        "(редиректы, sitemap, таблица title и description). Точный срок и цену называет исполнитель, когда посмотрит "
        "сайт изнутри: на нестандартном движке или со сложной вёрсткой работа может занять больше времени.")


def html_block(works, rate=0, h2="h2", h2_cls="sec", cls="card", limit=12):
    """Раздел для отчёта и аудита: итог по этапам и главные работы."""
    if not works:
        return ""
    t = totals(works, rate)
    stages = "".join(f'<tr><td>{_e(s)}</td><td style="text-align:right;white-space:nowrap">{_h(h)} ч'
                     + (f' · {_rub(h * rate)}' if rate else "") + '</td></tr>' for s, h in t["stages"].items())
    top = "".join(f'<li>{_e(w["title"])} <span class="mut">({_e(w["who"])}, {_h(w["hours"])} ч)</span></li>'
                  for w in works[:limit])
    return (f'<{h2} class="{h2_cls}">План работ и предварительная смета</{h2}><div class="{cls}">'
            f'<p class="mut" style="margin:0 0 8px">Что сделать по итогам аудита, в каком порядке и сколько это примерно '
            f'займёт, по предварительной оценке. Всего работ: {len(works)}, около {_h(t["hours"])} ч'
            + (f', ориентировочно {_rub(t["money"])}' if rate else "") + '.</p>'
            f'<div class="tw" style="margin:0"><table class="rg"><tbody>{stages}</tbody></table></div>'
            f'<p style="margin:12px 0 4px"><b>Первые работы</b></p><ol>{top}</ol>'
            f'<p class="mut">Весь план с часами по каждой работе - в смете (PDF и Excel). {NOTE}</p></div>')


def _doc(site, when, works, rate):
    from . import brand
    t = totals(works, rate)
    rows, cur = [], None
    for n, w in enumerate(works, 1):
        if w["stage"] != cur:
            cur = w["stage"]
            rows.append(f'<tr class="st"><td colspan="{5 if rate else 4}">{_e(cur)} - {_h(t["stages"][cur])} ч</td></tr>')
        rows.append(f'<tr><td>{n}</td><td><b>{_e(w["title"])}</b> <span class="mut">({_e(w["count"])})</span>'
                    f'<div class="mut">{_e(w["fix"])}</div></td><td>{_e(w["who"])}</td>'
                    f'<td class="r">{_h(w["hours"])}</td>' + (f'<td class="r">{_rub(w["hours"] * rate)}</td>' if rate else "")
                    + "</tr>")
    total = (f'<tr class="tot"><td></td><td>Итого</td><td></td><td class="r">{_h(t["hours"])}</td>'
             + (f'<td class="r">{_rub(t["money"])}</td>' if rate else "") + "</tr>")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Предварительная смета и план работ {_e(site)}</title><style>
:root{{--bd:#e3e3e6;--mut:#6b6b70}}@page{{size:A4;margin:14mm}}
body{{background:#fff;color:#1d1d1f;font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:900px;margin:0 auto;padding:20px 16px}}.mut{{color:var(--mut)}}h1{{font-size:24px;margin:0 0 4px}}
table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:7px 6px;border-bottom:1px solid var(--bd);vertical-align:top}}
th{{color:var(--mut);font-weight:500}}td.r,th.r{{text-align:right;white-space:nowrap}}tr{{break-inside:avoid}}
tr.st td{{background:#f4f5f8;font-weight:600;padding-top:10px}}tr.tot td{{font-weight:700;border-top:2px solid #1d1d1f}}
.sum{{display:flex;gap:14px;margin:14px 0}}.sum div{{border:1px solid var(--bd);border-radius:10px;padding:10px 14px}}
.sum b{{display:block;font-size:22px}}.pre{{border-left:3px solid #c9a227;background:#fbf7e9;padding:8px 12px;margin:12px 0}}{brand.BRAND_CSS}</style></head><body><main>
{brand.header_html()}
<h1>Предварительная смета и план работ</h1>
<p class="mut">{_e(site)} · по итогам SEO-аудита {_e(when)}</p>
<p class="pre">{NOTE}</p>
<div class="sum"><div><b>{len(works)}</b>работ</div><div><b>{_h(t["hours"])} ч</b>всего</div>
{f'<div><b>{_rub(t["money"])}</b>ориентировочно, {_rub(rate)} за час</div>' if rate else ""}</div>
<p>Работы идут по порядку: сначала то, что мешает поисковикам и посетителям прямо сейчас, потом то, что сильнее всего
влияет на позиции, в конце - улучшения. Внутри этапа сверху то, что больше всего поднимет здоровье сайта.</p>
<table><thead><tr><th>№</th><th>Работа</th><th>Кто делает</th><th class="r">Часов</th>{'<th class="r">Стоимость</th>' if rate else ""}</tr></thead>
<tbody>{"".join(rows)}{total}</tbody></table>
</main></body></html>"""


def write_xlsx(path, works, rate):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Предварительная смета"
    head = ["№", "Этап", "Работа", "Что сделать", "Кто делает", "Найдено", "Часов"] + (["Стоимость, ₽"] if rate else [])
    ws.append(head)
    for n, w in enumerate(works, 1):
        ws.append([n, w["stage"], w["title"], w["fix"], w["who"], w["count"], w["hours"]]
                  + ([round(w["hours"] * rate)] if rate else []))
    last = len(works) + 1
    ws.append(["", "", "Итого", "", "", "", f"=SUM(G2:G{last})"] + ([f"=SUM(H2:H{last})"] if rate else []))
    for c in ws[1] + ws[last + 1]:
        c.font = Font(bold=True)
    for c in ws[1]:
        c.fill = PatternFill("solid", fgColor="E3E8F2")
    for col, wd in zip("ABCDEFGH", (5, 30, 45, 70, 18, 14, 8, 14)):
        ws.column_dimensions[col].width = wd
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.append([])
    ws.append(["", "", NOTE])
    wb.save(path)


def write(out_dir, meta, issues, pdf=True):
    """смета.xlsx и смета.pdf (и смета.html для PDF) в папке проверки. Возвращает список работ."""
    from . import settings
    rate = float(getattr(settings, "HOUR_RATE", 0) or 0)
    works = build(issues)
    for f in ("смета.xlsx", "смета.pdf"):
        p = os.path.join(out_dir, f)
        if not works and os.path.exists(p):
            os.remove(p)
    if not works:
        return works
    from urllib.parse import urlsplit
    site = (urlsplit(meta.get("start") or "").hostname or "").removeprefix("www.")
    fin = str(meta.get("finished_at") or "")
    when = f"{fin[8:10]}.{fin[5:7]}.{fin[:4]}" if len(fin) >= 10 else ""
    try:
        write_xlsx(os.path.join(out_dir, "смета.xlsx"), works, rate)
    except PermissionError:
        print("Не удалось записать смета.xlsx - наверное, он открыт в Excel.")
    except Exception as e:
        print("Смета в Excel не собрана:", str(e)[:150])
    if pdf:
        tmp = os.path.join(out_dir, ".смета.html")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(_doc(site, when, works, rate))
        from .pdf import html_to_pdf
        err = html_to_pdf(tmp, os.path.join(out_dir, "смета.pdf"))
        os.remove(tmp)
        if err:
            print("Смета в PDF не собрана:", err)
    return works


def audit_html(summary):
    from . import settings
    b = html_block(summary.get("works") or [], settings.HOUR_RATE, h2="h2", h2_cls="", cls="")
    return f'<section class="pt">{b}</section>' if b else ""
