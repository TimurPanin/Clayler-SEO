"""Google Search Console: сверка с обходом (данные — seocrawler/search_console.py, meta «gsc»)."""
from urllib.parse import unquote

from ..common import CRIT, NOTE, WARN
from ... import search_console as G
from ...search_console import COVERAGE, indexed


def run(ctx):
    g = ctx.store.get_meta("gsc", None)
    if not g:
        return
    add, status = ctx.add, ctx.status
    src = f"Данные Google Search Console для {g['site']}, загружены {g['fetched']}."

    def st(url):
        return status.get(url) or status.get(unquote(url))

    broken = []
    for p in sorted(g.get("pages") or [], key=lambda p: -p["shows"]):
        x = st(p["url"])
        if x and (x[1] or (x[0] and x[0] != 200)):
            broken.append([p["url"], x[1] or x[0], round(p["shows"]), round(p["clicks"])])
    add("gsc_index_broken", CRIT, "Google Search Console",
        "Google показывает в поиске неработающие страницы (404, ошибки, редиректы)",
        src + " За последние 28 дней Google показывал эти адреса в поиске, а при проверке они отдают ошибку "
        "или перенаправляют. Колонки «Показы» и «Клики» - сколько людей их видели и сколько перешли: "
        "начните сверху, там больше всего потерянных посетителей.",
        "Если страница нужна, почините её. Если переехала, поставьте 301-редирект на новую (для редиректов это уже сделано, "
        "Google обновит выдачу сам). Если удалена насовсем, пусть отдаёт 404 или 410.",
        ["Адрес в поиске", "Код при проверке", "Показы", "Клики"], broken, page_col=None)

    ins = g.get("inspect") or []
    canon = [[x["url"], x["user_canonical"], x["google_canonical"]] for x in ins
             if x.get("google_canonical") and x.get("user_canonical") and x["google_canonical"] != x["user_canonical"]]
    add("gsc_canonical_diff", WARN, "Google Search Console", "Google выбрал другую основную страницу, чем указано на сайте",
        src + " Для этих страниц сайт указывает одну основную (canonical), а Google решил, что основная - другая. "
        "В поиске будет показана страница, которую выбрал Google. Обычно причина - почти одинаковый текст на "
        "нескольких страницах или внутренние ссылки, ведущие не на ту версию.",
        "Сделайте текст страниц заметно разным или склейте дубли 301-редиректом. Внутренние ссылки и sitemap "
        "должны вести на ту версию, которую вы указали в canonical.",
        ["Страница", "Canonical на сайте", "Основная по мнению Google"], canon, page_col=None)

    notidx = [[x["url"], COVERAGE.get(x.get("coverage"), x.get("coverage") or "нет данных"), x.get("last_crawl") or "-"]
              for x in ins if (x.get("verdict") or x.get("coverage")) and not indexed(x)]
    add("gsc_not_indexed", WARN, "Google Search Console", "Важные страницы не в индексе Google",
        src + f" Программа выборочно спросила у Google о {len(ins)} страницах, ближайших к главной. Эти страницы "
        "открываются и не закрыты от поиска, но в индексе Google их нет. Причина - в колонке «Что говорит Google».",
        "«Обнаружена, но не просканирована» и «Просканирована, но не проиндексирована» - Google не считает страницу "
        "достаточно полезной: добавьте своего текста, ссылки на неё с других страниц. Остальное - исправьте причину "
        "и нажмите в Search Console «Проверить URL» → «Запросить индексирование».",
        ["Страница", "Что говорит Google", "Робот был"], notidx, page_col=None)

    bad = [[s.get("path"), int(s.get("errors") or 0), int(s.get("warnings") or 0), (s.get("lastDownloaded") or "")[:10]]
           for s in g.get("sitemaps") or [] if int(s.get("errors") or 0) or int(s.get("warnings") or 0)]
    add("gsc_sitemap", WARN if any(r[1] for r in bad) else NOTE, "Google Search Console",
        "Google нашёл ошибки в sitemap",
        src + " Google прочитал эти файлы sitemap и нашёл в них ошибки или предупреждения.",
        "Откройте в Search Console «Файлы Sitemap» → нужный файл: там список ошибок. Исправьте и отправьте файл заново.",
        ["Sitemap", "Ошибок", "Предупреждений", "Google читал"], bad, page_col=None)

    near, snip = G.lost(g)
    cols = ["Запрос", "Страница в Google", "Место", "Показы", "Клики", "Ещё кликов"]
    add("gsc_low_ctr", WARN, "Google Search Console", "В Google сайт высоко, но по нему мало кликают",
        src + f" По этим запросам сайт в Google на 1-{G.LOW_CTR_MAX_POS} месте, а кликают меньше половины обычного "
        f"для такого места. «Ещё кликов» - сколько было бы при обычной кликабельности, за 28 дней. " + G.LOST_NOTE,
        "Откройте выдачу Google по запросу и посмотрите на свой сниппет глазами покупателя. Перепишите title и "
        "description страницы так, чтобы в них был запрос, выгода и цена или срок; проверьте, что Google не "
        "подставляет вместо них случайный текст со страницы.",
        cols, snip, page_col=None)
    add("gsc_near_top", NOTE, "Google Search Console", "Запросы Google, где до первой тройки недалеко",
        src + f" По этим запросам сайт в Google на {G.NEAR_FROM}-{G.NEAR_TO} месте, и его уже показывают. "
        f"«Ещё кликов» - сколько дало бы {G.TARGET}-е место за 28 дней. " + G.LOST_NOTE,
        "Начните сверху таблицы: добавьте на страницу текст, который отвечает на запрос, поправьте title и H1, "
        "поставьте на страницу ссылки с других страниц сайта. Если по запросу показывается не та страница, "
        "сделайте подходящую и сошлитесь на неё.",
        cols, near, page_col=None)
