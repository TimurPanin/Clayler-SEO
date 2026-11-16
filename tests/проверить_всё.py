"""Автотесты: поднимает тестовые сайты, проверяет каждый программой и сверяет найденные проблемы с эталоном.

Запуск:  python tests/проверить_всё.py            - проверить
         python tests/проверить_всё.py --обновить  - записать текущий результат как новый эталон
         (только если отличия ожидаемые: добавили проверку, поменяли текст)
Эталоны лежат в tests/эталоны/<сайт>.txt: «проблема ; количество» по строке.
Отчёты тестов пишутся во временную папку, «reports» не засоряются."""
import csv
import glob
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ETALON = os.path.join(HERE, "эталоны")
# сайт, порт, дополнительные флаги
SITES = [("testsite", 8765, []), ("imgsite", 8767, []), ("htmlsite", 8768, []), ("checksite", 8769, []),
         ("citysite", 8770, ["--regions"]), ("jssite", 8766, ["--js"]),
         ("httpssite", 8771, [])]


def wait_up(port, sec=15, scheme="http"):
    import ssl
    # без прокси VPN: через него 127.0.0.1 отвечал 502, и неподнятый тестовый сайт считался готовым
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    for _ in range(sec * 10):
        try:
            direct.open(f"{scheme}://127.0.0.1:{port}/", timeout=1)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.1)
    return False


def problems(folder):
    rows = list(csv.reader(open(os.path.join(folder, "проблемы.csv"), encoding="utf-8-sig"), delimiter=";"))
    return [f"{r[2]} ; {r[3]}" for r in rows[1:]]


