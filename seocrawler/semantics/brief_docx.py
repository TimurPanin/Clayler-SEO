"""ТЗ копирайтеру пачкой: «ТЗ копирайтеру.docx» в папке проверки — по одному заданию на каждую группу, где нужна
работа: сначала новые страницы (красные на карте спроса), потом страницы с замечаниями (жёлтые). В задании —
что сделать, готовые title, H1 и описание, главный запрос, слова для текста, запросы, вопросы для блока
«вопрос - ответ» и страница конкурента для примера. Собирается из семантика.json: при сборе семантики и по
кнопке на странице «Семантика» (тогда и для семантик, собранных раньше)."""
import os

from .. import brand
from ..audit import _para, _run, save_docx

FILE = "ТЗ копирайтеру.docx"
MAX_QUERIES = 15
GREY = "6B6B70"


def _groups(data):
    red = [g for g in data["groups"] if g["kind"] == "create" and g.get("a")]
    yellow = [g for g in data["groups"] if g["kind"] == "page" and g.get("a") and g["a"].get("problems")]
    key = lambda g: -(g.get("score") or 0)  # noqa: E731
    return sorted(red, key=key), sorted(yellow, key=key)


def water_line(now, rival):
    """«норма: вода до 20%, тошнота до 7, академическая до 15%; сейчас: вода 27%, тошнота 8,1, академическая 18%; у конкурента: …»."""
    from .. import settings as S
    from ..textstat import fmt
    line = (f"норма: вода до {S.WATER_MAX}%, тошнота до {fmt(S.NAUSEA_MAX)}, "
            f"академическая до {fmt(S.NAUSEA_ACAD_MAX)}%")
    for label, x in (("сейчас", now or {}), ("у конкурента", rival or {})):
        if x.get("water") is not None:
            line += f"; {label}: вода {fmt(x['water'])}%, тошнота {fmt(x['classic'])}, академическая {fmt(x['academic'])}%"
    return line


def write(folder, data):
    """Возвращает путь к файлу или None, если заданий нет."""
    if data and not any("land" in g for g in data.get("groups") or []):
        from . import plan
        plan.enrich(data, folder)   # адрес новой страницы, объём текста, подзаголовки
    red, yellow = _groups(data)
    if not red and not yellow:
        return None
    body = []
    who = brand.contacts_line()
    if who:
        body.append(_para([_run("Подготовил: ", color=GREY, size=20), _run(who, bold=True, size=20)], 200))
    body += [_para([_run("Технические задания на тексты", bold=True, size=36)], 80),
             _para([_run(f"{data.get('site', '')} · семантика собрана {data.get('made', '')} · новых страниц: {len(red)}, "
                         f"страниц на доработку: {len(yellow)}", color=GREY, size=20)], 200),
             _para([_run("Одно задание - одна страница. Title, H1 и описание - готовые варианты: их можно вставлять как есть "
                         "или поправить по смыслу. Объём - по текстам конкурентов на ту же тему, без меню и подвала. "
                         "Подзаголовки - из того, что люди ищут вместе с темой страницы. Запросы ниже - то, что люди набирают в поиске: главные стоит "
                         "использовать в тексте и подзаголовках, без повторов подряд.", size=20)], 240)]
    n = 0
    for part, items in (("Новые страницы", red), ("Доработать существующие страницы", yellow)):
        if not items:
            continue
        body.append(_para([_run(part, bold=True, size=30)], 160, keep=True))
        for g in items:
            n += 1
            a = g["a"] or {}
            now = a.get("now") or {}
            body.append(_para([_run(f"{n}. {g['name']}", bold=True, size=26)], 60, keep=True))
            body.append(_para([_run("Что сделать: ", color=GREY), _run(g["todo"])], 40, indent=360))
            if g.get("page"):
                body.append(_para([_run("Страница: ", color=GREY), _run(g["page"])], 40, indent=360))
            else:
                land = g.get("land") or {}
                if land.get("url"):
                    body.append(_para([_run("Адрес новой страницы: ", color=GREY), _run(land["url"], bold=True)], 40, indent=360))
                if g.get("near"):
                    body.append(_para([_run("Рядом с: ", color=GREY), _run(g["near"])], 40, indent=360))
            if a.get("main"):
                body.append(_para([_run("Главный запрос: ", color=GREY), _run(a["main"], bold=True)], 40, indent=360))
            for p in a.get("problems") or []:
                body.append(_para([_run("• " + p, size=20)], 20, indent=720))
            for label, key in (("Title", "title"), ("H1", "h1"), ("Описание (description)", "description")):
                if a.get(key):
                    runs = [_run(label + ": ", color=GREY), _run(a[key], bold=True)]
                    if now.get(key) is not None and not a.get("new"):
                        runs.append(_run(f"   (сейчас: {now.get(key) or 'нет'})", color=GREY, size=18))
                    body.append(_para(runs, 40, indent=360))
            words = [a.get("words") or "", ", ".join(a.get("missing") or []), ", ".join(a.get("lsi") or [])]
            if words[0]:
                body.append(_para([_run("Раскрыть в тексте: ", color=GREY), _run(words[0])], 40, indent=360))
            if words[1]:
                body.append(_para([_run("Часто ищут, а в тексте нет: ", color=GREY), _run(words[1])], 40, indent=360))
            if words[2]:
                body.append(_para([_run("Есть у конкурента: ", color=GREY), _run(words[2])], 40, indent=360))
            tz = g.get("tz") or {}
            if tz.get("volume"):
                body.append(_para([_run("Объём текста: ", color=GREY), _run(tz["volume"]["text"])]
                                  + ([_run(f"   (сейчас: {now['words']})", color=GREY, size=18)]
                                     if now.get("words") and not a.get("new") else []), 40, indent=360))
            elif now.get("words") and not a.get("new"):
                body.append(_para([_run(f"Сейчас слов на странице: {now['words']}", color=GREY, size=18)], 40, indent=360))
            wt = water_line(now if not a.get("new") else {}, a.get("rival_text"))
            if wt:
                body.append(_para([_run("Вода и тошнота: ", color=GREY), _run(wt)], 40, indent=360))
            if tz.get("h2"):
                body.append(_para([_run("Подзаголовки (H2): ", color=GREY)], 20, indent=360))
                for h in tz["h2"]:
                    body.append(_para([_run("• " + h, size=20)], 20, indent=720))
            qs = [r[0] for r in g.get("q") or [] if not r[7]][:MAX_QUERIES]
            if qs:
                body.append(_para([_run("Запросы: ", color=GREY), _run(", ".join(qs), size=20)], 40, indent=360))
            if g.get("faq"):
                body.append(_para([_run("Вопросы для блока «вопрос - ответ»: ", color=GREY),
                                   _run("; ".join(g["faq"][:8]), size=20)], 40, indent=360))
            if g.get("rivals"):
                body.append(_para([_run("Пример у конкурента: ", color=GREY), _run(g["rivals"][0], size=20)], 40, indent=360))
            body.append(_para([], 160))
    path = os.path.join(folder, FILE)
    save_docx(path, body)
    return path
