"""Вкладка «Обновления» на странице «Семантика»: даты обновлений Google и Яндекса на графиках сайта и «Что просело»
(semantics/updates.py). Страница: page/semupd.js.
GET  /api/semupd?f=папка                             - всё для вкладки (из файлов, без загрузки)
POST /api/semupd {f, load: 1}                        - загрузить даты обновлений и данные сайта по дням заново
POST /api/semupd {f, compare: "ГГГГ-ММ-ДД"}           - «Что просело»: до и после даты
POST /api/semupd {f, add: {date, name, src}}         - своя дата встряски Яндекса
POST /api/semupd {f, remove: id}                     - убрать дату встряски"""
from .semdec import load_semantics


def get(h):
    from ..semantics import updates as U
    full, data = load_semantics(h.query().get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    return h.send(200, U.build(data, full))


def post(h, body):
    from ..semantics import updates as U
    full, data = load_semantics(body.get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    if body.get("compare"):
        _res, err = U.compare(data, full, str(body["compare"]), data["site"])
        if err:
            return h.send(400, {"error": err})
    elif isinstance(body.get("add"), dict):
        a = body["add"]
        err = U.manual_add(str(a.get("date") or ""), str(a.get("name") or ""), str(a.get("src") or ""))
        if err:
            return h.send(400, {"error": err})
    elif body.get("remove"):
        U.manual_del(str(body["remove"]))
    return h.send(200, U.build(data, full, load=bool(body.get("load"))))
