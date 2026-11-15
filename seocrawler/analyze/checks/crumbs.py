"""Хлебные крошки (28.10.2026, по просьбе пользователя): есть ли они на всех страницах раздела, размечены ли для
поисковика, куда ведут их ссылки и не ссылается ли последний пункт на саму страницу.

Данные - из «Что мешает покупать» (shop.facts при обходе, колонка pages.shop): crumbs_html - видимых пунктов,
crumb_urls - ссылки видимых крошек, crumb_last - ссылка последнего пункта, crumb_ld_urls - адреса в JSON-LD
BreadcrumbList; разметка - schema_info.crumbs.
Старые проверки (без crumbs_html) получают только «есть не на всех страницах» - по названиям пунктов.
Нет разметки ни на одной странице - это rich_no_crumbs (rich.py), здесь не повторяется.
Повторы пунктов в крошках - buy_crumbs_repeat (buy.py)."""
import json
from collections import defaultdict
from urllib.parse import urlsplit

from ... import urls as U
from ..common import NOTE, WARN
from .codes import TEMP4

SECTION_MIN = 5       # страниц в разделе - меньше раздел не оцениваем
SECTION_SHARE = 0.6   # у такой доли страниц раздела крошки есть - у остальных их, похоже, забыли
ROWS = 300


def _load(p, col):
    try:
        return json.loads(p.get(col) or "{}") or {}
    except ValueError:
        return {}


def _section(url):
    parts = [x for x in urlsplit(url).path.split("/") if x]
    return parts[0] if parts else ""


def run(ctx):
    pages = [p for p in ctx.indexable if p.get("shop") is not None or p.get("schema_info") is not None]
    if not pages:
        return
    facts = {p["url"]: _load(p, "shop") for p in pages}
    markup = {p["url"]: (_load(p, "schema_info").get("crumbs") or 0) for p in pages}
    has = {u: bool(f.get("crumbs_html") or f.get("crumbs") or markup[u]) for u, f in facts.items()}
    if not any(has.values()):
        # только страницы, где крошки искали (колонка shop есть): у старой проверки без неё «крошек нет» было бы
        # ложным - они могут быть на каждой странице (проверка кода 29.10.2026)
        _none(ctx, [p for p in pages if p.get("shop") is not None])
        return
    # новая проверка (28.10.2026 и позже): нули shop.facts не пишет, поэтому смотрим любое из новых полей - крошки
    # бывают только в разметке, без видимого блока
    new_data = any(k in f for f in facts.values() for k in ("crumbs_html", "crumb_urls", "crumb_ld_urls"))
    _missing(ctx, pages, has, facts)
    if new_data:
        _no_markup(ctx, pages, facts, markup)
        _links(ctx, pages, facts)


def _none(ctx, pages):
    """Крошек нет ни на одной странице, а вложенные разделы есть (/cases/smartreading): посетителю из поиска не
    видно, в каком он разделе. hightime.agency 29.10.2026: отчёт молчал - _missing ищет только «не на всех страницах
    раздела», а rich_no_crumbs - 20 страниц глубже двух кликов (меню ведёт почти на всё сразу с главной)."""
    if any(i.key == "rich_no_crumbs" for i in ctx.issues):
        return    # там уже сказано: «если самих крошек нет, сначала добавить их»
    by = defaultdict(list)
    for p in pages:
        parts = [x for x in urlsplit(p["url"]).path.split("/") if x]
        if len(parts) >= 2:
            by[parts[0]].append(p["url"])
    deep = sum(len(v) for v in by.values())
    if deep < SECTION_MIN:
        return
    rows = [[f"/{s}/", len(us), us[0]] for s, us in sorted(by.items(), key=lambda kv: -len(kv[1]))]
    ctx.add("crumbs_none", NOTE, "Структура", "Хлебных крошек нет на сайте",
            f"Ни на одной странице нет строки «Главная → Раздел → Страница», а вложенных страниц на сайте {deep}. "
            "Посетитель, пришедший из поиска сразу на такую страницу, не видит, в каком он разделе, и не может в "
            "один клик вернуться к списку; поисковик хуже понимает структуру сайта и не показывает путь по разделам "
            "в сниппете.",
            "Передайте разработчику: вывести хлебные крошки на внутренних страницах (в шаблоне раздела) и сразу "
            "разметить их BreadcrumbList.",
            ["Раздел", "Вложенных страниц", "Пример страницы"], rows[:ROWS], page_col=None)


