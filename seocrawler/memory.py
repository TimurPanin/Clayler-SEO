"""Сколько памяти компьютера осталось. Без сторонних библиотек.

Ошибка «не хватило памяти» (MemoryError) в Windows бывает, когда кончается не сама оперативная память, а «предел
выделения»: оперативная память плюс файл подкачки (на компьютере пользователя 38 ГБ). Поэтому смотрим именно его -
сколько ещё можно выделить всем программам вместе. Обход dom-primer.ru упал так через 17 часов."""
import os
import time

# Осталось меньше - обход останавливается сам, как по кнопке «Остановить» (crawler/main_loop.low_memory)
MIN_FREE_MB = int(os.environ.get("CLAYLER_MIN_FREE_MB") or 1500)


def free_mb():
    """Сколько МБ ещё можно выделить (Windows: предел выделения; Linux: MemAvailable). None - узнать не удалось."""
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None
            return st.ullAvailPageFile // 2**20   # «PageFile» здесь - весь предел выделения, а не только файл
        except Exception:
            return None
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return None


def is_low():
    """(мало ли памяти, сколько свободно МБ)."""
    free = free_mb()
    return free is not None and free < MIN_FREE_MB, free


# ---------- сборка отчёта: при обходе память смотрит main_loop.low_memory, а сборка
# отчёта шла без присмотра - 01.11 при обновлении отчёта dom-primer.ru свободно было ~3 ГБ, сборка брала 5+ ГБ
class LowMemory(BaseException):
    """Памяти почти не осталось - сборку отчёта останавливаем сами, а не ждём MemoryError посреди записи файлов.
    BaseException, как Ctrl+C: шаги сборки с «except Exception - написать и идти дальше» (сравнение, страна, снимки)
    её не глотают, и сборка действительно останавливается."""

    def __init__(self, free):
        super().__init__(f"мало памяти: можно занять ещё {free} МБ")
        self.free = free


_GUARD_AT = [0.0]
ARMED = [False]   # включает run/build.build_report: анализ зовут и окно, и «Семантика» - там останавливаться нельзя


def guard(every=5.0):
    """Раз в every с смотрим память (вызывать часто можно: между замерами - одно сравнение времени). Только во время
    сборки отчёта (ARMED). Мало - LowMemory (run/build.build_report → run/cli.build_safely: подсказка и выход)."""
    if not ARMED[0]:
        return
    now = time.monotonic()
    if now - _GUARD_AT[0] < every:
        return
    _GUARD_AT[0] = now
    low, free = is_low()
    if low:
        raise LowMemory(free)


def build_stopped_text(free=None):
    """Что написать, если сборку отчёта остановили из-за памяти. «нехватка памяти» - чтобы окно и Telegram показали
    понятную ошибку (plain_errors)."""
    free = free_mb() if free is None else free
    left = f" (можно занять ещё {free} МБ)" if free is not None else ""
    return (f"\nНехватка памяти: компьютеру почти не осталось памяти{left} - сборку отчёта остановил, пока она не "
            "упала. Проверка сохранена, обходить сайт заново не нужно, но файлы отчёта могли обновиться не все. "
            "Закройте лишние программы и вкладки браузера и нажмите «⋯ → Обновить отчёт».")


# ---------- ресурсы проверки для окна программы: сколько памяти у самой программы и у её браузера,
# сколько свободно и как загружен процессор. Раньше это приходилось смотреть в Диспетчере задач.
LAST = {}   # последний замер - его кладут в файл состояния проверки (crawler/base.st, run/build.status)
ON_SAMPLE = None   # что сделать после замера (run/build.build_report: переписать файл состояния)


def _win_tree(root_pid):
    """[(pid, имя файла процесса)] - процесс и все его потомки (браузер Playwright и его драйвер, процессы расчёта
    на нескольких ядрах). Только Windows."""
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k = ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k.CreateToolhelp32Snapshot(2, 0)   # TH32CS_SNAPPROCESS
    kids, names = {}, {}
    try:
        e = PE()
        e.dwSize = ctypes.sizeof(PE)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            kids.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            names[e.th32ProcessID] = e.szExeFile.lower()
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    out, todo, seen = [], [root_pid], set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        out.append((p, names.get(p, "")))
        todo.extend(c for c in kids.get(p, ()) if c not in (0, p))
    return out


