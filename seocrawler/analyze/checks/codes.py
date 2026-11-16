"""Коды ответа."""
from collections import Counter
from urllib.parse import urlsplit

from ..common import CRIT, WARN, re
from ... import cms_help
from ...fetcher import REDIRECTS
from ...fmt import num as _n, plural as _plural

IMG = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|bmp|ico)$", re.I)
THUMB = re.compile(r"-(\d{2,4})x(\d{2,4})\.[a-z]{3,4}$", re.I)   # уменьшенная копия WordPress: photo-350x380.jpg

# 408 и 429 - не «страницы нет»: сервер не дождался запроса или просит обходить реже. Это про скорость обхода, а не
# битая страница: отдельный пункт too_many_requests, в битые ссылки не идут (коды 200-5xx по порядку)
TEMP4 = (408, 429)
MEANING = {
    200: "работает", 301: "переехала навсегда", 302: "временный редирект", 303: "временный редирект на другую страницу",
    307: "временный редирект", 308: "переехала навсегда",
    100: "промежуточный ответ вместо страницы", 201: "«создано» - так отвечают на отправку формы, а не на страницу",
    202: "«принято в работу» - страница не отдана", 203: "ответ изменён по дороге (прокси)",
    204: "«пусто» - страница без содержимого", 205: "«сбросить форму» - страница без содержимого",
    206: "кусок страницы вместо целой", 300: "«несколько вариантов» - браузер сам не выбирает",
    304: "«не изменилось», хотя робот об этом не спрашивал", 305: "устаревший код (через прокси)",
    306: "устаревший код, не используется",
    400: "неправильный запрос", 401: "нужен вход (логин и пароль)", 402: "нужна оплата", 403: "доступ закрыт",
    404: "страницы нет", 405: "сервер не разрешает так открывать адрес", 406: "сервер не отдаёт подходящий формат",
    407: "нужен вход на прокси", 408: "сервер не дождался запроса", 409: "конфликт на сервере",
    410: "удалена навсегда", 411: "сервер требует длину запроса", 412: "условие запроса не выполнено",
    413: "запрос слишком большой", 414: "адрес слишком длинный", 415: "формат не поддерживается",
    416: "запрошенного куска нет", 418: "шуточный код «я чайник» - так обычно отвечает защита от роботов",
    421: "запрос попал не на тот сервер", 422: "сервер не смог обработать запрос", 423: "адрес заблокирован",
    425: "слишком рано", 426: "нужен другой протокол", 428: "нужно условие в запросе",
    429: "слишком много запросов - сервер просит реже", 431: "заголовки запроса слишком большие",
    451: "закрыта по требованию закона",
    500: "внутренняя ошибка сервера", 501: "сервер не умеет отвечать на такой запрос",
    502: "сервер за прокси (nginx, CDN) не ответил как надо", 503: "сервер перегружен или на обслуживании",
    504: "сервер за прокси не ответил вовремя", 505: "версия HTTP не поддерживается", 507: "на сервере кончилось место",
    508: "сервер ушёл в цикл", 520: "ошибка за Cloudflare: сервер ответил непонятно",
    521: "за Cloudflare сервер выключен", 522: "за Cloudflare сервер не подключился", 523: "Cloudflare не нашёл сервер",
    524: "за Cloudflare сервер не ответил вовремя", 525: "ошибка https между Cloudflare и сервером",
    526: "сертификат сервера за Cloudflare не прошёл проверку",
}


# Короткая подпись для сводки «Что отвечают страницы» (report.code_label): там, где полное объяснение длинное.
# Остальные коды - полным объяснением, если оно короткое, иначе по группе (label)
SHORT = {429: "просит обходить реже", 503: "перегружен или на обслуживании", 502: "ошибка прокси сервера",
         504: "прокси сервера не дождался", 405: "так открывать нельзя", 406: "не тот формат", 418: "защита от роботов",
         303: "временный редирект", 201: "«создано»", 202: "«принято в работу»", 204: "пустой ответ",
         205: "пустой ответ", 206: "кусок страницы", 300: "несколько вариантов", 304: "«не изменилось» без запроса"}


def label(code):
    """Коротко, что значит код (сводка «Что отвечают страницы»), по тем же правилам, что meaning()."""
    if code in SHORT:
        return SHORT[code]
    m = meaning(code)
    if len(m) <= 30:
        return m
    return "необычный код" if odd(code) else "ошибка запроса" if code < 500 else "ошибка сервера"


