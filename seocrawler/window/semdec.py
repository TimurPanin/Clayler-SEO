"""Маршруты окна для решений по семантике (semantics/decisions.py): смешанные группы, страницы, которые мешают
друг другу, галочки у задач, «Проверить снова», задачи в Word и Telegram. Страница: page/semdec.js.

GET  /api/semdec?f=папка            — всё о решениях для страницы «Семантика»
GET  /api/semdec/docx?f=папка       — «Задачи разработчику.docx» (собирается заново и отдаётся)
GET  /api/semdec/tree?f=папка       — «дерево сайта.html» (собирается заново и открывается)
GET  /api/semdec/brands?f=папка     — бренды: спрос, страницы, бренд × категория, как пишут (page/sembrand.js)
POST /api/semdec/mixed      {f, group, axis, choice: split|keep|undo, page: адрес|"new"}
POST /api/semdec/landing    {f, group, choice: page|new|keep|undo, page}
POST /api/semdec/junk       {f, groups: [названия], back}
POST /api/semdec/cannibal   {f, key, choice: main|merge|split|ok|undo, main}
POST /api/semdec/done       {f, id, done}
POST /api/semdec/recheck    {f}
POST /api/semdec/telegram   {f, key}"""
import os
from urllib.parse import quote

from . import REPORTS


def load_semantics(folder):
    """(папка проверки, семантика.json с наложенными решениями) по имени папки; данных нет — None."""
    from ..semantics import export as SX, decisions as D, plan
    folder = os.path.basename(folder or "")
    full = os.path.join(REPORTS, folder)
    raw = SX.load(full) if folder else None
    # «запрос → страница» и ТЗ (объём, подзаголовки) - после решений человека
    return full, (plan.enrich(D.apply(raw, full), full) if raw else None)


def view(data):
    from ..semantics import decisions as D, recheck as R
    from .. import telegram
    cfg = telegram._cfg()
    groups = data["groups"]
    return {
        "host": data["decisions"]["host"],
        "telegram": bool(cfg.get("token") and cfg.get("chat_id")),
        "choices": {k: {"label": v[0], "hint": v[1]} for k, v in D.CHOICES.items()},
        "mixed": [dict(g["mixed"], group=i, name=g["name"], page=g.get("page") or "") for i, g in enumerate(groups) if g.get("mixed")],
        "kept": [dict(k, group=i, name=g["name"]) for i, g in enumerate(groups) for k in g.get("mixed_kept") or []],
        "splits": [dict(g["split"], group=i, name=g["name"], page=g.get("page") or "") for i, g in enumerate(groups) if g.get("split")],
        "landing": [dict(g["landing"], group=i, name=g["name"], page=g["page"], mixed=bool(g.get("mixed")))
                    for i, g in enumerate(groups) if g.get("landing")],
        "landing_set": [dict(g["landing_set"], group=i, name=g["name"]) for i, g in enumerate(groups) if g.get("landing_set")],
        "junk": [{"group": i, "name": g["name"], "n": len(g.get("q") or []), "sample": [r[0] for r in (g.get("q") or [])[:3]],
                  "page": g.get("page") or ""} for i, g in enumerate(groups) if g.get("junk")],
        "junk_removed": data.get("junk_removed") or [],
        "cannibal": [{"case": i, **{k: c.get(k) for k in ("key", "title", "why", "main", "pages", "decision", "auto", "task",
                                                         "decided_at")}} for i, c in enumerate(data.get("cannibal") or [])],
        "progress": data["decisions"]["cannibal"],
        "done": data["decisions"]["done"],
        "recheck": data["decisions"]["recheck"],
        "recheck_state": R.status(data["host"]),
        "recheck_pages": len(R.targets(data)),
    }


