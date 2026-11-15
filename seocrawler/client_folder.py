"""Папка «для клиента» внутри папки проверки: файлы (отчёт, PDF, Excel, смета), которые отправляют клиенту, с понятными именами,
чтобы не искать их среди служебных таблиц: полный отчёт (HTML), аудит в PDF и таблица Excel.
Заполняется в конце сборки отчёта (и при «Обновить отчёт»); у старых проверок — при первом открытии папки."""
import os
import shutil
from urllib.parse import urlsplit

DIR = "для клиента"
PREFIX = "SEO-аудит "
# файл проверки → окончание имени в папке для клиента
FILES = [("отчёт_для_клиента.html", " - полный отчёт.html"),
         ("аудит.pdf", ".pdf"),
         ("отчёт.xlsx", " - таблица.xlsx"),
         ("паутина.png", " - паутина сайта.png"),  # обложка для Авито и Kwork (web_cover.py)
         ("смета.pdf", " - смета и план работ.pdf"),
         ("смета.xlsx", " - смета.xlsx")]
# «Отчёт за месяц» (monthly.py) кладётся сюда кнопкой на экране «Клиенты», а не сборкой отчёта: fill() его не стирает
MONTHLY_TAIL = " - отчёт за месяц.html"


def _host(site):
    h = (urlsplit(site or "").hostname or "").lower()
    return (h[4:] if h.startswith("www.") else h) or "сайта"


def has_files(out_dir):
    return any(os.path.exists(os.path.join(out_dir, src)) for src, _ in FILES)


def fill(out_dir, site, check=False):
    """Копирует свежие файлы; старые копии (прошлая сборка) заменяются. Возвращает (путь к папке, ошибки)."""
    folder = os.path.join(out_dir, DIR)
    errors = []
    if not has_files(out_dir):
        return folder, errors
    os.makedirs(folder, exist_ok=True)
    want = set()
    for src, tail in FILES:
        p = os.path.join(out_dir, src)
        if not os.path.exists(p):
            continue
        name = PREFIX + _host(site) + tail
        want.add(name)
        try:
            shutil.copy2(p, os.path.join(folder, name))
        except OSError:
            errors.append(name)  # открыт у пользователя (Excel держит файл) — оставляем прошлую копию
    for f in os.listdir(folder):  # копии от прошлого адреса сайта или файлы, которых больше нет
        if f.startswith(PREFIX) and f not in want and not f.endswith(MONTHLY_TAIL):
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass
    for f, what in (leaks(folder) if check else []):   # сторож - при сборке отчёта (check), не при открытии папки
        print(f"ВНИМАНИЕ: в файле для клиента «{f}» есть {what} - проверьте перед отправкой.")
    return folder, errors


# что не должно уйти клиенту: ключи и токены доступа, пути к папкам на компьютере, служебные файлы программы
LEAKS = [("токен Яндекса", r"\by0_[A-Za-z0-9_-]{20,}|\bAQAAAA[A-Za-z0-9_-]{20,}"),
         ("токен Google", r"\bya29\.[A-Za-z0-9_.-]{20,}|\b1//0[A-Za-z0-9_-]{20,}"),
         ("токен Telegram-бота", r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}"),
         ("ключ API", r"\bsk-[A-Za-z0-9]{20,}|\bAIza[0-9A-Za-z_-]{30,}"),
         ("путь к папке на компьютере", r"\b[A-Za-z]:\\+(?:Users|Clayler)\b|\\AppData\\"),
         ("имя служебного файла программы", r"\bcrawl\.db\b|доступы\.json|настройки\.json|бренд\.json")]


def leaks(folder):
    """[(файл, что нашлось)] в текстовых файлах папки для клиента и в Excel/Word (они - zip с XML). PDF не читаем:
    он собирается из того же HTML."""
    import re
    import zipfile
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            p = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            try:
                if ext in (".html", ".htm", ".csv", ".txt", ".xml", ".conf", ".json"):
                    texts = [open(p, encoding="utf-8", errors="replace").read()]
                elif ext in (".xlsx", ".docx"):
                    with zipfile.ZipFile(p) as z:
                        texts = [z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith(".xml")]
                else:
                    continue
            except Exception:   # битый или зашифрованный файл - сторож не мешает сборке
                continue
            texts = [re.sub(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+", "", t) for t in texts]   # картинки внутри HTML
            for what, rx in LEAKS:
                if any(re.search(rx, t) for t in texts):
                    out.append((os.path.relpath(p, folder), what))
    return out
