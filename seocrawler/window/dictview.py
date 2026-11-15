"""Страница «Словарь» (page/dictionary.html, dictionary.js; логика - semantics/dictionary.py).

GET  /dictionary                   - страница
GET  /api/dict                     - темы, правила с метками и срабатываниями, сайты и их темы
GET  /api/dict/export              - весь словарь файлом «Словарь Clayler SEO.json»
GET  /api/dict/suggest?f=папка     - пары «похоже на синонимы» сайта (как на вкладке «Разложить новые»)
POST /api/dict  {act, ...}:
     add (node, kind, line) | remove (node, kind, line) | edit (node, kind, old, line) | move (node, kind, line, to)
     reset (node, kind) | node_add (name, parent) | node_rename (node, name) | node_delete (node)
     site (host, node | "auto") | import (data) | yes / no (f, a, b, node?)"""
import json
import time
from urllib.parse import quote


def get(h, path):
    from ..semantics import dictionary as D
    if path == "/api/dict":
        return h.send(200, D.view())
    if path == "/api/dict/export":
        body = json.dumps(D.export(), ensure_ascii=False, indent=1).encode("utf-8")
        name = f"Словарь Clayler SEO {time.strftime('%d.%m.%Y')}.json"
        h.send_response(200)
        h.send_header("Content-Type", "application/json; charset=utf-8")
        h.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(body)
        return
    if path == "/api/dict/suggest":
        from ..semantics import synonyms as S
        from .semdec import load_semantics
        full, data = load_semantics(h.query().get("f"))
        if not data:
            return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
        return h.send(200, S.view_cached(full, data))
    return h.send(404, {"error": "нет такого действия"})


def post(h, body):
    from ..semantics import dictionary as D
    act = body.get("act")
    s = lambda k: str(body.get(k) or "")[:2000]
    try:
        if act == "add":
            for line in s("line").split("\n"):
                if line.strip():
                    D.add(s("node"), _kind(s("kind")), line)
        elif act == "remove":
            D.remove(s("node"), _kind(s("kind")), s("line"))
        elif act == "edit":
            D.edit(s("node"), _kind(s("kind")), s("old"), s("line"))
        elif act == "move":
            D.move(s("node"), _kind(s("kind")), s("line"), s("to"))
        elif act == "reset":
            D.reset(s("node"), _kind(s("kind")))
        elif act == "node_add":
            D.add_node(s("name"), s("parent"))
        elif act == "node_rename":
            D.rename_node(s("node"), s("name"))
        elif act == "node_delete":
            D.delete_node(s("node"))
        elif act == "site":
            D.set_site(s("host"), None if s("node") == "auto" else s("node"))
        elif act == "import":
            n = D.import_(body.get("data"))
            return h.send(200, dict(D.view(), msg=f"Добавлено строк: {n}."))
        elif act in ("yes", "no", "yes_many", "no_many"):
            # «Да» / «Нет» на одну пару или пачкой (отмеченные галочками): [{a, b, node}]
            from ..semantics import synonyms as S
            from .semdec import load_semantics
            full, data = load_semantics(s("f"))
            if not data:
                return h.send(404, {"error": "Семантика для этой проверки ещё не собрана."})
            many = act.endswith("_many")
            pairs = body.get("pairs") if many else [{"a": s("a"), "b": s("b"), "node": s("node")}]
            pairs = [p for p in pairs or [] if isinstance(p, dict) and D.norm(p.get("a")) and D.norm(p.get("b"))][:200]
            if not pairs:
                return h.send(400, {"error": "Не понял пару слов." if not many else "Отметьте хотя бы одну пару."})
            for p in pairs:
                a, b = str(p["a"])[:200], str(p["b"])[:200]
                if act.startswith("yes"):
                    D.confirm(data, a, b, str(p.get("node") or "") or None)
                else:
                    D.reject(data, a, b)
            full, data = load_semantics(s("f"))
            return h.send(200, dict(S.view_cached(full, data), done=len(pairs)))
        else:
            return h.send(400, {"error": "нет такого действия"})
    except ValueError as e:
        return h.send(400, {"error": str(e)})
    return h.send(200, D.view())


def _kind(k):
    from ..semantics import dictionary as D
    if k not in D.KIND:
        raise ValueError("Нет такого вида.")
    return k
