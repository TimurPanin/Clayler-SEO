"""Карта связей кода: кто кого импортирует (не автотест).

Читает импорты всех файлов seocrawler/, app.py и crawl.py разбором кода (ast) и пишет
notes/обзор/08-СВЯЗИ_КОДА.md: части программы, какие части каждая использует, кто использует её,
и для каждого файла - его связи. Файл 08 руками не править: пересобрать этим скриптом.

Запуск: py -3 tests/карта_связей.py           - пересобрать 08-СВЯЗИ_КОДА.md
        py -3 tests/карта_связей.py <модуль>  - связи одного файла в окно, например: crawler.page
Пересобирать после нового файла кода или переноса функций между файлами (правило - CLAUDE.md, «Как работать»).
"""
import ast
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = os.path.join(ROOT, "seocrawler")
OUT = os.path.join(ROOT, "notes", "обзор", "08-СВЯЗИ_КОДА.md")
PART = {   # часть программы по папке или файлу; остальное в корне seocrawler - «общие и отчёты»
    "window": "окно", "run": "запуск проверки", "crawler": "обход", "analyze": "анализ",
    "semantics": "Семантика",
}


def modules():
    """{имя модуля: путь}: crawler.page, window.server, app, crawl …"""
    out = {}
    for top, dirs, files in os.walk(CODE):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                rel = os.path.relpath(os.path.join(top, name), CODE)[:-3].replace(os.sep, ".")
                out[rel[:-9] if rel.endswith(".__init__") else rel] = os.path.join(top, name)
    out.pop("__init__", None)
    out[""] = os.path.join(CODE, "__init__.py")   # сам пакет seocrawler
    for name in ("app", "crawl"):
        out["<" + name + ".py>"] = os.path.join(ROOT, name + ".py")
    return out


def package_of(mod, path):
    """Пакет, относительно которого считаются импорты «from . import x»."""
    if mod.startswith("<"):
        return None
    return mod if path.endswith("__init__.py") else mod.rpartition(".")[0]


def resolve(target, known):
    """Самое длинное известное имя модуля для target (x.y.z → x.y, если z - функция)."""
    while target and target not in known:
        target = target.rpartition(".")[0]
    return target if target in known else None


def imports_of(mod, path, known):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    pkg = package_of(mod, path)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "seocrawler" or a.name.startswith("seocrawler."):
                    found.add(resolve(a.name.removeprefix("seocrawler").lstrip("."), known))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:   # from . import x / from ..y import z - от пакета этого файла
            base = [p for p in (pkg or "").split(".") if p]
            base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
            head = ".".join(base + ([node.module] if node.module else []))
        elif node.module == "seocrawler" or (node.module or "").startswith("seocrawler."):
            head = node.module.removeprefix("seocrawler").lstrip(".")
        else:
            continue     # чужой модуль (json, openpyxl …)
        for a in node.names:
            full = f"{head}.{a.name}" if head else a.name
            # модуль (from . import fmt) или значение из модуля (from .common import Issue → analyze.common)
            r = full if full in known else resolve(head, known)
            found.add(r)
    found.discard(None)
    found.discard(mod)
    return found


def part(mod):
    if mod.startswith("<"):
        return "запуск (корень)"
    if mod == "":
        return "общие и отчёты"
    return PART.get(mod.split(".")[0], "общие и отчёты")


def label(mod):
    return mod if mod else "seocrawler (__init__)"


def build():
    known = modules()
    uses = {m: imports_of(m, p, known) for m, p in known.items()}
    used_by = defaultdict(set)
    for m, targets in uses.items():
        for t in targets:
            used_by[t].add(m)
    return known, uses, used_by


def write_md(known, uses, used_by):
    parts = defaultdict(lambda: defaultdict(int))
    for m, targets in uses.items():
        for t in targets:
            if part(m) != part(t):
                parts[part(m)][part(t)] += 1
    lines = [
        "# Связи кода: кто кого использует (собрано скриптом)",
        "",
        "Собрано `py -3 tests/карта_связей.py` разбором импортов. **Руками не править** - пересобрать скриптом.",
        "Зачем и как части работают вместе - [07-КАРТА_СВЯЗЕЙ.md](07-КАРТА_СВЯЗЕЙ.md). Импорт внутри функции тоже",
        "считается связью. Имена - без `seocrawler.`: `crawler.page` = `seocrawler/crawler/page.py`.",
        "",
        f"Файлов кода: {len(known)}.",
        "",
        "## Части программы: какая часть какую использует (число импортов)",
        "",
        "| Часть | Использует |",
        "|---|---|",
    ]
    for p in sorted(parts):
        lines.append(f"| {p} | " + ", ".join(f"{t} ({n})" for t, n in sorted(parts[p].items(), key=lambda x: -x[1])) + " |")
    lines += ["", "## Самые связанные файлы (правка задевает многих - запускать больше тестов)", "",
              "| Файл | Используют его | Он использует |", "|---|---|---|"]
    top = sorted(known, key=lambda m: -len(used_by[m]))[:20]
    for m in top:
        lines.append(f"| `{label(m)}` | {len(used_by[m])} | {len(uses[m])} |")
    lines += ["", "## Каждый файл: что использует и кто использует его", ""]
    for p in sorted({part(m) for m in known}):
        lines += [f"### {p}", "", "| Файл | Использует | Используют его |", "|---|---|---|"]
        for m in sorted(m for m in known if part(m) == p):
            a = ", ".join(f"`{label(x)}`" for x in sorted(uses[m])) or "-"
            b = ", ".join(f"`{label(x)}`" for x in sorted(used_by[m])) or "-"
            lines.append(f"| `{label(m)}` | {a} | {b} |")
        lines.append("")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    known, uses, used_by = build()
    if len(sys.argv) > 1:
        m = sys.argv[1].removeprefix("seocrawler.").removesuffix(".py").replace("/", ".")
        if m not in known:
            print("Нет такого файла кода: " + sys.argv[1])
            return 1
        print(f"{label(m)} ({part(m)})")
        print("  использует: " + (", ".join(sorted(map(label, uses[m]))) or "-"))
        print("  используют его: " + (", ".join(sorted(map(label, used_by[m]))) or "-"))
        return 0
    write_md(known, uses, used_by)
    print(f"Записано: {os.path.relpath(OUT, ROOT)} ({len(known)} файлов кода)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
