"""Ссылки и картинки на внутренний адрес сервера (10.x, 192.168.x, localhost)."""
from ..common import CRIT, NOTE, WARN, ipaddress, urlsplit


def run(ctx):
    store = ctx.store
    add, all_checked, db, src_of = ctx.add, ctx.all_checked, ctx.db, ctx.src_of
    def private_host(h):
        h = (h or "").lower()
        if h in ("localhost",) or h.endswith((".local", ".localhost", ".lan", ".internal")):
            return True
        try:
            ip = ipaddress.ip_address(h)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return False
    start_host = urlsplit(store.get_meta("start", "") or "").hostname
    private_urls = set()
    if not private_host(start_host):  # тестовый сайт на 127.0.0.1 не считаем
        for (dst,) in db.execute("SELECT DISTINCT dst FROM links"):
            if dst and private_host(urlsplit(dst).hostname):
                private_urls.add(dst)
    if private_urls:
        kind_ru = {"a": "ссылка", "img": "картинка", "srcset": "картинка", "css": "стиль (CSS)", "js": "скрипт (JS)",
                   "iframe": "фрейм", "canonical": "canonical", "redirect": "редирект", "hreflang": "hreflang"}
        prow = []
        for u in sorted(private_urls):
            r = db.execute("SELECT kind, COUNT(DISTINCT src), MIN(src), MAX(anchor) FROM links WHERE dst=? GROUP BY kind", (u,)).fetchall()
            for kind, n, ex, anchor in r:
                prow.append([u, kind_ru.get(kind, kind), anchor or "", n, ex])
        prow.sort(key=lambda x: -x[3])
        add("private_host", CRIT, "Ссылки", "Ссылки и картинки на внутренний адрес сервера",
            "На сайте стоят адреса вида 10.x.x.x, 192.168.x.x или localhost. Это внутренняя сеть хостинга: "
            "у посетителей такие картинки не показываются, а ссылки не открываются. Обычно адрес попадает "
            "в код, когда сайт настраивали за прокси или сохранили картинку во внутренней админке.",
            "Сначала откройте страницу в браузере и посмотрите код (Ctrl+U). Если там адрес внутренний, передайте "
            "разработчику: заменить его на домен сайта или на адрес, начинающийся с /. Если в браузере адрес "
            "нормальный, значит, сайт отдаёт роботам другую версию страницы (кеш сервера или настройка прокси): "
            "поисковик может видеть то же, что программа. Это тоже к разработчику или хостингу.",
            ["Адрес", "Что это", "Текст ссылки / alt", "На скольких страницах", "Например, здесь"], prow, page_col=None)

    ext = [r for r in all_checked if not r["internal"] and ((r["status"] or 0) >= 400 or r["error"])
           and r["url"] not in private_urls]

    def ext_hint(r):
        s = r["status"] or 0
        if s in (401, 403, 405, 429, 999) or s >= 500:
            return "Возможно, сайт не пускает роботов, а в браузере работает. Проверьте вручную."
        if s in (404, 410):
            return "Страницы нет. Замените или уберите ссылку."
        if (r["error"] or "").startswith("DNS"):
            return "Домен не существует. Уберите ссылку."
        return "Проверьте в браузере."
    # 401/403/405/429/999 и ошибки SSL у чужих сайтов — обычно защита от роботов, а не битая ссылка
    def ext_robot_block(r):
        return (r["status"] or 0) in (401, 403, 405, 406, 429, 999) or (r["error"] or "").startswith(("SSL", "Соединение сброшено на шаге https"))

    def from_own_page(r):
        """Ссылка стоит на своей странице. Иначе адрес - шаг чужого редиректа (yandex.ru/legal/… → капча): это не ваша
        ссылка, и «не открылся» про неё не значит «битая» (sait-primer.com). Она остаётся в ручной проверке."""
        return db.execute("SELECT 1 FROM links l JOIN urls u ON u.url=l.src WHERE l.dst=? AND u.internal=1 LIMIT 1",
                          (r["url"],)).fetchone() is not None
    ext_real = [r for r in ext if not ext_robot_block(r) and from_own_page(r)]
    real = {r["url"] for r in ext_real}
    ext_unsure = [r for r in ext if r["url"] not in real]
    add("ext_broken", WARN, "Ссылки", "Ссылки на чужие сайты, которые не открылись",
        "Ваш сайт ссылается на страницы других сайтов, а они не существуют (404, 410), домена нет "
        "или сервер ответил ошибкой даже после повторной проверки.",
        "Откройте каждую ссылку в браузере. Настоящие битые - замените или удалите.",
        ["Внешний адрес", "Ошибка", "Пояснение", "Где стоит ссылка"],
        [[r["url"], r["status"] or r["error"], ext_hint(r), src_of(r["url"], 2)] for r in ext_real], page_col=None)
    add("ext_unsure", NOTE, "Ссылки", "Чужие сайты не пустили программу - проверьте вручную",
        "Эти сайты ответили «доступ запрещён» (403), «слишком много запросов» (429) и т. п. Обычно так соцсети "
        "и крупные сайты защищаются от роботов, а в браузере ссылка работает. Программа не может сказать, "
        "битая ли ссылка, поэтому это не ошибка, а список для ручной проверки.",
        "Откройте несколько ссылок в браузере. Если открываются, ничего делать не нужно.",
        ["Внешний адрес", "Ответ", "Где стоит ссылка"],
        [[r["url"], r["status"] or r["error"], src_of(r["url"], 2)] for r in ext_unsure], page_col=None)

