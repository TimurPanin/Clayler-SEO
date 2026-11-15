"""Запись JSON-файла «надёжно»: сначала во временный файл рядом (имя.<процесс>-<поток>.json.tmp), потом замена.
Кто читает файл в это время (окно, бот, другая копия программы), не увидит его полузаписанным. Перед заменой
временный файл сбрасывается на диск (fsync): иначе при отключении света Windows может успеть записать замену
имени, но не содержимое, и после включения файл окажется пустым или из нулей (Словарь, настройки, Семантика)."""
import json
import os
import threading
import time


def _write(tmp, data, dump_args):
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, **dump_args)
        f.flush()
        os.fsync(f.fileno())


def load(path):
    """Прочитать JSON-файл; нет файла или он испорчен - пустой словарь."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(path, data, **dump_args):
    """dump_args идут в json.dump как есть (indent, separators); ensure_ascii=False всегда — русский текст как есть."""
    # своё временное имя у каждого потока: два сохранения сразу не мешают друг другу (окно отвечает в нескольких потоках)
    tmp = f"{path}.{os.getpid()}-{threading.get_ident()}.json.tmp"
    _write(tmp, data, dump_args)
    for i in range(20):   # Windows не даёт заменить файл, пока его читает другой поток: подождать чуть-чуть
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.05)
        except FileNotFoundError:   # временный файл уже убран (не должно быть) - записать заново
            if i == 19:
                raise
            _write(tmp, data, dump_args)
