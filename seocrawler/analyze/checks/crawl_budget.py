"""Бюджет обхода: какая доля адресов сайта, которые находит робот, — впустую."""
from ..common import CRAWL_WASTE_WARN, NOTE, WARN, defaultdict
from .codes import bucket


def run(ctx):
    add, db, issues = ctx.add, ctx.db, ctx.issues
    cats = defaultdict(list)
    blocked_n = 0
    for r in db.execute("""SELECT u.url, u.state, u.skip_reason, p.status, p.error, p.indexability, p.content_type,
                                  p.location
                           FROM urls u LEFT JOIN pages p ON p.url=u.url
                           WHERE u.internal=1 AND u.kind='page' AND u.state IN ('done','skipped')"""):
        url, state, reason, st_, err, idx, ctype, loc = r
        if state == "skipped":
            if (reason or "").startswith("Закрыт в robots"):
                blocked_n += 1  # робот их не открывает — время на них не тратит, в расчёт не входят
            continue  # пропущено по ограничениям программы — робот поисковика мог бы открыть, не считаем
        # ящик - общий сортировщик codes.bucket (закон сохранения): 404 с оборванным телом - ошибка, а не «не ответил»;
        # 204, 206 и другие необычные коды - не «полезная страница» (ревью кода 04.11.2026)
        b = bucket(st_, err, loc) if st_ is not None or err else None   # None - строки ответа нет
        if b == "noresp":
            cats["сервер не ответил"].append(url)
        elif b in ("redirect", "redirect_noloc") or idx == "Редирект":   # и meta refresh / JavaScript с кодом 200
            cats["редирект"].append(url)
        elif b in ("4xx", "5xx", "too_many_requests"):
            cats["ошибка 4xx/5xx"].append(url)
        elif b == "odd_codes":
            cats["необычный код ответа"].append(url)
        elif idx == "noindex":
            cats["закрыто noindex"].append(url)
        elif idx == "Канонизирована":
            cats["canonical на другую страницу"].append(url)
        elif ctype and ctype not in ("text/html", "application/xhtml+xml"):
            cats["файл (не страница)"].append(url)
        else:
            cats["полезная страница"].append(url)
    total_found = sum(len(v) for v in cats.values())
    waste = total_found - len(cats["полезная страница"]) - len(cats["файл (не страница)"])
    if total_found >= 20 and waste:
        share = round(100 * waste / total_found)
        order_ = ["полезная страница", "редирект", "ошибка 4xx/5xx", "необычный код ответа", "закрыто noindex",
                  "canonical на другую страницу", "сервер не ответил", "файл (не страница)"]
        order_ += [k for k in cats if k not in order_]   # посчитанное, но не вписанное выше - тоже в таблице
        brow = [[k, len(cats[k]), f"{round(100 * len(cats[k]) / total_found)}%", "\n".join(cats[k][:2])]
                for k in order_ if cats.get(k)]
        add("crawl_waste", WARN if share >= CRAWL_WASTE_WARN else NOTE, "Индексация",
            f"Бюджет обхода: {share}% адресов, которые находит робот, тратятся впустую",
            f"По ссылкам сайта робот находит {total_found} адресов страниц. Из них {waste} не дают ничего в поиск: "
            "это редиректы, ошибки, закрытые noindex или неосновные (canonical на другую) страницы. "
            "Робот тратит на них время вместо новых и важных страниц - у больших сайтов из-за этого новые "
            "страницы попадают в поиск неделями."
            + (f" Ещё {blocked_n} адресов закрыты в robots.txt - робот их не открывает, в расчёт они не входят." if blocked_n else ""),
            "Смотрите самые большие строки: убирать нужно не сами адреса, а ссылки на них (исправить ссылки на редиректы "
            "и битые, не ставить ссылки на закрытые страницы, фильтры закрыть так, чтобы по ним не было ссылок).",
            ["Что за адреса", "Сколько", "Доля", "Примеры"], brow, page_col=None)
        if issues and issues[-1].key == "crawl_waste":
            issues[-1].sitewide = f"{share}% ({waste:,} из {total_found:,})".replace(",", " ")  # вместо числа строк
    summary_waste = round(100 * waste / total_found) if total_found else None

    ctx.summary_waste = summary_waste
