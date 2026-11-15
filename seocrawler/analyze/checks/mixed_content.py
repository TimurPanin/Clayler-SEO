"""Смешанный контент: https-страница грузит файлы по http."""
from ..common import CRIT, WARN, _q


def run(ctx):
    add, db = ctx.add, ctx.db
    mixed_rows = _q(db, """SELECT DISTINCT src AS page, dst, kind FROM links
        WHERE kind IN ('img','srcset','css','js','iframe') AND src LIKE 'https://%' AND dst LIKE 'http://%'""")
    kind_ru = {"img": "картинка", "srcset": "картинка", "css": "стиль (CSS)", "js": "скрипт (JS)", "iframe": "встроенный фрейм"}
    active = [r for r in mixed_rows if r["kind"] in ("css", "js", "iframe")]
    passive = [r for r in mixed_rows if r["kind"] in ("img", "srcset")]
    add("mixed_active", CRIT, "Безопасность", "Смешанный контент: скрипты и стили по http:// на https-странице",
        "Страница открыта по защищённому https, а скрипты, стили или фреймы подключены по незащищённому http. "
        "Браузеры такие файлы блокируют - страница может сломаться.",
        "Замените http:// на https:// в адресах этих файлов.",
        ["Страница", "Файл", "Тип"], [[r["page"], r["dst"], kind_ru[r["kind"]]] for r in active])
    add("mixed_passive", WARN, "Безопасность", "Смешанный контент: картинки по http:// на https-странице",
        "Страница открыта по https, а картинки подключены по http. Браузер пытается загрузить их по https "
        "или показывает предупреждение, что соединение защищено не полностью.",
        "Замените http:// на https:// в адресах картинок.",
        ["Страница", "Картинка"], [[r["page"], r["dst"]] for r in passive])

