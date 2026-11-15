"""Sitemap."""
from ...fmt import num
from ..common import CRIT, NOTE, WARN, _q, defaultdict, link_rows
from .codes import TEMP4, not_open

# правило шире навигации (Disallow: /*? закрывает и фильтры, и сортировки) убирать нельзя (thehome.ru)
# готовое правило вписывается не всегда (fix_files._pagination_allows: только если навигация - единственный параметр
# и правило не откроет других закрытых адресов) - поэтому «если подошло», а не обещание
WIDE_RULE = ("Если правило закрывает все адреса с «?» (например, «Disallow: /*?»: и фильтры, и сортировки), не убирайте "
             "его, а добавьте узкое разрешение для навигации в нужном разделе, например «Allow: /catalog/*?PAGEN_1=». "
             "Если такое правило подошло к адресам сайта, оно уже вписано в robots.txt в файлах для разработчика - "
             "иначе его нужно составить вручную.")


def _rule(reason):
    """«Закрыт в robots.txt (Disallow: /*PAGEN)» → «Disallow: /*PAGEN»."""
    return (reason or "").replace("Закрыт в robots.txt (", "").rstrip(")")


def run(ctx):
    store = ctx.store
    add, all_checked, code, db, follow = ctx.add, ctx.all_checked, ctx.code, ctx.db, ctx.follow
    indexable, redir, status = ctx.indexable, ctx.redir, ctx.status
    sm = {r[0] for r in db.execute("SELECT url FROM sitemap")}
    sitemap_checked = bool(store.get_meta("sitemap_checked", False))
    skipped_sm = {r["url"]: r["skip_reason"] for r in _q(db, "SELECT url, skip_reason FROM urls WHERE state='skipped'")}
    if sm:
        info = {r["url"]: r for r in all_checked}
        redirects_sm, errors_sm, nonidx_sm, orphans = [], [], [], []
        sm_targets = set()
        # пустая страница («Элемент не найден», код 200) - не «рабочая сирота»: она уже в «Страница не найдена»
        for u in sorted(sm):
            if u in skipped_sm:
                if skipped_sm[u].startswith("Закрыт в robots"):
                    nonidx_sm.append([u, "закрыт в robots.txt", "Уберите из sitemap или откройте в robots.txt."])
                continue
            r = info.get(u)
            if not r:
                continue
            if u in redir:
                ch, loop = follow(u)
                final = ch[-1]
                fst = status.get(final)   # None - конец не проверялся (чужой сайт): не ошибка
                if loop or (fst and not_open(fst[0], fst[1], redir.get(final, ""))):
                    # редирект ведёт на ошибку — это не «устаревший адрес», а битая страница
                    errors_sm.append([u, f"{code(u)} → {final} → {code(final)}" if not loop else "редирект по кругу"])
                else:
                    sm_targets.add(final)
                    redirects_sm.append([u, code(u), final, code(final)])
            elif r["status"] in TEMP4:   # не битый: сервер просил обходить реже (codes.TEMP4) - так и пишем
                errors_sm.append([u, f"{r['status']} - сервер просил обходить реже, проверьте позже"])
            elif not_open(r["status"], r["error"], r["location"]):   # общее правило (codes.not_open)
                # у обрывка с кодом 200 - текст ошибки, а не «200»
                errors_sm.append([u, (r["error"] or "нет ответа") if r["status"] in (None, 0, 200) else r["status"]])
            elif r["indexable"] == 0:
                nonidx_sm.append([u, r["indexability"], "Уберите из sitemap или сделайте страницу индексируемой."])
            elif r["kind"] == "sitemap" and r["indexable"] == 1 and u not in ctx.soft404:
                orphans.append([u])
        add("sitemap_redirect", WARN, "Sitemap", "В sitemap устаревшие адреса (с редиректом)",
            "В sitemap записаны адреса, которые перенаправляют на другие. Поисковик тратит время на лишние переходы "
            "и получает противоречивые сигналы. Частая причина - sitemap генерирует адреса без слеша в конце, "
            "а сайт работает со слешем (или наоборот).",
            "Замените в sitemap адреса на конечные (колонка «Правильный адрес»). Обычно это настройка "
            "модуля, который создаёт sitemap.",
            ["Адрес в sitemap", "Код", "Правильный адрес", "Его код"], redirects_sm, page_col=None)
        add("sitemap_errors", CRIT, "Sitemap", "В sitemap адреса с ошибкой (404, 500…)",
            "В sitemap записаны адреса, которые не открываются: сразу или после редиректа отдают ошибку. "
            "Вы сами показываете поисковику несуществующие страницы.",
            "Откройте каждый адрес в браузере. Если страница нужна, почините её (ошибка 500 - к разработчику). "
            "Если нет, уберите адрес из sitemap.",
            ["Адрес в sitemap", "Ошибка"], errors_sm, page_col=None)
        add("sitemap_nonindex", WARN, "Sitemap", "В sitemap страницы, закрытые от поиска",
            "В sitemap должны быть только страницы, которые вы хотите видеть в выдаче. Здесь те, что закрыты "
            "(noindex, robots.txt) или указывают на другой адрес как основной (canonical).",
            "Уберите их из sitemap или откройте для поиска.",
            ["Адрес в sitemap", "Почему закрыт", "Что сделать"], nonidx_sm, page_col=None)
        # сироты, которые стоят в закрытой в robots.txt постраничной навигации (каталог, стр. 2, 3…)
        via = defaultdict(list)
        for src, dst in link_rows(db, ("src", "dst"), "kind='via_blocked'"):
            via[dst].append(src)
        behind = [[o[0], "\n".join(sorted(via[o[0]])[:2]), _rule(skipped_sm.get(sorted(via[o[0]])[0]))]
                  for o in orphans if o[0] in via]
        orphans = [o for o in orphans if o[0] not in via]
        probe = store.get_meta("blocked_probe", None)
        if sitemap_checked:
            add("behind_blocked", WARN, "Индексация", "Страницы доступны только через закрытую в robots.txt навигацию",
                "Ссылки на эти страницы стоят только на 2-й, 3-й… странице списка (каталога, раздела), а постраничная "
                "навигация закрыта в robots.txt. Робот туда не заходит и по ссылкам до страниц не доходит - "
                "знает о них только из sitemap. Внутреннего веса они почти не получают.",
                "Откройте постраничную навигацию в robots.txt (уберите правило из колонки «Правило») и закройте её "
                "от индексации через noindex, follow или canonical на первую страницу - тогда робот пройдёт по ссылкам, "
                "а в выдачу страницы 2, 3… не попадут. " + WIDE_RULE + " Другой путь - ссылки на товары из фильтров, подборок, похожих товаров.",
                ["Адрес", "Где стоит ссылка (закрытая страница)", "Правило robots.txt"], behind, page_col=None)
            add("orphans", WARN, "Sitemap", "Страницы-сироты: есть в sitemap, но на сайте на них нет ссылок",
                "Эти страницы работают, но ни одна страница сайта на них не ссылается. Поисковик узнает о них "
                "только из sitemap, посетитель - никак. Внутреннего веса они почти не получают."
                + (f" Закрытая в robots.txt постраничная навигация проверена ({probe['opened']} стр.) - этих страниц нет и там."
                   if probe and probe.get("opened") else ""),
                "Если страницы нужны, поставьте на них ссылки из подходящих разделов. Если нет, уберите из sitemap "
                "и закройте или удалите.",
                ["Адрес"], orphans, page_col=None)
            not_in = [[p["url"]] for p in indexable if p["url"] not in sm and p["url"] not in sm_targets]
            add("not_in_sitemap", NOTE, "Sitemap", "Рабочие страницы, которых нет в sitemap",
                "Не ошибка, но полный sitemap помогает поисковику быстрее находить новые страницы.",
                "Проверьте, почему модуль sitemap их не включает.",
                ["Адрес"], not_in, page_col=None)

    # страницы, ссылки на которые только на закрытой в robots.txt навигации, и в sitemap их нет
    probe = store.get_meta("blocked_probe", None) or {}
    if probe.get("hidden"):
        # после проверки навигации адрес мог найтись иначе (страницы из Вебмастера и Search Console - их поиск знает)
        known = {r[0] for r in db.execute("SELECT url FROM urls")} | set((store.get_meta("search_urls", None) or {}).get("urls") or {})
        rows = [[u, src, _rule(skipped_sm.get(src))] for u, src in probe["hidden"] if u not in sm and u not in known]
        total = (probe.get("hidden_total") or 0) - (len(probe["hidden"]) - len(rows))
        absent = bool(store.get_meta("sitemap_absent", False))
        add("hidden_behind_blocked", CRIT, "Индексация", "Страницы, которые поисковик не находит: ссылки на них только на закрытых страницах навигации",
            "Ссылки на эти страницы (обычно товары) стоят только на 2-й, 3-й… странице списка, а постраничная навигация "
            "закрыта в robots.txt. Робот туда не заходит и по ссылкам до страниц не доходит"
            + (", а в sitemap их нет - поисковик о страницах не знает, и в выдачу они не попадают." if sm else
               ", а sitemap на сайте нет - поисковик о страницах не знает, и в выдачу они не попадают." if absent else
               ". Sitemap в этой проверке не смотрели или он не прочитался: если этих страниц нет и в нём, "
               "поисковик о них не знает.")
            + " Адреса взяты из ссылок на закрытых страницах, сами страницы не открывались."
            + (f" Всего таких адресов найдено {num(total)}, в списке первые {num(len(rows))}." if total > len(rows) else ""),
            "Откройте постраничную навигацию в robots.txt (уберите правило из колонки «Правило robots.txt») и закройте её "
            "от индексации через noindex, follow или canonical на первую страницу - тогда робот пройдёт по ссылкам, "
            "а в выдачу страницы 2, 3… не попадут. " + WIDE_RULE + " И добавьте эти страницы в sitemap"
            + (" (сейчас его на сайте нет)." if absent else "."),
            ["Адрес", "Где стоит ссылка (закрытая страница)", "Правило robots.txt"], rows, page_col=None)

    if not sm and store.get_meta("sitemap_absent", False):
        add("sitemap_none", WARN, "Sitemap", "На сайте нет карты сайта (sitemap)",
            "Файл sitemap не нашёлся: адрес отвечает «нет такой страницы» или вместо файла открывается обычная "
            "страница. "
            "Поисковик узнаёт о страницах только по ссылкам и медленнее находит новые.",
            "Передайте разработчику: сделать sitemap.xml со всеми рабочими страницами и указать его адрес "
            "в robots.txt.",
            # проблема одна, а не по адресу
            ["Какие адреса проверены"], [["\n".join(store.get_meta("sitemaps", []) or [])]], page_col=None)
    ctx.sitemap_checked, ctx.sm = sitemap_checked, sm
