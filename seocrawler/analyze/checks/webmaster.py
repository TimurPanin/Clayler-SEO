"""Яндекс Вебмастер: что видит сам Яндекс и сверка с обходом (данные — seocrawler/webmaster.py, meta «webmaster»)."""
from urllib.parse import unquote

from ..common import CRIT, NOTE, WARN
from ...webmaster import EXCLUDED, PROBLEMS, SEVERITY



def run(ctx):
    wm = ctx.store.get_meta("webmaster", None)
    if not wm:
        return
    add, status = ctx.add, ctx.status
    src = f"Данные Яндекс Вебмастера для {wm['host']} на {wm['fetched']}."

    def st(url):
        return status.get(url) or status.get(unquote(url))

    probs = [(k, v) for k, v in (wm.get("problems") or {}).items() if v.get("state") == "PRESENT"]
    if probs:
        hard = any(v.get("severity") in ("FATAL", "CRITICAL") for _, v in probs)
        order = ["FATAL", "CRITICAL", "POSSIBLE_PROBLEM", "RECOMMENDATION"]
        probs.sort(key=lambda kv: order.index(kv[1].get("severity")) if kv[1].get("severity") in order else 9)
        add("wm_problems", CRIT if hard else WARN, "Яндекс Вебмастер", "Яндекс сам видит проблемы на сайте",
            src + " Это диагностика из раздела «Диагностика сайта» Вебмастера: так сайт видит сам Яндекс. "
            "Фатальные и критичные проблемы напрямую мешают сайту быть в поиске.",
            "Начните с фатальных и критичных. Подробности по каждой - в Вебмастере, «Диагностика» → «Диагностика сайта». "
            "Когда исправите, там же можно нажать «Проверить».",
            ["Что видит Яндекс", "Важность", "С какого числа"],
            [[PROBLEMS.get(k, k), SEVERITY.get(v.get("severity"), v.get("severity") or ""),
              (v.get("last_state_update") or "")[:10]] for k, v in probs], page_col=None)

    # в поиске — а программа видит ошибку или редирект
    broken = []
    for s in wm.get("in_search") or []:
        x = st(s.get("url"))
        if x and (x[1] or (x[0] and x[0] != 200)):
            broken.append([s["url"], x[1] or x[0], (s.get("last_access") or "")[:10]])
    add("wm_index_broken", CRIT, "Яндекс Вебмастер", "В поиске Яндекса есть неработающие страницы (404, ошибки, редиректы)",
        src + " Эти адреса Яндекс показывает в поиске, а при проверке они отдают ошибку или перенаправляют. "
        "Человек из поиска попадёт на ошибку, а Яндекс со временем уберёт страницу из выдачи и потеряет её позиции.",
        "Если страница нужна, почините её. Если переехала, поставьте 301-редирект на новую (для редиректов в "
        "таблице это уже сделано, Яндекс обновит выдачу сам). Если удалена насовсем, пусть отдаёт 404 или 410.",
        ["Адрес в поиске", "Код при проверке", "Робот был"], broken, page_col=None)

    removed = [e for e in (wm.get("events") or []) if e.get("event") == "REMOVED_FROM_SEARCH"]
    add("wm_removed", WARN, "Яндекс Вебмастер", "Страницы, недавно выпавшие из поиска Яндекса",
        src + " Яндекс убрал эти страницы из выдачи. Причина - в колонке «Почему». Если среди них есть важные "
        "страницы (товары, услуги, разделы) - сайт теряет по ним посетителей.",
        "Просмотрите список. Нужные страницы: исправьте причину (ошибка, noindex, canonical, дубль) и отправьте "
        "в Вебмастере на переобход («Индексирование» → «Переобход страниц»).",
        ["Страница", "Почему", "Когда", "Код при проверке"],
        [[e["url"], EXCLUDED.get(e.get("excluded_url_status"), e.get("excluded_url_status") or ""),
          (e.get("event_date") or "")[:10], (lambda x: (x[1] or x[0]) if x else "не найдена обходом")(st(e["url"]))]
         for e in removed], page_col=None)

    # нужные страницы, которых нет в поиске — только если список страниц в поиске загружен целиком
    total = (wm.get("summary") or {}).get("searchable_pages_count")
    ins = wm.get("in_search")
    if ins is not None and total is not None and len(ins) >= total:
        have = {s.get("url") for s in ins} | {unquote(s.get("url") or "") for s in ins}
        missing = [[p["url"], p.get("depth")] for p in ctx.indexable if p["url"] not in have]
        add("wm_not_in_index", WARN if len(missing) > len(ctx.indexable) * 0.2 else NOTE,
            "Яндекс Вебмастер",
            "Страницы сайта, которых нет в поиске Яндекса",
            src + " Эти страницы открываются, не закрыты от поиска и не указывают на другую как на основную, "
            "но Яндекс их в поиске не показывает. Бывает у новых страниц (Яндекс ещё не дошёл), у страниц глубоко "
            "в структуре и у страниц с малым количеством своего текста.",
            "Проверьте, что страницы есть в sitemap и на них ведут ссылки. Важные отправьте на переобход в Вебмастере. "
            "Если страница пустая или почти дублирует другую, дополните текст.",
            ["Страница", "Кликов от главной"], missing, page_col=None)
