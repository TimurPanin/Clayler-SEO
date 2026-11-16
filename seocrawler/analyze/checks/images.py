"""Картинки."""
from ..common import IMG_HEAVY_KB, IMG_OLD_FORMAT_KB, IMG_VERY_HEAVY_KB, NOTE, WARN, _q


def _bad_type_why(src, ct, example):
    """Почему «картинка» не картинка - понятным языком (dom-primer.ru: адрес «картинки» https://dom-primer.ru/ на
    293 товарах - у картинки пустой src, браузер грузит главную)."""
    from urllib.parse import urlsplit
    sp, own = urlsplit(src), (urlsplit(example or "").hostname or "").lower()
    same_host = (sp.hostname or "").lower() == own
    # «главная» - только своего сайта: корень чужого (https://cdn.example.com/) - не про пустой src в шаблоне;
    # и «пустой или неверный», а не «пустой»: какой он был в коде, по адресу не узнать
    if (same_host and sp.path in ("", "/") and not sp.query) or src.rstrip("/") == (example or "").rstrip("/"):
        return ("адрес картинки - " + ("главная страница" if sp.path in ("", "/") else "сама эта страница")
                + ": обычно у картинки пустой или неверный адрес (src), браузер вместо файла получает страницу")
    if sp.path in ("", "/") and not sp.query:
        return f"адрес картинки - главная страница другого сайта ({sp.hostname}), а не файл"
    if ct.startswith("text/html"):
        return "по адресу картинки сервер отдаёт страницу (часто - страницу ошибки), а не файл"
    return f"по адресу лежит файл другого типа ({ct}) - картинкой его не показать"