def meaning(code):
    """Что значит код ответа, простыми словами (колонка «Что это значит»)."""
    if code in MEANING:
        return MEANING[code]
    if not code:
        return "ответа нет"
    if code < 100 or code >= 600:
        return "нестандартный код - такого в HTTP нет"
    if code < 200:
        return "промежуточный ответ вместо страницы"
    if code < 300:
        return "необычный успешный ответ"
    if code < 400:
        return "необычный редирект"
    return "ошибка запроса" if code < 500 else "ошибка сервера"




def odd(code):
    """Код, которым обычная страница не отвечает: не 200, не редирект 301/302/303/307/308 и не ошибка 4xx/5xx
    (1xx, 2xx кроме 200, остальные 3xx, нестандартные). Такие адреса молча выпадали из всех проверок."""
    return bool(code) and (code < 200 or 200 < code < 300 or (300 <= code < 400 and code not in REDIRECTS)
                           or code >= 600)


# Закон сохранения: каждый проверенный адрес своего сайта - ровно в одном ящике. Пункты отчёта о кодах и
# сводка «Что отвечают страницы» строятся только через bucket(), поэтому не расходятся; tests/проверить_закон_сохранения.py
# перебирает все коды 0-999 и все готовые базы: адрес без ящика («unknown») - ошибка программы, а не сайта.
BUCKETS = ("ok", "redirect", "redirect_noloc", "4xx", "too_many_requests", "5xx", "odd_codes", "noresp")


def bucket(status, error="", location=""):
    """Ящик для ответа: ok, redirect, redirect_noloc, 4xx, too_many_requests, 5xx, odd_codes, noresp. Ошибка
    загрузки важна, только когда кода нет или он 200 (страница пришла обрывком); у 404 с оборванным телом код
    известен - это 4xx, а не «не ответил» (раньше такой адрес попадал в оба пункта)."""
    if not status:
        return "noresp"
    if status == 200:
        return "noresp" if error else "ok"
    if status in REDIRECTS:
        return "redirect" if location else "redirect_noloc"
    if odd(status):
        return "odd_codes"
    if status in TEMP4:
        return "too_many_requests"
    if 400 <= status < 500:
        return "4xx"
    if 500 <= status < 600:
        return "5xx"
    return "unknown"


# «Адрес не открывается» - одно правило для всех проверок (битые ссылки, sitemap, стили и
# скрипты, бюджет обхода, здоровье, паутина и редиректы считали каждый по-своему - «код от 400 или ошибка»).
# 408/429 - не битые (сервер просил реже), необычные коды - свой пункт odd_codes.
NOT_OPEN = ("4xx", "5xx", "noresp", "redirect_noloc")
# то же для запросов к базе (таблица pages как p); tests/проверить_закон_сохранения.py сверяет его с not_open()
NOT_OPEN_SQL = ("((p.status BETWEEN 400 AND 599 AND p.status NOT IN (408, 429)) OR COALESCE(p.status, 0) = 0 "
                "OR (p.status = 200 AND COALESCE(p.error, '') <> '') "
                "OR (p.status IN (301, 302, 303, 307, 308) AND COALESCE(p.location, '') = ''))")


def not_open(status, error="", location=None):
    """Адрес не открывается: ошибка 4xx (кроме 408/429), 5xx, нет ответа или обрывок, редирект без адреса.
    location None - адрес перехода в этих данных неизвестен: редирект тогда не считается «без адреса»."""
    return bucket(status, error, "?" if location is None else location) in NOT_OPEN


def recheck_marks(store, rows):
    """{адрес: что дала повторная проверка ошибки 5xx} (crawler/extra_passes.recheck_errors). С 22.10.2026 обход
    записывает адреса, где ошибка повторилась. У старых проверок списка нет: если перепроверено меньше предела (400),
    перепроверялись все ошибки сервера, и оставшиеся в базе - повторились (открывшиеся заменены новым ответом)."""
    from ...crawler.extra_passes import ExtraPassesMixin as _X
    meta = store.get_meta("errors_rechecked", None) or {}
    rep = meta.get("repeated")
    old_all = rep is None and meta.get("checked", 0) and meta["checked"] < meta.get("limit", 400)
    out = {}
    for r in rows:
        u, st = r["url"], r["status"]
        if rep is not None and u in rep:
            out[u] = f"повторилась ({rep[u]})"
        elif old_all and st in _X.TRANSIENT and st != 408:   # 408 перепроверяется только с 04.11.2026
            out[u] = f"повторилась ({st})"
        else:
            out[u] = "не перепроверялась"
    return out


