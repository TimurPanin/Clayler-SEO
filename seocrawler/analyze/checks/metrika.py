"""Яндекс Метрика: куда приходят люди из поиска (данные — seocrawler/metrika.py, meta «metrika»)."""
from urllib.parse import unquote, urlsplit

from ..common import CRIT, NOTE
from ...webmaster import _norm

BOUNCE_HIGH = 35      # отказов, % — у Метрики отказ: визит короче 15 секунд с одной страницей
BOUNCE_MIN_VISITS = 20


def run(ctx):
    m = ctx.store.get_meta("metrika", None)
    if not m or not m.get("landing"):
        return
    add, status = ctx.add, ctx.status
    src = f"Данные Яндекс Метрики (счётчик {m['counter']}) за 30 дней, загружены {m['fetched']}."

    def st(url):
        return status.get(url) or status.get(unquote(url)) or status.get(url.split("?")[0])

    broken = []
    for x in m["landing"]:
        s = st(x["url"])
        if s and (s[1] or (s[0] and s[0] != 200)):
            broken.append([x["url"], s[1] or s[0], round(x["visits"])])
    add("metrika_broken_landing", CRIT, "Яндекс Метрика", "Посетители из поиска попадают на неработающие страницы",
        src + " На эти адреса за месяц приходили люди из Яндекса и Google, а сейчас страницы отдают ошибку или "
        "перенаправляют. Колонка «Визитов из поиска» - сколько посетителей уже приходило: это потерянные клиенты.",
        "Почините страницы или поставьте 301-редирект на самую близкую по смыслу рабочую страницу "
        "(не на главную). Начните сверху - там больше всего посетителей.",
        ["Страница", "Код при проверке", "Визитов из поиска"], broken, page_col=0)

    host = urlsplit(ctx.store.get_meta("start", "") or "").hostname or ""
    high = [[x["url"], round(x["visits"]), f"{x['bounce']:.0f}%"] for x in m["landing"]
            if x["visits"] >= BOUNCE_MIN_VISITS and x["bounce"] >= BOUNCE_HIGH
            and _norm(urlsplit(x["url"]).hostname) == _norm(host)]
    add("metrika_bounce", NOTE, "Яндекс Метрика", f"Много отказов у посетителей из поиска (от {BOUNCE_HIGH}%)",
        src + f" На эти страницы пришло из поиска не меньше {BOUNCE_MIN_VISITS} человек за месяц, и больше "
        f"{BOUNCE_HIGH}% из них ушли меньше чем за 15 секунд, ничего не открыв. Обычно так бывает, когда страница "
        "не отвечает на запрос, долго грузится или неудобна на телефоне. Поисковики это замечают.",
        "Откройте страницу глазами человека из поиска: сразу ли видно то, что он искал (цена, услуга, адрес)? "
        "Проверьте скорость и вид на телефоне. В Метрике - «Вебвизор» по этой странице покажет, что люди делают.",
        ["Страница", "Визитов из поиска", "Отказы"], high, page_col=0)
