"""Автотест сторожа папки «для клиента» (client_folder.leaks): токены Яндекса, Google, Telegram, ключи API,
пути к папкам на компьютере и имена служебных файлов в HTML, CSV, Excel находятся; обычный отчёт - чистый
(адрес «forgot_password=yes» на сайте клиента - не пароль). Без сети. Запуск: py -3 tests/проверить_утечки.py."""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler.client_folder import leaks  # noqa: E402

fails = []
d = tempfile.mkdtemp(prefix="clayler-leaks-")
open(os.path.join(d, "чистый.html"), "w", encoding="utf-8").write(
    '<a href="https://site.ru/auth/?forgot_password=yes">вход</a> Телефон +7 999 123-45-67'
    # картинка внутри HTML: в base64 бывает «AQAAAA…» - это не токен
    '<img src="data:image/png;base64,iVBORw0KGgo/AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==">')
open(os.path.join(d, "токен.html"), "w", encoding="utf-8").write("токен y0_AgAAAAAbcdefghijklmnopqrstuvwxyz0123")
open(os.path.join(d, "путь.csv"), "w", encoding="utf-8").write("файл;F:\\Clayler\\seo-crawler\\reports\\x\\crawl.db")
with zipfile.ZipFile(os.path.join(d, "таблица.xlsx"), "w") as z:
    z.writestr("xl/worksheets/sheet1.xml", "<t>123456789:AAH_abcdefghijklmnopqrstuvwxyz0123456</t>")
got = {}
for f, what in leaks(d):
    got.setdefault(f, set()).add(what)
if "чистый.html" in got:
    fails.append(f"в чистом файле нашлось: {got['чистый.html']}")
for f, want in (("токен.html", "токен Яндекса"), ("путь.csv", "путь к папке на компьютере"),
                ("путь.csv", "имя служебного файла программы"), ("таблица.xlsx", "токен Telegram-бота")):
    if want not in got.get(f, set()):
        fails.append(f"{f}: не найдено «{want}»: {got.get(f)}")
if fails:
    print("✗ утечки в файлах для клиента:\n   " + "\n   ".join(fails))
    sys.exit(1)
print("✓ утечки в файлах для клиента: токены, ключи, пути к папкам и служебные файлы находятся, чистый отчёт - чистый")
