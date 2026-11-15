"""Кнопка «На весь экран» у больших таблиц в отчётах (отчёт.html, отчёт для клиента, дерево сайта). Тот же код,
что в окне программы: window/page/tablefs.js. Без библиотек, работает офлайн."""
from pathlib import Path

JS = (Path(__file__).parent / "window" / "page" / "tablefs.js").read_text(encoding="utf-8")
