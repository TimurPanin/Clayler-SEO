"""Автотест: поиск городских версий не тянется часами и слушается «Остановить» (regions.discover).

breez.ru: переключатель со всеми регионами России, программа больше 20 минут угадывала поддомены
по алфавиту, а «Остановить» не срабатывала. Теперь: первые 12 городов подряд не нашлись - поиск заканчивается;
«Остановить» прерывает поиск сразу; окно получает прогресс «город N из M».
Запуск: py -3 tests/проверить_поиск_городов.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seocrawler import regions  # noqa: E402

CITIES = ["Москва", "Адыгея", "Алтайский край", "Амурская область", "Архангельск", "Астрахань", "Белгород", "Брянск",
          "Владимир", "Волгоград", "Вологда", "Воронеж", "Иваново", "Иркутск", "Калининград", "Калуга", "Кемерово",
          "Киров", "Кострома", "Краснодар", "Красноярск", "Курган", "Курск", "Липецк", "Магадан", "Мурманск"]
HTML = ('<html><body><select name="city">' + "".join(
    f'<option{" selected" if c == "Москва" else ""}>{c}</option>' for c in CITIES) + "</select></body></html>")
START = "https://nosuch-clayler-test.invalid/"


def no_dns(host, port):
    raise OSError("нет такого адреса")   # в тесте без сети: настоящий DNS у пользователя отвечает «нет» за 11 с


def main():
    import time
    regions.socket.getaddrinfo = no_dns
    fails = []
    asked = []

    def fetch(u):
        asked.append(u)
        return 404, u

    names = regions.city_names(HTML)
    if len(names) != len(CITIES):
        fails.append(f"города в переключателе: {len(names)} из {len(CITIES)}")
    logs, prog = [], []
    out = regions.discover(START, HTML, [], fetch, log=logs.append, progress=lambda i, n: prog.append((i, n)))
    misses = [ln for ln in logs if "не нашёл его адрес" in ln]
    if out != []:
        fails.append(f"нашлись города, которых нет: {out}")
    if len(misses) != regions.MAX_MISSES:
        fails.append(f"после {regions.MAX_MISSES} промахов поиск не закончился: промахов {len(misses)}")
    if not any("дальше не ищу" in ln for ln in logs):
        fails.append("нет строки, что поиск закончен")
    if not prog or prog[-1][1] != len(CITIES) or prog[-1][0] > regions.MAX_MISSES + 2:
        fails.append(f"прогресс для окна: {prog[-3:]}")
    # «Остановить»: после третьего города поиск прерывается сразу
    logs.clear()
    seen = []
    out = regions.discover(START, HTML, [], fetch, log=logs.append,
                           stop=lambda: len(seen) >= 3, progress=lambda i, n: seen.append(i))
    if out != [] or len(seen) != 3 or not any("прерван" in ln for ln in logs):
        fails.append(f"«Остановить» не прервала поиск: городов {len(seen)}, журнал {logs[-2:]}")
    # город, у которого есть ссылка, сбрасывает счёт промахов и находится
    links = ["https://nosuch-clayler-test.invalid/murmansk/"]
    out = regions.discover(START, HTML.replace("<option>Белгород", "<option>Мурманск2").replace(
        "<option>Мурманск</option>", "").replace("Мурманск2", "Мурманск"), links, fetch, log=lambda s: None)
    if not any(r["city"] == "Мурманск" for r in out):
        fails.append(f"город по ссылке не нашёлся: {out}")
    # медленный DNS: поддомены угадываются не дольше MAX_SECONDS, варианты одного города - разом
    def slow_dns(host, port):
        time.sleep(0.3)
        raise OSError("нет такого адреса")
    regions.socket.getaddrinfo, regions.MAX_SECONDS = slow_dns, 0.5
    logs.clear()
    t0 = time.time()
    regions.discover(START, HTML, [], fetch, log=logs.append)
    took = time.time() - t0
    if not any("только по ссылкам" in ln for ln in logs):
        fails.append("предел времени на угадывание поддоменов не сработал")
    if took > 3:
        fails.append(f"варианты поддомена проверяются по очереди, а не разом: {took:.1f} с")
    if fails:
        print("✗ поиск городов:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("✓ поиск городов: заканчивается после 12 промахов и 3 минут, «Остановить» прерывает сразу, прогресс для окна")


if __name__ == "__main__":
    main()
