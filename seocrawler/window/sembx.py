"""Вкладка «Видимость» на странице «Семантика»: запросы сайта и конкурентов из Букварикса (semantics/bukvarix.py).
Страница: page/sembx.js.
GET  /api/sembx?f=папка                                  - разбор по группам семантики
POST /api/sembx {f, fetch: [домены], region}             - загрузить через бесплатный API Букварикса
POST /api/sembx {f, name, data: base64, domain?, region?} - добавить файл «Анализ домена»
POST /api/sembx {f, remove: домен}                       - убрать домен
POST /api/sembx {f, ads: 1}                              - цена клика в рекламе для запросов сайта (прогноз Директа)"""
import base64
import os
import time

from .semdec import load_semantics


def _out(v):
    (v.get("quick") or {}).get("ads", {}).pop("want", None)   # список для прогноза странице не нужен
    return v


def get(h):
    from ..semantics import bukvarix as B
    full, data = load_semantics(h.query().get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    return h.send(200, _out(B.build(data, data["host"])))


def post(h, body):
    from ..semantics import bukvarix as B
    full, data = load_semantics(body.get("f"))
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    host = data["host"]
    msg = []
    if body.get("ads"):
        from .. import direct
        want = B.build(data, host)["quick"]["ads"]["want"]
        if not want:
            return h.send(400, {"error": "Нечего считать: нет запросов, по которым сайт виден в поиске и известен спрос."})
        n, err = direct.ads(host, data.get("city"), want)
        if err and not n:
            return h.send(400, {"error": err})
        from ..fmt import num
        msg.append(f"цена клика в рекламе, запросов: {num(n)}" + (f" (дальше ошибка: {err})" if err else ""))
    elif body.get("remove"):
        B.remove(host, str(body["remove"]))
    elif body.get("data"):
        name = os.path.basename(str(body.get("name") or "букварикс.csv"))
        try:
            info = B.add_file(host, name, base64.b64decode(body["data"]), str(body.get("domain") or ""),
                              body.get("region") if body.get("region") in B.REGION_NAME else None)
        except Exception as e:
            return h.send(400, {"error": f"Не получилось прочитать «{name}»: {str(e)[:200]}."})
        msg.append(f"{info['domain']}: {info['n']} запросов из файла")
    else:
        region = body.get("region") if body.get("region") in B.REGION_NAME else B.region_of(data.get("city"))
        doms = []
        for d in body.get("fetch") or []:
            d = B.site(d)
            if d and "." in d and d not in doms:
                doms.append(d)
        if not doms:
            return h.send(400, {"error": "Впишите хотя бы один адрес сайта."})
        if len(doms) > 10:
            return h.send(400, {"error": "Не больше 10 сайтов за раз."})
        for i, d in enumerate(doms):
            if i:
                time.sleep(1)   # бесплатный API не любит частых запросов
            try:
                rows = B.fetch(d, region)
            except RuntimeError as e:
                return h.send(400, {"error": str(e) + (". Уже загружены: " + ", ".join(msg) if msg else "") + "."})
            B.put(host, d, region, rows, "Букварикс, загружено из программы")
            msg.append(f"{d}: {len(rows)}")
    out = _out(B.build(data, host))
    out["msg"] = ", ".join(msg)
    return h.send(200, out)
