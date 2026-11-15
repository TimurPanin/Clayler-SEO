"""Автотест правил хука tests/проверка_правки.py: размер кода, длина строк, широкие ошибки, подсказки типов.
Без git и без сети. Запуск: py -3 tests/проверить_правку.py"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from проверка_правки import (FILE_LIMIT, FUNC_LIMIT, GROW_LIMIT, LINE_LIMIT, check_broad_except,  # noqa: E402
                             check_file_size, check_func_size, check_line_length, check_type_hints)

fails = []


def func(name, lines, indent=""):
    return indent + f"def {name}():\n" + "".join(f"{indent}    x = {i}\n" for i in range(lines - 1))


def check(old, new, want, what):
    got = check_func_size("a.py", ast.parse(new), old)
    if bool(got) != want:
        fails.append(f"{what}: {got}")


check(None, func("short", FUNC_LIMIT), False, "новая на пределе")
check(None, func("long", FUNC_LIMIT + 1), True, "новая длиннее предела")
check(func("f", 50), func("f", FUNC_LIMIT + 1), True, "короткая выросла за предел")
check(func("f", 200), func("f", 200), False, "старая длинная не менялась")
check(func("f", 200), func("f", 200 + GROW_LIMIT), False, "мелкая починка старой длинной")
check(func("f", 200), func("f", 200 + GROW_LIMIT + 1), True, "старая длинная заметно выросла")
check(func("f", 200), func("f", 150), False, "старая длинная стала короче")
check(func("f", 200), func("g", 200), True, "переименованная длинная считается новой")
check(None, "class A:\n" + func("m", FUNC_LIMIT + 1, "    "), True, "длинный метод класса")
check(None, "def out():\n" + func("inner", FUNC_LIMIT + 1, "    "), True, "длинная вложенная функция")

text = "x = 1\n"
if check_file_size("a.py", text * FILE_LIMIT, None):
    fails.append("файл на пределе")
if not check_file_size("a.py", text * (FILE_LIMIT + 1), text * FILE_LIMIT):
    fails.append("файл перешёл предел")
if check_file_size("a.py", text * 1000, text * 1000):
    fails.append("старый большой файл не менялся")
if not check_file_size("a.py", text * 1001, text * 1000):
    fails.append("старый большой файл вырос")

long_line = "x" * (LINE_LIMIT + 1)
if not check_line_length("a.py", [long_line], []):
    fails.append("новая длинная строка")
if check_line_length("a.py", ["x" * LINE_LIMIT], []):
    fails.append("строка на пределе")
if check_line_length("a.py", [long_line + "y"], [long_line]):
    fails.append("правка старой длинной строки (таблицы) не должна мешать")

TRY = "try:\n    x()\nexcept Exception{}:\n    y()\n"
if not check_broad_except("a.py", TRY.format(""), None):
    fails.append("новый широкий except без комментария")
if check_broad_except("a.py", TRY.format(":  # почему") .replace("Exception::", "Exception:"), None):
    fails.append("широкий except с комментарием")
if check_broad_except("a.py", TRY.format(""), TRY.format("")):
    fails.append("старый широкий except не мешает")

if not check_type_hints("seocrawler/a.py", ast.parse("def f(x):\n    pass\n"), None):
    fails.append("новая общая функция без типов")
if check_type_hints("seocrawler/a.py", ast.parse("def f(x: int) -> int:\n    return x\n"), None):
    fails.append("функция с типами")
if check_type_hints("seocrawler/a.py", ast.parse("def _f(x):\n    pass\n"), None):
    fails.append("внутренняя функция")
if check_type_hints("seocrawler/analyze/checks/a.py", ast.parse("def run(ctx):\n    pass\n"), None):
    fails.append("проверка run")
if check_type_hints("seocrawler/a.py", ast.parse("def f(x):\n    pass\n"), "def f(x):\n    pass\n"):
    fails.append("старая функция не мешает")

if fails:
    print("✗ правила размера кода:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ правила хука: длинная функция, рост файла, длинная строка, широкий except и новая функция без типов не "
      "проходят, старое не мешает")