def cause(url):
    """Причина ошибки 4xx - одно исправление на группу адресов (отчёт market-primer.ru: 20 911 ошибок, почти все -
    миниатюры картинок одного размера, то есть одна причина, а не 20 тысяч)."""
    path = urlsplit(url).path
    seg = [x for x in path.split("/") if x]
    if IMG.search(path):
        if THUMB.search(path):   # размеров много (350x380, 570x428…), а исправление одно - пересоздать копии
            return "Уменьшенные копии картинок (миниатюры): файлов нет на сервере"
        return "Картинки" + (f" в папке /{seg[0]}/" if len(seg) > 1 else "") + ": файлов нет на сервере"
    if re.search(r"\.(css|js)$", path, re.I):
        return "Файлы стилей и скриптов"
    if re.search(r"\.(pdf|docx?|xlsx?|zip|rar)$", path, re.I):
        return "Документы и архивы"
    return f"Страницы в разделе /{seg[0]}/" if len(seg) > 1 else "Отдельные страницы"


_BAD = f"""SELECT u.url FROM urls u JOIN pages p ON p.url=u.url WHERE u.internal=1 AND {NOT_OPEN_SQL}"""
_BATCH = 5000   # адресов в одном запросе (у SQLite предел на число «?»)


def _broken_link_pages(store):
    """[(битый адрес своего сайта, со скольких разных страниц на него ссылки и картинки, номер адреса в strs или None)].
    В новой базе - по номерам в link_rows (по индексу, без перебора всех ссылок сайта), в старой - по таблице links."""
    db = store.db
    if store.legacy_links:
        return [(d, n, None) for d, n in db.execute(
            f"SELECT dst, COUNT(DISTINCT src) FROM links WHERE kind IN ('a','img') AND dst IN ({_BAD}) GROUP BY dst")]
    return db.execute(f"""SELECT d.s, COUNT(DISTINCT l.src), l.dst FROM link_rows l JOIN strs d ON d.id=l.dst
        WHERE l.kind IN ('a','img') AND l.src IN (SELECT id FROM strs) AND l.dst IN (SELECT id FROM strs WHERE s IN ({_BAD}))
        GROUP BY l.dst""").fetchall()


def _batches(ids):
    for k in range(0, len(ids), _BATCH):
        part = ids[k:k + _BATCH]
        yield part, ",".join("?" * len(part))


def _broken_rows(store, counts, tpl):
    """Строки «битых ссылок» (страница, куда, текст, код, ошибка) на битые адреса, кроме ссылок шаблона tpl. В новой
    базе - только ссылки на эти адреса по индексу link_rows_dst: раньше запрос перебирал все ссылки сайта (dom-primer:
    28 млн, 2+ минуты), а ссылки шаблона выбрасывались уже в Python."""
    db = store.db
    if store.legacy_links or any(i is None for _d, _n, i in counts):
        yield from (r for r in db.execute("""SELECT DISTINCT l.src, l.dst, l.anchor, p.status, p.error FROM links l
            JOIN pages p ON p.url=l.dst JOIN urls u ON u.url=l.dst
            WHERE u.internal=1 AND l.kind IN ('a','img') AND """ + NOT_OPEN_SQL) if r[1] not in tpl)
        return
    ids = [i for d, _n, i in counts if d not in tpl]
    for part, ph in _batches(ids):
        yield from db.execute(f"""SELECT DISTINCT s.s, d.s, a.s, p.status, p.error FROM link_rows l
            JOIN strs s ON s.id=l.src JOIN strs d ON d.id=l.dst LEFT JOIN strs a ON a.id=l.anchor
            JOIN pages p ON p.url=d.s JOIN urls u ON u.url=d.s
            WHERE l.dst IN ({ph}) AND l.kind IN ('a','img') AND u.internal=1 AND {NOT_OPEN_SQL}""", part)


def _template_pages(store, counts, tpl):
    """Страницы, где стоят битые ссылки шаблона: сводки по разделам и шаблонам, «паутина» и «Семантика» видят
    проблему на этих страницах, как до объединения в одну строку."""
    db = store.db
    out = set()
    if store.legacy_links or any(i is None for _d, _n, i in counts):
        dsts = list(tpl)
        for part, ph in _batches(dsts):
            out.update(u for (u,) in db.execute(
                f"SELECT DISTINCT src FROM links WHERE kind IN ('a','img') AND dst IN ({ph})", part))
        return out
    ids = [i for d, _n, i in counts if d in tpl]
    for part, ph in _batches(ids):
        out.update(u for (u,) in db.execute(f"""SELECT DISTINCT s.s FROM link_rows l JOIN strs s ON s.id=l.src
            WHERE l.kind IN ('a','img') AND l.dst IN ({ph})""", part))
    return out


