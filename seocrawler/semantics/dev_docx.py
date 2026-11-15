"""«Скачать все задачи (Word)»: задачи разработчику по страницам, которые мешают друг другу, одним файлом
«Задачи разработчику.docx» в папке проверки. В файл попадают случаи, по которым человек выбрал решение
(кроме «Не проблема»); текст задачи тот же, что на странице и в Telegram (decisions.task_text)."""
import os

from .. import brand
from ..audit import _para, _run, save_docx
from .decisions import CHOICES, _short

FILE = "Задачи разработчику.docx"
GREY = "6B6B70"


def write(folder, data):
    """data — семантика с наложенными решениями. Возвращает путь к файлу или None, если задач нет."""
    cases = [c for c in data.get("cannibal") or [] if c.get("decision") and c["decision"] != "ok" and c.get("task")]
    if not cases:
        return None
    body = []
    who = brand.contacts_line()
    if who:
        body.append(_para([_run("Подготовил: ", color=GREY, size=20), _run(who, bold=True, size=20)], 200))
    body += [_para([_run("Задачи разработчику", bold=True, size=36)], 80),
             _para([_run(f"{data.get('site', '')} · страницы, которые мешают друг другу в поиске · задач: {len(cases)}",
                         color=GREY, size=20)], 200),
             _para([_run("По одним и тем же запросам на сайте было несколько страниц: поиск не понимает, какую "
                         "показывать, и все стоят ниже. По каждому случаю уже выбрано решение, ниже что сделать.",
                         size=20)], 240)]
    for n, c in enumerate(cases, 1):
        body.append(_para([_run(f"{n}. {c.get('title') or ''}", bold=True, size=26)], 60, keep=True))
        body.append(_para([_run("Решение: ", color=GREY), _run(CHOICES[c["decision"]][0], bold=True)], 40, indent=360))
        body.append(_para([_run("Страницы: ", color=GREY),
                           _run(", ".join(_short(p["url"]) + (" (главная)" if p["url"] == c["main"] and c["decision"] in ("main", "merge") else "")
                                          for p in c["pages"]))], 40, indent=360))
        for line in c["task"].split("\n"):
            body.append(_para([_run(line)], 40, indent=360))
        body.append(_para([], 160))
    path = os.path.join(folder, FILE)
    save_docx(path, body)
    return path
