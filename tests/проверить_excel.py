"""Excel отчёта (xlsx_report.write_xlsx, потоковая запись с 01.11.2026): лист проблемы не длиннее MAX_ISSUE_ROWS строк,
над таблицей пометка «Показаны первые … из …», в списке проблем - полное число; оформление на месте (шапка, ссылки на
листы, закрепление, фильтр, цвет важности). Без сети. Запуск: py -3 tests/проверить_excel.py (и из проверить_всё.py)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("CLAYLER_NO_USER_SETTINGS", "1")
from seocrawler import xlsx_report as X  # noqa: E402
from seocrawler.analyze.common import Issue, CRIT, NOTE  # noqa: E402
from seocrawler.report import PAGE_EXPORT  # noqa: E402

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)


def main():
    if not X.available():
        print("- excel: пропущено (нет openpyxl)")
        return
    X.MAX_ISSUE_ROWS = 100
    big = Issue("img_no_size", NOTE, "Картинки", "Картинки без указанных размеров", "Почему плохо.", "Что сделать.",
                ["Страница", "Картинка"], [[f"https://site.test/p{i}/", f"https://site.test/i{i}.jpg"] for i in range(250)])
    small = Issue("broken_links", CRIT, "Ссылки", "Битые ссылки", "Почему.", "Исправить.",
                  ["Страница", "Куда", "Текст", "Ошибка"], [["https://site.test/", "https://site.test/x", "x\nдве строки", 404]])
    pages = [{k: None for k, _ in PAGE_EXPORT} | {"url": f"https://site.test/p{i}/", "depth": 1, "status": 200}
             for i in range(5)]
    summary = {"health": 50, "pages": 5, "indexable": 5, "checked": 10, "pages_clean": 2, "pages_warn_only": 1,
               "pages_crit": 2, "crit": 1, "warn": 0, "note": 1}
    path = os.path.join(tempfile.mkdtemp(prefix="clayler_xlsx_"), "t.xlsx")
    X.write_xlsx(path, {"start": "https://site.test/"}, [small, big], pages, summary, PAGE_EXPORT)
    from openpyxl import load_workbook
    wb = load_workbook(path)
    check(wb.sheetnames[:3] == ["Сводка", "Проблемы", "Страницы"], f"листы: {wb.sheetnames}")
    wp = wb["Проблемы"]
    counts = {wp.cell(r, 3).value: wp.cell(r, 4).value for r in range(2, wp.max_row + 1)}
    check(counts.get("Картинки без указанных размеров") == 250, f"в списке проблем не полное число: {counts}")
    check(wp["A1"].font.b and wp.freeze_panes == "A2" and wp.auto_filter.ref == "A1:F3", "шапка листа «Проблемы»")
    check(wp["C2"].hyperlink is not None and wp["A2"].fill.fgColor.rgb.endswith(X.SEV_FILL[CRIT]), "ссылка на лист и цвет")
    sheet = next(n for n in wb.sheetnames if "Картинки без" in n)
    ws = wb[sheet]
    check(ws.max_row == 6 + 100, f"строк на листе большой проблемы: {ws.max_row - 6}, ждали 100")
    check("Показаны первые 100 строк из 250" in (ws["A5"].value or ""), f"нет пометки об обрезке: {ws['A5'].value}")
    check(ws["A6"].value == "Страница" and ws["A6"].font.b and ws.freeze_panes == "A7", "шапка таблицы проблемы")
    check(ws.auto_filter.ref == "A6:B106", f"фильтр листа проблемы: {ws.auto_filter.ref}")
    check(ws["A4"].hyperlink is not None, "нет ссылки «к списку проблем»")
    s2 = wb[next(n for n in wb.sheetnames if "Битые" in n)]
    check(s2["A5"].value in (None, ""), "пометка об обрезке на коротком листе")
    check(s2["C7"].alignment.wrap_text, "многострочная ячейка без переноса")
    if fails:
        print("✗ excel:\n   " + "\n   ".join(fails))
        sys.exit(1)
    print("✓ excel: лист проблемы ограничен с пометкой, в списке полное число, оформление и ссылки на месте")


if __name__ == "__main__":
    main()
