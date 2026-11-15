"""Кеширование картинок, стилей и скриптов: велено ли браузеру запоминать их (заголовок Cache-Control
или Expires). Без этого посетитель на каждой странице заново качает одни и те же файлы (30.09.2026)."""
import re

from ..common import NOTE, WARN, CACHE_MIN_DAYS, _q


def verdict(cc):
    """Что не так с заголовком; пустая строка — всё хорошо."""
    low = (cc or "").lower()
    if not cc or cc == "-":
        return "указаний нет - браузер решает сам и часто перекачивает"
    if low.startswith("expires:"):
        return ""
    if "no-store" in low:
        return "запрещено запоминать (no-store)"
    if "no-cache" in low:
        return "каждый раз спрашивать сервер (no-cache)"
    m = re.search(r"max-age\s*=\s*(\d+)", low)
    if m:
        sec = int(m.group(1))
        if sec < CACHE_MIN_DAYS * 86400:
            return "хранить недолго: " + (f"{sec // 3600} ч" if sec >= 3600 else f"{sec} с")
        return ""
    return "срок хранения не указан"


def run(ctx):
    add, db = ctx.add, ctx.db
    cols = {r[1] for r in db.execute("PRAGMA table_info(pages)")}
    if "cache_control" not in cols:  # проверки до 30.09.2026 этих данных не собирали
        return
    rows = []
    for r in _q(db, """SELECT p.url, p.content_type, p.cache_control FROM pages p JOIN urls u ON u.url=p.url
                       WHERE u.internal=1 AND u.kind='resource' AND p.status=200 AND p.cache_control IS NOT NULL"""):
        ct = r["content_type"] or ""
        kind = "картинка" if ct.startswith("image/") else "стили (CSS)" if "css" in ct else \
            "скрипт (JS)" if "javascript" in ct or ct.endswith("/js") else ""
        v = kind and verdict(r["cache_control"])
        if v:
            rows.append([r["url"], kind, v, r["cache_control"]])
    rows.sort(key=lambda x: (x[1], x[0]))
    from ...site_tech import fixed_platform, CF_TIP, LIMIT
    if pf := fixed_platform(ctx.store):  # GitHub Pages, Tilda: срок хранения задаёт платформа, не владелец сайта
        add("no_cache", NOTE, "Скорость", "Браузеру не велено запоминать картинки, стили и скрипты",
            f"Сайт размещён на {pf['name']}: срок, на который браузер запоминает файлы, задаёт сама платформа"
            + (f" - {pf['cache']}" if pf.get("cache") else "") + ", владелец сайта его не меняет. Google PageSpeed "
            "отмечает это как «Неэффективная политика кеширования», но на скорость повторных визитов это влияет "
            "немного, а на позиции почти не влияет.",
            LIMIT + ", исправить его в настройках сайта нельзя. " + (
                CF_TIP + "срок хранения задаётся правилом кеширования Cloudflare (Caching → Cache Rules → Browser "
                "TTL, например 1 год для картинок, CSS и JS)." if pf["cloudflare_dns"] else
                "Если скорость важна, сайт можно перенести на хостинг, где заголовки настраиваются (или поставить "
                "перед ним Cloudflare). Иначе пункт можно оставить как есть."),
            ["Адрес файла", "Что это", "Что не так", "Заголовок сейчас"], rows, page_col=None)
        return
    add("no_cache", WARN, "Скорость", "Браузеру не велено запоминать картинки, стили и скрипты",
        "Когда посетитель переходит на следующую страницу, браузер берёт уже скачанные картинки, стили и скрипты "
        "из памяти - если сервер разрешил их запомнить (заголовок Cache-Control). Здесь не разрешил или разрешил "
        f"меньше чем на {CACHE_MIN_DAYS} дней: те же файлы качаются заново, страницы открываются медленнее, "
        "особенно с телефона. Google PageSpeed отмечает это как «Неэффективная политика кеширования».",
        "Передайте разработчику или хостингу: для картинок, CSS и JS отдавать заголовок "
        "«Cache-Control: public, max-age=31536000» (год). Обычно это одна настройка сервера (nginx: expires, "
        "Apache: mod_expires). Чтобы после правки стилей посетители получили новую версию, к адресу файла "
        "добавляют номер версии (style.css?v=2) - в Битриксе и WordPress это уже сделано.",
        ["Адрес файла", "Что это", "Что не так", "Заголовок сейчас"], rows, page_col=None)
