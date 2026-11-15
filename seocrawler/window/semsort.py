"""Вкладка «Разложить» на странице «Семантика»: новые запросы по готовым группам и словари (semantics/assign.py,
semantics/dicts.py). Страница: page/semsort.js.
GET  /api/semsort?f=папка          - последняя раскладка этого сайта
GET  /api/semsort/xlsx?f=папка     - она же в Excel («раскладка запросов.xlsx» в папке проверки)
GET  /api/semsort/dicts            - словари
POST /api/semsort                  {f, text, name, data: base64, gname, gdata: base64} - разложить
POST /api/semsort/dicts            {kind, lines | reset}
GET  /api/semsort/syn?f=папка      - синонимы сайта: тема, пары «похоже на синонимы» (semantics/synonyms.py)
POST /api/semsort/syn              {f, act: niche (niche: код темы | auto) | yes (a, b) | no (a, b)}"""
import base64
import os
from urllib.parse import quote

from .semdec import load_semantics

XLSX = "раскладка запросов.xlsx"
SHOW = 3000   # столько строк отдаём странице, остальное - в Excel


def _host(full, data):
    if data:
        return data["host"]
    return os.path.basename(full).split("_")[0]


def _out(d):
    from ..semantics import assign as A
    if not d:
        return {"rows": [], "summary": None}
    return {"made": d["made"], "source": d.get("source"), "summary": A.summary(d["rows"]), "rows": d["rows"][:SHOW],
            "more": max(0, len(d["rows"]) - SHOW), "names": {"articles": A.ARTICLES, "gallery": A.GALLERY, "none": A.NONE}}


def get(h, path):
    from ..semantics import assign as A, dicts as DI
    if path == "/api/semsort/dicts":
        return h.send(200, {"dicts": DI.load(), "defaults": DI.DEFAULTS})
    full, data = load_semantics(h.query().get("f"))
    if not os.path.basename(full):
        return h.send(404, {"error": "Нет такой проверки."})
    if path == "/api/semsort/syn":
        from ..semantics import synonyms as S
        if not data:
            return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
        return h.send(200, S.view(data))
    d = A.load(_host(full, data))
    if path == "/api/semsort":
        return h.send(200, _out(d))
    if path == "/api/semsort/xlsx":
        if not d:
            return h.send(404, "Запросы ещё не раскладывались.", "text/plain; charset=utf-8")
        try:
            A.write_xlsx(os.path.join(full, XLSX), d, _host(full, data))
        except OSError:
            return h.send(409, "Не получилось записать файл: наверное, он открыт в Excel. Закройте его и нажмите ещё раз.",
                          "text/plain; charset=utf-8")
        h.send_response(302)
        h.send_header("Location", f"/r/{quote(os.path.basename(full))}/{quote(XLSX)}")
        h.end_headers()
        return
    return h.send(404, {"error": "нет такого действия"})


def post(h, path, body):
    from ..semantics import assign as A, dicts as DI
    if path == "/api/semsort/dicts":
        kind = body.get("kind")
        if kind not in DI.KINDS:
            return h.send(400, {"error": "Нет такого словаря."})
        d = DI.reset(kind) if body.get("reset") else DI.save(kind, str(body.get("lines") or "").split("\n"))
        return h.send(200, {"dicts": d})
    full, data = load_semantics(body.get("f"))
    if not os.path.basename(full) or not os.path.isdir(full):
        return h.send(404, {"error": "Нет такой проверки."})
    if path == "/api/semsort/syn":
        return _syn(h, body, data)
    try:
        if body.get("gdata"):
            gname = os.path.basename(str(body.get("gname") or "группы.xlsx"))
            groups, source = A.groups_from_file(gname, base64.b64decode(body["gdata"])), f"из файла «{gname}»"
        elif data:
            groups, source = A.groups_from_semantics(data), "группы собранной семантики"
        else:
            return h.send(400, {"error": "Семантика для этой проверки ещё не собрана. Соберите её или добавьте свой "
                                         "файл с группами (колонки «Группа» и «Запрос»)."})
    except Exception as e:
        return h.send(400, {"error": f"Не получилось прочитать файл с группами: {str(e)[:150]}."})
    try:
        new = A.new_from(str(body.get("text") or ""), os.path.basename(str(body.get("name") or "")),
                         base64.b64decode(body["data"]) if body.get("data") else b"")
    except Exception as e:
        return h.send(400, {"error": f"Не получилось прочитать файл с запросами: {str(e)[:150]}. Подойдут Excel (xlsx), "
                                     "CSV или текстовый файл: запрос в первой колонке."})
    if not new:
        return h.send(400, {"error": "Нет новых запросов: вставьте их списком (по одному в строке) или добавьте файл."})
    if not groups:
        return h.send(400, {"error": "Нет групп, по которым раскладывать."})
    d = A.save(_host(full, data), A.run(groups, new, data=data), source)
    return h.send(200, _out(d))


def _syn(h, body, data):
    """Ответы по синонимам: тема сайта, «да, это одно», «нет» (словарь - semantics/dictionary.py)."""
    from ..semantics import dictionary as D, synonyms as S
    if not data:
        return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
    act = body.get("act")
    a, b = str(body.get("a") or "")[:100], str(body.get("b") or "")[:100]
    try:
        if act == "niche":
            nid = body.get("niche")
            D.set_site(data["host"], None if nid == "auto" else str(nid or ""))
        elif act in ("yes", "no"):
            if not D.norm(a) or not D.norm(b) or D.norm(a) == D.norm(b):
                return h.send(400, {"error": "Не понял пару слов."})
            if act == "yes":
                D.confirm(data, a, b)
            else:
                D.reject(data, a, b)
        else:
            return h.send(400, {"error": "нет такого действия"})
    except ValueError as e:
        return h.send(400, {"error": str(e)})
    _full, data = load_semantics(body.get("f"))
    return h.send(200, S.view(data))
