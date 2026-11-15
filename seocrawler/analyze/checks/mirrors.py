"""Склейка домена (версия 7).
/index.html и /index.php, которые открываются сами, но с canonical на главный адрес, - не копия сайта,
а замечание (на GitHub Pages /index.html всегда открывается сам, редирект там не задать)."""
from urllib.parse import urljoin

from ... import mirror_copy
from ..common import CRIT, NOTE, WARN
from .codes import TEMP4


def _same(a, b):
    return (a or "").rstrip("/").lower() == (b or "").rstrip("/").lower()


def _canonical(store, m, main):
    """canonical варианта: сохранён при обходе (с 05.10.2026), у старых проверок для /index.* — canonical главной
    из базы (это тот же файл, что и главная)."""
    if "canonical" in m:
        return urljoin(m["variant"], m["canonical"]) if m["canonical"] else ""
    if not m["variant"].startswith(main) or not m["variant"][len(main):].startswith("index."):
        return ""
    try:
        r = store.db.execute("SELECT canonical FROM pages WHERE url=?", (main,)).fetchone()
        return urljoin(main, r[0]) if r and r[0] else ""
    except Exception:
        return ""


def run(ctx):
    store = ctx.store
    add = ctx.add
    mirrors = store.get_meta("mirrors", None)
    if mirrors:
        main = mirrors["main"]
        mrow, dup, soft = [], [], []
        for m in mirrors["variants"]:
            ch = m["chain"]
            first, last = ch[0][1], ch[-1]
            path = "\n→ ".join(f"{u} ({c})" for u, c in ch)
            if not isinstance(first, int):
                continue  # вариант вообще не открывается (например, www нет в DNS) — дубля нет
            if first in (404, 410) and len(ch) == 1:
                continue
            # вариант есть, но отвечает ошибкой (403, 500, 503): посетитель, набравший его, видит ошибку. Ответ прокси
            # VPN за несуществующий адрес сюда не доходит - обход отмечает его «нет в DNS» (crawler/extra_passes.py)
            if first in TEMP4 and len(ch) == 1:
                continue   # 408/429 - сервер просил реже, а не ошибка: по такому ответу о варианте не судим
            if first >= 400 and len(ch) == 1:
                mrow.append([m["variant"], f"отвечает ошибкой {first} вместо редиректа на главный адрес", path])
                continue
            if first == 200:
                index = m["variant"].startswith(main) and m["variant"][len(main):].startswith("index.")
                if index and _same(_canonical(store, m, main), main):
                    soft.append([m["variant"], f"открывается сам, но в коде указан canonical на {main}", path])
                else:
                    dup.append([m["variant"], "открывается сам, без редиректа - это копия сайта", path])
            elif last[1] == "цикл":
                dup.append([m["variant"], "редирект по кругу", path])
            elif last[0] != main:
                mrow.append([m["variant"], f"ведёт не на главный адрес ({last[0]})", path])
            elif first in (302, 303, 307):
                mrow.append([m["variant"], f"временный редирект {first} - нужен постоянный 301", path])
            elif len(ch) > 2:
                mrow.append([m["variant"], f"цепочка из {len(ch) - 1} переходов - нужен один", path])
            elif last[1] != 200:
                mrow.append([m["variant"], f"главный адрес ответил {last[1]}", path])
        # одна причина - одна проблема: вариант ведёт на копию, которая сама открывается без редиректа (http при
        # выключенном https, timurpanin.ru) - исправится вместе с ней, так и пишем
        copies = {r[0] for r in dup}
        for r in mrow:
            tail = r[2].rsplit("\n→ ", 1)[-1].rsplit(" (", 1)[0]
            if tail in copies:
                r[1] += f" - а {tail} сам открывается без редиректа: исправится вместе с ним"
        from ...site_tech import platform
        pf = platform(store.get_meta("site_tech", None))
        no_redirect = pf and pf.get("redirects", "").startswith("нельзя")
        add("mirror_dup", CRIT, "Склейка домена", "Вариант адреса сайта открывается без редиректа",
            f"Главный адрес сайта - {main}. Этот вариант адреса (с www или без, http или https, /index.php) "
            "открывает тот же сайт, а не перенаправляет на главный. Для поисковика это копия сайта: "
            "вес ссылок делится, в выдачу может попасть не тот адрес.",
            (f"На {pf['name']} редирект с отдельного адреса настроить нельзя. Поставьте на страницу "
             f"<link rel=\"canonical\" href=\"{main}\"> - поисковики будут считать её главной."
             if no_redirect and all(main in r[0] for r in dup) else
             "Передайте разработчику или хостингу: настроить постоянный редирект 301 с этого варианта на главный адрес."),
            ["Вариант адреса", "Что не так", "Что ответил сервер"], dup, page_col=None)
        add("mirror_canonical", NOTE, "Склейка домена", "Главная открывается и по адресу с index.html или index.php",
            f"Главный адрес сайта - {main}. Этот вариант открывает ту же главную без редиректа, но в её коде указан "
            "canonical на главный адрес, поэтому поисковики считают его той же страницей, а не копией. "
            "Опасно, только если на этот адрес где-то ставят ссылки.",
            (f"Ничего делать не нужно: на {pf['name']} редирект с отдельного адреса не задаётся, canonical уже "
             "стоит. Следите, чтобы ссылки на сайте вели на главный адрес, а не на index.html."
             if no_redirect else
             "Можно оставить как есть. Аккуратнее - редирект 301 с этого адреса на главный (передайте разработчику)."),
            ["Вариант адреса", "Что не так", "Что ответил сервер"], soft, page_col=None)
        add("mirror_redirect", WARN, "Склейка домена", "Вариант адреса сайта перенаправляет неправильно",
            f"Главный адрес сайта - {main}. Остальные варианты должны вести на него одним постоянным редиректом 301.",
            "Передайте разработчику: заменить на один редирект 301 прямо на главный адрес.",
            ["Вариант адреса", "Что не так", "Что ответил сервер"], mrow, page_col=None)
        # Ссылки на копию сайта: по ним робот уходит на копию (так и на lancentre.ru обошли бы сайт дважды)
        twin = mirror_copy.twin_host(mirrors)
        if twin:
            rows = []
            for src, dst, anchor in store.db.execute(
                    "SELECT src, dst, anchor FROM links WHERE kind='a' AND (dst LIKE ? OR dst LIKE ?)",
                    (f"https://{twin}%", f"http://{twin}%")):
                if mirror_copy.is_twin(dst, twin) and not mirror_copy.is_twin(src, twin):
                    rows.append([src, dst, anchor or ""])
            add("mirror_links", WARN, "Склейка домена", "Ссылки на копию сайта",
                f"Копия сайта {twin} открывается без редиректа, и на неё стоят ссылки со страниц сайта. По ним "
                "поисковик уходит на копию и находит каждую страницу второй раз. Страницы копии в отчёт не входят: "
                "это те же страницы, что и на главном адресе.",
                f"Замените в этих ссылках адрес {twin} на главный адрес сайта. Главное - настроить редирект 301 "
                "с копии на главный адрес (проблема «Вариант адреса сайта открывается без редиректа»).",
                ["Страница", "Ссылка на копию", "Текст ссылки"], rows)