def _missing(ctx, pages, has, facts):
    """Крошки есть у большинства страниц раздела, а у этих нет."""
    by = defaultdict(list)
    for p in pages:
        s = _section(p["url"])
        if s:
            by[s].append(p)
    rows = []
    for s, ps in by.items():
        n = sum(1 for p in ps if has[p["url"]])
        if len(ps) >= SECTION_MIN and n >= SECTION_SHARE * len(ps) and n < len(ps):
            example = next(p["url"] for p in ps if has[p["url"]])
            rows += [[p["url"], f"/{s}/", f"{n} из {len(ps)}", example] for p in ps if not has[p["url"]]]
    ctx.add("crumbs_missing", NOTE, "Структура", "Хлебные крошки есть не на всех страницах раздела",
            "На большинстве страниц раздела есть строка «Главная → Раздел → …», а на этих её нет. Посетителю "
            "сложнее понять, где он, и вернуться в раздел; поисковик хуже видит, к какому разделу относится "
            "страница, и не может показать путь по разделам в сниппете.",
            "Передайте разработчику: вывести хлебные крошки на этих страницах так же, как на остальных страницах "
            "раздела (обычно шаблон этих страниц другой или крошки отключены в настройках).",
            ["Адрес", "Раздел", "Страниц раздела с крошками", "Пример страницы с крошками"], rows[:ROWS])


def _no_markup(ctx, pages, facts, markup):
    """Крошки видны, а разметки BreadcrumbList нет. Если разметки нет ни на одной странице и про это уже сказала
    rich_no_crumbs - не повторяем."""
    seen = [p for p in pages if facts[p["url"]].get("crumbs_html")]
    rows = [[p["url"], " → ".join(facts[p["url"]].get("crumbs") or [])] for p in seen if not markup[p["url"]]]
    if not rows:
        return
    if not any(markup.values()) and any(i.key == "rich_no_crumbs" for i in ctx.issues):
        return
    part = any(markup.values())
    ctx.add("crumbs_no_markup", NOTE, "Микроразметка", "Хлебные крошки видны, но не размечены для поисковиков",
            ("Крошки на этих страницах есть, а разметки BreadcrumbList у них нет, хотя на других страницах сайта "
             "она есть. " if part else "Крошки на страницах есть, а разметки BreadcrumbList нет ни на одной. ")
            + "По разметке Яндекс и Google показывают в выдаче путь по разделам («Главная › Каталог › Раздел») "
              "вместо длинного адреса - сниппет понятнее, по нему чаще кликают.",
            "Передайте разработчику: разметить блок хлебных крошек в шаблоне (JSON-LD BreadcrumbList или microdata)"
            + (" так же, как на страницах, где разметка уже есть." if part else "."),
            ["Адрес", "Крошки"], rows[:ROWS])


