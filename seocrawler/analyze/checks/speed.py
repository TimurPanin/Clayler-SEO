"""Скорость."""
from ..common import NOTE, SLOW_SECONDS, WARN


def run(ctx):
    store = ctx.store
    add, html_ok, indexable = ctx.add, ctx.html_ok, ctx.indexable
    rechecked = bool(store.get_meta("slow_rechecked", False))
    slow_rows, unverified = [], []
    re_n = re_slow = 0
    for p in html_ok:
        first = p.get("ttfb") if p.get("ttfb") is not None else p["elapsed"]
        if (first or 0) <= SLOW_SECONDS:
            continue
        again = p.get("ttfb_recheck")
        if rechecked and again is not None:
            re_n += 1
            if again <= SLOW_SECONDS:
                continue  # во второй раз ответил быстро — был случайный всплеск или нагрузка от самой проверки
            re_slow += 1
            slow_rows.append([p["url"], first, again])
        elif rechecked:
            unverified.append([p["url"], first, "не перемерена"])
        else:
            slow_rows.append([p["url"], first, ""])
    # Перемеряются самые медленные (до 600). Если среди них медленными оказались меньше половины,
    # остальные (менее медленные) тем более — это нагрузка от самой проверки, в отчёт их не берём.
    confirm = re_slow / re_n if re_n else 1
    if unverified and confirm >= 0.5:
        slow_rows += unverified
    dropped = len(unverified) if unverified and confirm < 0.5 else 0
    # без повторного спокойного замера (проверку остановили до него) - только замечание: у market-primer обход шёл
    # 7 ч, сервер был нагружен самой проверкой, и «медленными» вышли все 3 486 страниц
    add("slow", WARN if rechecked else NOTE, "Скорость", f"Сервер долго отвечает (больше {SLOW_SECONDS:g} секунды)",
        "Время от запроса до ответа сервера (без скачивания самой страницы). Замер сделан с вашего компьютера. "
        + (f"Самые медленные страницы ({re_n}) перемерены второй раз после обхода, по одной; медленными остались {re_slow}."
           + (f" Ещё {dropped} страниц были медленными только во время обхода - это нагрузка от самой проверки, в список не вошли."
              if dropped else "")
           if rechecked else "Это один замер во время обхода, повторного спокойного замера не было: сервер в этот момент был "
           "нагружен самой проверкой, поэтому это повод перемерить, а не вывод."),
        ("Если сервер медленный постоянно, передайте разработчику или хостингу: обычно помогает кеширование страниц."
         if rechecked else "Прежде чем передавать хостингу, перемерьте скорость: откройте 3-5 страниц из списка в обычное "
         "время. Если они открываются дольше секунды, передайте разработчику: обычно помогает кеширование страниц."),
        ["Адрес", "Секунд (при обходе)", "Секунд (повторно)"], slow_rows)
    add("no_compress", NOTE, "Скорость", "Страницы передаются без сжатия",
        "Сервер отдаёт страницы как есть, без сжатия (gzip или brotli). Сжатие обычно уменьшает объём в 3–5 раз.",
        "Передайте хостингу или разработчику: включить сжатие - это одна настройка сервера.",
        ["Адрес"], [[p["url"]] for p in html_ok if not p["content_encoding"] and (p["size"] or 0) > 2000], page_col=None)
    add("no_lastmod", NOTE, "Яндекс", "Сервер не сообщает дату изменения страницы (Last-Modified)",
        "Яндекс рекомендует отдавать дату последнего изменения страницы. Тогда робот быстрее понимает, "
        "что изменилось, и не перекачивает страницы зря.",
        "По желанию: передать разработчику.",
        ["Адрес"], [[p["url"]] for p in indexable if not p["last_modified"]], page_col=None)
    add("no_lang", NOTE, "Контент", "Не указан язык страницы",
        "В коде не указано, на каком языке страница (<html lang=\"ru\">). Помогает браузерам и поисковикам.",
        "Передайте разработчику: одна правка в шаблоне.",
        ["Адрес"], [[p["url"]] for p in indexable if not p["lang"]], page_col=None)

