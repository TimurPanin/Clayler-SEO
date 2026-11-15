"""Неинформативный текст ссылок («подробнее», «читать далее», «тут»).
Один текст ссылки на разные страницы (10.10.2026): ссылки «Газовые котлы» ведут на две-три разные страницы - они
спорят за один запрос. Если текст совпадает с главным запросом группы Семантики, рядом - страница под этот запрос
из «Запрос → страница»."""
from urllib.parse import urlsplit

from ..common import NOTE, defaultdict, link_rows, note_fault, re
from ...fmt import quote
from .meta_text import GENERIC_ANCHOR, PAGE_N
from ..sections import WEAK

MANY_MIN_SRC = 2     # у каждой из страниц-адресатов - ссылки хотя бы с двух страниц (не одна случайная)
MANY_TOP_SRC = 5     # а у главной из них - хотя бы с пяти: товары с одинаковым названием (по 3-4 ссылки) - не сюда
BUTTONS = {"сбросить", "сбросить фильтр", "сбросить все", "применить", "показать", "войти", "выйти", "наверх",
           "в избранное", "сравнить", "к сравнению", "отложить", "оформить заказ", "написать отзыв", "оставить отзыв",
           "версия для печати", "печать", "поделиться", "свернуть", "развернуть", "скрыть", "закрыть"}
MANY_ROWS = 300


def run(ctx):
    add, db = ctx.add, ctx.db
    weak_rx = re.compile(r"^(подробнее|читать далее|читать полностью|далее|ещё|еще|тут|здесь|сюда|по ссылке|"
                         r"перейти|узнать больше|смотреть|посмотреть|click here|read more|more|here)[.!…\s»→>]*$", re.I)
    weak = defaultdict(lambda: [0, set(), ""])
    for src, dst, anchor in link_rows(db, ("src", "dst", "anchor"), "kind='a' AND internal=1"):
        a = (anchor or "").strip()
        if a and weak_rx.match(a):
            w = weak[a.lower()]
            w[0] += 1
            w[1].add(src)
            w[2] = w[2] or f"{src} → {dst}"
    add("weak_anchors", NOTE, "Ссылки", "Ссылки с текстом «подробнее», «читать далее», «тут»",
        "Текст ссылки подсказывает поисковику и незрячим посетителям, куда она ведёт. «Подробнее» не говорит ничего; "
        "лучше - «Подробнее о доставке» или сам заголовок страницы.",
        "По желанию: в шаблоне карточек и анонсов сделать текстом ссылки название или добавить его к «Подробнее».",
        ["Текст ссылки", "Сколько ссылок", "На скольких страницах", "Пример"],
        [[k, v[0], len(v[1]), v[2]] for k, v in sorted(weak.items(), key=lambda kv: -kv[1][0])], page_col=None)
    try:
        many_pages(ctx, weak_rx)
    except Exception as e:   # дополнение: сбой не должен ломать анализ, но и пропасть молча не должен
        note_fault("один текст ссылки на разные страницы", "", e)


def many_pages(ctx, weak_rx):
    from ...urls import page_key
    from .link_plan import _stems, sem_pages
    from .meta_text import _brand, _city
    ok = {p["url"] for p in ctx.indexable if not urlsplit(p["url"]).query and not PAGE_N.search(p["url"])}
    if len(ok) < 20:
        return
    # текст → страница (одна для адреса со слэшем и без, http и https) → со скольких страниц ссылаются
    cnt = defaultdict(lambda: defaultdict(int))
    show, url_of = {}, {}
    for a, dst, n in ctx.db.execute("SELECT anchor, dst, COUNT(DISTINCT src) FROM links WHERE kind='a' AND internal=1 "
                                    "AND src<>dst GROUP BY anchor, dst"):
        a = " ".join((a or "").split())
        if dst not in ok or not 4 <= len(a) <= 80 or not re.search(r"[а-яёa-z]{3}", a, re.I):
            continue
        k = a.lower().replace("ё", "е")
        if weak_rx.match(a) or GENERIC_ANCHOR.match(a) or k in WEAK or k in BUTTONS:
            continue
        pk = page_key(dst) or dst
        url_of.setdefault(pk, dst)
        cnt[k][pk] += n
        show.setdefault(k, a)
    skip = set()
    for w in (_city(ctx.indexable), _brand(ctx.indexable), "купить", "цена", "цены"):
        skip |= _stems(w, set())
    sem = {}
    for u, g in sem_pages(ctx).items():
        key = frozenset(_stems((g.get("a") or {}).get("main") or g["name"], skip))
        if key:
            sem.setdefault(key, (u, page_key(u) or u))
    rows = []
    for k, dd in cnt.items():
        many = sorted(((pk, n) for pk, n in dd.items() if n >= MANY_MIN_SRC), key=lambda x: -x[1])
        if len(many) < 2 or many[0][1] < MANY_TOP_SRC:
            continue
        s = sem.get(frozenset(_stems(k, skip)))
        note = ""
        if s:
            note = (f"{s[0]} (среди этих)" if any(pk == s[1] for pk, _ in many)
                    else f"{s[0]} - ни одна из этих ссылок туда не ведёт")
        where = "; ".join(f"{url_of[pk]} - с {n} стр." for pk, n in many[:4]) + (
            f"; и ещё {len(many) - 4}" if len(many) > 4 else "")
        rows.append((0 if s else 1, -sum(n for _, n in many), [show[k], len(many), where, note]))
    rows.sort(key=lambda r: (r[0], r[1]))
    if not rows:
        return
    # пример - с этого сайта: до 24.10.2026 здесь у всех сайтов стояли «Газовые котлы» и «Газовые котлы Baxi»
    ex = quote(rows[0][2][0])
    ctx.add("anchor_many_pages", NOTE, "Ссылки", "Один текст ссылки ведёт на разные страницы",
            f"Текст ссылки подсказывает поисковику, о чём страница. Если ссылки с одним и тем же текстом ({ex}) ведут "
            "на две-три разные страницы, эти страницы спорят за один запрос, и ни одна не получает всю "
            "силу ссылок. Особенно важно, когда текст совпадает с запросом из семантики сайта: ссылки должны вести на "
            "страницу под этот запрос.",
            "Оставить этот текст только у ссылок на главную страницу под запрос (её адрес - в последней колонке, если "
            f"запрос есть в семантике). У ссылок на другие страницы текст уточнить: к {ex} добавить, чем эта страница "
            "отличается (бренд, вид, назначение).",
            ["Текст ссылки", "На сколько разных страниц", "Куда ведёт (со скольких страниц)",
             "Страница под этот запрос по семантике"], [r[2] for r in rows[:MANY_ROWS]], page_col=None)
