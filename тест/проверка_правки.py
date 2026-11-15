"""Быстрая проверка правки: перед коммитом (git pre-commit) и в конце ответа Claude (хук Stop).

Правила - документы/КАК_ПИСАТЬ_КОД.md. Это не автотест: только то, что проверяется за секунды и без сети,
поэтому не мешает идущей проверке сайта и правилу «тесты пока не делай».

  py -3 тест/проверка_правки.py --коммит   - файлы, которые идут в коммит (вызывает .githooks/pre-commit)
  py -3 тест/проверка_правки.py --ответ    - изменённые, но не закоммиченные файлы (вызывает .claude/settings.json)

Что проверяется:
1. в коммит не попадают личные файлы, отчёты, базы (только --коммит);
2. Python и JavaScript запускаются: нет ошибок в скобках, запятых, отступах (compile, node --check);
3. не добавлено новых «except ...: pass» - ошибка не глотается молча;
4. в добавленных строках кода (не в комментариях) нет длинного тире «—»;
5. правка кода идёт вместе с записью «СДЕЛАНО» в документы/решения/ и строкой в документы/обзор/ (только --коммит);
6. новый или удалённый файл кода - вместе с пересобранными связями обзор/08 (тест/карта_связей.py, только --коммит);
7. в записи «СДЕЛАНО» к правке кода есть строка «Суть: …» - правило «сначала суть» (только --коммит);
8. код не расползается: новая функция не длиннее FUNC_LIMIT строк, старая длинная не растёт больше чем на GROW_LIMIT,
   файл не переходит FILE_LIMIT строк, а уже большой не растёт. Старое не мешает, но расти не даёт;
9. новых строк кода длиннее LINE_LIMIT не больше, чем убрано таких же; новый широкий «except Exception» - только с
   комментарием на той же строке, почему нельзя уже; новая общая функция программы - с подсказками типов.
Нашлось - git не создаёт коммит (код 1), Claude получает список и исправляет (код 2).
"""
import ast
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# одно правило «молча» и одна длина на опись и проверку
from опись_кода import function_sizes, silent_excepts  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVATE_DIRS = ("данные/", "отчёты/", "архив/")
PRIVATE_NAMES = {"доступы.json", "настройки.json", "бренд.json", "наблюдение.json", "очередь.json",
                 "избранное.json", "уведомления.json"}
PRIVATE_ENDS = (".db", ".db-wal", ".db-shm", ".pickle")
CODE_TOP = ("seocrawler/",)
CODE_ROOT_FILES = {"app.py", "crawl.py"}
MAP = "документы/обзор/08-СВЯЗИ_КОДА.md"   # собирается тест/карта_связей.py
FUNC_LIMIT = 80        # строк в функции (цели программы, обзор/09)
FILE_LIMIT = 800       # строк в файле
# на столько может вырасти старая длинная функция: мелкая починка не должна требовать переделки ядра
GROW_LIMIT = 5
LINE_LIMIT = 120       # знаков в строке кода (КАК_ПИСАТЬ_КОД.md, раздел 3)
STOP_LIMIT = 3         # столько раз подряд хук Stop возвращает Claude к работе, потом отпускает
STOP_COUNT = os.path.join(ROOT, ".git", "clayler-stop-count")


def git(*args, binary=False):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=ROOT, capture_output=True)
    if binary:
        return r.stdout if r.returncode == 0 else None
    return r.stdout.decode("utf-8", "replace")


def split_z(text):
    return [p for p in text.split("\0") if p]


