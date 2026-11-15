"""Опись кода: где код не по правилам документы/КАК_ПИСАТЬ_КОД.md (не автотест, только список).

Считает в seocrawler/ (Python) и seocrawler/window/page/ (JavaScript):
- ошибка глотается молча: `except ...:` и сразу `pass` (правило 3 «Ошибки не глотать молча»);
- «голый» `except:` без названия ошибки;
- длинные функции (больше LONG_FUNC строк) и большие файлы (больше BIG_FILE строк);
- очень длинные строки (больше LONG_LINE знаков);
- `var` и `==` в JavaScript окна.

Запуск: py -3 тест/опись_кода.py            - итог и все места
        py -3 тест/опись_кода.py --коротко  - только итог (числа)
Итог переносить в документы/обзор/06-НЕДОЧЁТЫ_КОДА.md, когда числа заметно поменялись.
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = os.path.join(ROOT, "seocrawler")
PAGE = os.path.join(CODE, "window", "page")
LONG_FUNC = 100
BIG_FILE = 800
LONG_LINE = 200


def py_files():
    for top, dirs, files in os.walk(CODE):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(top, name)


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def silent_excepts(tree):
    """Обработчики ошибок, в которых только pass, и «голые» except:."""
    silent, bare = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bare.append(node.lineno)
            if all(isinstance(s, ast.Pass) for s in node.body):
                silent.append(node.lineno)
    return silent, bare


def function_sizes(tree):
    """{полное имя функции: (строк, номер строки)}. Полное - с классом и внешней функцией: Crawler._drain,
    run.follow."""
    out = {}

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                if not isinstance(child, ast.ClassDef):
                    out[name] = (child.end_lineno - child.lineno + 1, child.lineno)
                walk(child, name + ".")
            else:
                walk(child, prefix)
    walk(tree, "")
    return out


def long_functions(tree):
    return [(size, name.rsplit(".", 1)[-1], line) for name, (size, line) in function_sizes(tree).items()
            if size > LONG_FUNC]


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # русские буквы и при выводе в файл
    short = "--коротко" in sys.argv
    silent, bare, funcs, big, lines_total, broken = [], [], [], [], 0, []
    for path in py_files():
        with open(path, encoding="utf-8") as f:
            text = f.read()
        lines = text.splitlines()
        if len(lines) > BIG_FILE:
            big.append((len(lines), rel(path)))
        lines_total += sum(1 for ln in lines if len(ln) > LONG_LINE)
        try:
            tree = ast.parse(text)
        except SyntaxError as e:   # такой файл не запустится - это главное в описи
            broken.append(f"{rel(path)}:{e.lineno} {e.msg}")
            continue
        s, b = silent_excepts(tree)
        silent += [f"{rel(path)}:{n}" for n in s]
        bare += [f"{rel(path)}:{n}" for n in b]
        funcs += [(size, f"{rel(path)}:{line} {name}") for size, name, line in long_functions(tree)]

    js_var, js_eq, js_big = [], [], []
    for name in sorted(os.listdir(PAGE)):
        if not name.endswith(".js"):
            continue
        path = os.path.join(PAGE, name)
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        if len(lines) > BIG_FILE:
            js_big.append((len(lines), rel(path)))
        for i, ln in enumerate(lines, 1):
            code = re.sub(r"[!=]=\s*null\b", "", ln.split("//")[0])   # «x != null» - обычный приём: нет значения
            if re.search(r"\bvar\s", code):
                js_var.append(f"{rel(path)}:{i}")
            if re.search(r"[^=!<>]==[^=]|!=[^=]", code):
                js_eq.append(f"{rel(path)}:{i}")

    funcs.sort(reverse=True)
    big = sorted(big + js_big, reverse=True)
    print("Опись кода (правила - документы/КАК_ПИСАТЬ_КОД.md)")
    print(f"  файлы Python, которые не разбираются (синтаксис): {len(broken)}")
    print(f"  ошибка глотается молча (except: pass): {len(silent)}")
    print(f"  «голый» except: {len(bare)}")
    print(f"  функции длиннее {LONG_FUNC} строк: {len(funcs)}")
    print(f"  файлы длиннее {BIG_FILE} строк: {len(big)}")
    print(f"  строки длиннее {LONG_LINE} знаков (Python): {lines_total}")
    print(f"  JavaScript: var - {len(js_var)}, == или != - {len(js_eq)}")
    if short:
        return
    for title, items in (("Не разбираются", broken), ("Ошибка глотается молча", silent), ("«Голый» except", bare)):
        if items:
            print(f"\n{title}:")
            for x in items:
                print("  " + x)
    if funcs:
        print(f"\nФункции длиннее {LONG_FUNC} строк (строк, место):")
        for size, where in funcs:
            print(f"  {size:4}  {where}")
    if big:
        print(f"\nФайлы длиннее {BIG_FILE} строк:")
        for size, where in big:
            print(f"  {size:5}  {where}")
    for title, items in (("JavaScript: var", js_var), ("JavaScript: == или !=", js_eq)):
        if items:
            print(f"\n{title} ({len(items)}):")
            for x in items[:40]:
                print("  " + x)
            if len(items) > 40:
                print(f"  ... и ещё {len(items) - 40}")


if __name__ == "__main__":
    main()