def get(h, path):
    full, data = load_semantics(h.query().get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    if path == "/api/semdec":
        return h.send(200, view(data))
    if path == "/api/semdec/docx":
        from ..semantics import dev_docx
        try:
            out = dev_docx.write(full, data)
        except OSError:
            return h.send(409, "Не получилось записать файл: наверное, он открыт в Word. Закройте его и нажмите ещё раз.",
                          "text/plain; charset=utf-8")
        if not out:
            return h.send(200, "Задач пока нет: выберите решение хотя бы по одному случаю.", "text/plain; charset=utf-8")
        h.send_response(302)
        h.send_header("Location", f"/r/{quote(os.path.basename(full))}/{quote(dev_docx.FILE)}")
        h.end_headers()
        return
    if path == "/api/semdec/tree":   # дерево сайта и карта признаков (semantics/tree.py) - с учётом решений
        from ..semantics import tree
        try:
            out, _t = tree.write(full, data)
        except OSError:
            return h.send(409, "Не получилось записать файл дерева сайта.", "text/plain; charset=utf-8")
        if not out:
            return h.send(200, "Дерево не из чего строить: в семантике нет страниц.", "text/plain; charset=utf-8")
        h.send_response(302)
        h.send_header("Location", f"/r/{quote(os.path.basename(full))}/{quote(tree.FILE)}")
        h.end_headers()
        return
    if path == "/api/semdec/brands":   # вкладка «Бренды» (semantics/brands.py) - с учётом решений
        from ..semantics import brands
        return h.send(200, brands.view(brands.build(data, full)))
    if path == "/api/semdec/xlsx":   # Excel с учётом решений (semantics/xlsx_dec.py)
        from ..semantics import xlsx_dec
        try:
            xlsx_dec.write(full, data)
        except OSError:
            return h.send(409, "Не получилось записать файл: наверное, он открыт в Excel. Закройте его и нажмите ещё раз.",
                          "text/plain; charset=utf-8")
        h.send_response(302)
        h.send_header("Location", f"/r/{quote(os.path.basename(full))}/{quote(xlsx_dec.FILE)}")
        h.end_headers()
        return
    return h.send(404, {"error": "нет такого действия"})


def post(h, path, body):
    from ..semantics import decisions as D, recheck as R
    full, data = load_semantics(body.get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    host = data["host"]
    act = path[len("/api/semdec/"):]
    err = ""
    if act == "mixed":
        name, axis, choice = str(body.get("group") or ""), body.get("axis"), body.get("choice")
        if axis not in D.AXIS or choice not in ("split", "keep", "undo") or not name:
            return h.send(400, {"error": "Не понял решение по группе."})
        if choice == "split":
            page = str(body.get("page") or "new")
            if page != "new" and not page.startswith(("http://", "https://")):
                return h.send(400, {"error": "Выберите страницу для второй части или «Создать новую страницу»."})
        audit = None   # вторая часть к существующей странице: замечания к ней сразу, по данным проверки
        if choice == "split" and page != "new":
            g = next((x for x in data["groups"] if x["name"] == name), None)
            if g:
                pname, prows = D.other_part(g, axis)
                audit = D.page_audit(full, data, pname, prows, page)

        def fn(d):
            dd = d["mixed"].setdefault(D._gkey(name), {})
            if choice == "undo":
                dd.pop(axis, None)
                if not dd:
                    d["mixed"].pop(D._gkey(name), None)
            else:
                dd[axis] = {"choice": choice, "at": D.now(), "group": name}
                if choice == "split":
                    dd[axis]["page"] = page
                    if audit:
                        dd[axis]["audit"] = audit
        D.update(host, fn)
    elif act == "landing":   # «Похоже, не та страница»: выбрать страницу, «создать новую» или «страница верная»
        name, choice, page = str(body.get("group") or ""), body.get("choice"), str(body.get("page") or "")
        if not name or choice not in ("page", "new", "keep", "undo") or (choice == "page" and not page.startswith(("http://", "https://"))):
            return h.send(400, {"error": "Не понял решение по странице группы."})
        g = next((x for x in data["groups"] if x["name"] == name), None)
        audit = D.page_audit(full, data, name, g.get("q") or [], page) if g and choice == "page" else None

        def fn(d):
            if choice == "undo":
                d["landing"].pop(D._gkey(name), None)
            else:
                d["landing"][D._gkey(name)] = {"choice": choice, "page": page if choice == "page" else "",
                                               "from": (g or {}).get("page") or "", "at": D.now(), "group": name}
                if audit:
                    d["landing"][D._gkey(name)]["audit"] = audit
        D.update(host, fn)
    elif act == "junk":   # «Убрать в отсеянное» группы из текста кнопок и меню (groups: [названия]) или вернуть
        names = [str(x) for x in body.get("groups") or [] if str(x).strip()][:500]
        back = bool(body.get("back"))
        if not names:
            return h.send(400, {"error": "Не выбрано ни одной группы."})

        def fn(d):
            for n in names:
                if back:
                    d["junk"].pop(D._gkey(n), None)
                else:
                    d["junk"][D._gkey(n)] = {"at": D.now(), "group": n}
        D.update(host, fn)
    elif act == "cannibal":
        key, choice = str(body.get("key") or ""), body.get("choice")
        c = D.find_case(data, key)
        if not c or (choice not in D.CHOICES and choice != "undo"):
            return h.send(400, {"error": "Такого случая нет. Обновите страницу."})
        main = body.get("main") if body.get("main") in {p["url"] for p in c["pages"]} else c["main"]

        def fn(d):
            if choice == "undo":
                d["cannibal"].pop(key, None)
            else:
                d["cannibal"][key] = {"choice": choice, "main": main, "at": D.now(), "title": c["title"]}
        D.update(host, fn)
    elif act == "done":
        tid, on = str(body.get("id") or "")[:200], bool(body.get("done"))
        if not tid:
            return h.send(400, {"error": "Нет задачи."})

        def fn(d):
            if on:
                d["done"][tid] = D.now()
            else:
                d["done"].pop(tid, None)
        D.update(host, fn)
    elif act == "recheck":
        err = R.start(data, full)
    elif act == "telegram":
        from .. import telegram
        c = D.find_case(data, str(body.get("key") or ""))
        if not c or not c.get("task"):
            return h.send(400, {"error": "Сначала выберите решение по этому случаю."})
        e = telegram._e
        text = (f"🛠 <b>Задача разработчику</b> · {e(D.site_key(host))}\n<b>{e(c['title'])}</b>\n"
                f"Решение: {e(D.CHOICES[c['decision']][0])}\n\n{e(c['task'])}")
        err = telegram.send(text)
        if err:
            err = "Не отправилось в Telegram: " + err + " Бот настраивается в «Настройках», раздел Telegram."
    else:
        return h.send(404, {"error": "нет такого действия"})
    if err:
        return h.send(400, {"error": err})
    _full, data = load_semantics(body.get("f"))
    return h.send(200, view(data))