def changed_files(mode):
    """Пути (через /) изменённых файлов, которые существуют: в коммите или в рабочей папке."""
    if mode == "commit":
        paths = split_z(git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"))
    else:
        paths = split_z(git("diff", "HEAD", "--name-only", "--diff-filter=ACMR", "-z"))
        paths += split_z(git("ls-files", "--others", "--exclude-standard", "-z"))
    return sorted(set(paths))


def new_text(mode, path):
    if mode == "commit":
        data = git("show", ":" + path, binary=True)
    else:
        try:
            with open(os.path.join(ROOT, path), "rb") as f:
                data = f.read()
        except OSError:
            data = None
    return None if data is None else data.decode("utf-8", "replace")


def old_text(path):
    data = git("show", "HEAD:" + path, binary=True)
    return None if data is None else data.decode("utf-8", "replace")


def added_lines(mode, path, text):
    """Добавленные строки правки (для нового файла - все)."""
    diff = git("diff", *(["--cached"] if mode == "commit" else ["HEAD"]), "-U0", "--", path)
    if not diff.strip():
        return text.splitlines()
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def is_code(path):
    return path.startswith(CODE_TOP) or path in CODE_ROOT_FILES


def check_private(paths):
    bad = [p for p in paths if p.startswith(PRIVATE_DIRS) or os.path.basename(p) in PRIVATE_NAMES
           or p.endswith(PRIVATE_ENDS)]
    return [f"Личный или рабочий файл в коммите: {p} (убрать: git restore --staged \"{p}\")" for p in bad]


def check_python(path, text):
    try:
        compile(text, path, "exec")
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: Python не запустится - {e.msg} (скобка, запятая, отступ?)"], None
    return [], ast.parse(text)


def check_js(path, text):
    with tempfile.TemporaryDirectory() as tmp:
        name = os.path.join(tmp, "check.js")
        with open(name, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            r = subprocess.run(["node", "--check", name], capture_output=True)
        except OSError:
            return []   # Node.js не установлен - проверить нечем
    if r.returncode == 0:
        return []
    lines = [m.strip() for m in r.stderr.decode("utf-8", "replace").replace(name, path).splitlines() if m.strip()]
    where = lines[0] if lines else path                                   # «файл:строка»
    why = next((m for m in lines if "Error" in m), "")                    # «SyntaxError: ...»
    return [f"{where}: JavaScript не запустится - {why or 'ошибка разбора'}"]


def check_silent(path, tree, old):
    before = 0
    if old is not None:
        try:
            before = len(silent_excepts(ast.parse(old))[0])
        except SyntaxError:
            before = 0
    after = silent_excepts(tree)[0]
    if len(after) > before:
        where = ", ".join(str(n) for n in after[:10])
        return [f"{path}: добавлено «except ...: pass» ({before} → {len(after)}; строки {where}) - ошибка не должна "
                "глотаться молча: ловить конкретную ошибку и записать (КАК_ПИСАТЬ_КОД.md, раздел 3)"]
    return []


def parsed(text):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def check_func_size(path, tree, old_text_):
    """Новая функция длиннее предела или старая длинная заметно выросла. old_text_ - файл до правки (None - новый
    файл)."""
    old_tree = parsed(old_text_) if old_text_ else None
    before = function_sizes(old_tree) if old_tree else {}
    out = []
    for name, (size, line) in function_sizes(tree).items():
        was = before.get(name, (0, 0))[0]
        if size > max(was + GROW_LIMIT, FUNC_LIMIT):
            out.append(f"{path}:{line}: функция {name} - {size} строк (было {was}, предел {FUNC_LIMIT}): разбить на "
                       f"части, "
                       "одна функция - одно дело (КАК_ПИСАТЬ_КОД.md, раздел 1)")
    return out


def check_file_size(path, text, old_text_):
    size = len(text.splitlines())
    was = len(old_text_.splitlines()) if old_text_ else 0
    if size > max(was, FILE_LIMIT):
        return [f"{path}: {size} строк (было {was}, предел {FILE_LIMIT}): вынести часть в отдельный файл"]
    return []


def check_line_length(path, added, removed):
    """Новых длинных строк не больше, чем убрано: мелкая правка старой длинной таблицы не мешает."""
    def long_lines(lines):
        return [ln.strip() for ln in lines if len(ln.rstrip()) > LINE_LIMIT]
    new, old = long_lines(added), long_lines(removed)
    fresh = [x for x in new if x not in set(old)]
    extra = len(fresh) - len(set(old) - set(new))
    if extra > 0:
        return [f"{path}: новых строк длиннее {LINE_LIMIT} знаков: {extra}. Перенести: {fresh[0][:80]}"]
    return []


def check_broad_except(path, text, old_text_):
    """Новый «except Exception» без комментария на той же строке. Правило - ловить конкретную ошибку."""
    def broad_lines(source):
        tree = parsed(source) if source else None
        if tree is None:
            return []
        rows = source.splitlines()
        return [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Name)
                and n.type.id == "Exception" and "#" not in rows[n.lineno - 1]]
    now, before = broad_lines(text), broad_lines(old_text_)
    if len(now) > len(before):
        return [f"{path}: новый «except Exception» без комментария (строки {now[:5]}): ловить конкретную ошибку или "
                "написать на этой же строке, почему нельзя (КАК_ПИСАТЬ_КОД.md, раздел 3)"]
    return []


def check_type_hints(path, tree, old_text_):
    """Новая общая функция программы - с подсказками типов. Проверки (run) и окно вызываются по одному образцу: их не
    трогаем."""
    if "/analyze/checks/" in path or "/window/" in path:
        return []
    old_tree = parsed(old_text_) if old_text_ else None
    old = {n.name for n in old_tree.body if isinstance(n, ast.FunctionDef)} if old_tree else set()
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_") and n.name not in old and n.returns is None \
                and not any(a.annotation for a in n.args.args):
            out.append(f"{path}:{n.lineno}: новая функция {n.name} без подсказок типов (КАК_ПИСАТЬ_КОД.md, раздел 3)")
    return out


def removed_lines(mode, path):
    diff = git("diff", *(["--cached"] if mode == "commit" else ["HEAD"]), "-U0", "--", path)
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]


