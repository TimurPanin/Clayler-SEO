"""Вкладка «Спрос» на странице «Семантика»: узнаваемость, местный спрос, сезонность, ВЧ/СЧ/НЧ, что ещё искали,
ёлочка - из Вордстата через Директ (semantics/demand.py). Страница: page/semdemand.js.
GET  /api/semdemand?f=папка                       - всё для вкладки
POST /api/semdemand {f, act: brand|…}             - поставить загрузку в очередь (тратит суточный лимит фраз)
POST /api/semdemand {f, names: {site, text}}      - свои названия сайта для узнаваемости
POST /api/semdemand {f, cancel: 1}                - убрать задания этого сайта из очереди"""
from .semdec import load_semantics


def get(h):
    from ..semantics import demand
    full, data = load_semantics(h.query().get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    return h.send(200, demand.build(data, data["host"], full))


def post(h, body):
    from ..semantics import demand
    full, data = load_semantics(body.get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    host = data["host"]
    if body.get("cancel"):
        err = demand.cancel(host)
    elif isinstance(body.get("names"), dict):
        err = demand.set_names(host, str(body["names"].get("site") or ""), str(body["names"].get("text") or ""))
    else:
        err = demand.start(data, host, str(body.get("act") or ""), full)
    if err:
        return h.send(400, {"error": err})
    return h.send(200, demand.build(data, host, full))
