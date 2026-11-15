"""Где лежат файлы программы. Ваши рабочие и личные файлы (доступы, настройки, очередь, уведомления, журнал,
словари, решения семантики, списки сайтов) - в папке «data» рядом с программой, отчёты - в «reports».

Раньше эти папки назывались «data» и «reports», а ещё раньше личные файлы лежали прямо в корне. Всё старое
переносит окно программы при запуске (app.py → migrate), до того как прочитает файлы: папка переименовывается
целиком, а если новая уже есть - сливается по файлам; файл, который уже лежит на новом месте, не заменяется.
Проверка сайта (crawl.py) сама ничего не переносит: пока новой папки нет, она работает со старой.
Автотесты подменяют папки через CLAYLER_DATA_DIR и CLAYLER_REPORTS."""
import glob
import os
import shutil

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # папка программы
# старое русское имя папки → новое (переносит migrate_folders)
RENAMED = {"данные": "data", "отчёты": "reports"}


def _pick(new: str, old: str) -> str:
    """Новая папка, если она есть или старой нет; иначе старая (перенос ещё не делался или не удался)."""
    return old if not os.path.exists(new) and os.path.isdir(old) else new


DATA = os.environ.get("CLAYLER_DATA_DIR") or _pick(os.path.join(APP, "data"), os.path.join(APP, "данные"))


def reports_dir() -> str:
    """Папка проверок: «reports» рядом с программой (или старая «reports», пока не перенесена)."""
    return os.environ.get("CLAYLER_REPORTS") or _pick(os.path.join(APP, "reports"), os.path.join(APP, "отчёты"))


# что лежало в корне программы: старое имя → новое имя в «data»
MOVED = {
    "доступы.json": "доступы.json", "настройки.json": "настройки.json", "бренд.json": "бренд.json",
    "наблюдение.json": "наблюдение.json", "очередь.json": "очередь.json",
    "очередь история.json": "очередь история.json", "избранное.json": "избранное.json",
    "метки сайтов.json": "метки сайтов.json", "метки проблем.json": "метки проблем.json",
    "уведомления.json": "уведомления.json", "журнал программы.txt": "журнал программы.txt",
    "словари семантики.json": "словари семантики.json", "стоп-слова.json": "стоп-слова.json",
    "правила извлечения.json": "правила извлечения.json", "Бренды и прочие.xlsx": "Бренды и прочие.xlsx",
    "иконка.png": "иконка.png", "решения семантики": "решения семантики", "очередь": "списки сайтов",
}
MOVED_GLOBS = ("логотип.*", "доступы.json.испорчен-*")
_OLD = {new: old for old, new in MOVED.items()}


def data(*parts):
    """Путь внутри папки «data». Ещё не перенесено (окно на новом коде не запускалось) - старое место в корне."""
    p = os.path.join(DATA, *parts)
    if os.environ.get("CLAYLER_DATA_DIR") or os.path.exists(p) or not parts or parts[0] not in _OLD:
        return p
    old = os.path.join(APP, _OLD[parts[0]], *parts[1:])
    return old if os.path.exists(old) else p


def _move(src, dst):
    """Файл - если на новом месте его ещё нет; папка - по файлам: «data/списки сайтов» уже есть из git, а свои
    списки из старой «очередь» должны тоже переехать. Новой папки нет - старая переименовывается целиком."""
    if not os.path.exists(src):
        return
    try:
        if os.path.isdir(src) and os.path.isdir(dst):
            for name in os.listdir(src):
                _move(os.path.join(src, name), os.path.join(dst, name))
            if not os.listdir(src):
                os.rmdir(src)
            return
        if os.path.exists(dst):
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
    except OSError:   # файл открыт другой программой - в следующий раз
        pass


def migrate_folders() -> None:
    """Переименовать старые папки «data» → «data», «reports» → «reports» и «reports/archive» → «reports/archive».
    Не вышло (файл открыт другой программой) - программа работает со старой папкой и попробует в следующий раз."""
    global DATA
    for old, new in RENAMED.items():
        env = "CLAYLER_DATA_DIR" if new == "data" else "CLAYLER_REPORTS"
        if os.environ.get(env):   # автотесты подменили папку - настоящую не трогаем
            continue
        _move(os.path.join(APP, old), os.path.join(APP, new))
    reports = reports_dir()
    _move(os.path.join(reports, "архив"), os.path.join(reports, "archive"))
    DATA = os.environ.get("CLAYLER_DATA_DIR") or _pick(os.path.join(APP, "data"), os.path.join(APP, "данные"))


def migrate():
    """Перенести старые папки и старые файлы из корня программы в «data» (уже перенесённое не трогается).
    Зовёт только app.py."""
    migrate_folders()
    if os.environ.get("CLAYLER_DATA_DIR"):
        return
    os.makedirs(DATA, exist_ok=True)
    for old, new in MOVED.items():
        _move(os.path.join(APP, old), os.path.join(DATA, new))
    for pat in MOVED_GLOBS:
        for src in glob.glob(os.path.join(APP, pat)):
            _move(src, os.path.join(DATA, os.path.basename(src)))