def check_dash(path, lines):
    mark = "#" if path.endswith(".py") else "//"
    bad = [ln.strip() for ln in lines if "—" in ln.split(mark)[0]]
    return [f"{path}: длинное тире «—» в коде (окно и тексты клиенту - только « - »): {ln[:90]}" for ln in bad[:5]]


def check_map(paths):
    """Новый или удалённый файл кода - связи кода (обзор/08) пересобраны в том же коммите."""
    moved = split_z(git("diff", "--cached", "--name-only", "--diff-filter=ADR", "-z"))
    if any(is_code(p) and p.endswith(".py") for p in moved) and MAP not in paths:
        return ["Новый или удалённый файл кода - пересобрать связи: py -3 тест/карта_связей.py и добавить "
                + MAP + " в этот же коммит"]
    return []


def check_essence(paths):
    """Правка кода - в добавленных строках записи решений есть «Суть:» (правило «сначала суть», ИНЖЕНЕРНЫЕ_ПРАВИЛА, 0)."""
    records = [p for p in paths if p.startswith("документы/решения/")]
    if not any(is_code(p) for p in paths) or not records:
        return []   # нет кода - нечего; нет записи - об этом скажет check_records
    added = git("diff", "--cached", "-U0", "--", *records)
    if any(ln.startswith("+") and "Суть:" in ln for ln in added.splitlines()):
        return []
    return ["В записи «СДЕЛАНО» нет строки «Суть: …» - какое общее правило было нарушено и где ещё так же, с фактами "
            "(цифра из базы или строка кода); для новой функции - зачем она и какую задачу решает "
            "(ИНЖЕНЕРНЫЕ_ПРАВИЛА.md, раздел 0)"]


def check_records(paths):
    if not any(is_code(p) for p in paths):
        return []
    out = []
    if not any(p.startswith("документы/решения/") for p in paths):
        out.append("Правка кода без записи «## СДЕЛАНО <дата>: …» в документы/решения/<тема>.md - добавить в этот же коммит")
    if not any(p.startswith("документы/обзор/") for p in paths):
        out.append("Правка кода без строки в документы/обзор/ (сделано / не сделано) - добавить в этот же коммит")
    return out


def run(mode):
    paths = changed_files(mode)
    errors = check_private(paths) if mode == "commit" else []
    for path in paths:
        if not path.endswith((".py", ".js")):
            continue
        text = new_text(mode, path)
        if text is None:
            continue
        old, added = old_text(path), added_lines(mode, path, text)
        if path.endswith(".py"):
            found, tree = check_python(path, text)
            errors += found
            if tree is not None:
                errors += check_silent(path, tree, old)
                if is_code(path):
                    errors += check_func_size(path, tree, old) + check_broad_except(path, text, old)
                    errors += check_type_hints(path, tree, old)
                    errors += check_line_length(path, added, removed_lines(mode, path))
        else:
            errors += check_js(path, text)
        if is_code(path):
            errors += check_dash(path, added) + check_file_size(path, text, old)
    if mode == "commit":
        errors += check_records(paths) + check_essence(paths) + check_map(paths)
    return errors


def stop_counter(reset=False):
    """Сколько раз подряд хук Stop вернул Claude к работе (чтобы не крутиться бесконечно)."""
    if reset:
        if os.path.exists(STOP_COUNT):
            os.remove(STOP_COUNT)
        return 0
    try:
        with open(STOP_COUNT, encoding="utf-8") as f:
            n = int(f.read().strip() or 0) + 1
    except (OSError, ValueError):
        n = 1
    with open(STOP_COUNT, "w", encoding="utf-8") as f:
        f.write(str(n))
    return n


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    mode = "commit" if "--коммит" in sys.argv else "answer"
    errors = run(mode)   # JSON хука Stop на входе не нужен: что проверять, видно по git
    if not errors:
        if mode == "answer":
            stop_counter(reset=True)
        return 0
    text = "Проверка правки (тест/проверка_правки.py) нашла:\n" + "\n".join("- " + e for e in errors)
    if mode == "commit":
        print(text + "\nКоммит не создан. Исправьте и закоммитьте снова (обходить проверку --no-verify нельзя).",
              file=sys.stderr)
        return 1
    if stop_counter() > STOP_LIMIT:
        stop_counter(reset=True)
        print(json.dumps({"systemMessage": text + f"\n(после {STOP_LIMIT} попыток подряд - отпускаю; "
                                                  "исправить нужно до коммита)"}, ensure_ascii=False))
        return 0
    print(text + "\nИсправьте до конца ответа.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
