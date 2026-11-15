"""Стили и скрипты."""
from ..common import CRIT, NOTE, _q
from .codes import not_open


def run(ctx):
    KB, add, db, img_row = ctx.KB, ctx.add, ctx.db, ctx.img_row
    res_use = _q(db, "SELECT src, type, COUNT(DISTINCT page) AS n, MIN(page) AS ex FROM resources GROUP BY src, type")
    broken_res = []
    for r in res_use:
        if r["type"] not in ("css", "js", "srcset"):
            continue
        i = img_row(r["src"])
        if i and not_open(i.get("status"), i.get("error"), i.get("location")):   # общее правило (codes.not_open)
            broken_res.append([r["src"], {"css": "стиль (CSS)", "js": "скрипт (JS)",
                                          "srcset": "картинка (вариант в srcset)"}[r["type"]],
                               i.get("status") or i.get("error"), r["n"], r["ex"]])
    add("res_broken", CRIT, "Стили и скрипты", "Не загружаются стили, скрипты или варианты картинок",
        "Страница подключает файл, а он не открывается. Без стилей и скриптов страница может выглядеть сломанной "
        "или часть функций (меню, формы, корзина) не работать. Вариант картинки из srcset браузер выбирает сам "
        "по размеру экрана - на части устройств вместо картинки будет пустое место.",
        "Исправьте адрес файла в шаблоне или верните файл на сервер.",
        ["Файл", "Тип", "Ошибка", "На скольких страницах", "Например, здесь"], broken_res, page_col=None)
    heavy_res = []
    for r in res_use:
        i = img_row(r["src"])
        if r["type"] in ("css", "js") and i.get("status") == 200 and (i.get("size") or 0) > 300 * KB:
            heavy_res.append([r["src"], "CSS" if r["type"] == "css" else "JS", round(i["size"] / KB), r["n"]])
    heavy_res.sort(key=lambda x: -x[2])
    add("res_heavy", NOTE, "Стили и скрипты", "Тяжёлые стили и скрипты (больше 300 КБ)",
        "Большие файлы стилей и скриптов браузер должен скачать и обработать до того, как страница заработает. "
        "Вес указан в том виде, как файл передаётся (со сжатием, если оно включено).",
        "Передайте разработчику: убрать неиспользуемый код, разделить на части, подключать только там, где нужно.",
        ["Файл", "Тип", "КБ", "На скольких страницах"], heavy_res, page_col=None)
    nocomp_res = [[r["src"], "CSS" if r["type"] == "css" else "JS", round((i.get("size") or 0) / KB)]
                  for r in res_use for i in [img_row(r["src"])]
                  if r["type"] in ("css", "js") and i.get("internal") and i.get("status") == 200
                  and not i.get("content_encoding") and (i.get("size") or 0) > 2 * KB]
    add("res_no_compress", NOTE, "Стили и скрипты", "Стили и скрипты без сжатия",
        "Ваш сервер отдаёт файлы стилей и скриптов без сжатия. Текстовые файлы сжимаются в 3–5 раз.",
        "Передайте хостингу или разработчику: включить gzip или brotli для CSS и JS.",
        ["Файл", "Тип", "КБ"], nocomp_res, page_col=None)