def run(ctx):
    add, db = ctx.add, ctx.db
    KB = 1024
    res_info = {r["url"]: r for r in _q(db, """SELECT p.url, p.status, p.error, p.content_type, p.size, p.img_format,
        p.img_width, p.img_height, p.content_encoding, u.internal, u.kind FROM pages p JOIN urls u ON u.url=p.url""")}
    img_use = _q(db, """SELECT src, COUNT(DISTINCT page) AS n, MIN(page) AS ex,
        SUM(CASE WHEN alt IS NULL THEN 1 ELSE 0 END) AS no_attr,
        SUM(CASE WHEN alt IS NOT NULL AND TRIM(alt)='' THEN 1 ELSE 0 END) AS empty_alt,
        MAX(LENGTH(alt)) AS alt_len, MAX(alt) AS alt_ex,
        MIN(has_size) AS has_size, MAX(COALESCE(in_picture,0)) AS in_picture, MAX(COALESCE(srcset,0)) AS srcset
        FROM images GROUP BY src ORDER BY n DESC""")

    add("img_alt_missing", WARN, "Картинки", "Картинки совсем без атрибута alt",
        "У картинки нет атрибута alt. Поисковик не понимает, что на ней, а программа экранного доступа для незрячих "
        "прочитает вместо неё имя файла. Каждая картинка указана один раз, рядом - на скольких страницах она стоит.",
        "Добавьте alt с описанием того, что на картинке. Если картинка чисто декоративная (фон, разделитель) - "
        "поставьте пустой alt=\"\". Картинки из шаблона (много страниц) исправляются один раз.",
        ["Картинка", "На скольких страницах", "Например, здесь"],
        [[r["src"], r["n"], r["ex"]] for r in img_use if r["no_attr"]], page_col=None)
    add("img_alt_empty", NOTE, "Картинки", "Картинки с пустым alt",
        "Пустой alt говорит: «картинка декоративная, описывать нечего». Для иконок и фона это правильно, "
        "а для фотографий товаров, схем и людей - упущенная возможность попасть в поиск по картинкам.",
        "Просмотрите список: содержательным картинкам допишите описание, декоративные оставьте как есть.",
        ["Картинка", "На скольких страницах", "Например, здесь"],
        [[r["src"], r["n"], r["ex"]] for r in img_use if r["empty_alt"] and not r["no_attr"]], page_col=None)
    add("img_alt_long", NOTE, "Картинки", "Слишком длинный alt (больше 100 символов)",
        "Alt должен коротко описывать картинку. Длинные описания часто оказываются набором ключевых слов, "
        "а программы для незрячих читают их целиком.",
        "Сократите до одного короткого предложения о том, что изображено.",
        ["Картинка", "Символов", "Alt"],
        [[r["src"], r["alt_len"], r["alt_ex"]] for r in img_use if (r["alt_len"] or 0) > 100], page_col=None)

    def img_row(src):
        return res_info.get(src) or {}
    heavy = []
    for r in img_use:
        i = img_row(r["src"])
        if (i.get("size") or 0) > IMG_HEAVY_KB * KB and (i.get("status") == 200):
            dims = f'{i["img_width"]}×{i["img_height"]}' if i.get("img_width") else "?"
            heavy.append([r["src"], round(i["size"] / KB), i.get("img_format") or "", dims, r["n"], r["ex"]])
    heavy.sort(key=lambda x: -x[1])
    add("img_big", WARN if any(h[1] > IMG_VERY_HEAVY_KB for h in heavy) else NOTE, "Картинки", f"Тяжёлые картинки (больше {IMG_HEAVY_KB} КБ)",
        "Большие картинки замедляют загрузку страницы, особенно с мобильного интернета. Порог 100 КБ - как у Screaming Frog.",
        "Уменьшите картинку до размера, в котором она показывается, и сожмите. Перевод из PNG/JPEG в WebP "
        "обычно уменьшает вес в разы без заметной потери качества. Начните сверху: список отсортирован по весу.",
        ["Картинка", "КБ", "Формат", "Размер, px", "На скольких страницах", "Например, здесь"], heavy, page_col=None)
    old_fmt = [[r["src"], i.get("img_format"), round((i.get("size") or 0) / KB), r["n"]]
               for r in img_use for i in [img_row(r["src"])]
               if i.get("img_format") in ("JPEG", "PNG", "GIF") and (i.get("size") or 0) > IMG_OLD_FORMAT_KB * KB and not r["in_picture"]]
    old_fmt.sort(key=lambda x: -x[2])
    add("img_format", NOTE, "Картинки", "Картинки в старых форматах (JPEG, PNG, GIF) весом больше 50 КБ",
        "Современные форматы WebP и AVIF при том же качестве весят заметно меньше. Их понимают все современные браузеры.",
        "Переведите картинки в WebP (многие CMS и хостинги умеют делать это автоматически). "
        "Картинки внутри <picture>, где уже есть WebP-вариант, в список не попали.",
        ["Картинка", "Формат", "КБ", "На скольких страницах"], old_fmt, page_col=None)
    no_size = [[r["src"], r["n"], r["ex"]] for r in img_use if not r["has_size"]
               and img_row(r["src"]).get("img_format") != "SVG"]
    add("img_no_size", NOTE, "Картинки", "Картинки без указанных размеров (width и height)",
        "Пока картинка грузится, браузер не знает, сколько места под неё оставить, и текст «прыгает». "
        "Google учитывает такие сдвиги в оценке удобства страницы (показатель CLS).",
        "Пропишите у картинок атрибуты width и height (или задайте размеры в CSS через aspect-ratio).",
        ["Картинка", "На скольких страницах", "Например, здесь"], no_size, page_col=None)
    bad_type = []
    for r in img_use:
        i = img_row(r["src"])
        ct = (i.get("content_type") or "")
        if i.get("status") == 200 and ct and not ct.startswith("image/") and ct != "application/octet-stream":
            bad_type.append([r["src"], ct, _bad_type_why(r["src"], ct, r["ex"]), r["n"], r["ex"]])
    add("img_bad_type", WARN, "Картинки", "Вместо картинки сервер отдаёт что-то другое",
        "Адрес картинки отвечает «200 OK», но сервер присылает не изображение (обычно HTML-страницу). "
        "Посетитель видит пустое место или значок сломанной картинки. Что именно пришло и почему - в колонке "
        "«Почему».",
        "Проверьте адрес в браузере и замените картинку на рабочую. Если адрес картинки - главная или сама страница, "
        "обычно у картинки пустой или неверный адрес (src): в шаблоне не подставилась картинка товара или бренда.",
        ["Картинка", "Что пришло (Content-Type)", "Почему", "На скольких страницах", "Например, здесь"], bad_type,
        page_col=None)
    sample = ctx.store.get_meta("ext_files_sample", None) or {}
    add("img_ext_sample", NOTE, "Картинки", "Картинки с других сайтов проверены выборочно",
        "Фото лежат на другом сайте (обычно это хранилище картинок, CDN), и их очень много. Программа проверила "
        "часть фото с каждого такого сайта (сколько - в таблице): битых среди них не нашлось, поэтому остальные не открывала. "
        "Так проверка не тратит часы на тысячи одинаково исправных фото. Если бы нашлась хоть одна битая, "
        "программа проверила бы все.",
        "Ничего делать не нужно. Выводы о весе и формате картинок сделаны по проверенной выборке.",
        ["Сайт с картинками", "Проверено", "Не открывали"],
        [[h, v[0], v[1]] for h, v in sorted(sample.items(), key=lambda x: -x[1][1])], page_col=None)
    # Неправильный размер: картинка намного больше, чем показывается (нужен режим JavaScript)
    disp = _q(db, "SELECT src, MAX(w) AS w, MAX(h) AS h, MIN(page) AS ex FROM img_display GROUP BY src")
    oversized = []
    for d in disp:
        i = img_row(d["src"])
        rw, rh, size = i.get("img_width"), i.get("img_height"), i.get("size") or 0
        if not rw or not rh or i.get("img_format") == "SVG":
            continue
        # запас ×2 на экраны с высокой плотностью пикселей (ретина)
        need = min(1.0, (2 * d["w"] * 2 * d["h"]) / (rw * rh))
        saving = size * (1 - need)
        if rw > 2 * d["w"] and saving >= 4 * KB:
            oversized.append([d["src"], f"{rw}×{rh}", f'{d["w"]}×{d["h"]}', round(size / KB), round(saving / KB), d["ex"]])
    oversized.sort(key=lambda x: -x[4])
    add("img_oversized", NOTE, "Картинки", "Картинки намного больше, чем показываются на экране",
        "Файл картинки в несколько раз больше места, которое она занимает на странице: браузер качает лишнее. "
        "Размер на экране измерен во встроенном браузере (мобильный экран), с запасом ×2 для экранов высокой чёткости.",
        "Подготовьте уменьшенные версии и отдавайте их через srcset - браузер сам выберет подходящую.",
        ["Картинка", "Размер файла, px", "На экране, px", "Весит, КБ", "Можно сэкономить, КБ", "Например, здесь"],
        oversized, page_col=None)

    ctx.KB, ctx.img_row, ctx.res_info = KB, img_row, res_info
