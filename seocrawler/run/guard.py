"""Один процесс на одну папку проверки и никаких процессов без окна.

Было: пользователь закрыл программу, пока собирался отчёт thehome.ru. crawl.py остался работать без окна (Windows не
закрывает дочерние процессы вместе с родителем), занял 8 ГБ памяти, а новая проверка с «Продолжить прошлую проверку»
пошла по той же папке параллельно.

- watch_parent: проверку запустило окно (есть --stop-file) - раз в несколько секунд смотрим, живо ли оно. Окно
  закрыли - процесс сразу завершается. Всё проверенное уже в базе (SQLite пишет по ходу), «Продолжить прошлую
  проверку» доделает обход, «Обновить отчёт» - отчёт.
- claim: метка в папке «с ней работает процесс N», обновляется раз в HEARTBEAT секунд. Свежая чужая метка -
  папка занята: вторая проверка или сборка отчёта не начинается. Метка старше STALE секунд не считается (процесс
  упал или его закрыли), поэтому номер процесса, доставшийся потом другой программе, ничего не блокирует."""
import atexit
import json
import os
import sys
import threading
import time

LOCK = ".занято.json"
HEARTBEAT = float(os.environ.get("CLAYLER_LOCK_HEARTBEAT") or 30)
STALE = float(os.environ.get("CLAYLER_LOCK_STALE") or 120)
PARENT_CHECK = float(os.environ.get("CLAYLER_PARENT_CHECK") or 5)


def _alive(pid):
    """Работает ли процесс с этим номером. Без сторонних библиотек: в Windows - через WinAPI."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)   # в Windows так нельзя: там os.kill завершает процесс
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(parent=None):
    """Окно закрыли - завершить процесс. parent - номер процесса окна (по умолчанию тот, кто нас запустил)."""
    parent = parent or os.getppid()
    if not _alive(parent):
        return

    def loop():
        while True:
            time.sleep(PARENT_CHECK)
            if not _alive(parent):
                os._exit(3)   # писать некуда: журнал читало закрытое окно
    threading.Thread(target=loop, daemon=True, name="parent-watch").start()


def holder(folder):
    """Номер процесса, который сейчас работает с папкой (свежая чужая метка), или None."""
    path = os.path.join(folder, LOCK)
    try:
        if time.time() - os.path.getmtime(path) > STALE:
            return None
        with open(path, encoding="utf-8") as f:
            pid = int(json.load(f).get("pid") or 0)
    except (OSError, ValueError, AttributeError):
        return None
    return pid if pid and pid != os.getpid() and _alive(pid) else None


def claim(folder, what):
    """Занять папку. False - с ней уже работает другой процесс программы (сообщение напечатано)."""
    other = holder(folder)
    if other:
        print(f"С этой проверкой уже работает другой процесс программы (номер {other}): {os.path.basename(folder)}.")
        print("Дождитесь, пока он закончит, или закройте его в Диспетчере задач (Подробности → python.exe с этим "
              "номером) и запустите снова.")
        return False
    path = os.path.join(folder, LOCK)
    info = {"pid": os.getpid(), "what": what, "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def write():
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False)
        except OSError:
            pass
    write()

    def beat():
        while True:
            time.sleep(HEARTBEAT)
            if not os.path.isdir(folder):
                return
            write()
    threading.Thread(target=beat, daemon=True, name="folder-lock").start()

    def release():
        try:
            with open(path, encoding="utf-8") as f:
                if json.load(f).get("pid") == os.getpid():
                    os.remove(path)
        except (OSError, ValueError):
            pass
    atexit.register(release)
    return True


def busy(folder):
    """Для окна: работает ли с папкой какой-то процесс программы (в том числе оставшийся без окна)."""
    return holder(folder) is not None


if __name__ == "__main__":   # py -3 -m seocrawler.run.guard <папка> - кто занял папку
    print(holder(sys.argv[1]) if len(sys.argv) > 1 else "укажите папку")