def main():
    update = "--обновить" in sys.argv or "--update" in sys.argv
    os.makedirs(ETALON, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", CLAYLER_NO_USER_SETTINGS="1",
               CLAYLER_NO_SPELLER="1", CLAYLER_NO_PDF="1",
               CLAYLER_NO_SPEED_LAB="1")
    tmp = tempfile.mkdtemp(prefix="clayler-test-")
    env["CLAYLER_REPORTS"] = tmp
    failed = 0
    for name, port, flags in SITES:
        srv = subprocess.Popen([sys.executable, os.path.join(HERE, f"{name}.py"), str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            scheme = "https" if name == "httpssite" else "http"   # https-сайт с самоподписанным сертификатом
            if not wait_up(port, scheme=scheme):
                print(f"✗ {name}: тестовый сайт не запустился (порт {port} занят?)")
                failed += 1
                continue
            t0 = time.time()
            r = subprocess.run([sys.executable, os.path.join(ROOT, "crawl.py"), f"{scheme}://127.0.0.1:{port}/",
                                "--no-open", "--delay", "0"] + flags, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300)
            folders = sorted(glob.glob(os.path.join(tmp, f"127.0.0.1_{port}_*")))
            if r.returncode != 0 or not folders or not os.path.exists(os.path.join(folders[-1], "проблемы.csv")):
                print(f"✗ {name}: программа завершилась с ошибкой\n" + (r.stdout + r.stderr)[-1500:])
                failed += 1
                continue
            got = problems(folders[-1])
            sys.path.insert(0, ROOT)
            from seocrawler import client_report
            cpath = os.path.join(folders[-1], client_report.FILE)
            left = client_report.leftovers(open(cpath, encoding="utf-8").read()) if os.path.exists(cpath) else ["нет файла"]
            if left:
                failed += 1
                print(f"✗ {name}: в отчёте для клиента остались служебные фразы:\n   " + "\n   ".join(left[:10]))
            if name == "htmlsite":  # снимки с обведённой ошибкой (страница шире экрана, H1) — и внутри отчёта клиента
                shots = glob.glob(os.path.join(folders[-1], "снимки ошибок", "*.jpg"))
                doc = open(cpath, encoding="utf-8").read() if os.path.exists(cpath) else ""
                if len(shots) < 2 or "Ошибки на снимках" not in doc or 'src="снимки ошибок/' in doc:
                    failed += 1
                    print(f"✗ {name}: снимков с обведённой ошибкой {len(shots)}, в отчёте для клиента "
                          + ("есть" if "Ошибки на снимках" in doc else "нет") + " раздела «Ошибки на снимках»")
            path = os.path.join(ETALON, f"{name}.txt")
            if update or not os.path.exists(path):
                open(path, "w", encoding="utf-8", newline="\n").write("\n".join(sorted(got)) + "\n")
                print(f"• {name}: эталон записан ({len(got)} проблем), {time.time() - t0:.0f} с")
                continue
            want = [x for x in open(path, encoding="utf-8").read().splitlines() if x.strip()]
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            if not missing and not extra:
                print(f"✓ {name}: всё совпало ({len(got)} проблем), {time.time() - t0:.0f} с")
            else:
                failed += 1
                print(f"✗ {name}: отличия от эталона")
                for x in missing:
                    print("   было в эталоне, теперь нет:  " + x)
                for x in extra:
                    print("   появилось, в эталоне нет:    " + x)
        finally:
            srv.terminate()
    for script in ("проверить_вход.py", "проверить_города.py", "проверить_телеграм.py", "проверить_наблюдение.py",
                   "проверить_список.py", "проверить_разделы.py", "проверить_фото_cdn.py", "проверить_скорость_обхода.py", "проверить_сбои_сайта.py", "проверить_причину_обрыва.py", "проверить_страну.py", "проверить_понятные_ошибки.py", "проверить_баги_раздела1.py","проверить_перелинковку_семантики.py","проверить_решения.py",
                   "проверить_тексты.py", "проверить_файлы_разработчика.py", "проверить_ложные_находки.py",
                   "проверить_сравнение.py", "проверить_безопасность.py", "проверить_платформы.py", "проверить_видео.py", "проверить_узел_паутины.py", "проверить_картинку_паутины.py", "проверить_смету.py",
                   "проверить_план_семантики.py", "проверить_импорт_семантики.py", "проверить_раскладку.py", "проверить_новый_сайт.py", "проверить_дерево.py", "проверить_слова.py", "проверить_бренды.py", "проверить_бренды_сайта.py", "проверить_логотипы.py", "проверить_букварикс.py", "проверить_директ.py", "проверить_спрос.py", "проверить_обновления.py", "проверить_формы.py", "проверить_города_семантики.py", "проверить_синонимы.py", "проверить_маски.py", "проверить_модели.py", "проверить_карточку.py",
                   "проверить_параллельно.py", "проверить_очередь.py", "проверить_очередь_семантики.py", "проверить_поиск_городов.py", "проверить_водность.py", "проверить_адреса_поиска.py", "проверить_непроверенное.py", "проверить_покупку.py", "проверить_цены_по_карте.py", "проверить_кнопки_покупки.py", "проверить_согласие.py",
                   "проверить_снимки_телефона.py", "проверить_увеличение_снимков.py", "проверить_здоровье.py", "проверить_редкие_проверки.py", "проверить_темы_семантики.py", "проверить_короткие_маски.py",
                   "проверить_смену_сайта_семантики.py", "проверить_повтор_семантики.py", "проверить_повтор_отчёта.py", "проверить_уведомления.py",
                   "проверить_взлом.py", "проверить_клиентов.py", "проверить_пороги.py", "проверить_копию_сайта.py", "проверить_повтор_5xx.py", "проверить_надёжность_загрузки.py", "проверить_сторож.py", "проверить_коды_ответа.py", "проверить_закон_сохранения.py", "проверить_полноту.py", "проверить_сертификат_и_опечатки.py",
                   "проверить_адреса_как_на_сайте.py", "проверить_здоровье_по_частям.py", "проверить_запрос_страница.py", "проверить_время_ответа.py", "проверить_мёртвый_прокси.py", "проверить_извлечение.py", "проверить_hreflang.py", "проверить_подсветку.py", "проверить_советы_движка.py", "проверить_утечки.py", "проверить_коллтрекинг.py", "проверить_перенос_строки.py", "проверить_крошки.py", "проверить_разметку_цены.py","проверить_папку_данные.py", "проверить_закрытую_навигацию.py", "проверить_число_страниц_окна.py", "проверить_ход_проверки.py", "проверить_дочитывание.py", "проверить_любой_адрес.py", "проверить_modx.py", "проверить_правку.py", "проверить_испорченные_данные.py", "проверить_память_браузера.py", "проверить_одну_папку.py", "проверить_скорость_разбора.py", "проверить_мало_памяти.py", "проверить_ядра_анализа.py", "проверить_ресурсы.py", "проверить_excel.py",
                   "проверить_мелкие_функции.py"):
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        print((r.stdout + r.stderr).strip())
        failed += r.returncode != 0
    print("\nИТОГ: " + ("всё в порядке" if not failed else f"отличий - {failed}. Если они ожидаемые: "
                        "python tests/проверить_всё.py --обновить"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