def _win_proc(pid):
    """(своя память процесса в МБ, время процессора в секундах) или None."""
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                           "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                           "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                           "PrivateUsage")]
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000 | 0x0010, False, pid)   # QUERY_LIMITED_INFORMATION | VM_READ
    if not h:
        return None
    try:
        m = PMC()
        m.cb = ctypes.sizeof(PMC)
        if not k.K32GetProcessMemoryInfo(h, ctypes.byref(m), m.cb):
            return None
        t = [wintypes.FILETIME() for _ in range(4)]
        k.GetProcessTimes(h, *[ctypes.byref(x) for x in t])
        cpu = sum((x.dwHighDateTime << 32 | x.dwLowDateTime) for x in t[2:]) / 1e7   # ядро + пользователь
        return m.PrivateUsage / 2**20, cpu
    finally:
        k.CloseHandle(h)


def _win_system_times():
    """(простой, всего) процессора всего компьютера в секундах с начала работы Windows."""
    import ctypes
    from ctypes import wintypes
    t = [wintypes.FILETIME() for _ in range(3)]
    ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(x) for x in t])
    idle, kern, user = ((x.dwHighDateTime << 32 | x.dwLowDateTime) / 1e7 for x in t)
    return idle, kern + user   # время ядра включает простой


def cpu_busy(seconds=0.5):
    """Насколько занят процессор всего компьютера сейчас, % (замер за seconds). None - не Windows или не вышло."""
    if os.name != "nt":
        return None
    try:
        import time
        i1, t1 = _win_system_times()
        time.sleep(seconds)
        i2, t2 = _win_system_times()
        return round(100 * (1 - (i2 - i1) / (t2 - t1))) if t2 > t1 else None
    except Exception:
        return None


class Sampler:
    """Замер ресурсов: sample() - {prog_mb, browser_mb, free_mb, cpu, prog_cpu}. Процессор - доля всего компьютера
    (100% - все ядра заняты) за время с прошлого замера: у всего компьютера (cpu) и у программы с браузером
    (prog_cpu). Не Windows - только свободная память."""

    def __init__(self, pid=None):
        self.pid = pid or os.getpid()
        self.prev = None

    def sample(self):
        out = {"free_mb": free_mb()}
        if os.name != "nt":
            return out
        try:
            import time
            mine = browser = cpu_used = 0.0
            for p, name in _win_tree(self.pid):
                r = _win_proc(p)
                if r:
                    # сама программа и её процессы расчёта (python) - «программа», остальное (chrome, node) - браузер
                    if p == self.pid or name.startswith("python"):
                        mine += r[0]
                    else:
                        browser += r[0]
                    cpu_used += r[1]
            idle, total = _win_system_times()
            now = time.time()
            out.update(prog_mb=round(mine), browser_mb=round(browser))
            if self.prev:
                p_idle, p_total, p_used, p_now = self.prev
                if total > p_total:
                    out["cpu"] = round(100 * (1 - (idle - p_idle) / (total - p_total)))
                if now > p_now:
                    n = os.cpu_count() or 1
                    out["prog_cpu"] = max(0, min(100, round(100 * (cpu_used - p_used) / (now - p_now) / n)))
            self.prev = (idle, total, cpu_used, now)
        except Exception:
            pass
        return out


def start_sampling(every=5.0):
    """Фоновый замер раз в every секунд в LAST (проверку запустило окно программы)."""
    import threading
    import time
    s = Sampler()

    def loop():
        global LAST
        while True:
            LAST = s.sample()   # новый словарь целиком: читатели не увидят его наполовину заполненным
            if ON_SAMPLE:   # сборка отчёта: этап идёт минутами - свежие цифры в файл состояния сразу
                try:
                    ON_SAMPLE()
                except Exception:
                    pass
            time.sleep(every)
    threading.Thread(target=loop, daemon=True, name="resources").start()
