"""«Где теряем клики»: Вебмастер, Search Console и Метрика вместе с данными проверки (seocrawler/lost_clicks.py).
Проблем не добавляет (их дают checks/webmaster, search_console, metrika), только сводку для отчёта."""
from ... import lost_clicks


def run(ctx):
    try:
        ctx.lost_clicks = lost_clicks.compute(ctx)
    except Exception as e:  # чужие данные странной формы не должны ронять весь отчёт
        ctx.lost_clicks = {"sources": [], "missing": [], "error": str(e)[:200]}
