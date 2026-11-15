"""Где лежат файлы программы. Ваши рабочие и личные файлы (доступы, настройки, очередь, уведомления, журнал,
словари, решения семантики, списки сайтов) - в папке «данные» рядом с программой, а не в её корне (28.10.2026:
корень был завален двумя десятками файлов). Отчёты - по-прежнему в «отчёты».

Старые файлы из корня переносит в «данные» окно программы при запуске (app.py → migrate), до того как прочитает
их: файл, который уже лежит в «данные», не заменяется, папки сливаются по файлам. Проверка сайта (crawl.py) сама
ничего не переносит: её может запустить окно на старом коде, которое продолжит писать в корень. Пока файла в
«данные» нет, data() отдаёт его старое место в корне. Автотесты подменяют папку через CLAYLER_DATA_DIR."""
import glob
import os
import shutil

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # папка программы
DATA = os.environ.get("CLAYLER_DATA_DIR") or os.path.join(APP, "данные")

# что лежало в корне программы: старое имя → новое имя в «данные»
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
    """Путь внутри папки «данные». Ещё не перенесено (окно на новом коде не запускалось) - старое место в корне."""
    p = os.path.join(DATA, *parts)
    if os.environ.get("CLAYLER_DATA_DIR") or os.path.exists(p) or not parts or parts[0] not in _OLD:
        return p
    old = os.path.join(APP, _OLD[parts[0]], *parts[1:])
    return old if os.path.exists(old) else p


def _move(src, dst):
    """Файл - если в «данные» его ещё нет; папка - по файлам: «данные/списки сайтов» уже есть из git, а свои списки
    из старой «очередь» должны тоже переехать (проверка кода 28.10.2026)."""
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


def migrate():
    """Перенести старые файлы из корня программы в «данные» (уже перенесённое не трогается). Зовёт только app.py."""
    if os.environ.get("CLAYLER_DATA_DIR"):
        return
    os.makedirs(DATA, exist_ok=True)
    for old, new in MOVED.items():
        _move(os.path.join(APP, old), os.path.join(DATA, new))
    for pat in MOVED_GLOBS:
        for src in glob.glob(os.path.join(APP, pat)):
            _move(src, os.path.join(DATA, os.path.basename(src)))