def run(ctx):
    add, all_checked, db, inl, src_of = ctx.add, ctx.all_checked, ctx.db, ctx.inl, ctx.src_of
    own = [r for r in all_checked if r["internal"] and r["kind"] != "sitemap"]
    box = {}   # ящик -> адреса (bucket): каждый адрес ровно в одном
    for r in own:
        box.setdefault(bucket(r["status"], r["error"], r["location"]), []).append(r)
    int4 = box.get("4xx", [])
    causes = Counter(cause(r["url"]) for r in int4)
    groups = "; ".join(f"{c.split(':')[0]} - {_n(n)}" for c, n in causes.most_common(5))
    add("4xx", CRIT, "Коды ответа", "Страницы и файлы с ошибкой 4xx",
        "Адрес не открывается: страницы нет (404, 410), доступ закрыт (403) или нужен вход (401) - что значит "
        "каждый код, в колонке «Что это значит». Посетитель видит ошибку, а поисковик тратит время на пустые адреса."
        + (f" Адресов много, но причин {_n(len(causes))} - столько и отдельных исправлений: {groups}"
           + (" и другие" if len(causes) > 5 else "") + ". Колонка «Причина» в списке." if len(int4) >= 20 else ""),
        "Исправляйте по причинам, а не по адресам. Уменьшенные копии картинок - "
        + cms_help.how(cms_help.of_store(ctx.store), "thumbs", with_link=False)
        + " Страница переехала - 301-редирект на "
        "новый адрес; страницы больше нет - убрать ссылки на неё (где они стоят - в колонке «Где стоят ссылки» и в "
        "разделе «Битые ссылки»).",
        ["Адрес", "Код", "Что это значит", "Причина", "Ссылок на него", "Где стоят ссылки"],
        [[r["url"], r["status"], meaning(r["status"]), cause(r["url"]), len(inl.get(r["url"], ())), src_of(r["url"])]
         for r in sorted(int4, key=lambda r: (-causes[cause(r["url"])], r["url"]))])
    wait4 = box.get("too_many_requests", [])
    again = recheck_marks(ctx.store, wait4)
    add("too_many_requests", WARN, "Коды ответа", "Сервер просил обходить реже (429) или не дождался запроса (408)",
        "Это не битые страницы: сервер ограничил частоту запросов при проверке (429) или не успел принять запрос "
        "(408). Проверка выдерживала паузу, которую просил сервер, а после обхода эти адреса открывались ещё раз - "
        "колонка «Повторная проверка». Так же сервер может отвечать и роботам Яндекса и Google, если они обходят "
        "сайт часто.",
        "Откройте адрес в браузере. Если роботы поисковиков тоже получают 429 (видно в Вебмастере и Search Console), "
        "попросите разработчика или хостинг ослабить ограничение для них.",
        ["Адрес", "Код", "Что это значит", "Повторная проверка", "Где стоят ссылки"],
        [[r["url"], r["status"], meaning(r["status"]), again[r["url"]], src_of(r["url"])] for r in wait4])
    int5 = box.get("5xx", [])
    again = recheck_marks(ctx.store, int5)
    sure = int5 and all(again[r["url"]].startswith("повторилась") for r in int5)
    add("5xx", CRIT, "Коды ответа", "Ошибки сервера 5xx",
        "Сервер сломался, пока отдавал страницу. Если ошибка повторяется, поисковик может убрать страницу из выдачи."
        + (" Все адреса открыты ещё раз после обхода, по одному и с паузой: ошибка повторилась, это не случайный сбой."
           if sure else " Колонка «Повторная проверка»: повторилась ли ошибка, когда адрес открыли ещё раз после обхода."),
        "Откройте адрес в браузере. Если ошибка есть и там, передайте разработчику."
        + ("" if sure else " Если в браузере всё открывается, сервер не выдерживал скорость обхода: запустите с паузой побольше."),
        ["Адрес", "Код", "Что это значит", "Повторная проверка", "Где стоят ссылки"],
        [[r["url"], r["status"], meaning(r["status"]), again[r["url"]], src_of(r["url"])] for r in int5])
    strange = box.get("odd_codes", [])
    add("odd_codes", WARN, "Коды ответа", "Необычный код ответа вместо 200",
        "Адрес отвечает кодом, которым обычные страницы и файлы не отвечают (что он значит - в колонке «Что это "
        "значит»). Поисковик может не взять такую страницу в выдачу или посчитать пустой, браузер может показать "
        "пустой экран. В остальные проверки такие адреса не попадают.",
        "Передайте разработчику: рабочая страница должна отвечать кодом 200, переехавшая - 301, удалённая - 404 "
        "или 410.",
        ["Адрес", "Код", "Что это значит", "Где стоят ссылки"],
        [[r["url"], r["status"], meaning(r["status"]), src_of(r["url"])] for r in strange])
    noresp = box.get("noresp", [])
    add("noresp", CRIT, "Коды ответа", "Сервер не ответил",
        "Ответа не было или он оборвался (при обрыве и таймауте адрес открывается ещё раз). Тип ошибки "
        "подсказывает причину: домен не найден (DNS), таймаут (сервер слишком долго думал), соединение сброшено "
        "(сервер оборвал связь), загрузка дольше срока (сервер отдавал страницу слишком медленно).",
        "Откройте адрес в браузере. Если открывается, скорее всего, сервер ограничивает частые запросы: "
        "запустите аудит с меньшей скоростью. Если нет, передайте разработчику.",
        ["Адрес", "Ошибка", "Где стоят ссылки"], [[r["url"], r["error"] or "нет ответа", src_of(r["url"])] for r in noresp])

    # Битая ссылка в меню или подвале - строка на каждой странице: на dom-primer.ru их было 3,8 млн (45 таких
    # адресов из 530 битых, весь раздел «Свет» в меню отдавал 404). Такая ссылка - одна правка в шаблоне: она идёт
    # одной строкой «на N страницах, например: <страница>». Ссылка шаблона - по тому же
    # правилу, что в здоровье сайта (health.template_link), и здоровье считает её так же (Issue.group_dsts). Страницы
    # с ней - Issue.group_pages (сводки по разделам, шаблонам, «паутина», «Семантика»). Остальные - построчно.
    from ..health import health_base, template_link
    n_base = len(health_base(ctx.pages))
    counts = _broken_link_pages(ctx.store)
    tpl = {dst: n for dst, n, _i in counts if template_link(n, n_base)}
    grouped = []
    for dst, n in sorted(tpl.items(), key=lambda kv: (-kv[1], kv[0])):
        ex = db.execute("SELECT src, anchor FROM links WHERE dst=? AND kind IN ('a','img') LIMIT 1", (dst,)).fetchone()
        st = ctx.status.get(dst, (None, None))
        # пример страницы - отдельной строкой: отчёт делает его ссылкой и «показать на странице»
        grouped.append([f"на {_n(n)} {_plural(n, 'странице', 'страницах', 'страницах')} (меню, подвал или другой "
                        f"общий блок), например:\n{ex[0] if ex else '-'}", dst, ex[1] if ex else None, st[0] or st[1]])
    # Строки собираем сразу списками, а одинаковые адреса и тексты - одним объектом: словари и копии строк на каждую
    # ссылку занимали гигабайты
    cache = {}
    one = lambda x: cache.setdefault(x, x) if isinstance(x, str) else x   # noqa: E731
    broken = grouped + [[one(src), one(dst), one(anchor), st or err]
                        for src, dst, anchor, st, err in _broken_rows(ctx.store, counts, tpl)]
    cache = None
    add("broken_links", CRIT, "Ссылки", "Битые ссылки: где именно исправлять",
        "Каждая строка - ссылка или картинка на странице вашего сайта, которая ведёт в никуда."
        + (f" Ссылки из меню, подвала или другого общего блока стоят почти на каждой странице - каждая показана одной "
           f"строкой «на N страницах» (таких адресов: {_n(len(tpl))}): её исправляют один раз в шаблоне сайта."
           if tpl else ""),
        "Готовое задание для разработчика или контент-менеджера: открыть страницу из первой колонки "
        "и исправить или удалить ссылку из второй." + (" Строки «на N страницах» - сначала: одна правка в шаблоне "
                                                       "убирает ошибку сразу со всех этих страниц." if tpl else ""),
        ["Страница, где стоит ссылка", "Куда ведёт", "Текст ссылки / alt", "Ошибка"], broken)
    if tpl and ctx.issues and ctx.issues[-1].key == "broken_links":
        iss = ctx.issues[-1]
        iss.grouped, iss.group_dsts = len(tpl), set(tpl)
        iss.group_pages = _template_pages(ctx.store, counts, tpl)

