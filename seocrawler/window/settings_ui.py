"""«Пороги и проверки» в окне программы: пороги из settings.py и включение/выключение проверок.
Изменения пишутся в «настройки.json» в папке «data»; действуют на новые проверки и на «Обновить отчёт»."""
import ast
import glob
import os
import re

from .. import settings

CHECKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analyze", "checks")
SEV = {"CRIT": "критично", "WARN": "предупреждение", "NOTE": "замечание"}
TITLES = {"cert_expiry": "Сертификат HTTPS истёк или скоро истечёт",
          "domain_expiry": "Оплата домена закончилась или скоро закончится"}  # где название собирается из частей


def _text(node, consts, vals):
    """Строка из кода проверки: обычная, f-строка ({TITLE_LONG} → значение порога, остальное → «N»), склейка
    строк или имя константы файла (CAT = "Что мешает покупать")."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id, "")
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                out.append(str(v.value))
                continue
            name = v.value.id if isinstance(v.value, ast.Name) else ""
            x = vals.get(name) if name.isupper() else consts.get(name)   # строчное имя - переменная цикла (_adds)
            spec = "".join(str(c.value) for c in v.format_spec.values) if v.format_spec else ""   # {NEAR_DUP:.0%}
            try:
                out.append(format(x, spec) if x is not None else "N")
            except (TypeError, ValueError):
                out.append(str(x))
        return "".join(out)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):   # f"…{x:.1f} МБ".replace(".", ",")
        return _text(node.func.value, consts, vals)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _text(node.left, consts, vals) + _text(node.right, consts, vals)
    return ""


def _adds(tree):
    """Вызовы add(ключ, важность, раздел, название, …) в файле проверки: (вызов, ключ, {переменная цикла: значение}).
    Ключ - строка или собирается в цикле по списку или словарю файла: f"counter_{key}_missing" для каждого счётчика
    из NAMES, key из (("lab_lcp", "lcp"), …). Раньше такие проверки (счётчики на части страниц, скорость на телефоне)
    в «Пороги и проверки» не попадали, и выключить их было нельзя.
    Название из словаря файла по ключу (TEXT[key] = (название, …)) - в переменной цикла ""."""
    dicts = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
            try:
                val = ast.literal_eval(n.value)
            except ValueError:
                continue
            dicts.update({t.id: val for t in n.targets if isinstance(t, ast.Name)})
    parent = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "add"
                and len(n.args) >= 4):
            continue
        k = n.args[0]
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            yield n, k.value, {}
            continue
        p = parent.get(n)
        while p is not None and not isinstance(p, ast.For):
            p = parent.get(p)
        if p is None:
            continue
        it = p.iter
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and it.func.attr == "items"                 and isinstance(it.func.value, ast.Name) and it.func.value.id in dicts:
            rows = list(dicts[it.func.value.id].items())
        else:
            try:
                rows = list(ast.literal_eval(it))
            except ValueError:
                continue
        names = [x.id for x in (p.target.elts if isinstance(p.target, ast.Tuple) else [p.target])
                 if isinstance(x, ast.Name)]
        for row in rows:
            row = row if isinstance(row, tuple) else (row,)
            if len(row) != len(names):
                continue
            loop = {a: b for a, b in zip(names, row) if isinstance(b, str)}
            key = _text(k, loop, {})
            if not key or "N" in key:
                continue
            for d in dicts.values():   # TEXT[key] = (название, пояснение, что сделать)
                if isinstance(d.get(key), tuple) and d[key] and isinstance(d[key][0], str):
                    loop[""] = d[key][0]
            yield n, key, loop


def catalog():
    """Все проблемы, которые умеет находить программа: ключ, название, раздел, важность — из файлов проверок.
    Код проверок разбирается через ast, а не регулярным выражением: регулярное сбивалось на разделе-константе (CAT у
    «Что мешает покупать» - на экране у 26 проверок вместо названия стоял кусок пояснения) и на кавычках в условии
    важности, а две проверки (buy_copyright, server_versions) пропадали: на экране было 190 вместо 192."""
    seen, out = set(), []
    vals = dict(settings.DEFAULTS, **settings.load_user())
    for path in sorted(glob.glob(os.path.join(CHECKS_DIR, "*.py"))):
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except SyntaxError:
            continue
        consts = {t.id: n.value.value for n in tree.body
                  if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
                  for t in n.targets if isinstance(t, ast.Name)}
        for n, key, loop in _adds(tree):
            if key in seen or not re.fullmatch(r"[a-z0-9_]+", key):
                continue
            seen.add(key)
            # «WARN if … else NOTE» → «предупреждение или замечание»
            sev = " или ".join(dict.fromkeys(SEV[w] for w in re.findall(r"\b(CRIT|WARN|NOTE)\b", ast.unparse(n.args[1]))))
            title = TITLES.get(key) or _text(n.args[3], dict(consts, **loop), vals).strip() or loop.get("", "")
            out.append({"key": key, "title": title, "category": _text(n.args[2], consts, vals), "severity": sev})
    out.sort(key=lambda x: (x["category"], x["title"]))
    return out


def current():
    user = settings.load_user()
    val = lambda k: user.get(k, settings.DEFAULTS[k])
    off = set(val("DISABLED"))
    return {
        "thresholds": [{"name": n, "label": label, "unit": unit, "value": val(n), "default": settings.DEFAULTS[n]}
                       for n, label, unit in settings.UI],
        "checks": [dict(c, off=c["key"] in off) for c in catalog()],
        "file": settings.USER_FILE,
    }


def save(data):
    """data: {"thresholds": {имя: число}, "disabled": [ключи]}. Возвращает текст ошибки или ""."""
    out = {}
    names = {n for n, _, _ in settings.UI}
    for k, v in (data.get("thresholds") or {}).items():
        if k not in names:
            continue
        try:
            v = float(str(v).replace(",", "."))
        except ValueError:
            return f"Не число: {v}"
        if v < 0 or (v == 0 and k not in settings.ZERO_OK):
            return "Пороги должны быть больше нуля."
        d = settings.DEFAULTS[k]
        out[k] = v if isinstance(d, float) else int(round(v))
    known = {c["key"] for c in catalog()}
    out["DISABLED"] = sorted(k for k in (data.get("disabled") or []) if k in known)
    try:
        settings.save_user(out)
    except OSError as e:
        return "Не получилось сохранить: " + str(e)[:120]
    return ""
