"""Автотест картинки паутины для клиента (seocrawler/web_cover.py): одна и та же у одного сайта, цифра
здоровья и счётчики на месте, красные участки - только когда есть ошибки, картинка попадает в аудит (и демо) и в
отчёт для клиента, PNG - в папку «для клиента». Без браузера: сам PNG рисует Chrome или Edge и проверяется руками."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seocrawler import web_cover as C, client_folder  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


summary = {"health": 73, "pages": 1234, "by_status": [{"s": "200", "n": 1000}, {"s": "301", "n": 30},
                                                       {"s": "404", "n": 5}, {"s": "нет ответа", "n": 2}]}
check(C.counts(summary) == (7, 30), f"счётчики {C.counts(summary)}")
a = C.svg("https://www.site.ru/", 73, 1234, 7, 30, "04.10.2026")
b = C.svg("https://site.ru/page", 73, 1234, 7, 30, "04.10.2026")
check(a == C.svg("https://www.site.ru/", 73, 1234, 7, 30, "04.10.2026"), "картинка у одного сайта разная")
check(a != C.svg("https://other.ru/", 73, 1234, 7, 30, "04.10.2026"), "у разных сайтов одна и та же паутина")
check(b.count("#ff5f6e") > 0 and b.count("#ffc45a") > 0, "нет красных или жёлтых участков")
clean = C.svg("https://site.ru/", 100, 50, 0, 0, "")
check("#ff5f6e" not in clean and "#ffc45a" not in clean, "участки при сайте без ошибок")
check(">73%<" in a and "1 234" in a and "site.ru<" in a and "www.site.ru" not in a, "цифра здоровья, страницы или сайт")
check("data:image/png;base64," in a, "нет паучка")
check("—" not in a and "рограмм" not in a, "длинное тире или «программа» в картинке")
check(C.health_color(95) != C.health_color(75) != C.health_color(40), "цвет здоровья")
check(any(src == C.FILE for src, _ in client_folder.FILES), "картинки нет в папке «для клиента»")
# подпись в круге крупная, светлая и по центру круга (05.10: была мелкая, серая и ниже центра)
import re  # noqa: E402
cap = re.search(r'<text[^>]*font-size="(\d+)"[^>]*fill="(#[0-9a-f]+)">здоровье сайта<', a)
check(cap and int(cap.group(1)) >= 22 and cap.group(2) in ("#ffffff", "#f2f6ff"), "подпись «здоровье сайта» мелкая или тусклая")
cy = float(re.search(r'<circle cx="[\d.]+" cy="([\d.]+)" r="104"', a).group(1))
ys = [float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)"[^>]*>(?:73%|здоровье сайта)<', a)]
check(len(ys) == 2 and abs((ys[0] - 52 + ys[1] + 5) / 2 - cy) < 8, f"цифра и подпись не по центру круга: {ys}, центр {cy}")
# <style> внутри SVG действует на всю страницу: график здоровья не должен перекрашивать круг и подписи паутины
from seocrawler import compare  # noqa: E402
ch = compare._chart([("2026-09-01 10:00:00", 40), ("2026-10-01 10:00:00", 60)])
for sel in re.findall(r'([^{}]+)\{', re.search(r"<style>(.*?)</style>", ch).group(1)):
    check(sel.strip().startswith(".hchart"), f"в графике здоровья стиль на всю страницу: {sel}")

here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seocrawler")
for f, need in (("audit.py", "web_cover.for_report(meta, summary, demo=demo)"),
                ("report.py", "web_cover.for_report(meta, summary) if client")):
    with open(os.path.join(here, f), encoding="utf-8") as fh:
        check(need in fh.read(), f"{f}: картинки нет на первой странице")

if fails:
    print("ОШИБКИ в картинке паутины:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("✓ картинка паутины: одна у сайта, здоровье, ошибки, в аудите и в папке для клиента")