def _links(ctx, pages, facts):
    """Ссылки в крошках: ошибка, редирект; последний пункт - ссылка на саму страницу."""
    start = ctx.store.get_meta("start", "") or ""
    root = U.host_of(start) if start else ""
    status = ctx.status
    bad = {}           # (адрес, где) → [код, {страницы}]
    self_rows = []

    def look(n):
        st = status.get(n)
        if st is None:
            st = status.get(U.strip_params(n)[0])
        return st

    for p in pages:
        f = facts[p["url"]]
        # последний пункт - ссылка на саму страницу (crumb_last - ссылка именно последнего пункта, а не последняя
        # ссылка блока: у крошек Битрикса бывают выпадающие списки соседних разделов)
        last = U.normalize(f.get("crumb_last") or "", p["url"]) if f.get("crumb_last") else ""
        if last and U.same_page(last, p["url"]) and (f.get("crumbs_html") or 0) >= 2:
            self_rows.append([p["url"], " → ".join(f.get("crumbs") or [])])
        for where, hrefs in (("на странице", f.get("crumb_urls") or []), ("в разметке BreadcrumbList", f.get("crumb_ld_urls") or [])):
            for h in hrefs:
                if h.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                n = U.normalize(h, p["url"])
                if not n or (root and not U.same_site(n, root, True)) or U.same_page(n, p["url"]):
                    continue
                st = look(n)
                if not st:
                    continue      # адрес не проверялся (закрыт в robots.txt, вне раздела) - не судим
                code, err = st
                # временный редирект (302, 303, 307) - обычно вход в личный кабинет или выбор города: исправлять
                # нечего (lancentre.ru: «Личный кабинет» /personal/ → 302 на /auth/); постоянный - адрес устарел
                if code in (302, 303, 307) and not err:
                    continue
                if code in TEMP4:
                    continue      # 408/429 - сервер просил реже, страница не битая (codes.TEMP4; проверка кода 04.11.2026)
                if err or not code or code >= 300:
                    # обрывок с кодом 200 - текст ошибки (раньше «200» не попадал ни в битые, ни в редиректы)
                    shown = (err or "нет ответа") if not code or code == 200 else code
                    v = bad.setdefault((n, where), [shown, set()])
                    v[1].add(p["url"])
    broken = sorted(((u, w, c, ps) for (u, w), (c, ps) in bad.items() if not (isinstance(c, int) and c < 400)),
                    key=lambda x: -len(x[3]))
    redir = sorted(((u, w, c, ps) for (u, w), (c, ps) in bad.items() if isinstance(c, int) and 300 <= c < 400),
                   key=lambda x: -len(x[3]))

    def rows(items):
        out = []
        for u, w, c, ps in items[:ROWS]:
            to = ctx.follow(u)[0][-1] if isinstance(c, int) and 300 <= c < 400 else ""
            out.append([u, str(c), to, w, len(ps), sorted(ps)[0]])
        return out
    cols = ["Ссылка в крошках", "Ответ", "Куда ведёт", "Где", "Страниц с этой ссылкой", "Пример страницы"]
    ctx.add("crumbs_broken", WARN, "Структура", "Ссылки в хлебных крошках ведут на ошибку",
            "Пункт крошек ведёт на страницу, которая не открывается (404, ошибка сервера). Крошки есть на многих "
            "страницах, поэтому одна такая ссылка - это сотни переходов в никуда для посетителей и поисковика.",
            "Передайте разработчику: исправить адрес раздела в крошках (обычно он берётся из настроек раздела или "
            "товара) или восстановить страницу. Если ссылка в разметке BreadcrumbList - поправить и её.",
            cols, rows(broken), page_col=None, show_col=5)
    ctx.add("crumbs_redirect", NOTE, "Структура", "Ссылки в хлебных крошках ведут на редирект",
            "Пункт крошек ведёт на адрес, который перенаправляет на другой. Страница открывается, но каждый переход "
            "идёт через лишний шаг, а поисковик тратит обход на редиректы.",
            "Передайте разработчику: в крошках ставить сразу конечный адрес (колонка «Куда ведёт»). Часто дело в "
            "слэше на конце или в http вместо https.",
            cols, rows(redir), page_col=None, show_col=5)
    ctx.add("crumbs_self_link", NOTE, "Структура", "Последний пункт хлебных крошек - ссылка на ту же страницу",
            "Последний пункт крошек - это сама страница, а он сделан ссылкой на неё же. Нажатие ничего не меняет, "
            "а у поисковика на странице появляется лишняя ссылка на саму себя.",
            "Передайте разработчику: последний пункт крошек выводить текстом, без ссылки (в разметке BreadcrumbList "
            "у последнего пункта адрес можно не указывать).",
            ["Адрес", "Крошки"], self_rows[:ROWS])
