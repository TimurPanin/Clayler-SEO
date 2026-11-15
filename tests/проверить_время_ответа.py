"""Блок «Как быстро отвечает сервер» (report.speed_html) и столбцы «Индексируются / Закрыты» в «По разделам сайта»
(audit.sections_html): полоски по интервалам, медиана и среднее, второй замер у перемеренных, цвет
по порогу, старые проверки без новых полей. Без сети и тестового сайта.
Запуск: py -3 tests/проверить_время_ответа.py (и из проверить_всё.py)."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("CLAYLER_NO_USER_SETTINGS", "1")

from seocrawler import report  # noqa: E402
from seocrawler.audit import sections_html  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def page(i, t, recheck=None, status=200, ctype="text/html"):
    return {"url": f"https://x.ru/p{i}", "status": status, "content_type": ctype, "ttfb": t, "elapsed": 9,
            "ttfb_recheck": recheck}


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<ol>.*?</ol>", "", h, flags=re.S)))


def main():
    # 1. интервалы, медиана, среднее; файл и 404 не считаются; второй замер вместо первого
    pages = [page(1, 0.2), page(2, 0.3), page(3, 0.8), page(4, 1.5), page(5, 3.0, recheck=0.4),
             page(6, 6.0), page(7, 5.0, status=404), page(8, 5.0, ctype="application/pdf")]
    h = report.speed_html(pages)
    t = text(h)
    check("Как быстро отвечает сервер" in h, "нет заголовка блока")
    check("Обычно 0,60 с, в среднем 1,53 с" in t, f"медиана/среднее: {t[:400]}")
    check("Дольше 1 с: 2 из 6 страниц (33%)" in t, f"число медленных: {t[:500]}")
    check("перемерены второй раз" in t and "(1)" in t, "нет пояснения про второй замер")
    bars = re.findall(r'<details class="dp([^"]*)"><summary class="bar"><span class="bl">([^<]+)</span>.*?'
                      r'<span class="bn">([^<]+)</span>', h)
    got = [(lab, n, cls.strip()) for cls, lab, n in bars]
    check(got == [("до 0,5 с", "3", ""), ("0,5-1 с", "1", ""), ("1-2 с", "1", "far"), ("больше 5 с", "1", "vfar")],
          f"полоски: {got}")
    # 2. все быстрые; нет страниц - нет блока
    t = text(report.speed_html([page(1, 0.1), page(2, 0.2)]))
    check("Все страницы ответили быстрее 1 с" in t and "без скачивания" in t, f"все быстрые: {t[:300]}")
    check(report.speed_html([dict(page(1, None), elapsed=None)]) == "" and report.speed_html([]) == "", "блок без замеров")
    check("страницы.csv" not in report.speed_html(pages * 30, client=True), "имя .csv в отчёте для клиента")

    # 3. разделы: новые столбцы и старая проверка без них
    rows = [{"name": "Каталог", "path": "/catalog/", "pages": 1200, "idx": 1000, "closed": 150, "health": 80,
             "top": ["Нет H1 - 5"], "sub": [{"name": "Котлы", "path": "/catalog/kotly/", "pages": 40, "idx": 40,
                                             "closed": 0, "health": 90, "top": []}]},
            {"name": "Статьи", "path": "/blog/", "pages": 30, "health": 100, "top": []}]
    h = sections_html({"sections": rows})
    check("<th>Индексируются</th><th>Закрыты</th>" in h, "нет столбцов в разделах")
    check("<td>1 200</td><td>1 000</td><td>150</td>" in h, "числа раздела")
    check("<td>40</td><td>40</td><td>-</td>" in h, "подраздел без закрытых")
    check("<td>30</td><td>-</td><td>-</td>" in h, "старая проверка без новых полей")

    if fails:
        print("✗ время ответа и разделы:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("✓ время ответа и разделы: полоски, медиана, второй замер, столбцы разделов")


if __name__ == "__main__":
    main()
